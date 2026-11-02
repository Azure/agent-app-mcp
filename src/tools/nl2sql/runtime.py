"""Reviewed NL2SQL registration and scoped dependencies, imported only when selected."""

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from azure.cosmos.aio import CosmosClient
from azure.identity import ManagedIdentityCredential as SyncManagedIdentityCredential
from azure.keyvault.secrets.aio import SecretClient
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from shared.config import Configuration

from .catalog import Catalog
from .config import Settings, load_settings
from .contracts import NL2SQLError, QueryResult, Question, SourceId, SourcesResult
from .models import Models
from .service import Service
from .sql import SQLExecutor


def register_tools(server: MCPServer, service: Service) -> None:
    """Preserve the public SQL schemas, annotations, errors and bounded service behavior."""
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(name="nl2sql.list_sources", structured_output=True, annotations=annotations)
    async def list_sources() -> SourcesResult:
        """List enabled, operator-approved SQL sources; never return connection or credential data."""
        try:
            return await service.list_sources()
        except NL2SQLError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(name="nl2sql.query", structured_output=True, annotations=annotations)
    async def query(source_id: SourceId, question: Question) -> QueryResult:
        """Query an approved Azure SQL/SQL Server source using bounded read-only NL2SQL."""
        if not question.strip():
            raise ToolError("INPUT_INVALID: question must not be blank")
        try:
            return await service.query(source_id, question)
        except NL2SQLError as exc:
            raise ToolError(str(exc)) from None


@dataclass(frozen=True)
class NL2SQLToolset:
    settings: Settings

    @asynccontextmanager
    async def lifespan(self, server: MCPServer, credential):
        """Unwind partially initialized clients as well as a normal shutdown."""
        settings = self.settings
        async with AsyncExitStack() as stack:
            cosmos = await stack.enter_async_context(
                CosmosClient(str(settings.MCP_COSMOS_ENDPOINT), credential=credential)
            )
            database = cosmos.get_database_client(settings.MCP_COSMOS_DATABASE)
            models = Models(settings, credential)
            stack.push_async_callback(models.close)
            sync_credential = SyncManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
            stack.push_async_callback(asyncio.to_thread, sync_credential.close)
            vault = None
            if settings.KEY_VAULT_ENDPOINT:
                vault = await stack.enter_async_context(
                    SecretClient(str(settings.KEY_VAULT_ENDPOINT), credential)
                )
            sql = SQLExecutor(sync_credential, vault, secret_names=settings.MCP_SQL_SECRET_NAMES)
            stack.push_async_callback(sql.close)
            service = Service(
                Catalog(
                    database.get_container_client(settings.MCP_SOURCES_CONTAINER),
                    database.get_container_client(settings.MCP_METADATA_CONTAINER),
                    settings,
                ),
                models,
                sql,
                settings,
            )
            register_tools(server, service)
            yield


def configure(configuration: Configuration) -> NL2SQLToolset:
    """Validate all SQL-specific configuration without constructing provider clients."""
    return NL2SQLToolset(load_settings(configuration))
