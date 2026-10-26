EVIDENCEDESK
COE548 / COE748 final project - Rami Amacha

WHAT IT DOES
EvidenceDesk is a local research assistant with a browser UI, a bounded LangGraph
workflow, vector retrieval, and three additional tools:
  1. Crossref DOI metadata lookup.
  2. arXiv paper/identifier search.
  3. A custom source-ID and exact-quote auditor.
Conversation history is stored locally in SQLite. Tool errors and cache status
are visible. The full agent filters proposed claims that fail its mechanical
evidence checks; these checks do not establish semantic truth or paper quality.

TESTED ENVIRONMENT
Windows 11 x64; Python 3.12; Intel i7-1185G7 CPU, 4 cores/8 logical processors,
16 GB RAM. No GPU, paid model subscription, hosted-model account, or API key is
required. Downloading the three pinned runtime/model assets needs about 446 MB
of network transfer; extraction, dependency installation and resumable parts need
additional disk space. Model weights are downloaded, not hidden inside the ZIP.
The exact model revisions, asset sizes and SHA256 hashes are in runtime/manifest.json.

FIRST SETUP (Windows PowerShell or Command Prompt)
Install 64-bit Python 3.12 if it is not already available. The pinned llama.cpp
Windows binaries also require Microsoft's Visual C++ v14 x64 Redistributable.
If MSVCP140.dll or VCRUNTIME140*.dll is missing, install the current supported
x64 package from Microsoft's official guidance (do not download individual DLLs):
  https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
  https://aka.ms/vc14/vc_redist.x64.exe
Extract the code ZIP into a short local path, for example C:\EvidenceDesk.
Open the extracted folder containing app.py and requirements.txt.
Run these commands from that folder:

  py -3.12 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe scripts\setup_models.py
  .venv\Scripts\python.exe scripts\start_models.py
  .venv\Scripts\python.exe app.py

Open http://127.0.0.1:8010 in a browser. The two readiness indicators should show
that the language model and embedding model are available. The initial vector
index is built on the first retrieval question and is then cached locally.
For later starts, double-click run_windows.cmd after completing the first setup.

MANUAL SHUTDOWN
Press Ctrl+C in the app terminal. Stop model servers owned by the launcher with:
  .venv\Scripts\python.exe scripts\stop_models.py
The shutdown helper checks each process identity and start time before stopping it.
Partial restarts retain verified ownership records for already-running servers.
The launcher reuses a healthy service on ports 8091/8092; its health probe does
not independently verify that service's model identity. Keep those ports free of
unrelated services, or stop those services before starting this project. Servers
started separately are not automatically owned or stopped by this launcher.

OTHER PLATFORMS
The application code is ordinary Python, but the automatic binary installer is
tested on Windows x64 only. On Linux/macOS, use an official compatible llama.cpp
build and the same two GGUF model files. Start the chat API on 127.0.0.1:8091 and
the embedding API on 127.0.0.1:8092, with the model names/settings documented in
scripts/start_models.py. Cross-platform behavior has not been measured here.

TRY THESE FEATURES
  - What does CiteEval evaluate?
  - Summarize that paper in one sentence. (Use the same conversation.)
  - Check DOI 10.18653/v1/2025.wasp-main.14
  - Search arXiv for agentic retrieval augmented generation
  - What is EvidenceDesk accuracy on LegalBench? (Unsupported in the library.)
The quotation-audit dialog can also challenge a valid or fabricated quotation.
The Library view shows source IDs, dates, provenance and licenses.

DATA AND EVIDENCE SCOPE
data/corpus.json contains 11 original curated research notes, not 11 full papers.
They summarize verified 2025-2026 research and link to primary sources. Several
records also preserve a separate short licensed original-paper excerpt with its
attribution. The current vector index and auditor use each document's text field,
which is the original research note. They do not imply that matching a note is
verification against a full original PDF. See data/license_manifest.json and
data/references.json. Evaluation questions are separate and are never indexed.

REPRODUCE THE EVALUATION
Install optional plotting dependencies:
  .venv\Scripts\python.exe -m pip install -r requirements-eval.txt
Run offline tests without starting any model or network service:
  .venv\Scripts\python.exe -m unittest discover -s tests -v
Run the measured evaluation with both model servers active, following the exact
entry point and options in evaluation/README.md. Saved results are supplied in
evaluation/results. Numerical conclusions in the report refer to that saved run.
Do not change prompts, thresholds or cases after viewing test results and then
present the same run as an untouched evaluation.

CONFIGURATION AND PRIVACY
The default application and model servers bind only to 127.0.0.1. Optional local
model URL variables are documented in .env.example; the app reads environment
variables, not a live .env file automatically. External tool queries are sent to
Crossref or arXiv. Cached external responses expire after 24 hours and are labeled
cached; set the UI cache option off to request fresh metadata. User conversations,
model logs and vector caches are in state/ and are excluded from the submission.
No actual API key or other secret is included. Do not expose this prototype as a
public multi-user service without adding authentication and stronger deployment
controls. Avoid submitting sensitive personal material to external search tools.

CODE MAP
  app.py                   Loopback HTTP API and static file serving
  evidencedesk/agent.py     Four-node LangGraph workflow and delivery policy
  evidencedesk/llm.py       Real local-model HTTP clients; no canned model answers
  evidencedesk/retrieval.py Dense vector index and cosine retrieval
  evidencedesk/tools.py     Crossref, arXiv, custom evidence auditor and cache
  evidencedesk/store.py     Local SQLite conversation persistence
  static/                  Editable HTML/CSS/JavaScript UI
  scripts/                 Verified setup and local process launch/shutdown
  tests/                   Offline correctness and failure-handling tests
  evaluation/              Predeclared cases, metrics, actual outputs and plots
  runtime/manifest.json     Pinned public model/runtime download metadata

LICENSES
Project code is MIT licensed; see LICENSE.txt. Preserve third-party license and
attribution notices in THIRD_PARTY_NOTICES.txt and data/license_manifest.json.
