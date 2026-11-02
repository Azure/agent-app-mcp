# Changelog

## [v1.0.0] - 2026-11-02

### Changed
- Replace the demonstration with an NL2SQL-only official Python MCP SDK 2.3.0
  server, stateless `/mcp`, Entra application authorization and typed,
  bounded read-only SQL results.
- Use `agent-lz` managed-identity App Configuration, application Cosmos vector
  metadata and existing generation/embedding models. No extra Azure AI Search
  or agent framework dependency.
- Deploy only to existing Container Apps using immutable image digests.
- Consolidate compatible Dependabot updates in the MCP 2.3.0 graph:
  `certifi` 2026.10.19, `PyJWT` 2.15.0, `urllib3` 2.8.0 and `anyio` 4.14.2.
  Preserve official PyPI artifacts and unrelated locked packages.

### Fixed
- Scope MCP deployment to `AZURE_APP_RESOURCE_GROUP` and bind ACR operations to
  `CONTAINER_REGISTRY_RESOURCE_ID`, independently of the Foundry resource group.
- Discover the deployed MCP app identity; set its UAI client ID or clear stale
  `AZURE_CLIENT_ID` for system-only apps. Set ingress target port to 8080.
- Validate parent-published HTTPS `MCP_SERVER_URL` for OAuth resource metadata.
- Replace private-mirror lock URLs with hash/size-verified official PyPI URLs,
  without changing locked versions or dependency edges.

### Added
- Administrative approved-schema/example importer with staged metadata versions
  and conditional activation.
- Focused protocol, authorization, SQL, metadata and deployment tests.
- **Reusable release skill:** Added repository-local release guidance for authoritative version discovery, SemVer preparation, validation, sanitized release notes, publication approval gates, and safe reconciliation.

## [v0.3.8] - 2026-05-27

### Changed
- **Dependency refresh:** Updated the MCP SDK requirement to 1.23.0 and refreshed `uv.lock` with `PyJWT` 2.12.0.

## [v0.3.7] - 2026-05-27

### Changed
- **Dependency refresh:** Updated transitive runtime dependencies in `uv.lock`, including `urllib3`, `pygments`, `cryptography`, `idna`, `python-dotenv`, `python-multipart`, and `requests`.

All notable changes to this project will be documented in this file.  
This format follows [Keep a Changelog](https://keepachangelog.com/) and adheres to [Semantic Versioning](https://semver.org/).

## [v0.3.6] - 2026-05-27
### Fixed
- **Bash deploy image platform:** Added `--platform linux/amd64` to `scripts/deploy.sh` Docker builds so Apple Silicon hosts produce Azure Container Apps-compatible images. Fixes [Azure/GPT-RAG#464](https://github.com/Azure/GPT-RAG/issues/464).

### Changed
- **MCP runtime wording:** Clarified the README that this service is a Python FastMCP/Starlette MCP server consumed through GPT-RAG's `mcp` strategy, avoiding legacy Semantic Kernel or AutoGen variant confusion. Closes [Azure/GPT-RAG#463](https://github.com/Azure/GPT-RAG/issues/463).

## [v0.3.5] - 2026-02-04
### Fixed
- Fixed Docker builds on ARM-based machines by explicitly setting the target platform to `linux/amd64`, preventing Azure Container Apps deployment failures.
### Changed
- Standardized on the container best practice of using a non-privileged port (`8080`) instead of a privileged port (`80`), reducing the risk of runtime/permission friction and improving stability of long-running ingestion workloads.

## [v0.3.4] - 2025-12-10
### Changed
- Major updated simplifying gpt-rag MCP

## [v0.2.3] - 2025-08-31
### Changed
- Removed certain default tool configurations that were resulting in excessively long docker builds
- Added .dockerignore

## [v0.2.2] - 2025-08-31
### Changed
- Standardized resource group variable as `AZURE_RESOURCE_GROUP`. [#365](https://github.com/Azure/GPT-RAG/issues/365)

## [v0.2.1] - 2025-08-08
### Changed
- Updated azure.yaml to support azd deploy targeting the container app.
- Added bash scripts execution mode.

## [v0.2.0] - 2025-07-15
### Changed
- Updated to align with GPT RAG infrastructure v2.0.0.

## [v0.1.0] - 2025-07-15
### Changed
- Fixed hardcoded variables in configuration.
- Updated README documentation.
- Added documentation for MCP usage.
- Updated tooling with latest changes.
- Fixed max token handling.
- Added new messaging tools.

## [0.0.1] - 2025-05-20
### Added
- The first version of the GPT RAG MCP was created.
- Added support for Stdio, FastAPI, and SSE.
- Included initial set of tools.
