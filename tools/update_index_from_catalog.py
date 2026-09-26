#!/usr/bin/env python3
"""Merge the canonical extracted song catalog into the single-file lyrics app."""

from __future__ import annotations

from datetime import datetime
import html
import json
import os
from pathlib import Path
import re

import build_song_catalog as catalog_tools


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CATALOG = Path("/private/tmp/kk-sheetmusic-extraction/song-catalog.json")


ITEM_RE = re.compile(
    r'<div class="item" data-g="(?P<group>[^"]+)" data-i="(?P<id>\d+)" '
    r'data-n="(?P<search>[^"]*)"><span>(?P<label>[^<]+)</span>(?P<title>.*?)</div>',
    re.DOTALL,
)
SECTION_RE = re.compile(
    r'<section class="song" id="s(?P<id>\d+)"><h1>(?P<title>.*?)</h1>'
    r'<div class="lyrics">(?P<lyrics>.*?)</div></section>',
    re.DOTALL,
)


def lyrics_from_html(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def lyrics_to_html(value: str) -> str:
    return html.escape(value, quote=False).replace("\n", "<br>")


def main() -> None:
    base_index = Path(os.environ.get("KK_BASE_INDEX", INDEX))
    source = base_index.read_text()
    if "<title>" not in source:
        source = source.replace(
            "\n<style>",
            '<title>Kjalnesingar · Lyrics</title><link rel=icon href="data:,">\n<style>',
            1,
        )
    items = [{
        "id": match.group("id"),
        "group": match.group("group"),
        "title": html.unescape(match.group("title")),
    } for match in ITEM_RE.finditer(source)]
    sections = {match.group("id"): {
        "id": match.group("id"),
        "title": html.unescape(match.group("title")),
        "lyrics": lyrics_from_html(match.group("lyrics")),
    } for match in SECTION_RE.finditer(source)}
    if len(items) != 42 or len(sections) != 42:
        raise SystemExit(f"expected 42 existing items and sections, found {len(items)} and {len(sections)}")

    songs: list[dict[str, str]] = []
    for item in items:
        section = sections[item["id"]]
        key = catalog_tools.title_key(section["title"])
        title = catalog_tools.CANONICAL_TITLES.get(key, section["title"])
        lyrics = section["lyrics"]
        if key == catalog_tools.title_key("Hlíðin mín fríða"):
            lyrics = lyrics.split("Fyrst ég annars hjarta hræri", 1)[0].strip()
        if key == catalog_tools.title_key("Enn syngur vornóttin"):
            lyrics = lyrics.split("Drykkjuvísa (Heillaská)", 1)[0].strip()
        songs.append({"id": item["id"], "group": item["group"], "title": title, "lyrics": lyrics})

    catalog = json.loads(CATALOG.read_text())
    additions = [song for song in catalog["songs"] if song["existing_id"] is None]
    next_id = max(int(song["id"]) for song in songs) + 1
    for addition in additions:
        lyrics = str(addition["lyrics"]).strip()
        if not lyrics:
            raise SystemExit(f"empty extracted lyrics for {addition['title']}")
        songs.append({
            "id": str(next_id),
            "group": "extra",
            "title": str(addition["title"]),
            "lyrics": lyrics,
        })
        next_id += 1

    keys: dict[str, str] = {}
    for song in songs:
        key = catalog_tools.title_key(song["title"])
        if key in keys:
            raise SystemExit(f"duplicate title: {keys[key]!r} and {song['title']!r}")
        keys[key] = song["title"]

    item_html = "".join(
        '<div class="item" data-g="{group}" data-i="{id}" data-n="{search}">'
        '<span>{label}</span>{title}</div>'.format(
            group=html.escape(song["group"], quote=True),
            id=song["id"],
            search=html.escape(song["title"].casefold(), quote=True),
            label="Concert" if song["group"] == "concert" else "Extra",
            title=html.escape(song["title"], quote=False),
        )
        for song in songs
    )
    section_html = "".join(
        '<section class="song" id="s{id}"><h1>{title}</h1><div class="lyrics">{lyrics}</div></section>'.format(
            id=song["id"],
            title=html.escape(song["title"], quote=False),
            lyrics=lyrics_to_html(song["lyrics"]),
        )
        for song in songs
    )

    panel_pattern = re.compile(
        r'(<div id=list><div id=none>No matches</div>).*?(</div></div>\n<div id=deck>)',
        re.DOTALL,
    )
    source, panel_replacements = panel_pattern.subn(r"\1" + item_html + r"\2", source, count=1)
    deck_pattern = re.compile(r'(<div id=deck>).*?(</div>\n<script>)', re.DOTALL)
    source, deck_replacements = deck_pattern.subn(r"\1" + section_html + r"\2", source, count=1)
    stamp = datetime.now().strftime("%d.%m %H:%M")
    source, version_replacements = re.subn(
        r"(<span id=ver [^>]*>)[^<]*(</span>)",
        rf"\g<1>{stamp}\2",
        source,
        count=1,
    )
    if (panel_replacements, deck_replacements, version_replacements) != (1, 1, 1):
        raise SystemExit("failed to locate one or more index.html replacement regions")

    rendered_items = ITEM_RE.findall(source)
    rendered_sections = SECTION_RE.findall(source)
    if len(rendered_items) != len(songs) or len(rendered_sections) != len(songs):
        raise SystemExit("rendered item/section counts do not match the merged song count")

    if base_index == INDEX:
        Path("/private/tmp/kk-index-before.html").write_text(INDEX.read_text())
    INDEX.write_text(source)
    print(f"Updated {INDEX} with {len(songs)} songs ({len(additions)} additions); version {stamp}")


if __name__ == "__main__":
    main()
