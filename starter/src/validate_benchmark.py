"""Validate benchmark evidence against normalized physical PDF pages."""
from collections import Counter
import json
from pathlib import Path
import re


def canonical(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate(root: Path) -> list[dict]:
    pages = {(p["document_id"], p["page"]): p for p in read_jsonl(root / "data/processed/pages.jsonl")}
    questions = read_jsonl(root / "benchmark/questions.jsonl")
    counts = Counter(q["split"] for q in questions)
    if counts["dev"] < 15 or counts["test"] < 5 or set(counts) != {"dev", "test"}:
        raise ValueError("Need >=15 dev and >=5 test questions")
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Duplicate question IDs")
    filtered = [q for q in questions if q.get("filter")]
    if len(filtered) < 3 or not any(q["split"] == "test" for q in filtered):
        raise ValueError("Need >=3 filter questions, including >=1 test")
    for q in questions:
        for key in ("question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote"):
            if not q.get(key):
                raise ValueError(f"Missing {key}: {q['id']}")
        evidence = [{"source_id": q["gold_source_id"], "page": q["gold_page"],
                     "quote": q["evidence_quote"]}] + q.get("alternative_evidence", [])
        for item in evidence:
            page = pages[(item["source_id"], item["page"])]
            if canonical(item["quote"]) not in canonical(page["text"]):
                raise ValueError(f"Evidence not found: {q['id']}")
        for key, value in (q.get("filter") or {}).items():
            if key not in {"chapter", "chapter_number", "language", "version"}:
                raise ValueError(f"Invalid filter key: {key}")
            if str(value).casefold() not in q["question"].casefold():
                raise ValueError(f"Filter value must be explicit in question: {q['id']}")
            if pages[(q["gold_source_id"], q["gold_page"])]["metadata"].get(key) != value:
                raise ValueError(f"Filter contradicts source: {q['id']}")
    return questions


if __name__ == "__main__":
    print(f"Verified {len(validate(Path(__file__).resolve().parents[2]))} questions against PDF text.")
