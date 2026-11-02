import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from conftest import as_configuration
from shared.config import Settings as SharedSettings
from shared.config import load_configuration, load_settings
from tools.nl2sql.config import Settings, load_settings as load_sql_settings
from tools.nl2sql.contracts import NL2SQLError
from tools.nl2sql.service import Service


def service(settings, source):
    catalog, models, sql = AsyncMock(), AsyncMock(), AsyncMock()
    catalog.source.return_value = source
    catalog.retrieve.return_value = ([], {"dbo.Products"})
    models.embed.return_value = [0, 0, 1]
    models.generate.return_value = "SELECT TOP (1) Name FROM dbo.Products"
    return Service(catalog, models, sql, settings)


async def test_service_uses_guard_and_returns_no_sql(settings, source):
    instance = service(settings, source)
    await instance.query("synthetic", "question")
    instance.sql.execute.assert_awaited_once()
    instance.models.generate.return_value = "DELETE FROM dbo.Products"
    with pytest.raises(NL2SQLError, match="SQL_REJECTED"):
        await instance.query("synthetic", "question")
    assert instance.sql.execute.await_count == 1


async def test_source_revocation_and_errors(settings, source):
    instance = service(settings, source)
    instance.catalog.source.side_effect = [source, source.model_copy(update={"enabled": False})]
    with pytest.raises(NL2SQLError, match="SOURCE_CHANGED"):
        await instance.query("synthetic", "question")
    instance.sql.execute.assert_not_awaited()
    instance = service(settings, source)
    instance.models.embed.side_effect = RuntimeError("credentials/raw SQL")
    with pytest.raises(NL2SQLError) as error:
        await instance.query("synthetic", "question")
    assert "credentials" not in str(error.value)
    assert error.value.__suppress_context__


async def test_overall_timeout(settings, source):
    instance = service(settings, source)
    settings.MCP_QUERY_TIMEOUT_SECONDS = 0.02

    async def slow(*args):
        await asyncio.sleep(1)

    instance.models.embed.side_effect = slow
    with pytest.raises(NL2SQLError, match="QUERY_TIMEOUT"):
        await instance.query("synthetic", "question")
    instance.sql.execute.assert_not_awaited()


def test_sql_limits_fail_closed(settings):
    for field, value in (
        ("MCP_QUERY_TIMEOUT_SECONDS", 76),
        ("MCP_METADATA_TOP_K", 1000),
        ("MCP_COSMOS_ENDPOINT", "http://example.com"),
        ("MCP_SQL_SECRET_NAMES", ["secret/invalid"]),
    ):
        with pytest.raises(ValidationError):
            Settings.model_validate(settings.model_dump() | {field: value})


def test_shared_auth_limits_fail_closed(shared_settings):
    assert SharedSettings.model_validate(
        shared_settings.model_dump() | {"MCP_ALLOWED_CLIENT_IDS": []}
    )
    for field, value in (
        ("MCP_AUTH_RESOURCE_SCOPE", "api://other/.default"),
        ("MCP_SERVER_URL", "http://example.com/mcp"),
        ("MCP_SERVER_URL", "https://example.com/other"),
        ("MCP_SERVER_URL", "https://example.com/mcp?access=unexpected"),
    ):
        with pytest.raises(ValidationError):
            SharedSettings.model_validate(shared_settings.model_dump() | {field: value})


def test_parent_published_mcp_endpoint(shared_settings):
    configured = SharedSettings.model_validate(
        shared_settings.model_dump() | {"MCP_SERVER_URL": "https://synthetic-mcp.example.com/mcp"}
    )
    assert configured.resource_url == "https://synthetic-mcp.example.com/mcp"


async def test_app_configuration_label_and_json_arrays(
    settings, shared_settings, configuration, monkeypatch
):
    from types import SimpleNamespace
    import shared.config as module

    class Client:
        def __init__(self, endpoint, credential):
            assert endpoint == "https://example.azconfig.io"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def list_configuration_settings(self, **kwargs):
            assert kwargs == {"label_filter": "agent-lz"}

            async def items():
                for key, item in configuration.items():
                    yield SimpleNamespace(key=key, value=item.value, content_type=item.content_type)

            return items()

    monkeypatch.setattr(module, "AzureAppConfigurationClient", Client)
    monkeypatch.setenv("APP_CONFIG_ENDPOINT", "https://example.azconfig.io")
    loaded = await load_configuration(object())
    assert load_settings(loaded) == shared_settings.model_copy(update={"MCP_TOOLSETS": ["nl2sql"]})
    assert load_sql_settings(loaded) == settings


def test_importer_settings_do_not_require_server_auth_or_selection(settings):
    configuration = as_configuration(settings.model_dump(mode="json"))
    assert load_sql_settings(configuration) == settings
