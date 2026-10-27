"""Three tools beyond RAG: Crossref, arXiv, and a custom evidence auditor."""

import hashlib
import json
import re
from threading import Lock
import time
import unicodedata
from urllib.parse import quote
import xml.etree.ElementTree as ET
import requests

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def audit_claims(claims, sources):
    """Check source membership and exact normalized quote spans, not semantic truth."""
    by_id = {source["id"]: source for source in sources}
    checked = []
    for claim in claims:
        source_id = str(claim.get("source_id", ""))
        quotation = str(claim.get("quote", ""))
        source = by_id.get(source_id)
        if source is None:
            reason = "Source ID was not supplied to the answer generator."
        elif len(normalize(quotation)) < 12:
            reason = "Evidence quote is too short to audit (minimum 12 characters)."
        elif normalize(quotation) not in normalize(source["text"]):
            reason = "Quote does not match a contiguous span in the supplied source."
        elif not str(claim.get("text", "")).strip():
            reason = "Claim text is empty."
        else:
            reason = "Source ID and quoted span match the supplied evidence."
        valid = bool(source and len(normalize(quotation)) >= 12
                     and normalize(quotation) in normalize(source["text"])
                     and str(claim.get("text", "")).strip())
        checked.append(dict(claim, valid=valid, reason=reason))
    return {"checked": checked, "passed": sum(c["valid"] for c in checked),
            "total": len(checked),
            "scope": "Exact source/quote validation; this is not a semantic truth guarantee."}


class ResearchTools:
    def __init__(self, settings):
        self.settings = settings
        self.cache_dir = settings.state_dir / "tool_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.arxiv_lock = Lock()
        self.last_arxiv_call = 0.0

    def _cached(self, tool, query, fetch, use_cache=True):
        key = hashlib.sha256((tool + "\n" + query).encode()).hexdigest()
        path = self.cache_dir / (key + ".json")
        if use_cache and path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if time.time() - value["fetched_at"] < 86400 and value.get("ok"):
                    return dict(value, cache_status="cached", tool=tool)
            except (OSError, ValueError, KeyError, TypeError):
                pass  # A damaged cache is a cache miss, not a permanent app failure.
        try:
            data = fetch()
            value = {"ok": True, "data": data, "fetched_at": time.time()}
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            return dict(value, cache_status="live", tool=tool)
        except (requests.RequestException, ValueError, KeyError, ET.ParseError) as error:
            return {"ok": False, "tool": tool, "cache_status": "none", "data": [],
                    "error": f"{tool} could not complete the lookup. Check the query or network and retry.",
                    "error_type": type(error).__name__}

    def crossref(self, doi, use_cache=True):
        match = DOI_PATTERN.search(doi)
        if not match:
            return {"ok": False, "tool": "crossref", "cache_status": "none", "data": [],
                    "error": "Enter a DOI beginning with 10., for example 10.18653/v1/2025.wasp-main.14."}
        clean = match.group(0).rstrip(".,;")

        def fetch():
            response = requests.get("https://api.crossref.org/works/" + quote(clean, safe=""),
                                    headers={"User-Agent": "EvidenceDesk/1.0 (academic course project)"},
                                    timeout=self.settings.tool_timeout)
            response.raise_for_status()
            item = response.json()["message"]
            date = item.get("published", item.get("issued", {})).get("date-parts", [[None]])[0]
            return [{"id": "DOI1", "title": item.get("title", [clean])[0],
                     "doi": item.get("DOI", clean), "year": date[0],
                     "authors": [" ".join(filter(None, [a.get("given"), a.get("family")]))
                                 for a in item.get("author", [])],
                     "url": item.get("URL", "https://doi.org/" + clean),
                     "text": "Crossref metadata record. DOI: " + item.get("DOI", clean)
                             + ". Title: " + item.get("title", [clean])[0]
                             + ". Publication year: " + str(date[0]) + ".",
                     "source_type": "live_bibliographic_metadata"}]
        return self._cached("crossref", clean.lower(), fetch, use_cache)

    def arxiv(self, query, use_cache=True):
        clean = " ".join(str(query).split())[:240]
        if not clean:
            return {"ok": False, "tool": "arxiv", "data": [], "cache_status": "none",
                    "error": "A nonempty research query is required."}

        def fetch():
            # arXiv's API guidance asks clients to space requests by at least three seconds.
            with self.arxiv_lock:
                delay = max(0.0, 3.0 - (time.monotonic() - self.last_arxiv_call))
                if delay:
                    time.sleep(delay)
                self.last_arxiv_call = time.monotonic()
                identifier = re.search(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", clean)
                terms = [term for term in re.findall(r"[A-Za-z0-9-]+", clean)
                         if term.casefold() not in {"the", "and", "for", "papers", "arxiv", "search", "find", "about", "on", "in"}][:10]
                search_query = " AND ".join(f'all:"{term}"' for term in terms) or 'all:"research"'
                params = ({"id_list": identifier.group(1)} if identifier else
                          {"search_query": search_query, "start": 0, "max_results": 3,
                           "sortBy": "relevance"})
                response = requests.get("https://export.arxiv.org/api/query", params=params,
                    headers={"User-Agent": "EvidenceDesk/1.0"}, timeout=self.settings.tool_timeout)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            found = []
            for i, entry in enumerate(root.findall("a:entry", ns), 1):
                title = " ".join(entry.findtext("a:title", "", ns).split())
                summary = " ".join(entry.findtext("a:summary", "", ns).split())
                url = entry.findtext("a:id", "", ns).replace("http://", "https://")
                found.append({"id": f"ARX{i}", "title": title,
                    "year": entry.findtext("a:published", "", ns)[:4], "url": url,
                    "authors": [e.findtext("a:name", "", ns) for e in entry.findall("a:author", ns)],
                    "text": summary[:1800], "source_type": "live_arxiv_abstract"})
            return found
        return self._cached("arxiv", "and-query-v1:" + clean, fetch, use_cache)
