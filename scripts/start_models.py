"""Start the two local model APIs without opening extra terminal windows."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import psutil

ROOT = Path(__file__).resolve().parents[1]


def healthy(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def owned_processes(path):
    """Retain a recorded child only while its executable and start time match."""
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(records, list):
        return []
    owned = []
    seen = set()
    for record in records:
        try:
            process = psutil.Process(int(record["pid"]))
            binary = Path(record["binary"]).resolve()
            created = float(record["create_time"])
            key = (process.pid, created)
            if (Path(process.exe()).resolve() == binary
                    and abs(process.create_time() - created) < 0.01
                    and key not in seen):
                owned.append({"port": int(record["port"]), "pid": process.pid,
                              "binary": str(binary), "create_time": created})
                seen.add(key)
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, TypeError,
                ValueError, OSError):
            continue
    return owned


def save_owned_processes(path, records):
    """Checkpoint ownership after each launch, including partial startups."""
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "runtime")
    args = parser.parse_args()
    runtime = args.runtime_dir.resolve()
    binary = runtime / "bin" / ("llama-server.exe" if os.name == "nt" else "llama-server")
    state = ROOT / "state"
    state.mkdir(exist_ok=True)
    specifications = [
        (8091, "Qwen3-0.6B-Q4_K_M.gguf", ["-c", "4096", "--alias", "Qwen3-0.6B-Q4_K_M"]),
        (8092, "all-MiniLM-L6-v2-Q8_0.gguf",
         ["--embedding", "--pooling", "mean", "-c", "2048", "-b", "2048", "-ub", "2048",
          "--alias", "all-MiniLM-L6-v2-Q8_0"]),
    ]
    ownership_path = state / "model_processes.json"
    owned = owned_processes(ownership_path)
    save_owned_processes(ownership_path, owned)
    for port, filename, extra in specifications:
        if healthy(port):
            print(f"Model API already ready on port {port}.", flush=True)
            continue
        model = runtime / "models" / filename
        if not binary.is_file() or not model.is_file():
            raise SystemExit("Model files are missing. Run scripts/setup_models.py first.")
        command = [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                   "-t", "4", "-tb", "4", "-np", "1", *extra]
        with (state / f"model-{port}.log").open("ab") as log:
            process = subprocess.Popen(command, cwd=binary.parent, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        owned.append({"port": port, "pid": process.pid, "binary": str(binary),
                      "create_time": psutil.Process(process.pid).create_time()})
        save_owned_processes(ownership_path, owned)
        print(f"Starting model API on port {port} (PID {process.pid}).", flush=True)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if all(healthy(port) for port, _, _ in specifications):
            print("Both local model APIs are ready.", flush=True)
            return
        time.sleep(1)
    raise SystemExit("A model did not become ready. See state/model-8091.log and state/model-8092.log.")


if __name__ == "__main__":
    main()
