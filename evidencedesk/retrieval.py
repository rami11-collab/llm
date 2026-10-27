"""Dense 384-dimensional sentence embeddings and cosine similarity retrieval."""

import hashlib
import json
from pathlib import Path
from threading import Lock
import numpy as np

from .config import SETTINGS


class VectorLibrary:
    def __init__(self, models, settings=SETTINGS):
        self.models = models
        self.settings = settings
        raw = json.loads(settings.corpus_path.read_text(encoding="utf-8"))
        self.documents = raw["documents"]
        self.by_id = {document["id"]: document for document in self.documents}
        if len(self.by_id) != len(self.documents):
            raise ValueError("Corpus document IDs must be unique")
        self.vectors = None
        self.lock = Lock()

    def ensure_index(self):
        with self.lock:
            if self.vectors is not None:
                return
            self.settings.state_dir.mkdir(parents=True, exist_ok=True)
            fingerprint = hashlib.sha256(json.dumps({
                "model": self.settings.embedding_name,
                "documents": [(d["id"], d["title"], d["text"]) for d in self.documents],
            }, sort_keys=True).encode()).hexdigest()[:16]
            cache = self.settings.state_dir / f"vectors-{fingerprint}.npz"
            if cache.exists():
                with np.load(cache, allow_pickle=False) as saved:
                    vectors = saved["vectors"]
            else:
                texts = [d["title"] + ". " + d["text"] for d in self.documents]
                vectors = np.asarray(self.models.embed(texts), dtype=np.float32)
                np.savez_compressed(cache, vectors=vectors)
            if vectors.shape != (len(self.documents), 384) or not np.isfinite(vectors).all():
                raise ValueError("Unexpected or invalid embedding matrix")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if np.any(norms <= 1e-12):
                raise ValueError("Indexed embeddings must have nonzero norm")
            self.vectors = vectors / np.maximum(norms, 1e-12)

    def search(self, query, top_k=None):
        self.ensure_index()
        vector = np.asarray(self.models.embed([query])[0], dtype=np.float32)
        if vector.shape != (384,) or not np.isfinite(vector).all() or np.linalg.norm(vector) <= 1e-12:
            raise ValueError("Unexpected or invalid query embedding")
        vector /= max(float(np.linalg.norm(vector)), 1e-12)
        scores = self.vectors @ vector
        indices = np.argsort(-scores, kind="stable")[:top_k or self.settings.top_k]
        return [dict(self.documents[int(index)], score=float(scores[index])) for index in indices]

    def public_documents(self):
        return [{k: d.get(k) for k in ("id", "title", "year", "authors", "url", "doi", "license", "source_type")}
                for d in self.documents]
