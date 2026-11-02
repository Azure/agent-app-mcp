import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server import create_app, create_server
from shared.auth import EntraVerifier
from shared.config import ConfigurationValue, Settings as SharedSettings
from tools.nl2sql.config import Settings
from tools.nl2sql.contracts import Source
from tools.nl2sql.runtime import register_tools

TENANT = "10000000-0000-0000-0000-000000000001"
AUDIENCE = "20000000-0000-0000-0000-000000000002"
CLIENT = "30000000-0000-0000-0000-000000000003"


@pytest.fixture
def shared_settings():
    return SharedSettings(
        MCP_AUTH_TENANT_ID=TENANT,
        MCP_AUTH_AUDIENCE=AUDIENCE,
        MCP_AUTH_RESOURCE_SCOPE=f"api://{AUDIENCE}/.default",
        MCP_ALLOWED_CLIENT_IDS=[CLIENT],
    )


@pytest.fixture
def settings():
    return Settings(
        MCP_COSMOS_ENDPOINT="https://example.documents.azure.com",
        MCP_COSMOS_DATABASE="application",
        MCP_EMBEDDING_DIMENSIONS=3,
        AI_FOUNDRY_OPENAI_ENDPOINT="https://example.openai.azure.com",
        CHAT_DEPLOYMENT_NAME="generation",
        EMBEDDING_DEPLOYMENT_NAME="embedding",
    )


def as_configuration(values):
    return {
        key: ConfigurationValue(json.dumps(value) if isinstance(value, list) else str(value))
        for key, value in values.items()
        if value is not None
    }


@pytest.fixture
def configuration(shared_settings, settings):
    return as_configuration(
        shared_settings.model_dump(mode="json")
        | settings.model_dump(mode="json")
        | {"MCP_TOOLSETS": ["nl2sql"]}
    )


def nl2sql_app(service, shared_settings, verifier):
    server = create_server(shared_settings, verifier)
    register_tools(server, service)
    return create_app(server)


@pytest.fixture
def import_json():
    return json.loads(
        (Path(__file__).parents[1] / "samples" / "approved-synthetic.json").read_text()
    )


@pytest.fixture
def source(import_json):
    return Source.model_validate(import_json["source"])


@pytest.fixture
def signing(shared_settings):
    import time

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = Mock()
    jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=key.public_key())
    verifier = EntraVerifier(shared_settings, jwks)
    claims = {
        "iss": shared_settings.issuer,
        "aud": AUDIENCE,
        "tid": TENANT,
        "ver": "2.0",
        "azp": CLIENT,
        "roles": ["MCP.Invoke"],
        "exp": int(time.time()) + 600,
    }

    def token(**updates):
        return jwt.encode(claims | updates, key, algorithm="RS256", headers={"kid": "test"})

    return SimpleNamespace(key=key, jwks=jwks, verifier=verifier, claims=claims, token=token)


class Container:
    def __init__(self, documents=()):
        self.documents = list(documents)
        self.calls = []
        self.create_item = AsyncMock()
        self.replace_item = AsyncMock()

    def query_items(self, **kwargs):
        self.calls.append(kwargs)

        async def iterator():
            params = {p["name"]: p["value"] for p in kwargs.get("parameters", [])}
            for doc in self.documents:
                if "@object" in params:
                    if doc.get("kind") != "schema":
                        continue
                    if (doc.get("object_name") or "") != params["@object"]:
                        continue
                yield doc

        return iterator()
