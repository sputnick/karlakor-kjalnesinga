#!/usr/bin/env python3
"""Run the local Vision OCR helper over each selected new-song score."""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
EXTRACTION = Path("/private/tmp/kk-sheetmusic-extraction")
OUTPUT = EXTRACTION / "vision"
OCR = Path("/tmp/kk-vision-ocr")


def extract(filename: str) -> tuple[str, bool, str]:
    source = ROOT / "sheetmusic" / filename
    destination = OUTPUT / f"{filename}.txt"
    if destination.exists() and destination.stat().st_size:
        return filename, True, "cached"
    result = subprocess.run(
        [str(OCR), str(source), "2.5"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        destination.write_text(result.stdout)
    return filename, result.returncode == 0, result.stderr.strip()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((EXTRACTION / "song-catalog.json").read_text())
    files = sorted({
        str(song["selected_source"])
        for song in catalog["songs"]
        if song["existing_id"] is None and str(song["selected_source"]).lower().endswith(".pdf")
    }, key=str.casefold)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(extract, filename): filename for filename in files}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            filename, ok, detail = future.result()
            print(f"[{index:03}/{len(files)}] {'ok' if ok else 'ERROR'} {filename} {detail}", flush=True)


if __name__ == "__main__":
    main()
