"""
build_verified_registry.py - one-off generator (dev tool, not part of any cycle)
================================================================================

Reads the editor-verified source-lean CSV (Sameer trained a model on the MBFC
rubric, rated every outlet, and PERSONALLY VERIFIED each lean) and writes
`verified_registry.py` - a PURE-DATA module listing every outlet as a reference
source for Paksh, now carrying a lean label.

This SUPERSEDES scimago_registry.py: the CSV is a strict superset of the SCImago
domains, but every row also has a hand-verified `Paksh_Lean`. sources.py imports
this module instead of the old (lean-unrated) one.

What it does (and the invariants it respects)
----------------------------------------------
* DOMAIN ATTRIBUTION for the whole long tail. Every domain -> named outlet, so a
  GDELT-ingested article is credited to a real outlet (coverage + clustering
  breadth), exactly like the old registry.
* VOTING is decided by COUNTRY, to honour the bias-bar invariant:
    - FOREIGN outlets (country != India): `vote=False`. sources.py adds them to
      INTERNATIONAL_SOURCES, so analyze.lean_of() maps them to the NON-VOTING
      "international" tier. Their lean is calibrated to a home-market / US (MBFC)
      spectrum, NOT India's, so it must never move the India Left/Centre/Right
      bar. It is retained only as metadata / for a future transparency view.
    - INDIA outlets (country == India): `vote=True`. sources.py merges their
      lean into LEAN_BY_SOURCE so they vote in the bias bar. (Editor's explicit
      decision - the leans here are hand-verified by Sameer.)
* CURATED editorial SOURCES ALWAYS WIN. Any domain the hand-curated registry
  already owns is skipped here (never overridden). Additionally, to protect
  ONE-VOTE-PER-OWNER, an India (voting) row whose name matches a curated outlet
  is skipped rather than added as a second voter; foreign (non-voting) name
  clashes are disambiguated instead (they cannot double-count a vote).

Re-run:  py build_verified_registry.py
Output:  verified_registry.py  (checked into the repo; imported by sources.py)
"""

import csv
import re
from pathlib import Path

# Reuse the EXACT domain-normalisation the runtime uses, so dedupe and the
# "already curated?" test match resolve_source() precisely. Build the curated set
# from the hand-written SOURCES only - NOT DOMAIN_TO_SOURCE (which sources.py has
# already merged this registry into; that would make every host look curated).
from sources import SOURCES as _CURATED_SOURCES, _host

CURATED_DOMAINS = {_host(s["website"]) for s in _CURATED_SOURCES if s.get("website")}
CURATED_NAMES = {s["name"] for s in _CURATED_SOURCES}

CSV_PATH = Path(r"C:\Users\ambuj\Downloads\paksh_source_lean_complete_6643_v04.csv")
OUT_PATH = Path(__file__).with_name("verified_registry.py")

# Known same-publisher-different-domain duplicates the name/domain dedup above
# can't catch (different name string AND different domain from the curated
# entry). Each CSV row whose domain is a key here is the SAME outlet as the
# curated one, just under another ccTLD/domain - skip generating a second
# voter for it entirely. sources.py adds the domain -> curated-name resolution
# manually (see MANUAL_DOMAIN_ALIASES there), so the domain still attributes
# articles correctly, it just votes as the curated outlet, once.
KNOWN_DUPLICATE_DOMAINS = {
    "ndtv.in": "NDTV",   # same publisher as curated ndtv.com, listed twice in the CSV
}

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9\-]+)+$")

# CSV Paksh_Lean -> the pipeline's lean vocabulary ("left"|"center"|"right").
_LEAN_MAP = {"left": "left", "centre": "center", "center": "center", "right": "right"}
_LABEL = {"left": "Lean Left", "center": "Centre", "right": "Lean Right"}


def _read_rows():
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with CSV_PATH.open("r", encoding=enc, newline="") as fh:
                rows = list(csv.DictReader(fh))
            if rows and "Domain" in rows[0] and "Paksh_Lean" in rows[0]:
                return rows
        except (UnicodeDecodeError, LookupError):
            continue
    raise SystemExit(f"Could not read {CSV_PATH}")


def _clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def _clean_domain(raw: str) -> str:
    d = (raw or "").lower().strip()
    d = re.sub(r"^https?://", "", d).split("/")[0].strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def _lang_code(raw: str) -> str:
    first = (raw or "").split("/")[0].strip().lower()
    if first.startswith("eng"):
        return "en"
    if first.startswith("hin"):
        return "hi"
    return "other"


def _curated_owns(host: str) -> bool:
    """True if the curated editorial registry already resolves this host - exact
    match or a curated apex of which `host` is a subdomain. Mirrors resolve_source()
    so we never shadow (or duplicate) a hand-leaned outlet."""
    if host in CURATED_DOMAINS:
        return True
    return any(host.endswith("." + ch) for ch in CURATED_DOMAINS)


def build():
    rows = _read_rows()
    by_domain = {}          # FULL host -> chosen entry (best confidence / rank wins)
    skipped_bad = skipped_curated = skipped_dupe_vote = skipped_no_lean = 0
    skipped_known_dupe = 0

    _CONF_ORDER = {"high": 0, "medium": 1, "low": 2}

    for r in rows:
        name = _clean_name(r.get("Media"))
        host = _clean_domain(r.get("Domain"))
        if not name or not _DOMAIN_RE.match(host):
            skipped_bad += 1
            continue

        lean = _LEAN_MAP.get((r.get("Paksh_Lean") or "").strip().lower())
        if not lean:
            skipped_no_lean += 1
            continue

        # Curated editorial outlet already owns this host -> curated wins, skip.
        if _curated_owns(host):
            skipped_curated += 1
            continue

        # Known same-publisher duplicate under a different domain -> curated
        # outlet already votes for this publisher, skip the second voter.
        if host in KNOWN_DUPLICATE_DOMAINS:
            skipped_known_dupe += 1
            continue

        try:
            rank = int(str(r.get("Global_rank", "")).strip() or 10**9)
        except ValueError:
            rank = 10**9
        conf = (r.get("Lean_Confidence") or "").strip().lower()
        country = _clean_name(r.get("Country"))

        entry = {
            "name": name,
            "domain": host,
            "country": country,
            "region": _clean_name(r.get("Region")),
            "language": _lang_code(r.get("Language")),
            "typology": _clean_name(r.get("Typology")),
            "rank": rank,
            "lean": lean,
            "label": _LABEL[lean],
            "confidence": conf if conf in _CONF_ORDER else "low",
            "vote": country.lower() == "india",       # editor's call: India rows vote
        }
        prev = by_domain.get(host)
        # keep the stronger row on a domain clash: higher confidence, then lower rank
        if prev is None or (
            (_CONF_ORDER.get(entry["confidence"], 2), entry["rank"])
            < (_CONF_ORDER.get(prev["confidence"], 2), prev["rank"])
        ):
            by_domain[host] = entry

    # Deterministic order: India first (home market + the voting rows), then by
    # global rank, then name - so the generated file has a stable, reviewable diff.
    entries = sorted(
        by_domain.values(),
        key=lambda e: (not e["vote"], e["rank"], e["name"].lower()),
    )

    # Guarantee every generated name is UNIQUE and never equals a curated name.
    #   * India (voting) rows: a name clash with a curated outlet is a strong
    #     signal it is the SAME publisher -> SKIP it, so we never cast a second
    #     vote for one outlet (protects one-vote-per-owner).
    #   * Foreign (non-voting) rows: disambiguate with country, then domain, so
    #     two distinct outlets never collapse onto one name. They cannot move the
    #     bar, so a duplicate name is only a display/attribution issue.
    used = set(CURATED_NAMES)
    final = []
    for e in entries:
        base = e["name"]
        if base not in used:
            used.add(base)
            final.append(e)
            continue
        if e["vote"]:                                 # same-name Indian outlet -> curated wins
            skipped_dupe_vote += 1
            continue
        cand = f"{base} ({e['country']})" if e["country"] else base
        if cand in used:
            cand = f"{base} ({e['domain']})"
        n = 2
        while cand in used:
            cand = f"{base} ({e['domain']}#{n})"
            n += 1
        e["name"] = cand
        used.add(cand)
        final.append(e)

    _write(final, skipped_bad, skipped_curated, skipped_dupe_vote,
           skipped_no_lean, skipped_known_dupe, len(rows))
    return final


def _write(entries, skipped_bad, skipped_curated, skipped_dupe_vote,
           skipped_no_lean, skipped_known_dupe, total_rows):
    voting = sum(1 for e in entries if e["vote"])
    intl = len(entries) - voting
    lines = []
    lines.append('"""')
    lines.append("verified_registry.py - GENERATED, do not edit by hand.")
    lines.append("Regenerate with:  py build_verified_registry.py")
    lines.append("")
    lines.append("Editor-verified source-lean registry (MBFC-rubric model ratings,")
    lines.append("each lean personally verified by the editor). Used to attribute")
    lines.append("GDELT-ingested articles to named outlets AND to carry a lean.")
    lines.append("")
    lines.append("VOTING RULE (see build_verified_registry.py):")
    lines.append("  vote=True  -> India outlet; sources.py merges its lean into")
    lines.append("               LEAN_BY_SOURCE so it votes in the bias bar.")
    lines.append("  vote=False -> foreign outlet; sources.py adds it to")
    lines.append("               INTERNATIONAL_SOURCES (non-voting international tier).")
    lines.append("               Its lean is home-market/MBFC-calibrated, not India's,")
    lines.append("               so it must never move the India Left/Centre/Right bar.")
    lines.append("")
    lines.append(f"Rows read: {total_rows} | usable: {len(entries)} "
                 f"(voting India: {voting}, non-voting intl: {intl}) | "
                 f"skipped bad-domain: {skipped_bad}, no-lean: {skipped_no_lean}, "
                 f"already-curated: {skipped_curated}, dup-vote: {skipped_dupe_vote}, "
                 f"known-duplicate: {skipped_known_dupe}")
    lines.append('"""')
    lines.append("")
    lines.append("VERIFIED_SOURCES = [")
    for e in entries:
        lines.append(
            "    {"
            f"\"name\": {e['name']!r}, \"domain\": {e['domain']!r}, "
            f"\"country\": {e['country']!r}, \"region\": {e['region']!r}, "
            f"\"language\": {e['language']!r}, \"typology\": {e['typology']!r}, "
            f"\"rank\": {e['rank']}, \"lean\": {e['lean']!r}, "
            f"\"label\": {e['label']!r}, \"confidence\": {e['confidence']!r}, "
            f"\"vote\": {e['vote']}"
            "},"
        )
    lines.append("]")
    lines.append("")
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH.name}: {len(entries)} outlets "
          f"(voting India {voting}, non-voting intl {intl}) | "
          f"skipped bad {skipped_bad}, no-lean {skipped_no_lean}, "
          f"curated {skipped_curated}, dup-vote {skipped_dupe_vote}, "
          f"known-duplicate {skipped_known_dupe}")


if __name__ == "__main__":
    build()
