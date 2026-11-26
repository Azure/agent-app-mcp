from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tools.nl2sql import models as module


async def test_official_async_model_adapter_selected_deployments(settings, monkeypatch):
    client = AsyncMock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0, 0, 1])]
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1"))]
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr(module, "AsyncOpenAI", factory)
    monkeypatch.setattr(module, "get_bearer_token_provider", Mock(return_value="mock-provider"))
    models = module.Models(settings, object())
    assert factory.call_args.kwargs["base_url"] == "https://example.openai.azure.com/openai/v1/"
    assert factory.call_args.kwargs["api_key"] == "mock-provider"
    assert await models.embed("approved schema") == [0, 0, 1]
    assert client.embeddings.create.call_args.kwargs["model"] == "embedding"
    assert client.embeddings.create.call_args.kwargs["dimensions"] == 3
    assert await models.generate("question", None, [], {"dbo.Products"}) == "SELECT 1"
    assert client.chat.completions.create.call_args.kwargs["model"] == "generation"
    await models.close()
    client.close.assert_awaited_once()
