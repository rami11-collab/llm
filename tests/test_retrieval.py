"""Cosine ranking, cache identity, and invalid-vector handling with stub embeddings."""

import json
import numpy as np

from evidencedesk.retrieval import VectorLibrary
from tests.helpers import WorkspaceTestCase, document


def vector(first, second=0):
    value = np.zeros(384, dtype=np.float32)
    value[:2] = (first, second)
    return value


class StubEmbeddings:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [np.asarray(self.mapping[text]).copy().tolist() for text in texts]


class VectorLibraryTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.documents = [document("D1", "first"), document("D2", "second"), document("D3", "third")]
        self.mapping = {"D1. first": vector(10), "D2. second": vector(0, 2),
                        "D3. third": vector(1, 1), "question": vector(3)}
        self.config = self.settings(self.documents)

    def test_cosine_ranking_and_magnitude_invariance(self):
        library = VectorLibrary(StubEmbeddings(self.mapping), self.config)
        found = library.search("question", top_k=3)
        self.assertEqual([item["id"] for item in found], ["D1", "D3", "D2"])
        self.assertAlmostEqual(found[0]["score"], 1.0, places=6)
        self.assertAlmostEqual(found[1]["score"], 1 / np.sqrt(2), places=6)
        self.assertAlmostEqual(found[2]["score"], 0.0, places=6)

    def test_tied_scores_keep_corpus_order(self):
        mapping = dict(self.mapping, **{"D2. second": vector(7)})
        found = VectorLibrary(StubEmbeddings(mapping), self.config).search("question", top_k=2)
        self.assertEqual([item["id"] for item in found], ["D1", "D2"])

    def test_explicit_top_k_limits_results(self):
        found = VectorLibrary(StubEmbeddings(self.mapping), self.config).search("question", top_k=1)
        self.assertEqual([item["id"] for item in found], ["D1"])

    def test_reopened_index_uses_cached_document_vectors(self):
        first = StubEmbeddings(self.mapping)
        VectorLibrary(first, self.config).ensure_index()
        second = StubEmbeddings({"question": vector(1)})
        VectorLibrary(second, self.config).search("question")
        self.assertEqual(second.calls, [["question"]])

    def test_corpus_text_change_invalidates_vector_cache(self):
        VectorLibrary(StubEmbeddings(self.mapping), self.config).ensure_index()
        changed = [dict(value) for value in self.documents]
        changed[0]["text"] = "changed content"
        self.config.corpus_path.write_text(json.dumps({"documents": changed}), encoding="utf-8")
        mapping = dict(self.mapping, **{"D1. changed content": vector(1)})
        models = StubEmbeddings(mapping)
        VectorLibrary(models, self.config).ensure_index()
        self.assertEqual(len(models.calls), 1)
        self.assertEqual(len(list(self.config.state_dir.glob("vectors-*.npz"))), 2)

    def test_duplicate_document_ids_are_rejected(self):
        settings = self.settings([self.documents[0], self.documents[0]])
        with self.assertRaises(ValueError):
            VectorLibrary(StubEmbeddings(self.mapping), settings)

    def test_bad_document_embedding_shape_is_rejected(self):
        mapping = {key: np.zeros(3) for key in self.mapping}
        with self.assertRaises(ValueError):
            VectorLibrary(StubEmbeddings(mapping), self.config).ensure_index()

    def test_nonfinite_document_vector_is_rejected(self):
        mapping = dict(self.mapping)
        mapping["D1. first"] = vector(np.nan)
        with self.assertRaises(ValueError):
            VectorLibrary(StubEmbeddings(mapping), self.config).ensure_index()

    def test_zero_document_vector_is_rejected(self):
        mapping = dict(self.mapping, **{"D1. first": vector(0)})
        with self.assertRaises(ValueError):
            VectorLibrary(StubEmbeddings(mapping), self.config).ensure_index()

    def test_bad_query_vectors_are_rejected(self):
        for bad in (np.zeros(383), vector(np.inf), vector(0)):
            with self.subTest(shape=bad.shape, finite=bool(np.isfinite(bad).all())):
                mapping = dict(self.mapping, question=bad)
                with self.assertRaises(ValueError):
                    VectorLibrary(StubEmbeddings(mapping), self.config).search("question")

    def test_sibling_evaluation_file_is_not_ingested(self):
        (self.directory / "evaluation_cases.json").write_text(
            json.dumps({"documents": [document("LEAK", "predeclared test answers")]}), encoding="utf-8"
        )
        library = VectorLibrary(StubEmbeddings(self.mapping), self.config)
        self.assertEqual(set(library.by_id), {"D1", "D2", "D3"})

    def test_public_document_listing_excludes_passages_and_vectors(self):
        library = VectorLibrary(StubEmbeddings(self.mapping), self.config)
        self.assertEqual(len(library.public_documents()), 3)
        self.assertNotIn("text", library.public_documents()[0])
        self.assertNotIn("vectors", library.public_documents()[0])
