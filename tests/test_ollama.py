import asyncio
import json

import httpx
import pytest

from app.services.ollama import OllamaClient, OllamaClientError


def test_generate_sends_local_json_request_and_returns_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "{\"ok\": true}"})

    client = OllamaClient(transport=httpx.MockTransport(handler))
    result = asyncio.run(client.generate("extract fields"))

    assert result.response == '{"ok": true}'
    assert result.latency_seconds >= 0
    assert seen["url"] == "http://127.0.0.1:11434/api/generate"
    assert seen["payload"]["model"] == "llama3.2:3b"
    assert seen["payload"]["format"] == "json"
    assert seen["payload"]["stream"] is False


def test_generate_reports_http_errors_clearly():
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="model unavailable"))
    client = OllamaClient(transport=transport)

    with pytest.raises(OllamaClientError, match="HTTP 500: model unavailable"):
        asyncio.run(client.generate("prompt"))


def test_generate_reports_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OllamaClient(timeout_seconds=0.1, transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaClientError, match="timed out after 0.1 seconds"):
        asyncio.run(client.generate("prompt"))


def test_generate_rejects_missing_generated_text():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"done": True}))
    client = OllamaClient(transport=transport)

    with pytest.raises(OllamaClientError, match="did not contain generated text"):
        asyncio.run(client.generate("prompt"))
