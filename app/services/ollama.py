"""HTTP client for a locally running Ollama generation endpoint."""

from dataclasses import dataclass
from time import perf_counter

import httpx


class OllamaClientError(RuntimeError):
    """Raised when Ollama cannot return a usable generation response."""


@dataclass(frozen=True)
class OllamaGeneration:
    """Model text and wall-clock duration for one generation request."""

    response: str
    latency_seconds: float


class OllamaClient:
    """Small async client for Ollama's local ``/api/generate`` endpoint."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2:3b",
        timeout_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate(
        self,
        prompt: str,
        response_schema: dict[str, object] | None = None,
    ) -> OllamaGeneration:
        """Request a JSON-formatted completion and measure request latency.

        Raises ``OllamaClientError`` for connection, timeout, HTTP, or response
        format failures so callers can present a useful local-service error.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": response_schema or "json",
            "options": {"temperature": 0, "num_ctx": 24576, "num_predict": 4096},
        }
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise OllamaClientError(
                f"Ollama request timed out after {self.timeout_seconds:g} seconds."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise OllamaClientError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaClientError(
                f"Could not connect to Ollama at {self.base_url}: {exc}"
            ) from exc
        except ValueError as exc:
            raise OllamaClientError("Ollama returned an invalid JSON response envelope.") from exc

        model_text = body.get("response") if isinstance(body, dict) else None
        if not isinstance(model_text, str) or not model_text.strip():
            raise OllamaClientError("Ollama response did not contain generated text.")

        return OllamaGeneration(response=model_text, latency_seconds=perf_counter() - started)
