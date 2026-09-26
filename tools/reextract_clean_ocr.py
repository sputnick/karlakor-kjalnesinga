#!/usr/bin/env python3
"""OCR score lyrics with staff-line removal and language-specific recognition."""

from __future__ import annotations

import concurrent.futures
import csv
import io
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile

import cv2


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sheetmusic"
OUTPUT = Path("/private/tmp/kk-sheetmusic-extraction/cleanocr")
INDEX = Path("/private/tmp/kk-sheetmusic-extraction/cleanocr-index.json")


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def language_for(name: str) -> str:
    folded = name.casefold()
    patterns = [
        (r"magyarokhoz", "hun"),
        (r"abend|rhein|könig|warum|sänger|jodler|langkofel", "deu"),
        (r"capri|catarina|funiculi|sole mio|caruso|nella fantasia|bianco cigno", "ita"),
        (r"besame", "spa"),
        (r"bröllop|faageln|liljekonvalje", "swe"),
        (
            r"no woman|my way|release me|wonder of you|when i|learn me right|morning has broken|"
            r"green green|weep.mine.eyes|come again|lady fish|beginning to look|christmas song|"
            r"michelle|delilah|hallelujah",
            "eng",
        ),
    ]
    for pattern, language in patterns:
        if re.search(pattern, folded):
            return language
    return "isl"


def page_count(pdf: Path) -> int:
    result = run(["pdfinfo", str(pdf)])
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else 1


def staff_bounds(binary, width: int) -> tuple[int, int] | None:
    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(80, width // 18), 1)),
    )
    components = cv2.connectedComponentsWithStats(horizontal, 8)[2]
    centers = [
        y + height // 2
        for x, y, component_width, height, area in components[1:]
        if component_width >= width * 0.28 and height <= 18 and area >= component_width
    ]
    if len(centers) < 5:
        return None
    return min(centers), max(centers)


def remove_staff_lines(image):
    binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(60, image.shape[1] // 35), 1)),
    )
    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(50, image.shape[0] // 45))),
    )
    mask = cv2.dilate(
        cv2.bitwise_or(horizontal, vertical),
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)),
    )
    cleaned = image.copy()
    cleaned[mask > 0] = 255
    return cleaned, staff_bounds(binary, image.shape[1])


def token_is_text(value: str) -> bool:
    return bool(re.search(r"[^\W\d_]", value, re.UNICODE)) or value in {"-", "–", "—"}


def extract_rows(tsv: str, bounds: tuple[int, int] | None) -> list[str]:
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        value = row.get("text", "").strip()
        if not value:
            continue
        try:
            confidence = float(row["conf"])
            left, top = int(row["left"]), int(row["top"])
            width, height = int(row["width"]), int(row["height"])
        except (KeyError, ValueError):
            continue
        if confidence < 25 or not token_is_text(value):
            continue
        center = top + height / 2
        if bounds and not bounds[0] - 20 <= center <= bounds[1] + 60:
            continue
        words.append({
            "text": value, "confidence": confidence, "left": left,
            "top": top, "width": width, "height": height, "center": center,
        })

    rows: list[list[dict[str, object]]] = []
    for word in sorted(words, key=lambda item: (float(item["center"]), int(item["left"]))):
        best = None
        best_distance = float("inf")
        for index, existing in enumerate(rows):
            anchor = statistics.median(float(item["center"]) for item in existing)
            median_height = statistics.median(int(item["height"]) for item in existing)
            distance = abs(float(word["center"]) - anchor)
            if distance <= max(10, median_height * 0.55) and distance < best_distance:
                best, best_distance = index, distance
        if best is None:
            rows.append([word])
        else:
            rows[best].append(word)

    output = []
    for row in sorted(rows, key=lambda items: statistics.median(float(item["center"]) for item in items)):
        alpha = [item for item in row if re.search(r"[^\W\d_]", str(item["text"]), re.UNICODE)]
        if not alpha:
            continue
        strong = [item for item in alpha if float(item["confidence"]) >= 60]
        if not strong:
            continue
        median_height = statistics.median(int(item["height"]) for item in strong)
        kept = [
            item for item in row
            if int(item["height"]) >= median_height * 0.5
            and (float(item["confidence"]) >= 45 or str(item["text"]) in {"-", "–", "—"})
        ]
        real_words = [item for item in kept if re.search(r"[^\W\d_]", str(item["text"]), re.UNICODE)]
        if not real_words:
            continue
        mean_confidence = sum(float(item["confidence"]) for item in real_words) / len(real_words)
        letter_count = sum(sum(character.isalpha() for character in str(item["text"])) for item in real_words)
        if len(real_words) == 1:
            if mean_confidence < 82 or letter_count < 4:
                continue
        elif mean_confidence < 68 or letter_count < 5:
            continue
        if len(real_words) >= 4 and mean_confidence >= 78:
            for item in row:
                if str(item["text"]) == "1" and item not in kept:
                    item["text"] = "í"
                    kept.append(item)
        text = " ".join(str(item["text"]) for item in sorted(kept, key=lambda item: int(item["left"])))
        output.append(text)
    return output


def extract_page(pdf: Path, page: int, language: str, temp: Path) -> tuple[str, list[str]]:
    prefix = temp / f"page-{page}"
    render = run([
        "pdftoppm", "-f", str(page), "-l", str(page), "-r", "300",
        "-gray", "-singlefile", "-png", str(pdf), str(prefix),
    ])
    errors = [render.stderr.strip()] if render.returncode and render.stderr.strip() else []
    image_path = prefix.with_suffix(".png")
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return "", errors + [f"page {page}: render did not produce an image"]
    cleaned, bounds = remove_staff_lines(image)
    clean_path = temp / f"page-{page}-clean.png"
    cv2.imwrite(str(clean_path), cleaned)
    result = run([
        "tesseract", str(clean_path), "stdout", "-l", language, "--psm", "11", "tsv",
    ])
    if result.returncode:
        errors.append(f"page {page}: {result.stderr.strip()}")
    return "\n".join(extract_rows(result.stdout, bounds)), errors


def extract_pdf(pdf: Path) -> dict[str, object]:
    language = language_for(pdf.name)
    pages = page_count(pdf)
    chunks, errors = [], []
    with tempfile.TemporaryDirectory(prefix="kk-clean-ocr-", dir="/private/tmp") as directory:
        temp = Path(directory)
        for page in range(1, pages + 1):
            text, page_errors = extract_page(pdf, page, language, temp)
            chunks.append(text)
            errors.extend(page_errors)
    output_path = OUTPUT / f"{pdf.name}.txt"
    output_path.write_text("\n\f\n".join(chunks).strip() + "\n")
    return {
        "file": pdf.name,
        "pages": pages,
        "language": language,
        "alpha": sum(character.isalpha() for character in output_path.read_text()),
        "errors": errors,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    names = set(os.environ.get("KK_FILES", "").split("\n")) - {""}
    pdfs = sorted(SOURCE.glob("*.[pP][dD][fF]"), key=lambda path: path.name.casefold())
    if names:
        pdfs = [pdf for pdf in pdfs if pdf.name in names]
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        futures = {pool.submit(extract_pdf, pdf): pdf for pdf in pdfs}
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            record = future.result()
            records.append(record)
            print(
                f"[{count:03}/{len(pdfs)}] {record['language']:3} {record['alpha']:6} alpha  {record['file']}",
                flush=True,
            )
    records.sort(key=lambda record: str(record["file"]).casefold())
    INDEX.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {INDEX} with {len(records)} files", flush=True)


if __name__ == "__main__":
    main()
