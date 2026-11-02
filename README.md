# Agent application MCP

MCP component repository for [Agent Landing Zone](https://github.com/Azure/agent-landing-zone).
Product documentation lives in [Azure/AI-Landing-Zones](https://azure.github.io/AI-Landing-Zones/agent-landing-zone/).

The legacy GPT-RAG MCP implementation on `main` is retired. The repository is
being renewed with an independent, NL2SQL-only MCP server using the official
Python SDK, application-owned Cosmos DB metadata and Azure Container Apps.
The replacement has not been released and is available for review in
[the implementation pull request](https://github.com/Azure/agent-app-mcp/pull/64).

Do not combine the legacy deployment scripts with the replacement configuration.
Use the coordinated Agent Landing Zone release when it becomes available.
