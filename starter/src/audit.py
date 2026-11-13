"""Prepare review rows from actual retrieval; never invent human labels."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
from .prepare import write_json
from .validate_benchmark import read_jsonl

FIELDS = ["kind", "strategy", "question_id", "chunk_id", "page", "text", "metadata",
          "expected_answer", "evidence", "score", "reason"]


def create_samples(root: Path, traces: list[dict]) -> None:
    path = root / "results/audit.csv"
    if path.exists():
        raise ValueError("Audit already exists; preserve completed labels")
    rows = []
    samples = json.loads((root / "artifacts/coherence_sample.json").read_text(encoding="utf-8"))
    for strategy in "ABC":
        chunk_file = root / f"results/preparation/chunks_{'B' if strategy == 'C' else strategy}.jsonl"
        chunks = read_jsonl(chunk_file)
        for sample in samples:
            covering = [c for c in chunks if c["document_id"] == sample["document_id"]
                        and c["page"] == sample["page"]
                        and c["metadata"]["start_char"] <= sample["position"] < c["metadata"]["end_char"]]
            chunk = min(covering, key=lambda c: c["metadata"]["start_char"])
            rows.append(dict(kind="coherence", strategy=strategy, chunk_id=chunk["chunk_id"],
                             page=chunk["page"], text=chunk["text"],
                             metadata=json.dumps(chunk["metadata"], ensure_ascii=False)))
    for trace in traces:
        base = dict(strategy=trace["strategy"], question_id=trace["id"],
                    expected_answer=trace["expected_answer"], evidence=trace["evidence_quote"])
        rows.append(dict(base, kind="grounding",
                         text=json.dumps(trace["hits"], ensure_ascii=False)))
        for hit in trace["hits"]:
            rows.append(dict(base, kind="metadata", chunk_id=hit["chunk_id"], page=hit["page"],
                             text=hit["text"], metadata=json.dumps(
                                 {**hit["metadata"], "document_id": hit["document_id"],
                                  "source": hit["source"], "page": hit["page"]}, ensure_ascii=False)))
        if trace.get("filter"):
            rows.append(dict(base, kind="filter", evidence=json.dumps(trace["filter"], ensure_ascii=False),
                             text=json.dumps([h["metadata"] for h in trace["hits"]], ensure_ascii=False)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def summarize_audit(root: Path) -> None:
    with (root / "results/audit.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = Counter()
    traces = read_jsonl(root / "results/test/trace.jsonl")
    for strategy in "ABC":
        expected[(strategy, "coherence")] = 10
    for trace in traces:
        expected[(trace["strategy"], "grounding")] += 1
        expected[(trace["strategy"], "metadata")] += len(trace["hits"])
        if trace.get("filter"):
            expected[(trace["strategy"], "filter")] += 1
    actual = Counter((r["strategy"], r["kind"]) for r in rows)
    if actual != expected:
        raise ValueError("Audit row counts differ from actual test trace")
    groups = defaultdict(list)
    for row in rows:
        maximum = 1 if row["kind"] in {"metadata", "filter"} else 2
        if row["score"] not in {str(i) for i in range(maximum + 1)} or not row["reason"]:
            raise ValueError("Every audit row needs a valid score and reason")
        groups[(row["strategy"], row["kind"])].append(int(row["score"]))
    summary = [{"strategy": strategy, "kind": kind, "n": len(scores),
                "score_counts": dict(Counter(scores)), "mean": sum(scores) / len(scores)}
               for (strategy, kind), scores in sorted(groups.items())]
    write_json(root / "results/audit_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
