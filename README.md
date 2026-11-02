# Agent App MCP Server

MCP tool server for [Agent Landing Zone](https://github.com/Azure/agent-landing-zone),
using the official Python MCP SDK and Azure Container Apps.
`MCP_TOOLSETS` is a startup-scoped JSON array in App Configuration (`agent-lz`).
Missing or `[]` starts an authenticated, healthy server with no business tools.
Select `["nl2sql"]` explicitly for the supplied SQL tools and their
application-owned Cosmos DB metadata/model/SQL dependencies. Invalid or
unsupported selections fail startup. New reviewed toolsets use an explicit
lazy factory in `src/toolsets.py`; no plugins are discovered automatically.

For setup, SQL onboarding and operations, see the
[Agent App MCP setup guide](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/agent-app-mcp/).
