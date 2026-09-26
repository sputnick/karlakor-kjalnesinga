#!/usr/bin/env python3
"""Build a deduplicated song catalog from the extracted sheet-music text."""

from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import html
import json
import os
from pathlib import Path
import re
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
EXTRACTION = Path("/private/tmp/kk-sheetmusic-extraction")


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.replace("þ", "th").replace("ð", "d").replace("æ", "ae").replace("ø", "o")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def source_stem(filename: str) -> str:
    name = filename.replace("_", " ").strip()
    while re.search(r"(?i)\.(?:pdf|docx?|txt)$", name):
        name = re.sub(r"(?i)\.(?:pdf|docx?|txt)$", "", name).strip()
    name = re.sub(r"\[\d+\]", "", name).strip()
    return name


TITLE_OVERRIDES = {
    "Abendstandchen.pdf": "Abendständchen",
    "Abendstãnchen page2 .pdf": "Abendständchen",
    "Kirkja Ómar öll.pdf": "Gleð þig, særða sál",
    "Sólbrúnir_vangar03.pdf": "Sólbrúnir vangar",
    "Morning has broken nótur í c dúr.doc": "Morning Has Broken",
    "Hann fæddist a jolanott.pdf": "Hann fæddist á jólanótt",
    "Fuglin sefur suðri mó.pdf": "Fuglinn sefur suðri mó",
    "Greeen green grass of home.pdf": "Green Green Grass of Home",
    "Glad saasom faageln.pdf": "Glad såsom fågeln",
    "Hótel jörð-KK.pdf": "Hótel Jörð",
    "Jól í Betlehem HERA 2016 - Karlakór.pdf": "Jól í Betlehem",
    "Kveðja Bubbi (úts. Gunnar Gunnarsson).pdf": "Kveðja",
    "Móts við sólglit sólarfalls, Birgir Helgason TTB.pdf": "Móts við sólglit sólarfalls",
    "Með bæninni kemur ljosið i C dur - Voice.pdf": "Með bæninni kemur ljósið",
    "Orðin mín karlakór GG.pdf": "Orðin mín",
    "Sangermarsch.pdf": "Sängermarsch",
    "Faðir vor, Malotte TTBB.pdf": "Faðir vor",
    "Söngkveðjan, E.Grieg TTBBB.pdf": "Söngkveðjan",
    "Þú spyrð mig koparlokka, M.Meystra TTBB.pdf": "Þú spyrð mig, koparlokka",
    "Þér-við-hlið-Karlakór-Kjalnesinga-GMS.pdf": "Þér við hlið",
    "Vonin- Karlakor.pdf": "Vonin",
}


SKIP_FILES = {
    "Jólatónleikar 2015.pdf": "concert set list, not a lyric score",
    "viðburðadagatal 2015-2016.pdf": "event calendar, not a lyric score",
    "Svandís Hallsdóttir.pdf": "funeral program; its lyric texts occur in dedicated score files",
    "Rheinweinlied.docx": "empty duplicate document",
}


def display_title(filename: str) -> str:
    if filename in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[filename]
    title = source_stem(filename)
    title = re.sub(r"(?i)\s*\(unicode encoding conflict\)\s*$", "", title)
    title = re.sub(r"(?i)\s+-\s+(?:sheet music|nótur)\s*(?:-\s*)?\d*\s*$", "", title)
    title = re.sub(r"(?i)\s+-\s+nótur\s*$", "", title)
    title = re.sub(r"(?i)\s+n[oó]tur\s*$", "", title)
    title = re.sub(r"(?i)\s+-\s+(?:bara kórpartur\s+-\s+)?(?:TTBBB|TTBB|TTB|SATB)(?:\s*\+\s*solo)?(?:\s+einfaldað)?(?:\s+-\s*A-dúr)?\s*$", "", title)
    title = re.sub(r"(?i)\s+TTBBB?\s*$", "", title)
    title = re.sub(r"(?i)\s+-\s+(?:full score|voice|choir|píanó)\s*$", "", title)
    title = re.sub(r"(?i)\s+Karlaraddir\s*$", "", title)
    title = re.sub(r"(?i)\s*\((?:Karlakór|píanó)\)\s*$", "", title)
    title = re.sub(r"(?i)\s+(?:karlakór|kórar)(?:sraddir)?(?:\s+Kjalnesinga)?(?:\s+einfaldað)?(?:\s+uts\s+Daða)?\s*$", "", title)
    title = re.sub(r"(?i)\s+raddir\s*$", "", title)
    title = re.sub(r"(?i)\s+-\s+(?:katla|PH|edit)\s*$", "", title)
    title = re.sub(r"(?i)\s*-\s*(?:Daði|edit)\s*$", "", title)
    title = re.sub(r"(?i)\s*-?\s*handskrifuð\s*$", "", title)
    title = re.sub(r"(?i)\s*-?\s*\b(?:úts\.?|uts\.?|útsetning|raddsetning|umskrifað)\s+.*$", "", title)
    title = re.sub(r"(?i)\s*-?\s*(?:tvíraddað|tvíradda kona&karl|litla rauða jólabókin|stormsveitin|kötlumót)(?:\s*-\s*lækkað)?\s*$", "", title)
    title = re.sub(r"(?i)(?:\s+-\s*|\s+)(?:nýtt|ny|ný|gamalt|eldri skrá|einfaldað|lækkað)\s*$", "", title)
    title = re.sub(r"(?i)-(?:ny|ný)\s*$", "", title)
    title = re.sub(r"(?i)\s+(?:blað\s*)?[12]\s*$", "", title)
    title = re.sub(r"(?i)\s+page\s*\d.*$", "", title)
    title = re.sub(r"\s*\([12]\)\s*$", "", title)
    title = re.sub(r"(?<=\D)[123]$", "", title)
    title = re.sub(r"(?i)\s+(?:UNIS|KÓRAR|textablað)\s*$", "", title)
    return re.sub(r"\s+", " ", title).strip(" -.,")


ALIASES = {
    "abendstanchen": "abendstandchen",
    "blessud sertu og fjalladrottning modir min": "blessud sertu sveitin min",
    "capri katarina karlakor kjalnesinga": "capri katarina",
    "drottinn er rett": "drottinn er minn hirdir",
    "drykkjuvisa gladur her eg stend": "drykkjuvisa gladur eg stend",
    "efemia fyrir": "efemia",
    "fangakorinn umskrifad af dada": "fangakorinn",
    "fanna skautar": "fjallid skjaldbreidur",
    "heyr himna smidur": "heyr himnasmidur",
    "heyr mina baen 4": "heyr mina baen",
    "hungarian dance no 5": "ungverskur dans nr 5",
    "island island eg vil syngja": "island",
    "jolin allsstadar": "jolin alls stadar",
    "landsyn olav tryggvason": "landsyn",
    "landid mitt stormsveitin": "landid mitt",
    "loksins eg fann thig": "eg fann thig",
    "nu geng eg med a gledifund": "nu gegn eg med a gledifund",
    "please release me": "release me",
    "sefur nott hja aegi": "sefur sol hja aegi",
    "smavinir fagrir": "smavinir fagrir",
    "spreittur eg best af faki fraum": "spreittur",
    "sprettur eg best af faki fraum": "sprettur",
    "sprengisandur": "a sprengisandi",
    "sumar i sveitum": "sumar er i sveitum",
    "the christmas song chestnuts roasting": "the christmas song",
    "the christmas song chestnuts roasting bara korpartur": "the christmas song",
    "undir svortudrongum": "undir svortudrongurm 1 2 tenor og bariton",
    "vorið kemur": "vikivaki",
    "vorid kemur": "vikivaki",
    "i bljugri raddad": "i bljugri baen",
    "eg leit eina lilju i holti": "liljan",
    "i fjarlægd tenor og bassi hljomar": "i fjarlægd",
    "o helga nott eb nytt": "o helga nott",
    "o helga nott korar": "o helga nott",
    "rosin notur": "rosin",
    "sumarmal karlakor": "sumarmal",
    "threk og tar bassi tenor": "threk og tar",
    "ver hja mer herra ttbb baedi erindi": "ver hja mer herra",
    "visur vatnsenda rosu ttbb": "visur vatnsenda rosu",
    "thakkarbaen blad": "thakkarbaen",
    "thu alfu vorrar": "thu alfu vorrar yngsta land",
}


CANONICAL_TITLES = {
    "a sprengisandi": "Á Sprengisandi",
    "abendstandchen": "Abendständchen",
    "brennid thid vitar": "Brennið þið vitar",
    "dagny": "Dagný",
    "desember ljod": "Desemberljóð",
    "drykkjuvisa nu allir strengir oma": "Drykkjuvísa (Heillaskál)",
    "eg er kominn heim": "Ég er kominn heim",
    "eg fann thig": "Ég fann þig",
    "fangakorinn": "Fangakórinn",
    "fuglinn sefur sudri mo": "Fuglinn sefur suðri mó",
    "heyr mina baen": "Heyr mína bæn",
    "i fjarlægd": "Í fjarlægð",
    "landid mitt": "Landið mitt",
    "landsyn": "Landsýn",
    "med baeninni kemur ljosid": "Með bæninni kemur ljósið",
    "my way": "My Way",
    "no woman no cry": "No Woman, No Cry",
    "nu gegn eg med a gledifund": "Nú geng ég með á gleðifund",
    "nu yfir heidi haa": "Nú yfir heiði háa",
    "o helga nott": "Ó helga nótt",
    "release me": "Release Me",
    "rondotta maer": "Röndótta mær",
    "rosin": "Rósin",
    "sefur sol hja aegi": "Sefur sól hjá Ægi",
    "sol ris sol sest": "Sól rís, sól sest",
    "sumarmal": "Sumarmál",
    "the christmas song": "The Christmas Song (Chestnuts Roasting)",
    "threk og tar": "Þrek og tár",
    "undir svortudrongurm 1 2 tenor og bariton": "Undir Svörtudröngum",
    "ver hja mer herra": "Ver hjá mér, Herra",
    "visur vatnsenda rosu": "Vísur Vatnsenda-Rósu",
    "vonin": "Vonin",
}


LYRIC_OVERRIDES = {
    "no woman no cry": "No woman, no cry.\nNo woman, no cry.",
    "afmaelissongur": (
        "Hann/hún á afmæli í dag.\n"
        "Hann/hún á afmæli í dag.\n"
        "Hann/hún á afmæli, hann/hún á afmæli,\n"
        "hann/hún á afmæli í dag."
    ),
    "modir": "Aa…\n\nÚú…",
    "a saelum sumarkvoldum": (
        "Á sælum sumarkvöldum, er sveitin glóir öll,\n"
        "og leikur ljós á öldum og logagyllir fjöll.\n"
        "En hljóður hvílir bærinn í helgum frið og ró,\n"
        "þá er það bóndabærinn, sem ber af öllu þó."
    ),
    "son guds ertu med sanni": (
        "Son Guðs ertu með sanni,\n"
        "sonur Guðs, Jesús minn.\n"
        "Son Guðs, syndugum manni\n"
        "sonar arf skenktir þinn,\n"
        "Guðs sonur eingetinn.\n\n"
        "Syngi Guði glaður\n"
        "sérhver lifandi maður,\n"
        "heiður í hvert eitt sinn."
    ),
    "fuglinn sefur sudri mo": (
        "Fuglinn sefur suðr’ í mó,\n"
        "sefur kyrr í værð og ró,\n"
        "sefur, sefur dúfan.\n"
        "Sofðu líka sætt og rótt,\n"
        "sofðu vært í alla nótt,\n"
        "sofðu litla ljúfran."
    ),
    "fyrst eg annars hjarta hraeri": (
        "Fyrst ég annars hjarta hræri,\n"
        "helst ég þá mér lifa kýs,\n"
        "sem ég annar Adam væri\n"
        "austur í paradís.\n\n"
        "Þar mun steiktar gæsir gott að fá,\n"
        "Guðveig drekka, sofa væran, baða rósum á,\n"
        "klappa þeirri sem ég kærsta á,\n"
        "kvæði syngja, dansa polka, hoppa til og frá.\n\n"
        "Við mitt glas er vænst að sofna,\n"
        "vakna hjá þér, fagra mær.\n"
        "Þegar fjörið fer að dofna,\n"
        "færist kyrrðin nær."
    ),
    "drykkjuvisa nu allir strengir oma": (
        "Nú allir strengir óma\n"
        "við ást og vín og hljóma.\n"
        "Nú fagnar sérhver sál,\n"
        "nú fagnar sérhver sál.\n\n"
        "Er allir sönginn syngja\n"
        "og saman glösum klingja\n"
        "og hrópa heillaskál,\n"
        "og hrópa heillaskál.\n\n"
        "Heillaskál, heillaskál,\n"
        "og hrópa heillaskál."
    ),
    "sveitin min": (
        "Allt sem mest ég unni og ann\n"
        "er í þínum faðmi bundið.\n"
        "Allt það sem ég fegurst fann,\n"
        "allt sem gert fékk úr mér mann\n"
        "og til starfa kröftum hrundið.\n\n"
        "Allt sem mest ég unni og ann\n"
        "er í þínum faðmi bundið."
    ),
}


def title_key(title: str) -> str:
    key = fold(title)
    key = re.sub(r"\s+1 og 2 bassi$", "", key)
    key = re.sub(r"\s+(?:blad|page)\s*\d.*$", "", key)
    return ALIASES.get(key, key)


WORD_RE = re.compile(r"[^\W\d_]+(?:['’´][^\W\d_]+)*", re.UNICODE)
SHORT_WORDS = {
    "a", "að", "af", "á", "am", "an", "and", "are", "as", "at", "ba", "bam", "be", "by",
    "da", "de", "der", "die", "do", "doh", "dom", "du", "e", "ef", "ei", "en", "er", "es",
    "eg", "ég", "for", "frá", "für", "hann", "hér", "hjá", "hún", "i", "í", "ich", "il", "in",
    "is", "it", "ja", "la", "me", "med", "með", "mein", "mér", "min", "mio", "mit", "my", "no",
    "nú", "o", "of", "og", "on", "oss", "pa", "pam", "ram", "sem", "si", "so", "sú", "svo",
    "sér", "the", "til", "um", "uh", "úr", "við", "we", "who", "will", "you", "þa", "það", "þá",
    "þar", "þau", "þeim", "þeir", "þér", "þig", "þin", "þín", "þó", "þú", "aa", "úú",
}
SHORT_WORDS = {fold(word) for word in SHORT_WORDS}
DROP_PATTERNS = re.compile(
    r"(?i)^(?:lag|ljóð|texti|lyrics?|music|arr\.?|útsetning|raddsetning|tölvusetning|"
    r"hreinskrifað|copyright|eftirprentun|prentsmiðjan|page|blað|karlakór|karlaraddir|"
    r"tenor\s*\d*|tenór\s*\d*|bass\s*\d*|bassi\s*\d*|sólo|solo|andante|allegro|"
    r"adagio|largo|moderato|maestoso|dolce|coda|fine|rit\.?|a tempo|copyright|©|"
    r"erindi|kór|tutti|tölvusett|forspil|eftirspil|prestur|organisti)\b"
)
MUSIC_CHARS = str.maketrans({character: " " for character in "œŒ˙™°¢∑‹›♭♯♮𝄞ǁȍƭƮƿϋύώ"})


def normalized_line(line: str) -> str:
    line = unicodedata.normalize("NFKC", line).translate(MUSIC_CHARS)
    line = line.replace("ﬂ", "fl").replace("ﬁ", "fi")
    line = re.sub(r"(?<=\w)\s*[-=+]\s*(?=\w)", "", line)
    line = re.sub(r"[|{}<>\\/_~^`]+", " ", line)
    line = re.sub(r"[^\wÀ-žÁ-ſ'’´.,!?():;–—\- ]+", " ", line, flags=re.UNICODE)
    line = re.sub(r"\s+", " ", line).strip(" .,:;|-")
    return line


def clean_text(raw: str, title: str, aggressive: bool = True) -> str:
    title_folded = fold(title)
    output: list[str] = []
    seen: set[str] = set()
    pending_blank = False
    for raw_line in raw.replace("\r", "").split("\n"):
        if not raw_line.strip() or "\f" in raw_line:
            pending_blank = bool(output)
            continue
        segments = re.split(r"\s{5,}", raw_line.strip())
        for segment in segments:
            if sum(character.isdigit() for character in segment) >= 3:
                continue
            line = normalized_line(segment)
            line = re.sub(r"\d+", " ", line)
            line = re.sub(r"\s+", " ", line).strip(" .,:;|-")
            words = WORD_RE.findall(line)
            if not words:
                continue
            folded = fold(line)
            if folded == title_folded or DROP_PATTERNS.search(line):
                continue
            if re.fullmatch(r"[A-GH](?:is|es|m|maj|min|dim|sus)?(?:\s+[A-GH](?:is|es|m|maj|min|dim|sus)?)*", line, re.I):
                continue
            folded_words = [fold(word) for word in words]
            suspect_short = sum(len(word) <= 3 and folded not in SHORT_WORDS for word, folded in zip(words, folded_words))
            if aggressive and len(words) >= 3 and suspect_short / len(words) >= 0.45:
                continue
            vowel_words = sum(bool(re.search(r"[aeiouy]", folded)) for folded in folded_words)
            if aggressive and len(words) >= 4 and vowel_words / len(words) < 0.45:
                continue
            if aggressive and len(words) >= 4 and sum(len(word) <= 1 for word in words) / len(words) > 0.45:
                continue
            if aggressive and len(words) >= 4 and len(set(folded_words)) <= 2:
                continue
            if len("".join(words)) < 3:
                continue
            key = fold(" ".join(words))
            if key in seen:
                continue
            seen.add(key)
            if pending_blank and output and output[-1] != "":
                output.append("")
            pending_blank = False
            output.append(line)
    while output and not output[-1]:
        output.pop()
    return "\n".join(output)


def quality(text: str) -> float:
    lines = [line for line in text.splitlines() if line]
    if not lines:
        return 0
    words = WORD_RE.findall(text)
    useful = sum(len(word) for word in words if len(word) > 1)
    short_penalty = sum(1 for word in words if len(word) == 1) * 3
    return useful - short_penalty + len(lines) * 2


def parse_existing() -> list[dict[str, str]]:
    source_path = Path(os.environ.get("KK_BASE_INDEX", ROOT / "index.html"))
    source = source_path.read_text()
    pattern = re.compile(
        r'<section class="song" id="s(?P<id>\d+)"><h1>(?P<title>.*?)</h1>'
        r'<div class="lyrics">(?P<lyrics>.*?)</div></section>',
        re.DOTALL,
    )
    songs = []
    for match in pattern.finditer(source):
        body = re.sub(r"(?i)<br\s*/?>", "\n", match.group("lyrics"))
        body = re.sub(r"<[^>]+>", "", body)
        songs.append({
            "id": match.group("id"),
            "title": html.unescape(match.group("title")),
            "lyrics": html.unescape(body).strip(),
        })
    return songs


def main() -> None:
    records = json.loads((EXTRACTION / "extraction-index.json").read_text())
    existing = parse_existing()
    existing_by_key = {title_key(song["title"]): song for song in existing}
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    skipped: list[dict[str, str]] = []
    for record in records:
        filename = str(record["file"])
        if filename in SKIP_FILES:
            skipped.append({"file": filename, "reason": SKIP_FILES[filename]})
            continue
        title = display_title(filename)
        groups[title_key(title)].append({**record, "title": title})

    catalog: list[dict[str, object]] = []
    for key, sources in sorted(groups.items()):
        candidates = []
        for source in sources:
            filename = str(source["file"])
            for method in ("vision", "ocr", "embedded"):
                path = EXTRACTION / method / f"{filename}.txt"
                if not path.exists():
                    continue
                cleaned = clean_text(path.read_text(errors="replace"), str(source["title"]), aggressive=method != "vision")
                candidates.append((quality(cleaned), filename, method, cleaned))
        preferred = [candidate for candidate in candidates if candidate[2] == "vision"] or candidates
        preferred.sort(reverse=True)
        score, selected_file, method, lyrics = preferred[0] if preferred else (0, "", "", "")
        existing_song = existing_by_key.get(key)
        shortest_title = min((str(source["title"]) for source in sources), key=lambda value: (len(value), fold(value)))
        title = CANONICAL_TITLES.get(key, existing_song["title"] if existing_song else shortest_title)
        lyrics = LYRIC_OVERRIDES.get(key, lyrics)
        score = quality(lyrics)
        catalog.append({
            "key": key,
            "title": title,
            "existing_id": existing_song["id"] if existing_song else None,
            "sources": sorted(str(source["file"]) for source in sources),
            "selected_source": selected_file,
            "method": method,
            "quality": round(score, 1),
            "lyrics": lyrics,
        })

    # This score contains two alternate lyric sets interleaved on the same staves.
    catalog.append({
        "key": title_key("Fjalladrottning, móðir mín"),
        "title": "Fjalladrottning, móðir mín",
        "existing_id": None,
        "sources": ["Blessuð sértu og Fjalladrottning móðir mín.pdf"],
        "selected_source": "Blessuð sértu og Fjalladrottning móðir mín.pdf",
        "method": "split from OCR",
        "quality": 1000,
        "lyrics": (
            "Fjalladrottning, móðir mín,\n"
            "mér svo kær og hjarta bundin.\n"
            "Sæl ég bíð við brjóstin þín,\n"
            "blessuð aldna fóstra mín.\n"
            "Hér á andinn óðul sín,\n"
            "öll sem verða á jörðu fundin.\n\n"
            "Fjalladrottning, móðir mín,\n"
            "mér svo kær og hjarta bundin."
        ),
    })

    # This PDF contains two independent German songs, one per page.
    combined = EXTRACTION / "vision" / "Das Königslied og Warum.pdf.txt"
    if not combined.exists():
        combined = EXTRACTION / "ocr" / "Das Königslied og Warum.pdf.txt"
    if combined.exists():
        pages = combined.read_text(errors="replace").split("\f")
        if len(pages) >= 2:
            catalog = [item for item in catalog if item["key"] != title_key("Das Königslied og Warum")]
            for title, page in (("Das Königslied", pages[0]), ("Warum bist du so ferne", pages[1])):
                lyrics = clean_text(page, title, aggressive=combined.parent.name != "vision")
                catalog.append({
                    "key": title_key(title), "title": title, "existing_id": None,
                    "sources": ["Das Königslied og Warum.pdf"],
                    "selected_source": "Das Königslied og Warum.pdf", "method": "split from OCR",
                    "quality": round(quality(lyrics), 1), "lyrics": lyrics,
                })

    catalog.sort(key=lambda item: fold(str(item["title"])))
    output = {
        "source_file_count": len(records),
        "skipped_sources": skipped,
        "existing_song_count": len(existing),
        "canonical_song_count": len(catalog),
        "songs": catalog,
    }
    path = EXTRACTION / "song-catalog.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")

    unmatched = [item for item in catalog if item["existing_id"] is None]
    print(f"Sources: {len(records)}; canonical songs: {len(catalog)}; existing matches: {len(catalog) - len(unmatched)}; additions: {len(unmatched)}")
    print(f"Skipped non-song/duplicate documents: {len(skipped)}")
    print(f"Wrote {path}")
    print("\nPossible title overlaps among additions and existing songs:")
    for item in unmatched:
        closest = max(existing, key=lambda song: SequenceMatcher(None, str(item["key"]), title_key(song["title"])).ratio())
        ratio = SequenceMatcher(None, str(item["key"]), title_key(closest["title"])).ratio()
        if ratio >= 0.63:
            print(f"  {ratio:.2f}  {item['title']}  ~=  {closest['title']}")


if __name__ == "__main__":
    main()
