"""Shared typed settings and App Configuration snapshot bootstrap (agent-lz)."""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from azure.appconfiguration.aio import AzureAppConfigurationClient
from pydantic import BaseModel, Field, HttpUrl, StrictStr, model_validator


class Settings(BaseModel):
    """Authentication is required even when no business toolsets are selected."""

    MCP_AUTH_TENANT_ID: UUID
    MCP_AUTH_AUDIENCE: UUID
    MCP_AUTH_RESOURCE_SCOPE: str
    MCP_ALLOWED_CLIENT_IDS: list[UUID]
    MCP_SERVER_URL: HttpUrl | None = None
    MCP_TOOLSETS: list[StrictStr] = Field(default_factory=list, strict=True)

    @model_validator(mode="after")
    def secure_auth(self):
        if self.MCP_AUTH_RESOURCE_SCOPE != f"api://{self.MCP_AUTH_AUDIENCE}/.default":
            raise ValueError("Resource scope must target the dedicated MCP audience")
        url = self.MCP_SERVER_URL
        if url and (
            url.scheme != "https"
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path != "/mcp"
        ):
            raise ValueError("MCP_SERVER_URL must be the public HTTPS /mcp endpoint")
        return self

    @property
    def issuer(self):
        return f"https://login.microsoftonline.com/{self.MCP_AUTH_TENANT_ID}/v2.0"

    @property
    def resource_url(self):
        if self.MCP_SERVER_URL:
            return str(self.MCP_SERVER_URL)
        hostname = os.getenv("CONTAINER_APP_HOSTNAME")
        return f"https://{hostname}/mcp" if hostname else "http://localhost:8080/mcp"


@dataclass(frozen=True)
class ConfigurationValue:
    value: str | None
    content_type: str | None = None


Configuration = Mapping[str, ConfigurationValue]
SettingsT = TypeVar("SettingsT", bound=BaseModel)


def parse_settings(
    model: type[SettingsT], configuration: Configuration, *, json_fields: tuple[str, ...] = ()
) -> SettingsT:
    """Validate only the caller's fields; never accept Key Vault references as values."""
    values = {}
    for name in model.model_fields:
        if name not in configuration:
            continue
        item = configuration[name]
        if item.content_type and "keyvaultref" in item.content_type:
            raise ValueError("Runtime configuration fields must not contain secret values")
        values[name] = json.loads(item.value) if name in json_fields else item.value
    return model.model_validate(values)


def load_settings(configuration: Configuration) -> Settings:
    return parse_settings(
        Settings, configuration, json_fields=("MCP_ALLOWED_CLIENT_IDS", "MCP_TOOLSETS")
    )


async def load_configuration(credential) -> Configuration:
    """Read one startup-scoped snapshot; keep validation at each settings boundary."""
    endpoint = os.environ.get("APP_CONFIG_ENDPOINT", "")
    if not re.fullmatch(r"https://[A-Za-z0-9-]+\.azconfig\.io", endpoint):
        raise ValueError("APP_CONFIG_ENDPOINT must be an HTTPS App Configuration endpoint")
    async with AzureAppConfigurationClient(endpoint, credential) as client:
        values = {}
        async for item in client.list_configuration_settings(label_filter="agent-lz"):
            values[item.key] = ConfigurationValue(item.value, item.content_type)
        return values
