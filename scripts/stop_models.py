"""Stop only the model processes created by this project's launcher."""

import json
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "state" / "model_processes.json"
if not path.exists():
    raise SystemExit("No model processes were recorded by this project.")
records = json.loads(path.read_text(encoding="utf-8"))
for record in records:
    try:
        process = psutil.Process(record["pid"])
        expected = Path(record["binary"]).resolve()
        if (Path(process.exe()).resolve() == expected
                and abs(process.create_time() - record.get("create_time", -1)) < 0.01):
            process.terminate()
            process.wait(timeout=10)
            print(f"Stopped model API on port {record['port']}.")
        else:
            print(f"Skipped PID {record['pid']}: process identity no longer matches.")
    except psutil.NoSuchProcess:
        print(f"PID {record['pid']} is already stopped.")
    except (psutil.AccessDenied, psutil.TimeoutExpired) as error:
        print(f"Could not stop PID {record['pid']}: {type(error).__name__}.")
