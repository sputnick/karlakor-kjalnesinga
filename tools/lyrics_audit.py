#!/usr/bin/env python3
"""Cross-song audit of index.html (or of the correction files before merging).

KK_WORK=<workdir> python3 tools/lyrics_audit.py         -> audits index.html
KK_WORK=<workdir> python3 tools/lyrics_audit.py --corr  -> audits $KK_WORK/corrections/*.json against the page
"""
import html, json, os, re, sys, unicodedata
from collections import defaultdict
from itertools import combinations
from pathlib import Path

# Work directory holding corrections/, decisions.json and reports (outside the repo).
W = Path(os.environ.get("KK_WORK", "/private/tmp/kk-lyrics-work"))
REPO = Path(__file__).resolve().parents[1]
SECTION_RE = re.compile(r'<section class="song" id="s(\d+)"><h1>(.*?)</h1><div class="lyrics">(.*?)</div></section>', re.S)
ITEM_RE = re.compile(r'<div class="item" data-g="([^"]+)" data-i="(\d+)" data-n="([^"]*)"><span>[^<]+</span>(.*?)</div>')
JUNK = set("õỗỖğĞôÔộỘỡờớợịĩìîùủũưứừựỳỹđĐőűñ") | set("бгдежзийклмнпрстуфхцчшщъыьэюяБГДЕЖЗИЙКЛМНПРСТУФХЦЧШЩЪЫЬЭЮЯ")
CREDIT = re.compile(r"(?im)^.*(?:\b(?:ljóð|texti|lag|útsetning|útsett|raddsett|raddsetning|þýðing|þýddi|words and music|music by|lyrics by|copyright)\b\s*(?:/\s*\w+\s*)?:|\b(?:úts|radds|arr)\.)")
THORN = re.compile(r"\b[Pp](?:ú|ið|að|ví|ar|ér|eir|ess|ig|egar|ín|inn|ína|essi|etta|ó)\b")


def fold(t):
    t = unicodedata.normalize("NFKD", t.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("þ", "th").replace("ð", "d").replace("æ", "ae").replace("ø", "o")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


LANG_EXTRA = {
    "is": "áéíóúýþðæöÁÉÍÓÚÝÞÐÆÖ",
    "sv": "åäöÅÄÖéÉ", "da": "æøåÆØÅ", "no": "æøåÆØÅ", "de": "äöüßÄÖÜ",
    "hu": "áéíóöőúüűÁÉÍÓÖŐÚÜŰ", "it": "àèéìíòóùÀÈÉÌÒÙ", "es": "áéíñóúüÁÉÍÑÓÚÜ¿¡",
    "la": "", "en": "éè", "kl": "",
}
PUNCT = set("–—‘’“”„«»…·")


def stray(text, lang):
    ok = set(LANG_EXTRA.get((lang or "is")[:2], LANG_EXTRA["is"])) | PUNCT
    return sorted({c for c in text if ord(c) > 126 and c not in ok})


def load_page():
    s = (REPO / "index.html").read_text()
    songs = {int(i): {"title": html.unescape(t), "lyrics": html.unescape(re.sub(r"<br>", "\n", l))}
             for i, t, l in SECTION_RE.findall(s)}
    return s, songs


def main():
    s, songs = load_page()
    if "--corr" in sys.argv:
        for f in sorted((W / "corrections").glob("*.json"), key=lambda p: int(p.stem)):
            c = json.loads(f.read_text())
            songs[c["id"]] = {"title": c["title"], "lyrics": c["lyrics"], "lang": c.get("language", "")}
    else:
        for f in (W / "corrections").glob("*.json"):
            c = json.loads(f.read_text())
            if c["id"] in songs:
                songs[c["id"]]["lang"] = c.get("language", "")
    problems = defaultdict(list)
    # structure
    items = ITEM_RE.findall(s)
    if "--corr" not in sys.argv:
        ids_i = [int(i) for _, i, _, _ in items]
        ids_s = [int(i) for i, *_ in SECTION_RE.findall(s)]
        print("items", len(items), "sections", len(ids_s), "same order", ids_i == ids_s,
              "unique ids", len(set(ids_s)) == len(ids_s))
    titles = defaultdict(list)
    for i, d in songs.items():
        titles[fold(d["title"])].append(i)
        t = d["lyrics"]
        if not t.strip():
            problems[i].append("empty")
        if unicodedata.normalize("NFC", t) != t or unicodedata.normalize("NFC", d["title"]) != d["title"]:
            problems[i].append("not NFC")
        lang = d.get("lang") or "is"
        j = stray(t + d["title"], lang)
        if j:
            problems[i].append(f"unexpected chars for {lang}: {j}")
        if CREDIT.search(t):
            problems[i].append("credit line: " + CREDIT.search(t).group(0)[:60])
        m = THORN.findall(t)
        if m:
            problems[i].append(f"p-for-þ {m[:5]}")
    for k, v in titles.items():
        if len(v) > 1:
            problems[v[0]].append(f"duplicate title with {v[1:]}")
    # cross-song line overlap
    linesets = {i: {fold(l) for l in d["lyrics"].split("\n") if len(fold(l)) >= 18} for i, d in songs.items()}
    inv = defaultdict(set)
    for i, ls in linesets.items():
        for l in ls:
            inv[l].add(i)
    pair = defaultdict(int)
    for l, ids in inv.items():
        if 1 < len(ids) < 6:
            for a, b in combinations(sorted(ids), 2):
                pair[(a, b)] += 1
    overlaps = []
    for (a, b), n in sorted(pair.items(), key=lambda x: -x[1]):
        small = min(len(linesets[a]), len(linesets[b])) or 1
        if n >= 3 or n / small >= 0.4:
            overlaps.append((a, b, n, round(n / small, 2)))
    for i in sorted(problems):
        print(f"[{i}] {songs[i]['title']}: " + " | ".join(problems[i]))
    print(f"\n{len(problems)} songs with problems")
    print("\nCross-song line overlaps (a, b, shared lines, share of smaller):")
    for a, b, n, r in overlaps:
        print(f"  {a} {songs[a]['title']!r} <-> {b} {songs[b]['title']!r}: {n} lines ({r})")


if __name__ == "__main__":
    main()
