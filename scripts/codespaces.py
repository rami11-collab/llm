"""Linux/Codespaces installation and startup for the original EvidenceDesk app."""

import argparse
import contextlib
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
PYTHON = ROOT / ".venv" / "bin" / "python"
LLAMA_SOURCE = STATE / "llama.cpp"
LLAMA_COMMIT = "c6fb3b5be2209f6c12339833198190f6f6829581"  # b11899
LLAMA_URL = "https://github.com/ggml-org/llama.cpp.git"
LLAMA_FLAGS = [
    "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DGGML_NATIVE=OFF",
    "-DGGML_CUDA=OFF", "-DLLAMA_BUILD_TESTS=OFF", "-DLLAMA_BUILD_EXAMPLES=OFF",
    "-DLLAMA_BUILD_APP=OFF", "-DLLAMA_BUILD_SERVER=ON", "-DLLAMA_BUILD_UI=OFF",
    "-DLLAMA_USE_PREBUILT_UI=OFF", "-DLLAMA_OPENSSL=ON",
]
MODEL_NAME = "Qwen3-0.6B-Q4_K_M"
EMBEDDING_NAME = "all-MiniLM-L6-v2-Q8_0"


def run(command, **kwargs):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True, **kwargs)


def output(command):
    return subprocess.check_output([str(part) for part in command], cwd=ROOT, text=True).strip()


@contextlib.contextmanager
def lock(name):
    STATE.mkdir(exist_ok=True)
    with (STATE / name).open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another EvidenceDesk setup/start command is still running. Wait for it to finish.")
        yield


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def setup():
    if platform.system() != "Linux":
        raise RuntimeError("This setup is for Linux/GitHub Codespaces. See README.md for Windows.")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use Python 3.12, as provided by the repository's Codespaces container.")
    for name in ("evidencedesk/agent.py", "static/index.html", "data/corpus.json", "runtime/manifest.json"):
        if not (ROOT / name).is_file():
            raise RuntimeError(f"The complete project is required; missing {name}. Pull the restored repository first.")
    if not PYTHON.is_file():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    run([PYTHON, "-c", 'import sys; assert sys.version_info[:2] == (3, 12), "Existing .venv must use Python 3.12"'])
    environment = dict(os.environ, PIP_CACHE_DIR=str(STATE / "pip-cache"))
    run([PYTHON, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
         "-r", ROOT / "requirements.txt", "cmake==4.1.0"], env=environment)
    run([PYTHON, "-m", "pip", "check"], env=environment)
    prerequisites = all(shutil.which(tool) for tool in ("git", "g++", "make", "pkg-config"))
    openssl = prerequisites and subprocess.run(["pkg-config", "--exists", "openssl"], check=False).returncode == 0
    if not openssl:
        prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
        run([*prefix, "apt-get", "update"])
        run([*prefix, "apt-get", "install", "-y", "--no-install-recommends",
             "git", "build-essential", "pkg-config", "libssl-dev", "ca-certificates"])

    if not LLAMA_SOURCE.exists():
        run(["git", "clone", "--depth", "1", "--branch", "b11899", "--single-branch",
             LLAMA_URL, LLAMA_SOURCE])
    if not (LLAMA_SOURCE / ".git").is_dir():
        raise RuntimeError(f"Refusing to overwrite the existing non-Git directory {LLAMA_SOURCE}.")
    if output(["git", "-C", LLAMA_SOURCE, "status", "--porcelain"]):
        raise RuntimeError("The local llama.cpp checkout has changes. Preserve them before rerunning setup.")
    if output(["git", "-C", LLAMA_SOURCE, "rev-parse", "HEAD"]) != LLAMA_COMMIT:
        run(["git", "-C", LLAMA_SOURCE, "fetch", "--depth", "1", "origin", LLAMA_COMMIT])
        run(["git", "-C", LLAMA_SOURCE, "checkout", "--detach", LLAMA_COMMIT])
    if output(["git", "-C", LLAMA_SOURCE, "rev-parse", "HEAD"]) != LLAMA_COMMIT:
        raise RuntimeError("llama.cpp source revision verification failed.")

    cmake = PYTHON.parent / "cmake"
    build = LLAMA_SOURCE / "build"
    built = build / "bin" / "llama-server"
    installed = ROOT / "runtime" / "bin" / "llama-server"
    receipt_path = STATE / "codespaces-runtime.json"
    expected = {"commit": LLAMA_COMMIT, "flags": LLAMA_FLAGS,
                "architecture": platform.machine(), "cmake": output([cmake, "--version"]).splitlines()[0]}
    try:
        receipt = json.loads(receipt_path.read_text())
    except (OSError, ValueError):
        receipt = {}
    valid = (all(receipt.get(key) == value for key, value in expected.items())
             and built.is_file() and installed.is_file()
             and receipt.get("sha256") == digest(built) == digest(installed))
    if valid:
        print("Reusing verified Linux llama-server build.", flush=True)
    else:
        # CMake's incremental build reuses valid outputs from an interrupted/previous build.
        run([cmake, "-S", LLAMA_SOURCE, "-B", build, *LLAMA_FLAGS])
        run([cmake, "--build", build, "--target", "llama-server", "--parallel", min(4, os.cpu_count() or 2)])
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, installed)
        run([installed, "--version"])
        write_json(receipt_path, dict(expected, sha256=digest(installed)))

    specification = importlib.util.spec_from_file_location("evidencedesk_model_setup", ROOT / "scripts" / "setup_models.py")
    installer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(installer)
    manifest = json.loads((ROOT / "runtime" / "manifest.json").read_text(encoding="utf-8"))
    for asset in sorted((item for item in manifest["assets"] if item["kind"] == "model"), key=lambda item: item["size"]):
        print(f"Installing/checking original model: {asset['filename']} (huggingface.co)", flush=True)
        try:
            installer.download(asset)
        except (OSError, RuntimeError) as error:
            raise RuntimeError(f"Model installation failed for {asset['filename']}: {error}. "
                               "Setup is incomplete; resolve the download/checksum error and rerun setup.") from error
    print("Original models verified and Linux runtime installed. Setup complete.", flush=True)


def health(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        body = response.read(65537)
        if response.status == 200 and len(body) <= 65536:
            payload = json.loads(body)
            return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()
    return None


def original_app(payload):
    return bool(payload and payload.get("model") == MODEL_NAME
                and payload.get("embedding") == EMBEDDING_NAME
                and payload.get("corpus_size") == 11
                and isinstance(payload.get("models"), dict))


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def start(port):
    if not 1 <= port <= 65535:
        raise RuntimeError("EVIDENCEDESK_APP_PORT must be between 1 and 65535.")
    existing = health(port)
    if listening(port) and not original_app(existing):
        raise RuntimeError(f"Port {port} is occupied by another service. No process was stopped. "
                           "Use EVIDENCEDESK_APP_PORT=8011 bash scripts/run_codespaces.sh for another port.")
    required = [PYTHON, ROOT / "runtime" / "bin" / "llama-server",
                ROOT / "runtime" / "models" / (MODEL_NAME + ".gguf"),
                ROOT / "runtime" / "models" / (EMBEDDING_NAME + ".gguf")]
    if any(not path.is_file() for path in required):
        raise RuntimeError("Setup is incomplete. First run: bash scripts/setup_codespaces.sh")
    # Detach the model launcher's session so its children survive the lifecycle hook.
    run([PYTHON, ROOT / "scripts" / "start_models.py"], start_new_session=True)
    process = None
    if not original_app(existing):
        with (STATE / f"app-{port}.log").open("ab") as log:
            process = subprocess.Popen([str(PYTHON), str(ROOT / "app.py"), "--port", str(port)],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, env=dict(os.environ, PYTHONUNBUFFERED="1"))
        import psutil
        child = psutil.Process(process.pid)
        write_json(STATE / f"codespaces-app-{port}.json", {
            "pid": process.pid, "create_time": child.create_time(),
            "binary": str(Path(child.exe()).resolve()), "app": str(ROOT / "app.py"), "port": port,
        })
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"The application exited. Read state/app-{port}.log for the error.")
        payload = health(port)
        if original_app(payload) and all(payload["models"].get(role) is True for role in ("llm", "embeddings")):
            print(f"Both original models and EvidenceDesk are ready. In GitHub Codespaces, open Ports → {port} → Open in Browser.", flush=True)
            return
        time.sleep(1)
    raise RuntimeError(f"Readiness failed. Inspect state/app-{port}.log and state/model-8091.log / state/model-8092.log.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "start"))
    parser.add_argument("--port", type=int, default=os.environ.get("EVIDENCEDESK_APP_PORT", "8010"))
    args = parser.parse_args()
    try:
        with lock("codespaces-" + args.action + ".lock"):
            setup() if args.action == "setup" else start(args.port)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"EvidenceDesk: {error}") from error


if __name__ == "__main__":
    main()
