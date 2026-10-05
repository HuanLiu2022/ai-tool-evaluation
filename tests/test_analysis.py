import asyncio
import json

import pymupdf as fitz
import pytest

from app.schemas import EXPECTED_FIELD_IDS
from app.services.analysis import (
    AnalysisService,
    InvalidModelOutputError,
    parse_model_output,
)
from app.services.ollama import OllamaGeneration


def valid_model_payload() -> dict:
    return {
        "document_title": "Fictional Technical Report",
        "document_revision": "C",
        "configuration_scope": "production release",
        "analysis": {
            "fields": [
                {
                    "field_id": field_id,
                    "field_name": field_id,
                    "value": "example",
                    "unit": None,
                    "qualifier": None,
                    "conditions": [],
                    "source_section": {"section_id": "1.1", "section_title": "Overview"},
                    "confidence": 0.9,
                    "uncertainty": None,
                }
                for field_id in EXPECTED_FIELD_IDS
            ],
            "summary": "A concise report summary.",
        },
    }


def test_parse_model_output_accepts_json_and_markdown_fence():
    raw = json.dumps(valid_model_payload())

    parsed = parse_model_output(raw)
    fenced = parse_model_output(f"```json\n{raw}\n```")

    assert len(parsed.analysis.fields) == 15
    assert fenced.analysis.summary == "A concise report summary."


@pytest.mark.parametrize("raw", ["not json", "{}"])
def test_parse_model_output_rejects_invalid_or_incomplete_output(raw):
    with pytest.raises(InvalidModelOutputError):
        parse_model_output(raw)


def test_analysis_service_saves_raw_and_validated_outputs(tmp_path):
    raw = json.dumps(valid_model_payload())

    class FakeOllamaClient:
        async def generate(self, prompt: str, response_schema: dict | None = None) -> OllamaGeneration:
            assert "[PAGE 1 | SECTION CONTEXT:" in prompt
            assert "Ground Truth" not in prompt
            assert response_schema is not None
            return OllamaGeneration(response=raw, latency_seconds=0.25)

    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Sample engineering content")
    document.save(pdf_path)
    document.close()

    service = AnalysisService(ollama_client=FakeOllamaClient(), results_dir=tmp_path / "results")
    response = asyncio.run(service.analyze(pdf_path))

    raw_path = tmp_path / "results" / response.raw_output_file
    validated_path = tmp_path / "results" / response.validated_output_file
    assert raw_path.read_text() == raw
    assert json.loads(validated_path.read_text())["analysis"]["summary"] == "A concise report summary."
    assert len(response.analysis.fields) == 15
    assert response.model_latency_seconds == 0.25
    assert response.latency_seconds > 0
