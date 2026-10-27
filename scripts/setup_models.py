"""Install the pinned public Windows CPU runtime and models in this project only."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
CHUNK = 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(CHUNK):
            digest.update(data)
    return digest.hexdigest()


def download(asset):
    folder = RUNTIME / "models" if asset["kind"] == "model" else RUNTIME
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / asset["filename"]
    if target.exists() and target.stat().st_size == asset["size"] and sha256(target) == asset["sha256"]:
        print("Verified existing:", asset["filename"], flush=True)
        return target
    with urllib.request.urlopen(urllib.request.Request(asset["url"], headers={"Range": "bytes=0-0"}),
                                timeout=45) as response:
        if response.status != 206:
            raise RuntimeError("Download server did not honor a partial request.")
        resolved_url = response.geturl()
        response.read()
    parts = RUNTIME / "download_parts" / asset["filename"]
    parts.mkdir(parents=True, exist_ok=True)
    count = (asset["size"] + CHUNK - 1) // CHUNK

    def fetch(index):
        start = index * CHUNK
        end = min(start + CHUNK, asset["size"]) - 1
        part = parts / f"{index:05d}.part"
        if part.exists() and part.stat().st_size == end - start + 1:
            return
        for attempt in range(6):
            try:
                request = urllib.request.Request(resolved_url,
                    headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206:
                        raise RuntimeError("Server ignored partial download request.")
                    data = response.read()
                if len(data) != end - start + 1:
                    raise RuntimeError("Incomplete download segment.")
                part.write_bytes(data)
                return
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(min(2 ** attempt, 10))

    print(f"Downloading {asset['filename']} ({asset['size']/1e6:.1f} MB)", flush=True)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch, index) for index in range(count)]
        for done, future in enumerate(as_completed(futures), 1):
            future.result()
            if done % 50 == 0 or done == count:
                print(f"  {done}/{count} segments", flush=True)
    with target.open("wb") as output:
        for index in range(count):
            output.write((parts / f"{index:05d}.part").read_bytes())
    if target.stat().st_size != asset["size"] or sha256(target) != asset["sha256"]:
        raise RuntimeError("Checksum mismatch; remove the matching download_parts folder and retry.")
    print("SHA256 verified:", asset["filename"], flush=True)
    return target


def main():
    if os.name != "nt":
        raise SystemExit("The automatic binary installer targets Windows x64. See README.txt for other platforms.")
    manifest = json.loads((RUNTIME / "manifest.json").read_text(encoding="utf-8"))
    for asset in sorted(manifest["assets"], key=lambda item: item["size"]):
        path = download(asset)
        if asset["kind"] == "runtime":
            destination = (RUNTIME / "bin").resolve()
            destination.mkdir(exist_ok=True)
            with zipfile.ZipFile(path) as archive:
                if any(not (destination / item.filename).resolve().is_relative_to(destination)
                       for item in archive.infolist()):
                    raise RuntimeError("Unsafe archive member path.")
                archive.extractall(destination)
    print("Setup complete. No API key is needed.")


if __name__ == "__main__":
    main()
