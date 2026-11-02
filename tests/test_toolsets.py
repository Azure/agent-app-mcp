"""Startup-scoped selection, real SDK protocol, isolation, and cleanup contracts."""

import json
import os
import subprocess
import sys
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import INTERNAL_ERROR
from pydantic import ValidationError
from starlette.testclient import TestClient

import server
import toolsets
from conftest import as_configuration
from shared.config import ConfigurationValue, load_settings
from tools.nl2sql import runtime
from tools.nl2sql.contracts import NL2SQLError, QueryResult, SourcesResult


@asynccontextmanager
async def sdk_session(app, token):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://localhost:8080",
        headers={"Authorization": f"Bearer {token}"},
    ) as http:
        async with streamable_http_client(
            "http://localhost:8080/mcp", http_client=http
        ) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                yield session


@pytest.fixture
def boundaries(configuration, signing, monkeypatch):
    """Only shared bootstrap is necessary for an empty server."""
    credential, cosmos, vault = AsyncMock(), AsyncMock(), AsyncMock()
    for client in (credential, cosmos, vault):
        client.__aenter__.return_value = client
    cosmos.get_database_client = Mock()
    models, sql, service = AsyncMock(), AsyncMock(), AsyncMock()
    service.list_sources.return_value = SourcesResult(sources=[])
    service.query.return_value = QueryResult(
        source_id="synthetic", query_id="test-id", metadata_version="v1",
        columns=[], rows=[], row_count=0,
    )
    sync_credential = Mock()
    factories = {}
    for name, value in (
        ("CosmosClient", cosmos),
        ("Models", models),
        ("SyncManagedIdentityCredential", sync_credential),
        ("SecretClient", vault),
        ("SQLExecutor", sql),
        ("Service", service),
    ):
        factories[name] = Mock(return_value=value)
        monkeypatch.setattr(runtime, name, factories[name])
    monkeypatch.setattr(server, "ManagedIdentityCredential", Mock(return_value=credential))
    monkeypatch.setattr(server, "EntraVerifier", Mock(return_value=signing.verifier))
    bootstrap = AsyncMock(return_value=configuration)
    monkeypatch.setattr(server, "load_configuration", bootstrap)
    return SimpleNamespace(
        credential=credential, cosmos=cosmos, vault=vault, models=models, sql=sql,
        sync_credential=sync_credential, service=service, factories=factories,
        bootstrap=bootstrap,
    )


@pytest.mark.parametrize("selection", [None, "[]"])
async def test_empty_runtime_real_sdk_and_no_sql_clients(
    selection, shared_settings, signing, boundaries
):
    configuration = as_configuration(shared_settings.model_dump(mode="json"))
    configuration.pop("MCP_TOOLSETS")
    if selection is not None:
        configuration["MCP_TOOLSETS"] = ConfigurationValue(selection)
    # Even malformed SQL values and forbidden references are irrelevant when disabled.
    configuration.update({
        "MCP_COSMOS_ENDPOINT": ConfigurationValue("not-a-url"),
        "AI_FOUNDRY_OPENAI_ENDPOINT": ConfigurationValue("http://invalid"),
        "MCP_SQL_SECRET_NAMES": ConfigurationValue("not-json"),
        "KEY_VAULT_ENDPOINT": ConfigurationValue(
            '{"uri":"https://example.vault.azure.net/secrets/no"}',
            "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8",
        ),
    })
    boundaries.bootstrap.return_value = configuration
    app = server.Runtime(lifespan=server.lifespan)
    async with app.router.lifespan_context(app):
        async with sdk_session(app, signing.token()) as session:
            assert (await session.list_tools()).tools == []
            absent = await session.call_tool(
                "nl2sql.query", {"source_id": "synthetic", "question": "count?"}
            )
            assert absent.is_error
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://localhost:8080"
        ) as http:
            assert (await http.get("/healthz")).json() == {"status": "ok"}
            for token in (None, signing.token(roles=[]), signing.token(aud="wrong")):
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                denial = await http.post("/mcp", headers=headers)
                assert denial.status_code == 401
                assert "resource_metadata=" in denial.headers["www-authenticate"]
            assert (await http.get("/.well-known/oauth-protected-resource/mcp")).status_code == 200
    for factory in boundaries.factories.values():
        factory.assert_not_called()
    boundaries.credential.__aexit__.assert_awaited_once()


async def test_selected_runtime_real_sdk_contract_and_shutdown(boundaries, signing):
    app = server.Runtime(lifespan=server.lifespan)
    async with app.router.lifespan_context(app):
        async with sdk_session(app, signing.token()) as session:
            tools = (await session.list_tools()).tools
            assert {tool.name for tool in tools} == {"nl2sql.list_sources", "nl2sql.query"}
            query = next(tool for tool in tools if tool.name == "nl2sql.query")
            assert query.input_schema["required"] == ["source_id", "question"]
            assert query.input_schema["properties"]["source_id"]["maxLength"] == 128
            assert query.input_schema["properties"]["question"]["maxLength"] == 4000
            assert query.output_schema == QueryResult.model_json_schema()
            assert query.annotations.read_only_hint is True
            assert query.annotations.destructive_hint is False
            assert query.annotations.open_world_hint is False
            sources = await session.call_tool("nl2sql.list_sources", {})
            assert sources.structured_content == {"schema_version": 1, "sources": []}
            result = await session.call_tool(
                "nl2sql.query", {"source_id": "synthetic", "question": "count?"}
            )
            assert result.structured_content == boundaries.service.query.return_value.model_dump()
            boundaries.service.query.assert_awaited_once_with("synthetic", "count?")
            boundaries.service.query.side_effect = NL2SQLError("SOURCE_CHANGED: disabled")
            assert (await session.call_tool(
                "nl2sql.query", {"source_id": "synthetic", "question": "count?"}
            )).is_error
    boundaries.factories["SecretClient"].assert_not_called()
    boundaries.models.close.assert_awaited_once()
    boundaries.sql.close.assert_awaited_once()
    boundaries.sync_credential.close.assert_called_once()
    boundaries.cosmos.__aexit__.assert_awaited_once()
    boundaries.credential.__aexit__.assert_awaited_once()


async def test_empty_server_official_sdk_denies_invalid_token(
    shared_settings, signing, boundaries
):
    boundaries.bootstrap.return_value = as_configuration(shared_settings.model_dump(mode="json"))
    app = server.Runtime(lifespan=server.lifespan)
    async with app.router.lifespan_context(app):
        with pytest.raises(ExceptionGroup) as denied:
            async with sdk_session(app, signing.token(roles=[])):
                pytest.fail("Unauthorized client must not initialize")
        # SDK 2.3.0 translates HTTP denial into a typed protocol error. The HTTP
        # status/challenge are checked separately above; do not accept unrelated errors.
        def assert_denied(error):
            if isinstance(error, ExceptionGroup):
                for child in error.exceptions:
                    assert_denied(child)
            else:
                assert isinstance(error, MCPError)
                assert error.code == INTERNAL_ERROR
                assert error.message == "Server returned an error response"

        assert_denied(denied.value)
    for factory in boundaries.factories.values():
        factory.assert_not_called()


@pytest.mark.parametrize(
    "raw",
    ["", "nl2sql", '"nl2sql"', "{}", "null", "true", "1",
     "[1]", "[null]", "[true]", "[{}]", '["nl2sql", 1]'],
)
def test_invalid_selection_shapes_fail_explicitly(raw, shared_settings):
    configuration = as_configuration(shared_settings.model_dump(mode="json"))
    configuration["MCP_TOOLSETS"] = ConfigurationValue(raw)
    with pytest.raises((json.JSONDecodeError, ValidationError)):
        load_settings(configuration)


@pytest.mark.parametrize(
    "names", [["unknown"], ["nl2sql", "unknown"], ["nl2sql", "nl2sql"], ["NL2SQL"], [""]]
)
def test_entire_selection_rejected_before_lazy_load(names, shared_settings):
    shared_settings.MCP_TOOLSETS = names
    loader = Mock()
    with pytest.raises(ValueError, match="MCP_TOOLSETS"):
        toolsets.prepare_toolsets(shared_settings, {}, registry={"nl2sql": loader})
    loader.assert_not_called()


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"MCP_COSMOS_DATABASE": None}, ValidationError),
        ({"MCP_COSMOS_ENDPOINT": ConfigurationValue("http://invalid")}, ValidationError),
        ({"AI_FOUNDRY_OPENAI_ENDPOINT": None}, ValidationError),
        ({"CHAT_DEPLOYMENT_NAME": ConfigurationValue("")}, ValidationError),
        ({"MCP_SQL_SECRET_NAMES": ConfigurationValue("bad-json")}, json.JSONDecodeError),
        ({"MCP_SQL_SECRET_NAMES": ConfigurationValue('["bad/name"]')}, ValidationError),
        ({"KEY_VAULT_ENDPOINT": ConfigurationValue("http://invalid")}, ValidationError),
        ({"MCP_COSMOS_ENDPOINT": ConfigurationValue(
            '{"uri":"https://example.vault.azure.net/secrets/no"}',
            "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8",
        )}, ValueError),
    ],
)
def test_selected_invalid_settings_fail_before_toolset_clients(
    changes, error, configuration, boundaries
):
    for key, value in changes.items():
        if value is None:
            configuration.pop(key)
        else:
            configuration[key] = value
    with pytest.raises(error):
        with TestClient(server.Runtime(lifespan=server.lifespan)):
            pytest.fail("Invalid configuration must not start")
    for factory in boundaries.factories.values():
        factory.assert_not_called()
    boundaries.credential.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("field", ["MCP_AUTH_TENANT_ID", "MCP_AUTH_AUDIENCE",
                                  "MCP_AUTH_RESOURCE_SCOPE", "MCP_ALLOWED_CLIENT_IDS"])
def test_empty_server_still_requires_shared_auth(field, shared_settings, boundaries):
    configuration = as_configuration(shared_settings.model_dump(mode="json"))
    configuration.pop(field)
    boundaries.bootstrap.return_value = configuration
    with pytest.raises(ValidationError):
        with TestClient(server.Runtime(lifespan=server.lifespan)):
            pytest.fail("Missing authentication must not start")
    for factory in boundaries.factories.values():
        factory.assert_not_called()
    boundaries.credential.__aexit__.assert_awaited_once()


@pytest.mark.parametrize(
    "field", ["MCP_AUTH_AUDIENCE", "MCP_ALLOWED_CLIENT_IDS", "MCP_TOOLSETS"]
)
def test_shared_fields_never_accept_key_vault_references(field, shared_settings):
    configuration = as_configuration(shared_settings.model_dump(mode="json"))
    configuration[field] = ConfigurationValue(
        "unused", "application/vnd.microsoft.appconfig.keyvaultref+json;charset=utf-8"
    )
    with pytest.raises(ValueError, match="must not contain secret"):
        load_settings(configuration)


@pytest.mark.parametrize("failure", [None, "Models", "SQLExecutor", "registration", "transport"])
def test_startup_failure_and_normal_shutdown_unwind_clients(
    failure, configuration, boundaries, monkeypatch
):
    configuration["KEY_VAULT_ENDPOINT"] = ConfigurationValue("https://example.vault.azure.net")
    if failure in boundaries.factories:
        boundaries.factories[failure].side_effect = RuntimeError("startup failure")
    elif failure == "registration":
        monkeypatch.setattr(runtime, "register_tools", Mock(side_effect=RuntimeError("startup failure")))
    elif failure == "transport":
        monkeypatch.setattr(server, "create_app", Mock(side_effect=RuntimeError("startup failure")))

    def start():
        with TestClient(server.Runtime(lifespan=server.lifespan)) as client:
            assert client.get("/healthz").json() == {"status": "ok"}
            assert client.post("/mcp").status_code == 401

    if failure:
        with pytest.raises(RuntimeError, match="startup failure"):
            start()
    else:
        start()
    boundaries.cosmos.__aexit__.assert_awaited_once()
    boundaries.credential.__aexit__.assert_awaited_once()
    if failure != "Models":
        boundaries.models.close.assert_awaited_once()
        boundaries.sync_credential.close.assert_called_once()
        boundaries.vault.__aexit__.assert_awaited_once()
    if failure not in ("Models", "SQLExecutor"):
        boundaries.sql.close.assert_awaited_once()


async def test_second_reviewed_toolset_needs_no_server_changes(
    configuration, boundaries, signing, monkeypatch
):
    events = []

    class FakeToolset:
        @asynccontextmanager
        async def lifespan(self, mcp, credential):
            events.append("start")

            @mcp.tool(name="fake.ping")
            async def ping() -> str:
                return "pong"

            try:
                yield
            finally:
                events.append("stop")

    factory = Mock(return_value=FakeToolset())
    loader = Mock(return_value=factory)
    monkeypatch.setattr(toolsets, "REGISTRY", toolsets.REGISTRY | {"fake": loader})
    configuration["MCP_TOOLSETS"] = ConfigurationValue('["nl2sql", "fake"]')
    app = server.Runtime(lifespan=server.lifespan)
    async with app.router.lifespan_context(app):
        async with sdk_session(app, signing.token()) as session:
            assert {tool.name for tool in (await session.list_tools()).tools} == {
                "nl2sql.list_sources", "nl2sql.query", "fake.ping"
            }
            assert not (await session.call_tool("fake.ping", {})).is_error
    assert events == ["start", "stop"]
    factory.assert_called_once_with(configuration)
    loader.assert_called_once_with()
    boundaries.sql.close.assert_awaited_once()


def test_later_toolset_validation_failure_constructs_no_earlier_clients(
    configuration, boundaries, monkeypatch
):
    factory = Mock(side_effect=ValueError("fake invalid configuration"))
    monkeypatch.setattr(
        toolsets, "REGISTRY", toolsets.REGISTRY | {"fake": Mock(return_value=factory)}
    )
    configuration["MCP_TOOLSETS"] = ConfigurationValue('["nl2sql", "fake"]')
    with pytest.raises(ValueError, match="fake invalid configuration"):
        with TestClient(server.Runtime(lifespan=server.lifespan)):
            pytest.fail("All settings must validate before toolset dependency construction")
    for provider in boundaries.factories.values():
        provider.assert_not_called()
    boundaries.credential.__aexit__.assert_awaited_once()


def test_later_toolset_startup_failure_unwinds_earlier_toolset(
    configuration, boundaries, monkeypatch
):
    class FailingToolset:
        @asynccontextmanager
        async def lifespan(self, mcp, credential):
            raise RuntimeError("later toolset startup failure")
            yield

    monkeypatch.setattr(
        toolsets, "REGISTRY",
        toolsets.REGISTRY | {"fake": lambda: lambda config: FailingToolset()},
    )
    configuration["MCP_TOOLSETS"] = ConfigurationValue('["nl2sql", "fake"]')
    with pytest.raises(RuntimeError, match="later toolset startup failure"):
        with TestClient(server.Runtime(lifespan=server.lifespan)):
            pytest.fail("Failed toolset must abort server startup")
    boundaries.sql.close.assert_awaited_once()
    boundaries.models.close.assert_awaited_once()
    boundaries.sync_credential.close.assert_called_once()
    boundaries.cosmos.__aexit__.assert_awaited_once()
    boundaries.credential.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("selection", ["missing", "empty"])
def test_fresh_process_empty_startup_never_imports_sql_runtime(shared_settings, selection):
    """A fresh interpreter prevents cached test imports from hiding eager imports."""
    code = textwrap.dedent("""
        import importlib.abc
        import sys
        from unittest.mock import AsyncMock, Mock
        class NoSQL(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith(("tools.nl2sql", "azure.cosmos", "azure.keyvault",
                                        "openai", "pyodbc")):
                    raise AssertionError("Disabled dependency imported: " + fullname)
        sys.meta_path.insert(0, NoSQL())
        from azure.identity.aio import ManagedIdentityCredential
        from azure.appconfiguration.aio import AzureAppConfigurationClient
        import azure.identity.aio
        import azure.appconfiguration.aio
        azure.identity.aio.ManagedIdentityCredential = Mock()
        azure.appconfiguration.aio.AzureAppConfigurationClient = Mock()
        import server
        azure.identity.aio.ManagedIdentityCredential.assert_not_called()
        azure.appconfiguration.aio.AzureAppConfigurationClient.assert_not_called()
        from shared.config import ConfigurationValue
        from starlette.testclient import TestClient
        import json
        values = json.loads(sys.argv[1])
        if sys.argv[2] == "missing":
            values.pop("MCP_TOOLSETS")
        values["MCP_SQL_SECRET_NAMES"] = "invalid-json"
        configuration = {
            k: ConfigurationValue(json.dumps(v) if isinstance(v, list) else str(v))
            for k, v in values.items() if v is not None
        }
        credential = AsyncMock()
        credential.__aenter__.return_value = credential
        server.ManagedIdentityCredential.return_value = credential
        server.load_configuration = AsyncMock(return_value=configuration)
        with TestClient(server.app) as client:
            assert client.get("/healthz").json() == {"status": "ok"}
            assert client.post("/mcp").status_code == 401
        assert not any(n.startswith("tools.nl2sql") for n in sys.modules)
        credential.__aexit__.assert_awaited_once()
    """)
    result = subprocess.run(
        [sys.executable, "-c", code, shared_settings.model_dump_json(), selection],
        env=os.environ | {"PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
