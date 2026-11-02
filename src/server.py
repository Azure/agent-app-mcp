"""Thin official MCPServer composition. No import-time Azure calls."""

import os
from contextlib import AsyncExitStack, asynccontextmanager

from azure.identity.aio import ManagedIdentityCredential
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from shared.auth import EntraVerifier
from shared.config import Settings, load_configuration, load_settings
from toolsets import prepare_toolsets


def create_server(settings: Settings, verifier=None) -> MCPServer:
    """Shared auth and health are mandatory regardless of selected toolsets."""
    server = MCPServer(
        "agent-app-mcp",
        version="1.0.0",
        token_verifier=verifier or EntraVerifier(settings),
        auth=AuthSettings(
            issuer_url=settings.issuer,
            resource_server_url=settings.resource_url,
            required_scopes=["MCP.Invoke"],
            validate_token_resource=False,
        ),
    )

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(_request):
        return JSONResponse({"status": "ok"})

    return server


def create_app(server: MCPServer) -> Starlette:
    """Use the same bounded stateless HTTP transport for every toolset selection."""
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=16384,
        host="0.0.0.0",
    )


@asynccontextmanager
async def lifespan(app):
    async with AsyncExitStack() as stack:
        credential = await stack.enter_async_context(
            ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID"))
        )
        configuration = await load_configuration(credential)
        settings = load_settings(configuration)
        toolsets = prepare_toolsets(settings, configuration)
        server = create_server(settings)
        for toolset in toolsets:
            await stack.enter_async_context(toolset.lifespan(server, credential))
        sdk_app = create_app(server)
        await stack.enter_async_context(sdk_app.router.lifespan_context(sdk_app))
        app.state.sdk_app = sdk_app
        yield


class Runtime(Starlette):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await super().__call__(scope, receive, send)
        else:
            await self.state.sdk_app(scope, receive, send)


app = Runtime(lifespan=lifespan)
