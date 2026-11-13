"""Strict evidence retrieval metrics; human audit labels are separate."""
from collections import defaultdict
from typing import Any
from .validate_benchmark import canonical


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    gold = [{"source_id": question["gold_source_id"], "page": question["gold_page"],
             "quote": question["evidence_quote"]}] + question.get("alternative_evidence", [])
    evaluated = []
    for hit in hits[:3]:
        match = any(hit["document_id"] == e["source_id"] and hit["page"] == e["page"]
                    and canonical(e["quote"]) in canonical(hit["text"]) for e in gold)
        evaluated.append({**hit, "evidence_hit": match})
    return {**question, "hits": evaluated,
            "hit1": bool(evaluated and evaluated[0]["evidence_hit"]),
            "hit3": any(h["evidence_hit"] for h in evaluated),
            "metric": "same source + physical page + complete evidence; whitespace normalized"}


def summarize(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for trace in traces:
        grouped[(trace["strategy"], trace["split"])].append(trace)
    return [{"strategy": strategy, "split": split, "n": len(rows),
             "hit1_n": sum(t["hit1"] for t in rows), "hit3_n": sum(t["hit3"] for t in rows),
             "hit1": sum(t["hit1"] for t in rows) / len(rows),
             "hit3": sum(t["hit3"] for t in rows) / len(rows)}
            for (strategy, split), rows in sorted(grouped.items())]
