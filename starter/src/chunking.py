"""Chunks never cross physical PDF pages; offsets refer to normalized page text."""
import hashlib
import re
from .models import Chunk, DocumentPage


def make_chunk(page: DocumentPage, start: int, end: int, method: str) -> Chunk:
    text = page.text[start:end]
    identity = f"{page.document_id}:{page.page}:{method}:{start}:{end}:{text}"
    chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    metadata = {**page.metadata, "start_char": start, "end_char": end,
                "chunking": method}
    return Chunk(chunk_id, page.document_id, page.source, page.page, text, metadata)


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    chunks = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        chunks.append(make_chunk(page, start, end, "fixed"))
        if end == len(page.text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Prefer blank-line boundaries; split long blocks at line/word boundaries."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    chunks = []
    start = 0
    while start < len(page.text):
        end = min(start + max_size, len(page.text))
        if end < len(page.text):
            floor = start + max_size // 2
            boundaries = [m.end() for m in re.finditer(r"\n\s*\n", page.text[start:end])]
            preferred = [start + b for b in boundaries if start + b >= floor]
            if preferred:
                end = preferred[-1]
            else:
                cut = page.text.rfind("\n", floor, end)
                if cut < floor:
                    cut = page.text.rfind(" ", floor, end)
                if cut >= floor:
                    end = cut + 1
        chunks.append(make_chunk(page, start, end, "paragraph"))
        start = end
    return chunks
