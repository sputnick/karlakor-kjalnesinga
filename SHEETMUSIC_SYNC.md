# Sheet-music sync handoff

Use the prompt below when files are added to `sheetmusic/` or when the lyrics page needs to be rebuilt.
It is deliberately strict about source accounting, duplicate prevention and Icelandic spelling. Everything
learned in earlier syncs is in **Lessons learned**, and the prompt for each subagent is in **Subagent brief**.
Read both before starting.

## Continuation prompt

> Update the Karlakór Kjalnesinga lyrics page from every score in `sheetmusic/`.
>
> Start by reading `README.md`, `index.html`, `SONGS.md` and this file. Inspect `git status`, the current branch and the
> remote before changing anything. Preserve unrelated and untracked user files.
>
> Treat the current `index.html` as the canonical, curated baseline. Preserve existing lyrics, song IDs, group labels,
> order, search behaviour, local-storage behaviour and the single-file GitHub Pages design unless a source proves a
> correction is needed. Never regenerate an existing good lyric from lower-quality OCR. The 42 hand-entered songs
> (ids 0–41) are the choir's own versions: do not rewrite them.
>
> Enumerate every PDF, DOC and DOCX in `sheetmusic/` programmatically and produce an auditable source inventory. Every file
> must end up either mapped to a song (its path appears in that song's `songs/*.md` front matter and in `SONGS.md`)
> or skipped with a written reason. Extract embedded text first, and use OCR only for image-only pages. OCR text is
> a *locator* (which song, which lyricist, roughly which words), never the final lyric.
>
> Build a canonical song catalog before editing HTML. Normalize Unicode, punctuation, case, arrangement suffixes and file
> names for matching. Merge alternate arrangements, voice parts, scans and transpositions into one song. Check fuzzy title
> overlaps by hand, and also check *text* overlaps: the same poem often appears under different titles (see Lessons
> learned). Identify non-song files (calendars, set lists, programmes, empty documents) and record a skip reason for each.
>
> Correct the lyrics with subagents. Split the new songs into batches of about 14 and give each batch to its own
> subagent. **Use the Sonnet model for all web search and scraping.** Each subagent follows the **Subagent brief**
> exactly, writes one `corrections/<id>.json` per song in a work directory outside the repo, and never edits
> `index.html`. The rule is: **trust the online text over OCR** for wording, spelling and line/stanza shape, but
> keep the stanza selection and any deliberate wording changes that the score itself sets. Before launching, mark
> every internationally published commercial song in its original language as `skipped-copyright` (see Lessons
> learned: the API refuses to output those lyrics and kills the agent).
>
> Merge centrally with `tools/lyrics_merge.py` only after checking duplicates, title changes and splits
> (`decisions.json`). Then run `tools/lyrics_audit.py`, an Icelandic proofreading pass and a browser test, and
> regenerate the song export with `tools/export_songs.py`.
>
> Every rendered song must have one unique normalized title, one unique section ID, one matching list item and
> nonempty lyrics. Update the visible version stamp (`lyrics_merge.py` does this in UTC, which is Icelandic time).
>
> Commit and push coherent checkpoints as soon as each is ready. Do not hold everything until all agents finish.
> After each push, confirm on https://sputnick.github.io/karlakor-kjalnesinga/ that the new stamp is live. Stage
> only intended files. Never commit `sheetmusic/`, extraction caches, screenshots, `.firecrawl/`, `.playwright-mcp/`
> or the work directory.
>
> In the final report, give: the filesystem source count and how it is accounted for; the page song count; counts per
> text status; skipped documents with reasons; audit results (characters, credit lines, cross-song overlaps); the
> browser test results; commit hashes and push status; and the list of songs that still need human proofreading
> or missing lyrics. Do not call the task complete while a verse or an Icelandic spelling remains unverified. Say
> which ones are unverified instead.

## Tools (all in `tools/`)

| Script | What it does |
|---|---|
| `extract_sheetmusic.py`, `reextract_clean_ocr.py`, `vision_ocr.swift`, `run_vision_batch.py` | First-pass text extraction (embedded text, Tesseract, macOS Vision) into `/private/tmp/kk-sheetmusic-extraction/` |
| `build_song_catalog.py` | Groups score files into songs → `song-catalog.json` (title overrides, skips) |
| `update_index_from_catalog.py` | The original import that appended new songs to `index.html` (historical; do not re-run over the curated page) |
| `lyrics_check.py <file.json>…` | Validates one subagent correction file (schema, NFC, OCR-junk characters, credit lines, hyphenation, duplicated stanzas/lines) |
| `lyrics_merge.py [--dry-run]` | Applies `$KK_WORK/corrections/*.json` + `$KK_WORK/decisions.json` to `index.html`: escapes HTML, keeps ids and concert/curated order, sorts the sheet-music block by folded title, writes the placeholder for missing lyrics, stamps the version |
| `lyrics_audit.py [--corr]` | Whole-page audit: item/section structure, unique ids and titles, per-language stray characters, `p`-for-`þ`, credit lines, and **cross-song line overlap** (catches the same poem under two titles) |
| `export_songs.py` | Writes `songs/<slug>.md` (front matter + lyrics) for every song and the `SONGS.md` index |

`decisions.json` format: `{"remove": {"<id>": "reason"}, "no_extra": [<ids whose extra_songs are ignored>], "title": {"<id>": "Final title"}}`.
Export with the corrected catalog: `KK_CORRECTIONS=$KK_WORK/corrections KK_CATALOG=<catalog with existing_id on every song> python3 tools/export_songs.py`.
Without those variables, the export keeps the metadata already stored in `songs/*.md` and only refreshes titles and lyrics from `index.html`.

## Concert programme and song keys

- The "Concert" group is the current programme, in singing order. It is set by the `"concert"` list of ids in
  `decisions.json`. `lyrics_merge.py` then puts those songs first in that order and makes every other song an
  "extra": curated originals in their existing order, then the sheet-music songs alphabetically. Titles are never
  changed to match a programme list. Match programme names to existing songs by hand, since names on programmes
  are often shortened, e.g. "Sælir söngbræður" is "Sælir verða söngbræður" and "Þú álfu vorrar" is "Þú álfu vorrar yngsta land".
- When the programme changes, bump `KEY_O` in `index.html` (`kk.order` → `kk.order.2` → …). Otherwise members' saved
  custom orders from the previous concert would override the new running order. Per-song font sizes (`kk.fs`) are kept.
- Keys from the programme sheet are stored as `key:` in each song's `songs/*.md` front matter and shown in
  `SONGS.md`. They use Icelandic notation: H = B natural, B = B-flat, and the bracket holds the starting note,
  e.g. "E dúr (H)". `export_songs.py` keeps existing front-matter values, so keys survive re-exports.
- Programme of 26 Sep 2026 (19 songs): Kvöldið er fagurt, Sælir verða söngbræður, Þú komst í hlaðið, Heyr
  himnasmiður, Loch Lomond, Undir Svörtudröngum, Rauði Riddarinn, Nú máttu hægt, Sefur sól hjá Ægi, Suður um höfin,
  Violetta, Ríðum sem fjandinn, Drykkjuvísa (Heillaskál), Þú álfu vorrar yngsta land, Fjallið Skjaldbreiður, Fyrst
  ég annars hjarta hræri, Hún hring minn ber, Kvæðið um fuglana, Réttarvatn.

## Lessons learned (sync of 26 Sep 2026)

**Extraction**
- The first OCR import (commit `57bb85d`) was mostly unusable as lyrics. It mixed in credit lines, dynamics and
  chord symbols, duplicated voice parts, split syllables, and substituted characters (`þ→p`, `ð→o/õ/ỗ/ğ`, `á→a`,
  Cyrillic look-alikes). Tuning OCR further is not worth it. Subagents that *look at the score* (the Read tool opens
  PDFs; `pdftoppm -r 170 -png -f N -l N` to zoom) and then find the published text get far better results.
- Anthology PDFs: `Abendstandchen.pdf` is all of Mendelssohn Op. 75 and `Rheinweinlied.pdf` is Op. 76. Only the song
  a file is named after goes on the page (`no_extra`). Other songs in the same print are not the choir's repertoire.
- The catalog can map files to the wrong song. `Landið Mitt.pdf` and `Landið Mitt Stormsveitin_lækkað.pdf` actually
  contain "Land míns föður" (id 157), not "Landið mitt" (id 158). Subagents catch this when they look at the score.
  The corrected mapping now lives in `songs/*.md`.

**Web search and scraping**
- Built-in WebSearch has a **session-wide cap of about 200 searches**. Sixteen parallel agents used it up after
  about 5 songs each. Use the team's **Firecrawl CLI** instead. It is authenticated; check with `firecrawl --status`.
  Always run it from the work directory, never the repo, because it writes a `.firecrawl/` cache there.
  `firecrawl search '"<first line>" texti' --limit 5 --country IS` costs 2 credits. `firecrawl scrape <url>
  --only-main-content -o x.md` costs 1 credit. Allow at most 3 searches and 3 scrapes per song. Firecrawl allows
  2 concurrent jobs, so many agents get rate-limited.
- WebFetch's summarizer refuses to return full lyric text. Use `curl -sL -A "Mozilla/5.0"` or `firecrawl scrape` and read the raw text.
- Sources that worked well:
  - Hymns: `https://api.kirkjan.is/api/hymns?pageSize=2000` (all 895 hymns with full text, JSON) and `kirkjan.is/salmabok/<slug>`
  - Song text collections: `snerpa.is/allt_hitt/textasafn/` (grep the index), `notendur.snerpa.is/systaoggaui/`, `glatkistan.com/?s=`
  - Poems and archives: `ljod.is/poem/<n>`, `ismus.is/bragi`, is./sv./de.wikisource (MediaWiki search API), `timarit.is/?q=`
  - Song and chord sites: `guitarparty.com`, `kvak.is`, `olisig.is`, `icetones.se`, `afigamli.is`
  - Foreign texts: `lieder.net`, `runeberg.org`, `volksliederarchiv.de`
  - The choir's own concert programmes: `karlakor.is/wp-content/uploads/2025/03/Vor2012.pdf`, `Vor2014.pdf`, `Vor2017.pdf`, …
- Sources that were blocked: DuckDuckGo and Bing HTML (bot wall), hymnary.org (403), Reddit (Firecrawl refuses it).

**Copyright and the content filter**
- The API **refuses to output well-known copyrighted commercial lyrics** (English/Italian pop, standards, musicals,
  Christmas pop). When that happens, the agent dies and loses its whole batch. It killed 3 of 16 agents on their
  first song. Before launching, pre-write `skipped-copyright` records for such songs. Agents must never quote them,
  not even in notes. On the page these songs show `(Texti vantar – sjá nótur.)`. The user can supply the text
  (edit the song's section in `index.html`, then re-run the export).
- Icelandic texts usually pass, including Icelandic words to foreign tunes, and are processed normally. The choir
  owns its scores and has said any text-only online version may be used. But **re-outputting the full text of a
  well-known Icelandic pop song can also trip the filter**: a proofreading agent died on a batch containing
  Ömmubæn, Pöddulagið, Sagan af Jesúsi, Þú átt mig ein and similar songs. Any agent that *edits* existing lyrics must
  make small targeted replacements (a minimal Edit or `str.replace`) and must never restate whole stanzas. Keep such
  songs out of batches whose loss would be expensive.
- Public-domain foreign songs (O sole mio, Dowland, Mendelssohn, Söderman, Kodály/Berzsenyi) are **not**
  copyright-skipped. One agent over-applied the rule to O sole mio.

**Lyric form and dedup**
- The same poem often sits under several titles. For example, "Blessuð sértu sveitin mín", "Fjalladrottning,
  móðir mín" and "Sveitin mín" are three stanzas of one poem by Sigurður Jónsson frá Arnarvatni. They were merged
  into id 62, and ids 91 and 233 were removed. `lyrics_audit.py` reports these as cross-song overlaps.
- Suites can contain a movement that is also its own entry. "Ett bondbröllop" (85) includes "I Bröllopsgården"
  (128), so 85 now ends with a pointer line instead of repeating the text.
- Formatting rules:
  - One poetic line per line and one blank line between stanzas.
  - A refrain is written once, then marked `(Viðlag)` / `(Chorus)` / `(Refrain)` where it recurs.
  - Musical repeats, echo repeats and "la la" filler are not expanded.
  - Vocalise-only pieces (Móðir, Hungarian Dance, Sängermarsch, Jodler, Hallelujah arrangement) keep minimal syllables and status `needs-review`.
- Keep the score's stanza selection (hymns often use 1, 2 and 4), and note the omitted stanzas.
- When the score's wording and the online text disagree, **follow the score** (the user confirmed this policy on 26 Sep 2026): the choir sings from it. Online
  sources are often the ones with typos, e.g. olisig.is had "handa"/"heygja" for "handan"/"heyja", and glatkistan
  had "gilið" for "gilin". The exception is a score that is clearly misprinted. Record every difference in `notes`.

**Titles**
- Icelandic titles use sentence case ("Afmælissöngur", "Betri bílar").
- Keep the name the choir knows. Do not retitle to the poem's formal name: keep "Ég kveiki á kertum mínum", not
  "Á föstudaginn langa". When an Icelandic title replaces a well-known English one, add the English name, e.g.
  "Líður að dögun (Morning Has Broken)", so search still finds it.
- Review every title change in one list before merging.

**Validation pitfalls**
- Never treat `ý`/`Ý` as OCR junk. An early validator bug did this and nearly made agents strip `ý`.
- The credit-line check must look for `Keyword:` patterns only. The words "lag" and "ljóð" are common inside real lyrics.
- `par` ("couple") is a real word, not a `þar` OCR error.
- Tell every subagent **not to spawn its own subagents or forks**. One upgrade agent split its list across forks,
  and a fork redid ids that belonged to its siblings. That caused a race: duplicated notes and a status that
  contradicted its notes, which then needed a manual audit.
- Give every agent its own scratch folder (`W/tmp/<agent>/`) and tell it never to write shared helper scripts
  such as `W/tmp/fix.py`. Two proofreaders overwrote each other's script there and briefly corrupted two
  `proofread` fields.
- Agents make typing slips: stray characters inside words, stray English words, invalid JSON after an Edit,
  repeated syllables. Always run the per-language stray-character audit, then a proofreading pass.

**Page and deployment**
- The app is id-based, so removing a song leaves a gap and nothing breaks. Saved orders drop missing ids, and new
  ids slot in at the end of their group. The browser test confirmed this with a stored order containing the removed ids.
- Browser test: the deck uses smooth scrolling, so wait about 3 s before reading the position after opening a song.
  Playwright MCP writes `.playwright-mcp/` into the repo, which is git-ignored.
- `.gitignore` covers `sheetmusic/`, `.firecrawl/`, `.playwright-mcp/` and `__pycache__/`.

## Subagent brief

Give each subagent this text, filling in the work directory `W` and its batch number. The packet
`W/packets/batch-NN.json` holds `id`, `title`, `current_page_lyrics` and `sources` (score path and OCR text files).
Also provide `W/all-titles.json`, a list of `{id, title, curated_original}` for every song on the page.

> You are fixing song lyrics for the lyrics web app of Karlakór Kjalnesinga, an Icelandic men's choir. The choir owns
> these scores, so any text-only lyric version found online may be copied.
>
> **Deliverable:** for each song in your packet, write `W/corrections/<id>.json`. Write only those files. Never edit
> the git repo or other ids' files.
>
> **Tools.** Read opens PDFs directly (`pages: "1-4"`). Zoom with `pdftoppm -r 170 -png -f N -l N`. Search with
> `cd W/tmp && firecrawl search '"<first line>" texti' --limit 5 --country IS`, at most 3 per song. Fetch with
> `curl -sL -A "Mozilla/5.0" <url>` or `firecrawl scrape <url> --only-main-content -o W/tmp/<id>.md`, at most 3 per
> song. WebFetch will not return full lyrics. OCR text files are hints only.
>
> **Procedure.**
> 1. From the score, identify the title, lyricist, composer, translator, sung language, the stanzas the score sets
>    (underlay and printed stanzas) and the form.
> 2. Find the same text online in the same language and translation (see the source list in SHEETMUSIC_SYNC.md).
> 3. Trust the online text over OCR for wording, spelling, punctuation and line/stanza shape. Keep the score's
>    stanza selection and its deliberate wording changes, and explain any difference in `notes`. A different
>    translation is not a match.
> 4. If nothing reliable is online, transcribe from the score images using Icelandic grammar. Never invent text;
>    write `[?]` for anything unreadable. Set `needs_second_pass` when unsure.
>
> **Format.** Plain text, one poetic line per line, one blank line between stanzas. Each stanza appears once; never copy
> voice parts or musical repeats. A recurring unchanged refrain is written once, then `(Viðlag)` / `(Chorus)` /
> `(Refrain)`. Strip titles, credits, "Úts."/"Radds.", tempo, dynamics, voice labels, chords, rehearsal marks and
> copyright lines. Use correct Icelandic `á é í ó ú ý þ ð æ ö` in NFC. Titles use sentence case and keep the name the
> choir knows.
>
> **Copyright.** Never write, quote or paraphrase the original-language lyrics of internationally published
> commercial songs (pop, rock, standards, musicals, film or Christmas pop). The API will kill your run if you do.
> If the score sets Icelandic words, do those as normal. Otherwise write `"status": "skipped-copyright", "lyrics": ""`
> and move on. Public-domain songs are not in this category.
>
> **Duplicates and splits.** If the song is the same text as another entry in `all-titles.json`, set
> `"duplicate_of": <id>`. If the score holds other independent songs, list them in `"extra_songs"`, or name the
> existing entry in `notes`. For a score with no sung text, set status `needs-review` and keep minimal syllables.
>
> **Schema.** `{id, title, language (ISO), lyricist, composer, translator, lyrics,
> status: online-verified|score-transcribed|needs-review|skipped-copyright, urls[], stanzas_in_score,
> stanzas_written, form_notes, notes, needs_second_pass, duplicate_of, extra_songs[]}`. Write it with
> `json.dump(..., ensure_ascii=False, indent=1)`. After each file, run `python3 tools/lyrics_check.py <file>`. The
> credit-word check is heuristic: keep a real lyric word it flags and say so in `notes`.
>
> Work one song at a time and save each file as soon as it is done. Do not spawn subagents or forks. Finish with a table of
> id | title | status | main URL | flags (under 40 lines).

## Current baseline

- Source inventory: 337 files (335 PDF, 1 DOC, 1 DOCX). 333 are mapped to songs and 4 are skipped:
  `Jólatónleikar 2015.pdf` (concert set list), `Rheinweinlied.docx` (empty duplicate), `Svandís Hallsdóttir.pdf`
  (funeral programme; its texts have their own score files) and `viðburðadagatal 2015-2016.pdf` (event calendar).
- Page: **268 songs**. 42 are hand-entered originals (ids 0–41; 32 have a score in `sheetmusic/`, 10 are app-only).
  226 come from the scores (ids 42–269, without 91 and 233, which were merged into 62). The Concert group is the
  19-song programme of 26 Sep 2026.
- Text status after the 26 Sep 2026 sync: 176 checked against online text, 30 transcribed from the score (no
  published text found), 42 hand-entered, 15 lyrics missing (copyright filter: Caruso, Delilah, Green Green Grass
  of Home, It's Beginning to Look a Lot Like Christmas, Laura, Learn me right, Michelle, My Way, Nella Fantasia,
  New York New York, No Woman No Cry, Release Me, The Christmas Song, The Wonder of You, When I'm Sixty-Four),
  5 wordless pieces needing review (Hallelujah arrangement, Hungarian Dance No. 5, Jodler, Móðir, Sängermarsch).
- Every song from the scores was proofread by an Opus agent, except eight well-known Icelandic pop songs kept out
  because of the content filter: Ömmubæn, Pöddulagið, Sagan af Jesúsi, Sólbrúnir vangar, Þakklæti, Þórður sjóari,
  Þú átt mig ein and Vetrarsól. All eight are checked against online text.
- Human check still wanted (`needs_proofreading`/notes in `songs/*.md`): Ett bondbröllop, Glaðir sem fuglar
  ("Sviffráir"), Gullnu vængir, I bröllopsgården, Jökullinn, Ég leit eina lilju í holti, Meðan nóttin líður,
  Norðurleiðarútan, Óðurinn til gleðinnar, Slá í gegn, Sól rís, sól sest ("Samleikann"), Ukuarluarisaa and
  Undir bláhimni.
- Checkpoints: `57bb85d` (raw OCR import, 270 songs), then `56f91e0` → `7d1cdf2` → `394cf61` (concert) → `0a55679`
  → `085fdfb` → `3c2465a` → `17f9aeb` → `6f3c7ea` and the final proofreading commit; see `git log`.

Recompute these figures on every sync. They are a baseline, not constants.
