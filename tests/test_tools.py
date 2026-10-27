"""Mocked HTTP verifies normal records, timeout handling, spacing, and cache recovery."""

import hashlib
import json
from unittest.mock import Mock, patch

import requests

from evidencedesk.tools import ResearchTools
from tests.helpers import WorkspaceTestCase

ATOM = """<?xml version='1.0'?>
<feed xmlns='http://www.w3.org/2005/Atom'><entry>
<id>http://arxiv.org/abs/2504.12516v1</id><title> BrowseComp: A Benchmark </title>
<published>2025-04-16T22:27:45Z</published><summary>A test abstract with evidence.</summary>
<author><name>Test Author</name></author></entry></feed>"""


def crossref_response():
    response = Mock(spec=requests.Response)
    response.raise_for_status.return_value = None
    response.json.return_value = {"message": {
        "DOI": "10.18653/v1/2025.wasp-main.14", "title": ["Atlas"],
        "published": {"date-parts": [[2025, 12, 23]]},
        "author": [{"given": "Akash", "family": "Kodali"}],
        "URL": "https://doi.org/10.18653/v1/2025.wasp-main.14",
    }}
    return response


def arxiv_response(text=ATOM):
    response = Mock(spec=requests.Response)
    response.raise_for_status.return_value = None
    response.text = text
    return response


class ResearchToolsTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.settings(tool_timeout=0.25)
        self.tools = ResearchTools(self.config)
        self.doi = "10.18653/v1/2025.wasp-main.14"

    @patch("evidencedesk.tools.requests.get")
    def test_crossref_maps_metadata_and_uses_bounded_timeout(self, get):
        get.return_value = crossref_response()
        result = self.tools.crossref(self.doi)
        self.assertTrue(result["ok"])
        self.assertEqual(result["cache_status"], "live")
        record = result["data"][0]
        self.assertEqual((record["title"], record["year"]), ("Atlas", 2025))
        self.assertEqual(record["authors"], ["Akash Kodali"])
        self.assertEqual(get.call_args.kwargs["timeout"], 0.25)
        self.assertIn("10.18653%2Fv1%2F2025.wasp-main.14", get.call_args.args[0])

    @patch("evidencedesk.tools.requests.get")
    def test_invalid_doi_does_not_contact_network(self, get):
        self.assertFalse(self.tools.crossref("not a DOI")["ok"])
        get.assert_not_called()

    @patch("evidencedesk.tools.requests.get", side_effect=requests.Timeout("offline timeout"))
    def test_crossref_timeout_returns_actionable_failure(self, get):
        result = self.tools.crossref(self.doi)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "Timeout")
        self.assertEqual(result["cache_status"], "none")
        self.assertEqual(result["data"], [])
        self.assertIn("retry", result["error"])

    @patch("evidencedesk.tools.requests.get")
    def test_fresh_cache_avoids_duplicate_http(self, get):
        get.return_value = crossref_response()
        self.tools.crossref(self.doi)
        cached = self.tools.crossref(self.doi)
        self.assertEqual(cached["cache_status"], "cached")
        self.assertEqual(get.call_count, 1)

    @patch("evidencedesk.tools.requests.get")
    def test_use_cache_false_forces_new_request(self, get):
        get.return_value = crossref_response()
        self.tools.crossref(self.doi)
        self.tools.crossref(self.doi, use_cache=False)
        self.assertEqual(get.call_count, 2)

    @patch("evidencedesk.tools.requests.get")
    def test_expired_cache_is_refetched(self, get):
        get.return_value = crossref_response()
        self.tools.crossref(self.doi)
        path = next(self.tools.cache_dir.glob("*.json"))
        value = json.loads(path.read_text(encoding="utf-8"))
        value["fetched_at"] = 0
        path.write_text(json.dumps(value), encoding="utf-8")
        result = self.tools.crossref(self.doi)
        self.assertEqual(result["cache_status"], "live")
        self.assertEqual(get.call_count, 2)

    @patch("evidencedesk.tools.requests.get")
    def test_corrupted_cache_is_a_miss_not_a_crash(self, get):
        get.return_value = crossref_response()
        self.tools.crossref(self.doi)
        next(self.tools.cache_dir.glob("*.json")).write_text("{incomplete", encoding="utf-8")
        result = self.tools.crossref(self.doi)
        self.assertTrue(result["ok"])
        self.assertEqual(result["cache_status"], "live")
        self.assertEqual(get.call_count, 2)

    @patch("evidencedesk.tools.requests.get")
    def test_failed_request_is_not_persisted_as_a_successful_cache(self, get):
        get.side_effect = [requests.Timeout("temporary"), crossref_response()]
        self.assertFalse(self.tools.crossref(self.doi)["ok"])
        recovered = self.tools.crossref(self.doi)
        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["cache_status"], "live")
        self.assertEqual(get.call_count, 2)

    @patch("evidencedesk.tools.requests.get")
    def test_arxiv_atom_is_parsed_and_url_is_https(self, get):
        get.return_value = arxiv_response()
        result = self.tools.arxiv("citation reliability")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"][0]["year"], "2025")
        self.assertTrue(result["data"][0]["url"].startswith("https://"))
        query = get.call_args.kwargs["params"]["search_query"]
        self.assertIn("citation", query)
        self.assertIn("reliability", query)
        self.assertIn("AND", query)

    @patch("evidencedesk.tools.requests.get")
    def test_arxiv_identifier_uses_id_list(self, get):
        get.return_value = arxiv_response()
        self.tools.arxiv("https://arxiv.org/abs/2504.12516v1")
        self.assertEqual(get.call_args.kwargs["params"], {"id_list": "2504.12516v1"})

    @patch("evidencedesk.tools.requests.get")
    def test_arxiv_malformed_xml_is_reported_as_failure(self, get):
        get.return_value = arxiv_response("<not-complete")
        self.assertFalse(self.tools.arxiv("broken XML")["ok"])

    @patch("evidencedesk.tools.requests.get", side_effect=requests.Timeout("offline"))
    def test_arxiv_timeout_is_handled(self, get):
        result = self.tools.arxiv("timeout example")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "Timeout")

    @patch("evidencedesk.tools.time.sleep")
    @patch("evidencedesk.tools.time.monotonic", side_effect=[100.0, 100.0, 101.0, 103.0])
    @patch("evidencedesk.tools.requests.get")
    def test_arxiv_requests_respect_three_second_start_spacing(self, get, monotonic, sleep):
        get.return_value = arxiv_response()
        self.tools.arxiv("first query", use_cache=False)
        self.tools.arxiv("second query", use_cache=False)
        sleep.assert_called_once_with(2.0)

    @patch("evidencedesk.tools.requests.get")
    def test_empty_arxiv_query_does_not_contact_network(self, get):
        self.assertFalse(self.tools.arxiv("   ")["ok"])
        get.assert_not_called()
