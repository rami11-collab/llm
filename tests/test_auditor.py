"""Mechanical validity is deliberately distinct from semantic entailment."""

import unittest

from evidencedesk.tools import audit_claims


class EvidenceAuditorTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{"id": "P01", "text": "The benchmark contains 100 research tasks. It evaluates report quality."}]

    def claim(self, **updates):
        value = {"text": "The benchmark has 100 tasks.", "source_id": "P01",
                 "quote": "The benchmark contains 100 research tasks."}
        value.update(updates)
        return value

    def test_valid_source_and_contiguous_quote_pass(self):
        result = audit_claims([self.claim()], self.sources)
        self.assertEqual((result["passed"], result["total"]), (1, 1))
        self.assertTrue(result["checked"][0]["valid"])

    def test_quote_case_whitespace_and_unicode_width_are_normalized(self):
        changed = self.claim(quote="Ｔｈｅ  BENCHMARK\n contains 100 research tasks.")
        self.assertTrue(audit_claims([changed], self.sources)["checked"][0]["valid"])

    def test_known_but_not_retrieved_source_is_rejected(self):
        result = audit_claims([self.claim(source_id="P02")], self.sources)
        self.assertEqual(result["passed"], 0)
        self.assertIn("not supplied", result["checked"][0]["reason"])

    def test_noncontiguous_quote_is_rejected(self):
        result = audit_claims([self.claim(quote="benchmark contains report quality")], self.sources)
        self.assertFalse(result["checked"][0]["valid"])

    def test_too_short_quote_is_rejected(self):
        self.assertFalse(audit_claims([self.claim(quote="100")], self.sources)["checked"][0]["valid"])

    def test_empty_claim_text_is_rejected(self):
        self.assertFalse(audit_claims([self.claim(text="  ")], self.sources)["checked"][0]["valid"])

    def test_missing_fields_are_rejected_without_crashing(self):
        result = audit_claims([{}, {"text": "Unsupported claim"}], self.sources)
        self.assertEqual((result["passed"], result["total"]), (0, 2))

    def test_mixed_batch_keeps_individual_failures(self):
        result = audit_claims([self.claim(), self.claim(source_id="P99"),
                               self.claim(quote="A fabricated quotation.")], self.sources)
        self.assertEqual([item["valid"] for item in result["checked"]], [True, False, False])
        self.assertEqual((result["passed"], result["total"]), (1, 3))

    def test_empty_audit_has_no_claim_denominator(self):
        result = audit_claims([], self.sources)
        self.assertEqual(result["checked"], [])
        self.assertEqual((result["passed"], result["total"]), (0, 0))

    def test_semantically_false_claim_can_pass_mechanical_audit(self):
        # This challenge documents the scope limit; accepting a genuine quote does not prove truth.
        result = audit_claims([self.claim(text="This benchmark proves every agent is perfectly reliable.")], self.sources)
        self.assertTrue(result["checked"][0]["valid"])
        self.assertIn("not a semantic", result["scope"])


if __name__ == "__main__":
    unittest.main()
