#!/usr/bin/env python3
"""Export every song in index.html to songs/<slug>.md and write the SONGS.md index.

index.html stays the source of truth for titles, lyrics, group and order. Metadata
(sources, references, credits, key, text status) comes from, in order of preference:
  1. correction files in $KK_CORRECTIONS (one <id>.json per song, from a lyrics sync)
  2. the extraction catalog at $KK_CATALOG, only when set (maps score files to songs;
     each entry needs an "existing_id")
  3. the front matter of the existing songs/*.md file for that id
so re-running after a plain lyric edit keeps what earlier syncs recorded.

Usage: python3 tools/export_songs.py
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SONGS = ROOT / "songs"
LISTING = ROOT / "SONGS.md"
CORRECTIONS = Path(os.environ.get("KK_CORRECTIONS", "/nonexistent"))
CATALOG = Path(os.environ["KK_CATALOG"]) if os.environ.get("KK_CATALOG") else None
FIRST_SHEET_ID = 42  # ids below this were entered by hand before the sheet-music import

ITEM_RE = re.compile(r'<div class="item" data-g="([^"]+)" data-i="(\d+)" data-n="[^"]*"><span>[^<]+</span>(.*?)</div>')
SECTION_RE = re.compile(r'<section class="song" id="s(\d+)"><h1>(.*?)</h1><div class="lyrics">(.*?)</div></section>', re.S)
FIELDS = ["id", "title", "group", "key", "language", "lyricist", "composer", "translator",
          "text_status", "needs_proofreading", "sources", "references"]
STATUS_TEXT = {
    "curated": "hand-entered",
    "online-verified": "checked against online text",
    "score-transcribed": "transcribed from score",
    "needs-review": "needs review",
    "skipped-copyright": "lyrics missing",
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("þ", "th").replace("ð", "d").replace("æ", "ae").replace("ø", "o")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def read_front_matter(path: Path) -> dict:
    meta = {}
    text = path.read_text()
    if not text.startswith("---\n"):
        return meta
    for line in text[4:text.find("\n---\n", 4)].splitlines():
        key, _, value = line.partition(": ")
        try:
            meta[key] = json.loads(value)
        except json.JSONDecodeError:
            pass
    return meta


def main() -> None:
    page = INDEX.read_text()
    items = [(g, int(i)) for g, i, _ in ITEM_RE.findall(page)]
    sections = {int(i): (html.unescape(t), html.unescape(re.sub(r"<br>", "\n", l)).strip())
                for i, t, l in SECTION_RE.findall(page)}

    previous = {}
    if SONGS.exists():
        for path in SONGS.glob("*.md"):
            meta = read_front_matter(path)
            if "id" in meta:
                previous[int(meta["id"])] = meta

    catalog_sources: dict[int, list[str]] = {}
    if CATALOG and CATALOG.exists():
        by_title = {unicodedata.normalize("NFC", t).casefold(): i for i, (t, _) in sections.items()}
        for song in json.loads(CATALOG.read_text())["songs"]:
            sid = song.get("existing_id")
            if sid is None:
                sid = by_title.get(unicodedata.normalize("NFC", song["title"]).casefold())
            if sid is not None:
                catalog_sources.setdefault(int(sid), []).extend(
                    "sheetmusic/" + unicodedata.normalize("NFC", f) for f in song["sources"])

    SONGS.mkdir(exist_ok=True)
    written = set()
    rows = []
    for group, sid in items:
        title, lyrics = sections[sid]
        meta = dict(previous.get(sid, {}))
        correction = CORRECTIONS / f"{sid}.json"
        if correction.exists():
            c = json.loads(correction.read_text())
            meta.update({
                "language": c.get("language", ""),
                "lyricist": c.get("lyricist", ""),
                "composer": c.get("composer", ""),
                "translator": c.get("translator", ""),
                "text_status": c["status"],
                "needs_proofreading": bool(c.get("needs_second_pass")) or c["status"] != "online-verified",
                "references": c.get("urls", []),
            })
        if sid in catalog_sources:
            meta["sources"] = sorted(set(catalog_sources[sid]))
        meta.setdefault("text_status", "curated" if sid < FIRST_SHEET_ID else "score-transcribed")
        meta.setdefault("needs_proofreading", meta["text_status"] not in ("curated", "online-verified"))
        meta.setdefault("sources", [])
        meta.setdefault("references", [])
        for key in ("key", "language", "lyricist", "composer", "translator"):
            meta.setdefault(key, "")
        meta.update({"id": sid, "title": title, "group": group})

        name = fold(title) + ".md"
        if name in written:
            raise SystemExit(f"two songs map to {name}")
        written.add(name)
        front = "\n".join(f"{k}: {json.dumps(meta[k], ensure_ascii=False)}" for k in FIELDS)
        # Two trailing spaces make a Markdown hard line break, so stanzas render as written.
        body = "\n".join(line + "  " if line.strip() else "" for line in lyrics.split("\n"))
        (SONGS / name).write_text(f"---\n{front}\n---\n\n# {title}\n\n{body}\n")
        rows.append((group, title, name, meta))

    for path in SONGS.glob("*.md"):
        if path.name not in written:
            path.unlink()

    def cell(text: str) -> str:
        return text.replace("|", "\\|")

    def source_cell(meta: dict) -> str:
        if not meta["sources"]:
            return "app only"
        return "<br>".join(f"`{cell(s)}`" for s in meta["sources"])

    def ref_cell(meta: dict) -> str:
        refs = meta["references"]
        if not refs:
            return ""
        host = re.sub(r"^https?://(www\.)?", "", refs[0]).split("/")[0]
        more = f" +{len(refs) - 1}" if len(refs) > 1 else ""
        return f"[{host}]({refs[0]}){more}"

    counts: dict[str, int] = {}
    for *_, meta in rows:
        counts[meta["text_status"]] = counts.get(meta["text_status"], 0) + 1
    lines = [
        "# Song index",
        "",
        "Generated by `tools/export_songs.py` from `index.html`. Each song's lyrics are in `songs/`.",
        "Score paths point into the local `sheetmusic/` folder, which is not committed.",
        "",
        f"**{len(rows)} songs.** " + ", ".join(
            f"{STATUS_TEXT.get(k, k)}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) + ".",
        "",
        "| # | Song | Group | Key | Text | Score file(s) | Online text |",
        "|---:|---|---|---|---|---|---|",
    ]
    for n, (group, title, name, meta) in enumerate(rows, 1):
        status = STATUS_TEXT.get(meta["text_status"], meta["text_status"])
        if meta["needs_proofreading"] and meta["text_status"] not in ("needs-review", "skipped-copyright"):
            status += " · proofread"
        lines.append(f"| {n} | [{cell(title)}](songs/{name}) | {group} | {cell(meta['key'])} | {status} | {source_cell(meta)} | {ref_cell(meta)} |")
    LISTING.write_text("\n".join(lines) + "\n")
    print(f"wrote {len(rows)} songs to {SONGS.relative_to(ROOT)}/ and {LISTING.name}")


if __name__ == "__main__":
    main()
