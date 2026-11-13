"""Prepare real PDF pages, manifest and chunk artifacts without Docker/models."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import statistics
import time

from .ingestion import load_pdf
from .chunking import fixed_size, by_paragraph

ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), encoding="utf-8")


def main() -> None:
    started = time.perf_counter()
    config = json.loads((ROOT / "data/corpus_config.json").read_text(encoding="utf-8"))
    pdf = ROOT / config["local_path"]
    all_pages = load_pdf(pdf, config["source_id"], config["source_path_or_url"])
    selected = {}
    for chapter in config["selection"]:
        for number in chapter["physical_pages"]:
            if number in selected:
                raise ValueError(f"Duplicate physical page: {number}")
            page = all_pages[number - 1]
            if not page.text or len(page.text) < 100:
                raise ValueError(f"Empty/nearly blank selected page: {number}")
            if page.metadata["replacement_characters"]:
                raise ValueError(f"Extraction has replacement characters on page {number}; inspect fonts")
            page.metadata.update(chapter=chapter["chapter"], chapter_number=chapter["chapter_number"],
                                 language=config["language"], version=config["version"],
                                 printed_page=number - 22)
            selected[number] = page
    pages = [selected[n] for n in sorted(selected)]
    if len(pages) < 30:
        raise ValueError("Corpus requires at least 30 distinct content pages")
    rows = [asdict(p) for p in pages]
    write_jsonl(ROOT / "data/processed/pages.jsonl", rows)
    page_manifest = [{"page": p.page, "printed_page": p.metadata["printed_page"],
                      "chapter": p.metadata["chapter"], "char_count": len(p.text),
                      "normalized_sha256": hashlib.sha256(p.text.encode()).hexdigest()}
                     for p in pages]
    manifest = {**config, "physical_page_count": len(all_pages), "counted_page_count": len(pages),
                "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": page_manifest,
                "total_normalized_characters": sum(len(p.text) for p in pages),
                "extraction_library": "pypdf", "extraction_version": importlib.metadata.version("pypdf")}
    write_json(ROOT / "data/manifest.json", manifest)
    errors = [{"page": p.page, **p.metadata} for p in all_pages
              if p.metadata["empty"] or p.metadata["replacement_characters"]]
    write_jsonl(ROOT / "results/preparation/extraction_issues.jsonl", errors)
    strategies = json.loads((ROOT / "configs/strategies.json").read_text(encoding="utf-8"))
    stats = {}
    for name, strategy in strategies.items():
        chunks = []
        for page in pages:
            if strategy["chunking"] == "fixed":
                chunks.extend(fixed_size(page, strategy["chunk_size"], strategy["overlap"]))
            else:
                chunks.extend(by_paragraph(page, strategy["chunk_size"]))
        # C changes query filtering only, so reuse B's chunks instead of duplicating them.
        chunk_file = f"results/preparation/chunks_{'B' if name == 'C' else name}.jsonl"
        if name != "C":
            write_jsonl(ROOT / chunk_file, [asdict(c) for c in chunks])
        sizes = [len(c.text) for c in chunks]
        stats[name] = {**strategy, "chunk_file": chunk_file, "chunk_count": len(chunks), "min_chars": min(sizes),
                       "max_chars": max(sizes), "mean_chars": statistics.mean(sizes),
                       "total_chars": sum(sizes)}
    # Freeze source positions before retrieval scores are available.
    write_json(ROOT / "artifacts/coherence_sample.json", [
        {"document_id": p.document_id, "page": p.page, "position": len(p.text) // 2,
         "rule": "midpoint of each of first 10 selected physical pages"} for p in pages[:10]])
    benchmark = ROOT / "benchmark/questions.jsonl"
    if benchmark.exists():
        from .validate_benchmark import validate
        validate(ROOT)
    summary = {"status": "prepared_without_embeddings_or_database", "counted_pages": len(pages),
               "physical_pdf_pages": len(all_pages), "strategies": stats,
               "preparation_seconds": time.perf_counter() - started,
               "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "paid_api_cost": 0, "retrieval_metrics": None}
    write_json(ROOT / "results/preparation/summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
