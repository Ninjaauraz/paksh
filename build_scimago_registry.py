"""
build_scimago_registry.py - one-off generator (dev tool, not part of any cycle)
===============================================================================

Reads the SCImago Media Ranking CSV (a public global ranking of news outlets:
name, domain, country, region, language, typology, rank) and writes
`scimago_registry.py` - a PURE-DATA module listing every usable outlet as a
REFERENCE source for Paksh.

Why this exists
---------------
Paksh attributes each GDELT-ingested article to a named outlet via
`resolve_source()` -> DOMAIN_TO_SOURCE. Any domain we don't know resolves to a
bare registrable domain (e.g. "nytimes.com") and clusters as an anonymous
long-tail outlet. Mapping the SCImago domains means that when any of these
outlets covers India, we attribute it to a real name and it adds coverage +
clustering breadth.

INVARIANTS RESPECTED
--------------------
* NO LEAN IS EVER GUESSED. Every generated entry is lean="unrated". A ranking
  is NOT a political-lean judgement, and lean labels are editorial (Sameer's
  call). Unrated outlets never vote in the Left/Centre/Right bias bar, and
  analyze.py drops all-unrated clusters as junk - so this is purely additive.
* Curated editorial SOURCES always win: any domain already known to the
  hand-curated registry is skipped here (never overridden).

Re-run:  py build_scimago_registry.py
Output:  scimago_registry.py  (checked into the repo; imported by sources.py)
"""

import csv
import re
from pathlib import Path

# Reuse the EXACT domain-normalisation logic the runtime uses, so dedupe and
# the "already curated?" test match resolve_source() precisely. IMPORTANT: build
# the curated-domain set from the hand-written SOURCES only - NOT from
# DOMAIN_TO_SOURCE, which sources.py has already merged THIS registry into (that
# would make every host look "already curated" and wipe the output to zero).
from sources import SOURCES as _CURATED_SOURCES, _host

CURATED_DOMAINS = {_host(s["website"]) for s in _CURATED_SOURCES if s.get("website")}

CSV_PATH = Path(r"C:\Users\ambuj\Downloads\SCImago Media Ranking.csv")
OUT_PATH = Path(__file__).with_name("scimago_registry.py")

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9\-]+)+$")


def _read_rows():
    """Yield CSV rows, tolerant of the file's encoding (SCImago exports vary)."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with CSV_PATH.open("r", encoding=enc, newline="") as fh:
                rows = list(csv.DictReader(fh))
            # sanity: header parsed as expected
            if rows and "Domain" in rows[0]:
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
    """First listed language -> Paksh code. en / hi are first-class; everything
    else is 'other' (still ingested if GDELT tags it en/hi, this is metadata)."""
    first = (raw or "").split("/")[0].strip().lower()
    if first.startswith("eng"):
        return "en"
    if first.startswith("hin"):
        return "hi"
    return "other"


def _curated_owns(host: str) -> bool:
    """True if the curated editorial registry already resolves this host - either
    an exact match or a curated apex of which `host` is a subdomain. Mirrors the
    rated-match logic in resolve_source() so we never shadow a human-leaned outlet."""
    if host in CURATED_DOMAINS:
        return True
    return any(host.endswith("." + ch) for ch in CURATED_DOMAINS)


def build():
    rows = _read_rows()
    by_domain = {}          # FULL host -> chosen entry (lowest rank wins on dupes)
    skipped_bad = skipped_curated = 0

    for r in rows:
        name = _clean_name(r.get("Media"))
        host = _clean_domain(r.get("Domain"))   # full host, e.g. economictimes.indiatimes.com
        if not name or not _DOMAIN_RE.match(host):
            skipped_bad += 1
            continue

        # Key by FULL host (like the curated registry) so distinct brands sharing
        # one apex (indiatimes.com, india.com) stay separate and are never
        # mis-attributed to each other.
        if _curated_owns(host):
            skipped_curated += 1
            continue

        try:
            rank = int(str(r.get("Global_rank", "")).strip() or 10**9)
        except ValueError:
            rank = 10**9

        country = _clean_name(r.get("Country"))
        entry = {
            "name": name,
            "domain": host,
            "country": country,
            "region": _clean_name(r.get("Region")),
            "language": _lang_code(r.get("Language")),
            "rank": rank,
            "is_india": country.lower() == "india",
        }
        prev = by_domain.get(host)
        if prev is None or rank < prev["rank"]:
            by_domain[host] = entry

    # Deterministic order: India first (Paksh's home market), then by global rank,
    # then name - so the generated file has a stable, reviewable diff.
    entries = sorted(
        by_domain.values(),
        key=lambda e: (not e["is_india"], e["rank"], e["name"].lower()),
    )

    # Guarantee every generated name is UNIQUE and never equals a curated name.
    # A shared name would make DOMAIN_TO_SOURCE route this host to that name and
    # inherit its lean/region (e.g. a foreign "The Guardian" borrowing the UK
    # Guardian's 'left'), or silently merge two distinct outlets. Disambiguate
    # with country, then host, so each stays its own non-voting entry.
    from sources import SOURCES as _CURATED
    used = {s["name"] for s in _CURATED}
    for e in entries:
        base = e["name"]
        if base not in used:
            used.add(base)
            continue
        cand = f"{base} ({e['country']})" if e["country"] else base
        if cand in used:
            cand = f"{base} ({e['domain']})"
        # extremely unlikely, but keep going until unique
        n = 2
        while cand in used:
            cand = f"{base} ({e['domain']}#{n})"
            n += 1
        e["name"] = cand
        used.add(cand)

    _write(entries, skipped_bad, skipped_curated, len(rows))
    return entries


def _write(entries, skipped_bad, skipped_curated, total_rows):
    india = sum(1 for e in entries if e["is_india"])
    lines = []
    lines.append('"""')
    lines.append("scimago_registry.py - GENERATED, do not edit by hand.")
    lines.append("Regenerate with:  py build_scimago_registry.py")
    lines.append("")
    lines.append("Reference outlets from the SCImago Media Ranking, used ONLY to")
    lines.append("attribute GDELT-ingested articles to named outlets (domain")
    lines.append("resolution + clustering breadth). Every entry is lean-UNRATED and")
    lines.append("NON-VOTING: a ranking is not a political-lean judgement, and lean")
    lines.append("labels are editorial. These never move the bias bar.")
    lines.append("")
    lines.append(f"Rows read: {total_rows} | usable: {len(entries)} "
                 f"(India: {india}) | skipped bad-domain: {skipped_bad} | "
                 f"skipped already-curated: {skipped_curated}")
    lines.append('"""')
    lines.append("")
    lines.append("SCIMAGO_SOURCES = [")
    for e in entries:
        lines.append(
            "    {"
            f"\"name\": {e['name']!r}, \"domain\": {e['domain']!r}, "
            f"\"country\": {e['country']!r}, \"region\": {e['region']!r}, "
            f"\"language\": {e['language']!r}, \"rank\": {e['rank']}, "
            f"\"is_india\": {e['is_india']}, \"lean\": \"unrated\""
            "},"
        )
    lines.append("]")
    lines.append("")
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH.name}: {len(entries)} reference outlets "
          f"(India {india}) | skipped bad {skipped_bad}, curated {skipped_curated}")


if __name__ == "__main__":
    build()
