"""Persistence and session isolation are tested without invoking a model."""

from evidencedesk.store import ConversationStore
from tests.helpers import WorkspaceTestCase


class ConversationStoreTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.store = ConversationStore(self.directory / "memory")

    def test_sessions_do_not_share_turns(self):
        self.store.save("alice", "Alice private question", {"answer": "A"})
        self.store.save("bob", "Bob private question", {"answer": "B"})
        self.assertEqual([item["question"] for item in self.store.history("alice")], ["Alice private question"])
        self.assertEqual([item["question"] for item in self.store.history("bob")], ["Bob private question"])
        self.assertEqual(self.store.history("new-session"), [])

    def test_history_returns_latest_turns_in_chronological_order(self):
        for number in range(5):
            self.store.save("same", str(number), {"answer": str(number)})
        self.assertEqual([item["question"] for item in self.store.history("same", limit=2)], ["3", "4"])

    def test_unicode_and_nested_response_round_trip(self):
        response = {"answer": "Réponse عربية", "claims": [{"source_id": "P01", "valid": True}]}
        self.store.save("unicode", "سؤال", response)
        self.assertEqual(self.store.history("unicode")[0]["response"], response)

    def test_parameterized_session_id_is_treated_literally(self):
        identifier = "session'; DROP TABLE turns;--"
        self.store.save(identifier, "literal", {"answer": "safe"})
        self.store.save("ordinary", "still exists", {"answer": "yes"})
        self.assertEqual(self.store.history(identifier)[0]["question"], "literal")
        self.assertEqual(self.store.history("ordinary")[0]["question"], "still exists")

    def test_new_instance_loads_persisted_history(self):
        self.store.save("persisted", "question", {"answer": "answer"})
        reopened = ConversationStore(self.directory / "memory")
        self.assertEqual(reopened.history("persisted")[0]["response"]["answer"], "answer")
