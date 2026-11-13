"""PDF extraction; physical page numbers are one-based, never printed labels."""
from pathlib import Path
import re
import unicodedata
from .models import DocumentPage


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = normalize_text(page.extract_text(extraction_mode="layout") or "")
        pages.append(DocumentPage(document_id, source, number, text,
                                  {"empty": not bool(text),
                                   "replacement_characters": text.count("\ufffd")}))
    return pages


def normalize_text(text: str) -> str:
    """Keep paragraphs/code indentation; expand ligatures, remove soft hyphens."""
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()
