"""PDF text extraction with page and section-heading context."""

from pathlib import Path
from statistics import median
from typing import BinaryIO

import pymupdf as fitz

from app.schemas import ExtractedPage


def extract_pdf(source: str | Path | BinaryIO) -> list[ExtractedPage]:
    """Extract page text and carry forward the latest detected heading.

    A heading is provisionally detected from PDF text spans that are larger
    than the page's typical text size. This lightweight heuristic is a baseline;
    engineering PDF layouts may need tuning once representative documents exist.
    Page numbers in the result are one-based.
    """
    document = (
        fitz.open(stream=source.read(), filetype="pdf")
        if hasattr(source, "read")
        else fitz.open(source)
    )
    pages: list[ExtractedPage] = []
    current_heading: str | None = None

    try:
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text("text").strip()
            page_sizes = [
                span["size"]
                for block in page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
                if span["text"].strip()
            ]
            # The median avoids treating the larger of two common font sizes as typical.
            typical_size = median(page_sizes) if page_sizes else 0
            headings = [
                span["text"].strip()
                for block in page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
                for span in line["spans"]
                if span["text"].strip() and span["size"] > typical_size * 1.15
            ]
            if headings:
                current_heading = headings[0]
            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    section_heading=current_heading,
                    text=page_text,
                )
            )
    finally:
        document.close()

    return pages
