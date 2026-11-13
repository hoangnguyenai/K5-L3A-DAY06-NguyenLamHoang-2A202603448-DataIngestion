"""CLI: prepare offline, evaluate dev, freeze selection, then evaluate holdout test."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

from .prepare import ROOT, write_json, write_jsonl
from .validate_benchmark import read_jsonl, validate
from .evaluation import evaluate_query, summarize
from .models import Chunk


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs() -> dict:
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    if digest(ROOT / manifest["local_path"]) != manifest["pdf_sha256"]:
        raise ValueError("PDF changed: rerun prepare and review benchmark")
    pages = read_jsonl(ROOT / "data/processed/pages.jsonl")
    expected = {p["page"]: p["normalized_sha256"] for p in manifest["pages"]}
    if len(pages) != len(expected) or any(
        hashlib.sha256(p["text"].encode()).hexdigest() != expected.get(p["page"]) for p in pages
    ):
        raise ValueError("Processed pages differ from manifest; rerun prepare")
    paths = ["data/manifest.json", "configs/strategies.json", "benchmark/questions.jsonl",
             "benchmark/protocol.md", "artifacts/coherence_sample.json",
             "results/preparation/chunks_A.jsonl", "results/preparation/chunks_B.jsonl"]
    paths.extend(str(p.relative_to(ROOT)).replace("\\", "/")
                 for p in sorted((ROOT / "starter/src").glob("*.py")))
    return {p: digest(ROOT / p) for p in paths}


def load_chunks(strategy: str, settings: dict) -> list[Chunk]:
    from .chunking import fixed_size, by_paragraph
    from .models import DocumentPage
    # Rebuild from source pages: stale edited chunk artifacts must never affect scoring.
    chunks = []
    for row in read_jsonl(ROOT / "data/processed/pages.jsonl"):
        page = DocumentPage(**row)
        if settings["chunking"] == "fixed":
            chunks.extend(fixed_size(page, settings["chunk_size"], settings["overlap"]))
        else:
            chunks.extend(by_paragraph(page, settings["chunk_size"]))
    path = ROOT / f"results/preparation/chunks_{'B' if strategy == 'C' else strategy}.jsonl"
    if read_jsonl(path) != [asdict(c) for c in chunks]:
        raise ValueError("Chunk artifact differs from current configuration; rerun prepare")
    return chunks


def cached_vectors(embedder, texts: list[str], namespace: str):
    key = hashlib.sha256(json.dumps([embedder.signature, texts], ensure_ascii=False).encode()).hexdigest()
    cache = ROOT / "starter/.cache/embeddings" / f"{namespace}-{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), True
    vectors = embedder.embed_documents(texts)
    write_json(cache, vectors)
    return vectors, False


def evaluate(split: str) -> None:
    from dotenv import load_dotenv
    from .embeddings import DEFAULT_MODEL, MyEmbedder
    from .store import PgVectorStore
    load_dotenv(ROOT / "starter/.env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("Copy starter/.env.example to starter/.env and configure DATABASE_URL")
    questions = validate(ROOT)
    hashes = inputs()
    revision = os.getenv("EMBEDDING_REVISION") or None
    model_name = os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL
    selection_path = ROOT / "artifacts/selection.json"
    if split == "test":
        if not selection_path.exists():
            raise ValueError("Run dev, then select before opening test results")
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection["input_hashes"] != hashes:
            raise ValueError("Inputs changed after selection; independent test would be invalid")
        model_name, revision = selection["model"], selection["model_revision"]
    started = time.perf_counter()
    # Fail early if database is unavailable; do not download the model first.
    import psycopg
    with psycopg.connect(url, connect_timeout=5) as conn:
        conn.execute("SELECT 1")
    embedder = MyEmbedder(model_name, revision)
    store = PgVectorStore(url, embedder.dimensions)
    store.create_schema()
    questions = [q for q in questions if q["split"] == split]
    query_vectors, query_cached = cached_vectors(embedder, [q["question"] for q in questions], split)
    strategies = json.loads((ROOT / "configs/strategies.json").read_text(encoding="utf-8"))
    traces, measurements = [], {}
    for name, settings in strategies.items():
        chunks = load_chunks(name, settings)
        texts = [c.text for c in chunks]
        token_counts = embedder.token_counts(texts)
        begin = time.perf_counter()
        vectors, reused = cached_vectors(embedder, texts, "documents")
        embedding_seconds = time.perf_counter() - begin
        begin = time.perf_counter()
        store.upsert(name, chunks, vectors)
        ingest_seconds = time.perf_counter() - begin
        first_count = store.count(name)
        store.upsert(name, chunks, vectors)
        second_count = store.count(name)
        if first_count != len(chunks) or second_count != first_count:
            raise ValueError(f"Re-ingestion count failed: {name}")
        for q, vector in zip(questions, query_vectors):
            filters = q.get("filter") if settings["use_filter"] else None
            begin = time.perf_counter()
            hits = store.search(name, vector, 3, filters)
            trace = evaluate_query(q, hits)
            trace.update(strategy=name, applied_filter=filters,
                         retrieval_seconds=time.perf_counter() - begin)
            traces.append(trace)
        measurements[name] = {"chunk_count": len(chunks), "embedding_seconds": embedding_seconds,
                              "embedding_cache_reused": reused, "ingest_seconds": ingest_seconds,
                              "count_before_reload": first_count, "count_after_reload": second_count,
                              "total_tokens_before_truncation": sum(token_counts),
                              "truncated_chunks": sum(n > embedder.max_seq_length for n in token_counts),
                              "max_input_tokens": max(token_counts)}
    output = ROOT / f"results/{split}"
    write_jsonl(output / "trace.jsonl", traces)
    metrics = summarize(traces)
    write_json(output / "metrics.json", metrics)
    versions = {}
    for package in ["pypdf", "fonttools", "psycopg", "sentence-transformers", "torch", "transformers"]:
        versions[package] = importlib.metadata.version(package)
    record = {"split": split, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
              "model": model_name, "model_revision": embedder.revision, "dimensions": embedder.dimensions,
              "max_seq_length": embedder.max_seq_length, "normalized_vectors": True,
              "query_document_preprocessing": "collapse whitespace; same model, no prompt",
              "python": sys.version, "libraries": versions, "database": store.versions(),
              "input_hashes": hashes, "measurements": measurements,
              "query_embedding_cache_reused": query_cached,
              "truncated_queries": sum(n > embedder.max_seq_length for n in embedder.token_counts(
                  [q["question"] for q in questions])),
              "elapsed_seconds": time.perf_counter() - started, "paid_api_cost": 0,
              "cost_note": "local CPU model; electricity/download cost not measured"}
    write_json(output / "run.json", record)
    update_experiment_log(split, metrics)
    if split == "test":
        from .audit import create_samples
        create_samples(ROOT, traces)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


def update_experiment_log(split: str, metrics: list[dict]) -> None:
    path = ROOT / "artifacts/experiment_log.csv"
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    by_strategy = {m["strategy"]: m for m in metrics}
    for row in rows:
        result = by_strategy[row["strategy"]]
        row[f"{split}_hit1"] = f"{result['hit1_n']}/{result['n']}"
        row[f"{split}_hit3"] = f"{result['hit3_n']}/{result['n']}"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def select() -> None:
    run = json.loads((ROOT / "results/dev/run.json").read_text(encoding="utf-8"))
    if run["input_hashes"] != inputs():
        raise ValueError("Dev results are stale")
    rows = json.loads((ROOT / "results/dev/metrics.json").read_text(encoding="utf-8"))
    selected = sorted(rows, key=lambda r: (-r["hit3"], -r["hit1"],
                     run["measurements"][r["strategy"]]["chunk_count"], r["strategy"]))[0]["strategy"]
    path = ROOT / "artifacts/selection.json"
    if path.exists():
        raise ValueError("Selection already frozen; do not overwrite after seeing test")
    write_json(path, {"selected_strategy": selected, "input_hashes": run["input_hashes"],
                     "model": run["model"], "model_revision": run["model_revision"],
                     "dev_run_sha256": digest(ROOT / "results/dev/run.json"),
                     "criterion": "dev Hit@3, then Hit@1, then fewer chunks, then A/B/C order",
                     "frozen_at_utc": datetime.now(timezone.utc).isoformat()})
    print(f"Frozen strategy {selected}. Test may now be run once.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "validate", "dev", "select", "test", "audit"])
    args = parser.parse_args()
    if args.stage == "prepare":
        from .prepare import main as prepare
        prepare()
    elif args.stage == "validate":
        validate(ROOT)
        inputs()
        settings = json.loads((ROOT / "configs/strategies.json").read_text(encoding="utf-8"))
        for name, config in settings.items():
            load_chunks(name, config)
        print("Corpus, benchmark and chunks verified.")
    elif args.stage == "select":
        select()
    elif args.stage == "audit":
        from .audit import summarize_audit
        summarize_audit(ROOT)
    else:
        if args.stage == "test" and (ROOT / "results/test/trace.jsonl").exists():
            raise ValueError("Test was already evaluated; preserve outputs and disclose any further tuning")
        evaluate(args.stage)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No connection URLs, API keys or provider response bodies in committed logs.
        error = {"stage": sys.argv[1] if len(sys.argv) > 1 else None,
                 "error_type": type(exc).__name__, "at_utc": datetime.now(timezone.utc).isoformat()}
        write_json(ROOT / "results/error.json", error)
        print(f"Pipeline failed ({type(exc).__name__}); check configuration and local services.", file=sys.stderr)
        if isinstance(exc, (ValueError, FileNotFoundError, ModuleNotFoundError)):
            print(str(exc), file=sys.stderr)
        raise SystemExit(1)
