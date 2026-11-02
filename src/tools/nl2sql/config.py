"""NL2SQL-only settings. Validated only for selected SQL tools or the admin importer."""

import re

from pydantic import BaseModel, Field, HttpUrl, model_validator

from shared.config import Configuration, parse_settings


class Settings(BaseModel):
    MCP_SQL_SECRET_NAMES: list[str] = Field(default_factory=list)
    MCP_COSMOS_ENDPOINT: HttpUrl
    MCP_COSMOS_DATABASE: str = Field(min_length=1)
    MCP_SOURCES_CONTAINER: str = "mcp-sources"
    MCP_METADATA_CONTAINER: str = "mcp-nl2sql-metadata"
    MCP_EMBEDDING_DIMENSIONS: int = Field(default=3072, ge=1, le=65536)
    MCP_QUERY_TIMEOUT_SECONDS: int = Field(default=75, ge=1, le=75)
    MCP_METADATA_TOP_K: int = Field(default=8, ge=1, le=32)
    AI_FOUNDRY_OPENAI_ENDPOINT: HttpUrl
    CHAT_DEPLOYMENT_NAME: str = Field(min_length=1)
    EMBEDDING_DEPLOYMENT_NAME: str = Field(min_length=1)
    KEY_VAULT_ENDPOINT: HttpUrl | None = None

    @model_validator(mode="after")
    def secure_urls(self):
        for name in ("MCP_COSMOS_ENDPOINT", "AI_FOUNDRY_OPENAI_ENDPOINT", "KEY_VAULT_ENDPOINT"):
            url = getattr(self, name)
            if url and (url.scheme != "https" or url.username or url.password):
                raise ValueError("Provider endpoints require HTTPS without credentials")
        if any(not re.fullmatch(r"[A-Za-z0-9-]{1,127}", n) for n in self.MCP_SQL_SECRET_NAMES):
            raise ValueError("SQL secret names must be Key Vault reference names")
        endpoint_path = self.AI_FOUNDRY_OPENAI_ENDPOINT.path
        if endpoint_path not in (None, "/"):
            raise ValueError("AI_FOUNDRY_OPENAI_ENDPOINT must be the platform endpoint root")
        return self


def load_settings(configuration: Configuration) -> Settings:
    return parse_settings(Settings, configuration, json_fields=("MCP_SQL_SECRET_NAMES",))
