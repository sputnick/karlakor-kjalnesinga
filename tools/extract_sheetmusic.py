#!/usr/bin/env python3
"""Extract searchable text from every score, adding OCR for image-only PDFs."""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sheetmusic"
OUTPUT = Path("/private/tmp/kk-sheetmusic-extraction")
EMBEDDED = OUTPUT / "embedded"
OCR = OUTPUT / "ocr"
ALPHA_THRESHOLD = 300


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def language_for(name: str) -> str:
    folded = name.casefold()
    if re.search(r"abend|rhein|könig|warum|sänger|jodler|langkofel", folded):
        return "deu+isl+eng"
    if re.search(r"capri|catarina|funiculi|sole mio|caruso|nella fantasia|bianco cigno", folded):
        return "ita+isl+eng"
    if "besame" in folded:
        return "spa+isl+eng"
    if re.search(r"bröllop|faageln|magyarokhoz", folded):
        return "swe+dan+nor+isl+eng"
    return "isl+eng"


def page_count(pdf: Path) -> int:
    result = run(["pdfinfo", str(pdf)])
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else 1


def ocr_pdf(pdf: Path, pages: int) -> tuple[str, list[str]]:
    chunks: list[str] = []
    errors: list[str] = []
    language = language_for(pdf.name)
    with tempfile.TemporaryDirectory(prefix="kk-score-ocr-", dir="/private/tmp") as temp:
        temp_path = Path(temp)
        for page in range(1, pages + 1):
            prefix = temp_path / f"page-{page}"
            render = run([
                "pdftoppm", "-f", str(page), "-l", str(page), "-r", "300",
                "-gray", "-singlefile", "-png", str(pdf), str(prefix),
            ])
            if render.returncode:
                errors.append(f"render page {page}: {render.stderr.strip()}")
                chunks.append("")
                continue
            image = prefix.with_suffix(".png")
            result = run([
                "tesseract", str(image), "stdout", "-l", language, "--psm", "6",
                "-c", "preserve_interword_spaces=1",
            ])
            if result.returncode:
                errors.append(f"ocr page {page}: {result.stderr.strip()}")
            chunks.append(result.stdout.strip())
    return "\n\f\n".join(chunks).strip() + "\n", errors


def extract_pdf(pdf: Path) -> dict[str, object]:
    embedded_path = EMBEDDED / f"{pdf.name}.txt"
    result = run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), str(embedded_path)])
    embedded = embedded_path.read_text(errors="replace") if embedded_path.exists() else ""
    alpha = sum(character.isalpha() for character in embedded)
    pages = page_count(pdf)
    errors = [result.stderr.strip()] if result.returncode and result.stderr.strip() else []
    method = "embedded"
    selected_path = embedded_path
    force_ocr = os.environ.get("KK_OCR_ALL") == "1"
    if alpha < ALPHA_THRESHOLD or force_ocr:
        method = "ocr"
        selected_path = OCR / f"{pdf.name}.txt"
        if selected_path.exists() and os.environ.get("KK_REUSE_OCR", "1") == "1":
            text = selected_path.read_text(errors="replace")
        else:
            text, ocr_errors = ocr_pdf(pdf, pages)
            selected_path.write_text(text)
            errors.extend(ocr_errors)
    return {
        "file": pdf.name,
        "format": "pdf",
        "pages": pages,
        "embedded_alpha": alpha,
        "method": method,
        "embedded_path": str(embedded_path),
        "ocr_path": str(OCR / f"{pdf.name}.txt") if (OCR / f"{pdf.name}.txt").exists() else None,
        "text_path": str(selected_path),
        "text_alpha": sum(character.isalpha() for character in selected_path.read_text(errors="replace")),
        "errors": errors,
    }


def extract_document(document: Path) -> dict[str, object]:
    output_path = EMBEDDED / f"{document.name}.txt"
    result = run(["textutil", "-convert", "txt", "-stdout", str(document)])
    output_path.write_text(result.stdout)
    return {
        "file": document.name,
        "format": document.suffix.lower().lstrip("."),
        "pages": None,
        "embedded_alpha": sum(character.isalpha() for character in result.stdout),
        "method": "textutil",
        "text_path": str(output_path),
        "text_alpha": sum(character.isalpha() for character in result.stdout),
        "errors": [result.stderr.strip()] if result.returncode and result.stderr.strip() else [],
    }


def main() -> None:
    EMBEDDED.mkdir(parents=True, exist_ok=True)
    OCR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(SOURCE.glob("*.[pP][dD][fF]"), key=lambda path: path.name.casefold())
    records: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        futures = {pool.submit(extract_pdf, pdf): pdf for pdf in pdfs}
        complete = 0
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            records.append(record)
            complete += 1
            print(
                f"[{complete:03}/{len(pdfs)}] {record['method']:8} "
                f"{record['text_alpha']:6} alpha  {record['file']}",
                flush=True,
            )
    for document in sorted(list(SOURCE.glob("*.doc")) + list(SOURCE.glob("*.docx"))):
        records.append(extract_document(document))
    records.sort(key=lambda record: str(record["file"]).casefold())
    index_path = OUTPUT / "extraction-index.json"
    index_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {index_path} with {len(records)} source files", flush=True)


if __name__ == "__main__":
    main()
