#!/usr/bin/env python3
"""Merge subagent correction files into index.html.

Usage: KK_WORK=<workdir> python3 tools/lyrics_merge.py [--dry-run]
Reads   $KK_WORK/corrections/<id>.json   (one per song id >= 42)
        $KK_WORK/decisions.json          ({"remove": {id: reason}, "no_extra": [ids], "title": {id: title}})
Writes  index.html and $KK_WORK/merge-report.json
"""
import html, json, os, re, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Work directory holding corrections/, decisions.json and reports (outside the repo).
W = Path(os.environ.get("KK_WORK", "/private/tmp/kk-lyrics-work"))
REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "index.html"
FIRST_NEW = 42
PLACEHOLDER = "(Texti vantar – sjá nótur.)"

ITEM_RE = re.compile(r'<div class="item" data-g="([^"]+)" data-i="(\d+)" data-n="[^"]*"><span>[^<]+</span>(.*?)</div>')
SECTION_RE = re.compile(r'<section class="song" id="s(\d+)"><h1>(.*?)</h1><div class="lyrics">(.*?)</div></section>', re.S)


def fold(t):
    t = unicodedata.normalize("NFKD", t.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("þ", "th").replace("ð", "d").replace("æ", "ae").replace("ø", "o")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def to_html(text):
    return html.escape(text, quote=False).replace("\n", "<br>")


def from_html(value):
    return html.unescape(re.sub(r"(?i)<br\s*/?>", "\n", value))


def main():
    dry = "--dry-run" in sys.argv
    src = INDEX.read_text()
    items = [(g, int(i), html.unescape(t)) for g, i, t in ITEM_RE.findall(src)]
    secs = {int(i): (html.unescape(t), from_html(l)) for i, t, l in SECTION_RE.findall(src)}
    assert len(items) == len(secs), (len(items), len(secs))
    dec = json.loads((W / "decisions.json").read_text()) if (W / "decisions.json").exists() else {}
    remove = {int(k): v for k, v in dec.get("remove", {}).items()}
    no_extra = {int(k) for k in dec.get("no_extra", [])}
    title_override = {int(k): v for k, v in dec.get("title", {}).items()}

    songs = []  # dicts: id, group, title, lyrics
    report = {"updated": [], "missing_correction": [], "removed": [], "added": []}
    extras = []
    for g, i, t in items:
        title, lyrics = secs[i]
        if i in remove:
            report["removed"].append({"id": i, "title": title, "reason": remove[i]})
            continue
        if i >= FIRST_NEW:
            f = W / "corrections" / f"{i}.json"
            if f.exists():
                c = json.loads(f.read_text())
                assert c["id"] == i, f
                title = unicodedata.normalize("NFC", c["title"].strip())
                lyrics = unicodedata.normalize("NFC", c["lyrics"].strip())
                if c["status"] == "skipped-copyright" or not lyrics:
                    lyrics = PLACEHOLDER
                report["updated"].append({"id": i, "title": title, "status": c["status"]})
                if i not in no_extra:
                    for e in c.get("extra_songs") or []:
                        extras.append((i, e))
            else:
                report["missing_correction"].append(i)
        title = title_override.get(i, title)
        songs.append({"id": i, "group": g, "title": title, "lyrics": lyrics})

    next_id = max(max(secs), 0) + 1
    for parent, e in extras:
        songs.append({"id": next_id, "group": "extra",
                      "title": unicodedata.normalize("NFC", e["title"].strip()),
                      "lyrics": unicodedata.normalize("NFC", e["lyrics"].strip())})
        report["added"].append({"id": next_id, "title": e["title"], "split_from": parent})
        next_id += 1

    # Keep concert + curated originals in their existing order; sort the sheet-music block by folded title.
    head = [s for s in songs if s["id"] < FIRST_NEW]
    tail = sorted((s for s in songs if s["id"] >= FIRST_NEW), key=lambda s: (fold(s["title"]), s["id"]))
    songs = head + tail

    seen = {}
    for s in songs:
        k = fold(s["title"])
        if k in seen:
            raise SystemExit(f"duplicate normalized title {s['title']!r} ids {seen[k]} and {s['id']}")
        seen[k] = s["id"]
        if not s["lyrics"].strip():
            raise SystemExit(f"empty lyrics for id {s['id']}")

    item_html = "".join(
        '<div class="item" data-g="{g}" data-i="{i}" data-n="{n}"><span>{lab}</span>{t}</div>'.format(
            g=s["group"], i=s["id"], n=html.escape(s["title"].casefold(), quote=True),
            lab="Concert" if s["group"] == "concert" else "Extra", t=html.escape(s["title"], quote=False))
        for s in songs)
    sec_html = "".join(
        '<section class="song" id="s{i}"><h1>{t}</h1><div class="lyrics">{l}</div></section>'.format(
            i=s["id"], t=html.escape(s["title"], quote=False), l=to_html(s["lyrics"]))
        for s in songs)

    out, a = re.subn(r'(<div id=list><div id=none>No matches</div>).*?(</div></div>\n<div id=deck>)',
                     lambda m: m.group(1) + item_html + m.group(2), src, count=1, flags=re.S)
    out, b = re.subn(r'(<div id=deck>).*?(</div>\n<script>)',
                     lambda m: m.group(1) + sec_html + m.group(2), out, count=1, flags=re.S)
    stamp = datetime.now(timezone.utc).strftime("%d.%m %H:%M")  # UTC == Icelandic time
    out, c = re.subn(r"(<span id=ver [^>]*>)[^<]*(</span>)", lambda m: m.group(1) + stamp + m.group(2), out, count=1)
    assert (a, b, c) == (1, 1, 1), (a, b, c)
    assert len(ITEM_RE.findall(out)) == len(SECTION_RE.findall(out)) == len(songs)

    report["final_count"] = len(songs)
    report["stamp"] = stamp
    (W / "merge-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}, ensure_ascii=False))
    if report["missing_correction"]:
        print("missing corrections:", report["missing_correction"])
    if not dry:
        INDEX.write_text(out)
        print("wrote", INDEX)


if __name__ == "__main__":
    main()
