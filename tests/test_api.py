import json

import pymupdf as fitz
from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.schemas import EXPECTED_FIELD_IDS
from app.services.analysis import AnalysisService
from app.services.ollama import OllamaGeneration


def _model_output() -> str:
    return json.dumps(
        {
            "document_title": "Fictional Technical Report",
            "document_revision": "C",
            "configuration_scope": "production release",
            "analysis": {
                "fields": [
                    {
                        "field_id": field_id,
                        "field_name": field_id,
                        "value": "example",
                        "source_section": {"section_id": "1.1", "section_title": "Overview"},
                    }
                    for field_id in EXPECTED_FIELD_IDS
                ],
                "summary": "A concise summary.",
            },
        }
    )


def test_health_endpoint():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_endpoint_accepts_pdf_and_returns_validated_result(tmp_path, monkeypatch):
    class FakeOllamaClient:
        async def generate(self, prompt: str, response_schema=None) -> OllamaGeneration:
            assert "[PAGE 1 | SECTION CONTEXT:" in prompt
            return OllamaGeneration(response=_model_output(), latency_seconds=0.01)

    service = AnalysisService(ollama_client=FakeOllamaClient(), results_dir=tmp_path)
    monkeypatch.setattr(routes, "analysis_service", service)

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "A small test PDF")
    pdf_bytes = document.tobytes()
    document.close()

    response = TestClient(app).post(
        "/analyze",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == "sample"
    assert len(payload["analysis"]["fields"]) == 15
    assert payload["raw_output_file"].endswith("_raw.txt")


def test_analyze_endpoint_rejects_non_pdf_filename():
    response = TestClient(app).post(
        "/analyze",
        files={"file": ("notes.txt", b"text", "text/plain")},
    )

    assert response.status_code == 415
