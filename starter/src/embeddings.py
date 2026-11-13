"""Real local multilingual embeddings; failures propagate, no fallback vectors."""
import hashlib
import re
from pathlib import Path

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class MyEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, revision: str | None = None) -> None:
        from huggingface_hub import HfApi, snapshot_download
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.revision = HfApi().model_info(model_name, revision=revision).sha
        folder = Path(__file__).resolve().parents[1] / ".cache" / "models"
        folder.mkdir(parents=True, exist_ok=True)
        available = HfApi().list_repo_files(model_name, revision=self.revision)
        weights = "model.safetensors" if "model.safetensors" in available else "pytorch_model.bin"
        # Download the PyTorch model only, not duplicate ONNX/OpenVINO/TF exports.
        snapshot = snapshot_download(model_name, revision=self.revision, cache_dir=folder,
                                     allow_patterns=["*.json", "*.txt", "*.model", weights])
        self.model = SentenceTransformer(snapshot, device="cpu", trust_remote_code=False)
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.max_seq_length = self.model.max_seq_length
        self.signature = hashlib.sha256(
            f"{model_name}:{self.revision}:{self.dimensions}:{self.max_seq_length}:normalized".encode()
        ).hexdigest()

    def token_counts(self, texts: list[str]) -> list[int]:
        texts = [re.sub(r"\s+", " ", t).strip() for t in texts]
        return [len(ids) for ids in self.model.tokenizer(texts, truncation=False)["input_ids"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        texts = [re.sub(r"\s+", " ", t).strip() for t in texts]
        return self.model.encode(texts, batch_size=16, normalize_embeddings=True,
                                 show_progress_bar=True, convert_to_numpy=True).tolist()

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]
