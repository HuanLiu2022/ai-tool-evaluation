"""Orchestrate section-aware PDF extraction and local model analysis."""

import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import BinaryIO
from uuid import uuid4

from pydantic import ValidationError

from app.schemas import AnalysisResponse, ExtractedPage, ModelAnalysis, model_output_json_schema
from app.services.document import extract_pdf
from app.services.ollama import OllamaClient, OllamaClientError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = PROJECT_ROOT / "app" / "prompts" / "analysis.txt"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"


class AnalysisError(RuntimeError):
    """Base error for PDF analysis failures."""


class InvalidModelOutputError(AnalysisError):
    """Raised when model text is not valid for the analysis response schema."""


def parse_model_output(raw_output: str) -> ModelAnalysis:
    """Parse a model JSON object and validate its metadata and 15 field results.

    A surrounding Markdown JSON fence is tolerated, but partial or malformed
    JSON is rejected rather than repaired into potentially misleading data.
    """
    candidate = raw_output.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    try:
        parsed = json.loads(candidate)
        return ModelAnalysis.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise InvalidModelOutputError(f"Ollama output did not match the required JSON schema: {exc}") from exc


def _document_context(pages: list[ExtractedPage]) -> str:
    """Format extracted pages with traceable page and heading markers."""
    parts = []
    for page in pages:
        heading = page.section_heading or "Section heading not detected"
        parts.append(f"[PAGE {page.page_number} | SECTION CONTEXT: {heading}]\n{page.text}")
    return "\n\n".join(parts)


def _safe_stem(filename: str) -> str:
    """Return a compact filename stem safe for local result artifact names."""
    stem = Path(filename).name.rsplit(".", 1)[0]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return (safe or "document")[:80]


class AnalysisService:
    """Analyze one PDF using extracted text and the configured local Ollama model."""

    def __init__(self, ollama_client: OllamaClient | None = None, results_dir: Path = RESULTS_DIR) -> None:
        self.ollama_client = ollama_client or OllamaClient()
        self.results_dir = Path(results_dir)

    async def analyze(self, source: str | Path | BinaryIO, filename: str | None = None) -> AnalysisResponse:
        """Extract and analyze a PDF, saving raw and validated outputs separately.

        ``source`` may be a filesystem path or a binary file object. Ground
        truth is not loaded or passed into any inference operation.
        """
        started = perf_counter()
        display_name = filename or (Path(source).name if isinstance(source, (str, Path)) else "uploaded-document.pdf")
        try:
            if isinstance(source, (str, Path)):
                pages = extract_pdf(source)
            else:
                source.seek(0)
                pages = extract_pdf(source)
        except Exception as exc:
            raise AnalysisError(f"Could not extract PDF text: {exc}") from exc
        if not pages or not any(page.text.strip() for page in pages):
            raise AnalysisError("The PDF contains no extractable text.")

        try:
            prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise AnalysisError(f"Could not read analysis prompt at {PROMPT_PATH}: {exc}") from exc
        prompt = prompt_template.replace("{{DOCUMENT_CONTEXT}}", _document_context(pages))

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
        stem = _safe_stem(display_name)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        raw_filename = f"{stem}_{run_id}_raw.txt"
        raw_path = self.results_dir / raw_filename
        try:
            generation = await self.ollama_client.generate(
                prompt,
                response_schema=model_output_json_schema(),
            )
        except OllamaClientError:
            raise
        raw_path.write_text(generation.response, encoding="utf-8", newline="\n")

        try:
            model_analysis = parse_model_output(generation.response)
        except InvalidModelOutputError as exc:
            raise InvalidModelOutputError(f"{exc} Raw output saved to data/results/{raw_filename}.") from exc

        response = AnalysisResponse(
            document_id=Path(display_name).stem,
            document_title=model_analysis.document_title,
            document_revision=model_analysis.document_revision,
            configuration_scope=model_analysis.configuration_scope,
            analysis=model_analysis.analysis,
            latency_seconds=perf_counter() - started,
            model_latency_seconds=generation.latency_seconds,
            run_id=run_id,
            raw_output_file=raw_filename,
            validated_output_file=f"{stem}_{run_id}_validated.json",
        )
        validated_path = self.results_dir / response.validated_output_file
        validated_path.write_text(
            response.model_dump_json(indent=2),
            encoding="utf-8",
            newline="\n",
        )
        return response
