import pymupdf as fitz

from app.services.document import extract_pdf


def test_extract_pdf_preserves_page_numbers_text_and_heading(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    page1 = document.new_page()
    page1.insert_text((72, 72), "Section 1: Overview", fontsize=18)
    page1.insert_text((72, 110), "Operating pressure is 10 bar.", fontsize=11)
    page2 = document.new_page()
    page2.insert_text((72, 72), "Additional operating notes.", fontsize=11)
    document.save(pdf_path)
    document.close()

    pages = extract_pdf(pdf_path)

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].section_heading == "Section 1: Overview"
    assert "Operating pressure is 10 bar." in pages[0].text
    assert pages[1].page_number == 2
    assert pages[1].section_heading == "Section 1: Overview"
    assert "Additional operating notes." in pages[1].text
