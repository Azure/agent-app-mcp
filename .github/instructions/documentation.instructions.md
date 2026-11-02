---
applyTo: "README.md,TROUBLESHOOTING.md,CONTRIBUTING.md,SECURITY.md,SUPPORT.md"
---

# Repository documentation

- Describe the current NL2SQL-only official Python MCP SDK service.
- Keep `README.md` short and link directly to the central MCP setup guide.
- Keep product setup, SQL onboarding, deployment and operational diagnosis in
  `Azure/AI-Landing-Zones`, published from `main`.
- Keep contribution, security, support, and conduct policy in their dedicated
  files rather than duplicating it.
- Verify commands, paths, endpoints, configuration keys, labels, and defaults
  against executable repository sources.
- Link to the published Agent Landing Zone documentation instead of copying broad product
  guidance into this component repository.
- Coordinate changes on `main` in `Azure/AI-Landing-Zones` when this
  component changes umbrella deployment, configuration, or user experience.
- Never put secrets, personal data, or private Azure validation environment
  and resource-group names in examples.
- Follow `SECURITY.md`; do not direct vulnerability reports to public issues.
