import json
from pathlib import Path
import unittest

from src.chunking import by_paragraph, fixed_size
from src.evaluation import evaluate_query, summarize
from src.models import DocumentPage
from src.store import PgVectorStore
from src.validate_benchmark import validate

ROOT = Path(__file__).resolve().parents[2]


class PipelineTests(unittest.TestCase):
    def test_evidence_requires_source_page_and_complete_quote(self):
        q = {"gold_source_id": "doc", "gold_page": 2, "evidence_quote": "only if approved"}
        wrong_page = {"document_id": "doc", "page": 1, "text": "only if approved"}
        partial = {"document_id": "doc", "page": 2, "text": "if approved"}
        correct = {"document_id": "doc", "page": 2, "text": "Allowed only\nif approved."}
        result = evaluate_query(q, [wrong_page, partial, correct])
        self.assertFalse(result["hit1"])
        self.assertTrue(result["hit3"])
        self.assertFalse(evaluate_query(q, [partial])["hit3"])

    def test_alternative_evidence_and_separate_splits(self):
        q = {"gold_source_id": "doc", "gold_page": 1, "evidence_quote": "main",
             "alternative_evidence": [{"source_id": "other", "page": 5, "quote": "equivalent"}]}
        hit = {"document_id": "other", "page": 5, "text": "equivalent"}
        result = evaluate_query(q, [hit])
        self.assertTrue(result["hit1"])
        rows = summarize([{**result, "strategy": "A", "split": "dev"},
                          {**evaluate_query(q, []), "strategy": "A", "split": "test"}])
        self.assertEqual([(r["split"], r["hit3_n"], r["n"]) for r in rows],
                         [("dev", 1, 1), ("test", 0, 1)])

    def test_chunking_preserves_unicode_offsets_and_all_content(self):
        page = DocumentPage("doc", "source", 3, "Điều kiện.\n\n" + "Nội dung dài. " * 100,
                            {"chapter": "A"})
        for chunks in (fixed_size(page, 100, 10), by_paragraph(page, 100)):
            covered = set()
            for c in chunks:
                start, end = c.metadata["start_char"], c.metadata["end_char"]
                self.assertEqual(c.text, page.text[start:end])
                self.assertEqual(c.metadata["chapter"], "A")
                self.assertEqual(c.page, 3)
                self.assertLessEqual(len(c.text), 100)
                covered.update(range(start, end))
            self.assertEqual(len(covered), len(page.text))

    def test_rejects_invalid_cosine_vectors_before_database_write(self):
        store = PgVectorStore("unused", 2)
        for vector in ([0, 0], [1], [float("nan"), 1], [float("inf"), 1]):
            with self.assertRaises(ValueError):
                store.vector_literal(vector)

    def test_real_corpus_benchmark_and_controlled_comparison(self):
        questions = validate(ROOT)
        self.assertEqual(len(questions), 20)
        manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["counted_page_count"], 35)
        self.assertEqual(len({p["page"] for p in manifest["pages"]}), 35)
        settings = json.loads((ROOT / "configs/strategies.json").read_text(encoding="utf-8"))
        self.assertEqual({k for k in settings["B"] if settings["B"][k] != settings["C"][k]},
                         {"use_filter"})


if __name__ == "__main__":
    unittest.main()
