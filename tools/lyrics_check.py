#!/usr/bin/env python3
"""Validate one or more correction files: python3 tools/lyrics_check.py <workdir>/corrections/123.json ...

Prints PASS or a list of problems per file. Exit code 1 if any file fails.
"""
import json, re, sys, unicodedata
from collections import Counter

REQUIRED = ["id", "title", "language", "lyrics", "status", "urls", "notes"]
STATUSES = {"online-verified", "score-transcribed", "needs-review", "skipped-copyright"}
# Characters that never occur in correct Icelandic but are typical OCR confusions.
OCR_JUNK = set("õỗỖğĞôÔộỘỡờớợịĩìîùủũưứừựỳỹđĐőűñ") | set("бгдежзийклмнпрстуфхцчшщъыьэюяБГДЕЖЗИЙКЛМНПРСТУФХЦЧШЩЪЫЬЭЮЯаеорсух")
ICELANDIC_ALLOWED_EXTRA = set("áéíóúýþðæöÁÉÍÓÚÝÞÐÆÖ")
CREDIT = re.compile(r"(?i)\b(ljóð|lag|texti|útsetn|útsett|úts\.|radds|raddsett|raddsetn|þýð|þýðing|arr\.|arranged|words and music|music by|lyrics by|composer|copyright|©|ttbb|ttb|tenór [12i]|bassi [12i]|allegro|andante|moderato|lento|rit\.|a tempo|cresc|dim\.|unis|sóló:|solo:|intro|coda|d\.c\.|d\.s\.|fine)\b")


def check(path):
    problems = []
    try:
        d = json.load(open(path))
    except Exception as e:
        return [f"invalid JSON: {e}"]
    for k in REQUIRED:
        if k not in d:
            problems.append(f"missing field {k}")
    if problems:
        return problems
    if d["status"] not in STATUSES:
        problems.append(f"status must be one of {sorted(STATUSES)}")
    if d["status"] == "online-verified" and not d["urls"]:
        problems.append("online-verified requires at least one URL")
    text = d["lyrics"]
    if d["status"] == "skipped-copyright":
        return problems
    if not text.strip():
        problems.append("empty lyrics")
    for field in ("title", "lyrics"):
        v = d[field]
        if unicodedata.normalize("NFC", v) != v:
            problems.append(f"{field} is not NFC-normalized")
        junk = sorted({c for c in v if c in OCR_JUNK})
        if junk and d["language"].lower().startswith(("is", "ice")):
            problems.append(f"{field} has OCR-junk characters {junk}")
    if "\n\n\n" in text:
        problems.append("more than one blank line between stanzas")
    if text != text.strip():
        problems.append("leading/trailing whitespace")
    lines = [l for l in text.split("\n") if l.strip()]
    for l in lines:
        if l != l.strip():
            problems.append(f"line has edge whitespace: {l!r}")
        if re.search(r"\w- \w|\w -\w|\w - - ", l):
            problems.append(f"looks like syllable hyphenation: {l!r}")
        if CREDIT.search(l):
            problems.append(f"possible credit/performance marking: {l!r}")
    if d["language"].lower().startswith(("is", "ice")):
        for l in lines:
            # 'p' at word start before a vowel where 'þ' is expected is the classic OCR miss.
            for w in re.findall(r"\b[Pp](?:ú|ið|að|ví|ar|ér|eir|ess|ig|in|its|á|egar)\b", l):
                problems.append(f"'p' for 'þ'? {w!r} in {l!r}")
    stanzas = [s.strip() for s in text.split("\n\n") if s.strip()]
    dup_st = [s for s, n in Counter(stanzas).items() if n > 1 and len(s) > 40]
    for s in dup_st:
        problems.append(f"stanza repeated verbatim (use a refrain marker instead): {s[:60]!r}")
    line_counts = Counter(l.strip().casefold() for l in lines if len(l.strip()) > 25)
    for l, n in line_counts.items():
        if n > 2:
            problems.append(f"line occurs {n}x (voice-part duplication?): {l[:60]!r}")
    return problems


bad = 0
for p in sys.argv[1:]:
    pr = check(p)
    if pr:
        bad += 1
        print(f"FAIL {p}")
        for x in pr:
            print("   -", x)
    else:
        print(f"PASS {p}")
sys.exit(1 if bad else 0)
