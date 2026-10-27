# Run the original EvidenceDesk app on GitHub

This runs the original interface, Qwen3 chat model, MiniLM embedding model, and
Crossref/arXiv tools on a GitHub Codespace. Nothing needs to run in your laptop's
Command Prompt. The original Windows instructions and application files are
unchanged.

## Start in your browser

1. Open the repository's **Code → Codespaces** menu and create a Codespace on the
   branch containing this complete project. You can also reopen an existing one.
2. A new Codespace automatically installs the pinned Python dependencies, builds
   the pinned Linux llama.cpp runtime, downloads the two original GGUF models,
   and verifies their original SHA256 checksums. The first setup needs about
   422 MB for models plus dependencies/source and takes several minutes.
3. Startup runs both models and the app. Wait for **Both original models and
   EvidenceDesk are ready** in the startup output.
4. In the editor's **Ports** tab, use **8010 → Open in Browser**. This opens the
   Codespaces forwarded address. The README's `127.0.0.1` link refers to a server
   on the viewer's own computer and is not the Codespaces browser address.

Port 8010 stays private to your GitHub account by default. The two model APIs
stay on loopback and are not automatically forwarded. Your professor can create
their own Codespace from the complete repository. No paid model API key is used.
Codespaces itself is a GitHub service subject to the account's available usage.

## Existing Codespace

After fetching the restored project branch, open **Terminal → New Terminal**
inside the browser editor and run:

```bash
bash scripts/setup_codespaces.sh
bash scripts/run_codespaces.sh
```

Alternatively, use **Codespaces: Rebuild Container** from the editor's Command
Palette to apply `.devcontainer/devcontainer.json`; setup/start then run
automatically. Reopening an already configured Codespace restarts the services.

Setup reuses verified model files and valid build outputs. It keeps conversation
state and caches. Builds use at most four CPU workers. The exact original model
assets are read from `runtime/manifest.json`; the Linux runtime is built from
official llama.cpp release `b11899`, commit
`c6fb3b5be2209f6c12339833198190f6f6829581`. TLS and checksum verification stay
enabled. Download or verification errors stop setup rather than substituting
models or showing a false ready state.

## Check the demonstration

Both status indicators should be ready. Try these in the original chat:

- `What does CiteEval evaluate?` — local research-note retrieval.
- `Check DOI 10.18653/v1/2025.wasp-main.14` — live Crossref DOI metadata.
- `Search arXiv for agentic retrieval augmented generation` — live arXiv search.

Crossref is a DOI lookup in the original project; title/topic searches use arXiv.
Internet access to `huggingface.co` and its download redirect destinations is
required during model installation; live searches use `api.crossref.org` and
`export.arxiv.org`. Tool errors are shown if a service cannot be reached.

The original offline software tests can be run with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

These tests do not prove live model inference or remote API connectivity. Startup
requires both actual model health checks and the original 11-record corpus.

If setup fails, read its terminal output and rerun setup after correcting that
specific error. App/model logs are under `state/`. Startup refuses to replace an
unrelated service already occupying port 8010. For another app port, use:

```bash
EVIDENCEDESK_APP_PORT=8011 bash scripts/run_codespaces.sh
```

Then forward/open that port from the Codespaces Ports tab. To shut down the
whole environment, stop the Codespace through GitHub; retained files remain for
the next start. Only the web app needs forwarding, not model ports 8091/8092.
