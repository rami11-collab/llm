"""Small, explicit configuration; no hosted-model credentials are required."""

from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    llm_url: str = os.environ.get("EVIDENCEDESK_LLM_URL", "http://127.0.0.1:8091")
    embedding_url: str = os.environ.get("EVIDENCEDESK_EMBEDDING_URL", "http://127.0.0.1:8092")
    model_name: str = "Qwen3-0.6B-Q4_K_M"
    embedding_name: str = "all-MiniLM-L6-v2-Q8_0"
    top_k: int = 3
    retrieval_threshold: float = 0.30
    llm_timeout: float = 90.0
    tool_timeout: float = 12.0
    seed: int = 42
    corpus_path: Path = ROOT / "data" / "corpus.json"
    state_dir: Path = ROOT / "state"


SETTINGS = Settings()
