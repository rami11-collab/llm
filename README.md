# EvidenceDesk

Local research assistant with vector RAG, Crossref DOI lookup, arXiv search,
conversation history and a custom source-ID/quotation auditor.

This repository contains the code and running instructions. The report,
presentation and demonstration video are submitted separately.

## Run locally — Windows x64

Tested with Python 3.12 on Windows 11, CPU inference and 16 GB RAM. Install
64-bit Python 3.12 and the [Microsoft Visual C++ v14 x64 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
Open a terminal in this folder, where `app.py` and `requirements.txt` are located.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\setup_models.py
.\.venv\Scripts\python.exe scripts\start_models.py
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:8010** in a browser on the same computer. Leave the
terminal open while using the app. Both local models should show as ready.

The first setup downloads approximately **446 MB** of pinned free model/runtime
assets and verifies their sizes and SHA256 hashes. These weights and binaries
are not stored in this repository. No paid API key or hosted-model subscription
is required. Fresh external lookups require Internet access.

Try: `What does CiteEval evaluate?` Then inspect its sources and audit results.

## Later starts and shutdown

After setup, double-click `run_windows.cmd`. For manual starts, stop the app
with Ctrl+C and stop launcher-owned model servers with:

```powershell
.\.venv\Scripts\python.exe scripts\stop_models.py
```

## Documentation and tests

- [README.txt](README.txt): full setup, prerequisites, configuration, platform
  limitations and run instructions.
- `evidencedesk/`: agent, model clients, retrieval, tools and conversation store.
- `static/`: HTML/CSS/JavaScript interface.
- `data/`: eleven original attributed research notes and provenance.
- `scripts/`: verified model setup and process launch/shutdown.
- `tests/`: 41 offline software tests.
- [Evaluation instructions](evaluation/README.md) and `evaluation/results/`:
  scoring code, cases and actual saved results.

Run the offline tests after installing dependencies:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The quotation auditor checks identifiers and matching text spans. It does not
establish semantic truth. The library contains short curated notes, not full
papers. See the README and saved evaluation for the system's measured limits.

Project code is MIT licensed; see [LICENSE.txt](LICENSE.txt) and
[third-party notices](THIRD_PARTY_NOTICES.txt).
