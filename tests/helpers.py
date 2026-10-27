"""Task-local disposable fixtures; no network or real model assets are required."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from evidencedesk.config import SETTINGS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_BASE = (PROJECT_ROOT / "tests" / "_temporary").resolve()
assert TEMP_BASE.is_relative_to(PROJECT_ROOT)


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        TEMP_BASE.mkdir(exist_ok=True)
        self.workspace = tempfile.TemporaryDirectory(prefix="case-", dir=TEMP_BASE)
        self.directory = Path(self.workspace.name).resolve()
        assert self.directory.is_relative_to(TEMP_BASE)
        self.addCleanup(self.workspace.cleanup)

    def settings(self, documents=None, **kwargs):
        path = self.directory / "corpus.json"
        path.write_text(json.dumps({"documents": documents or []}), encoding="utf-8")
        values = {"corpus_path": path, "state_dir": self.directory / "state",
                  "embedding_name": "deterministic-test-embeddings", "top_k": 3}
        values.update(kwargs)
        return replace(SETTINGS, **values)


def document(identifier, text, title=None):
    return {"id": identifier, "title": title or identifier, "text": text,
            "year": 2025, "authors": ["Test Author"], "url": "https://example.org/" + identifier,
            "doi": None, "license": "test fixture", "source_type": "curated_note"}
