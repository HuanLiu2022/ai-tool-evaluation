import pytest
from pydantic import ValidationError

from app.schemas import EXPECTED_FIELD_IDS, AnalysisContent, ExtractedPage


def test_extracted_page_accepts_page_context():
    page = ExtractedPage(page_number=1, section_heading="1 Overview", text="Example")

    assert page.page_number == 1
    assert page.section_heading == "1 Overview"
    assert page.text == "Example"


def test_extracted_page_rejects_zero_page_number():
    with pytest.raises(ValidationError):
        ExtractedPage(page_number=0, text="Example")


def test_analysis_content_requires_each_requested_field_once():
    fields = [
        {"field_id": field_id, "field_name": field_id, "value": None}
        for field_id in EXPECTED_FIELD_IDS
    ]

    result = AnalysisContent(fields=fields, summary="Summary")

    assert len(result.fields) == 15


def test_analysis_content_rejects_missing_fields():
    with pytest.raises(ValidationError):
        AnalysisContent(fields=[], summary="Summary")
