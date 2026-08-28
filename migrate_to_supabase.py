"""
migrate_to_supabase.py - Paksh 2.0 Phase 1: SQLite -> Supabase content migration.

Reads paksh.db (the pipeline's SOURCE OF TRUTH - unchanged by this script) and EMITS
idempotent SQL files that mirror its content into the new Supabase content tables
(topics, outlets, storylines, events, articles - see the paksh_content_schema_v1
migration). It does NOT connect to Postgres directly: this repo has no Postgres
driver and no service-role credential in its environment (by design - see
CLAUDE.md: secrets never live in source files), so the emitted .sql files are the
actual migration artifact. Apply them with a privileged connection (the Supabase
MCP tool's execute_sql, or `psql`/any Postgres client using the service-role key,
outside this repo).

SAFETY
------
* Read-only against paksh.db. Never writes to SQLite.
* Every statement is `INSERT ... ON CONFLICT (id) DO UPDATE SET ...` (or the
  natural key for topics/outlets) - safe to re-run, safe to re-apply, safe to
  resume after a partial run. Running it twice produces the same end state.
* Derived fields (dominant lean, blindspot, per-lean counts) are computed by
  IMPORTING database.py's own functions - never reimplemented - so the migrated
  rows are guaranteed identical to what the current pipeline/site already shows.
* Existing IDs are preserved exactly: events.id and articles.id in Supabase equal
  the SQLite integer ids, because Supabase's saved_stories.story_id /
  reading_history.story_id already reference these ids as plain text.

SCOPE (Phase 1 - see the implementation report for the reasoning)
-------------------------------------------------------------------
Outlets: the FULL registry (sources.py + verified_registry.py). Small, reference
data, needed for the read API's outlet/lean joins to mean anything at all.

Events + articles: the most recent N non-demo events (--limit, default 500) and
their member articles - a real, representative, high-value validation slice (the
same events the homepage actually shows), not the full ~13,500/373,000 corpus.
This is a deliberate, incremental first step (see the philosophy section of the
Phase 1 brief: "choose incremental over one large migration"). Re-running this
script with a larger --limit (or none, for everything) is the SAME idempotent
operation - no code change needed to complete the backfill later.

Storylines: computed via storylines.build_storylines() over the FULL current
corpus (so linkage is correct even for a partial migrated batch), then only the
storylines actually touching a migrated event are emitted.

Embeddings: intentionally never migrated (see CLAUDE.md / the architecture audit -
they are a local pipeline working-cache, not a serving concern).

Usage:
    py migrate_to_supabase.py --limit 500 --emit-dir migration_sql
    py migrate_to_supabase.py --limit 0 --emit-dir migration_sql   # 0 = everything
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import database
import sources
from verified_registry import VERIFIED_SOURCES

try:
    from storylines import build_storylines
except ImportError:
    build_storylines = None

TOPIC_HI = {
    "Politics": "राजनीति", "Economy": "अर्थव्यवस्था", "International": "अंतरराष्ट्रीय",
    "Sports": "खेल", "Crime & Law": "अपराध व कानून", "Science & Tech": "विज्ञान व तकनीक",
    "Health": "स्वास्थ्य", "Entertainment": "मनोरंजन", "Environment": "पर्यावरण",
    "Society": "समाज", "General": "सामान्य",
}


# ---------------------------------------------------------------- SQL helpers

def _s(v):
    """Safe SQL string literal, or NULL."""
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def _b(v):
    return "TRUE" if v else "FALSE"


def _nb(v):
    """Nullable SQL boolean literal. Unlike _b() (which treats None as falsy -
    correct for degraded, always a real bool), content_complete's None is a
    distinct, meaningful 'grandfathered/pre-gate' state and must stay SQL NULL,
    never collapse to FALSE (which would wrongly hide the row)."""
    if v is None:
        return "NULL"
    return "TRUE" if v else "FALSE"


def _n(v):
    return "NULL" if v is None else str(v)


def _j(v):
    """Safe SQL jsonb literal, or NULL."""
    if v is None:
        return "NULL"
    return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def _ts(v):
    """ISO8601-ish string -> a safe ::timestamptz literal, or NULL."""
    if not v:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'::timestamptz"


def _batches(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _write(emit_dir: Path, name: str, statements):
    """Write one .sql file per (already-batched) list of complete statements."""
    if not statements:
        return
    path = emit_dir / name
    path.write_text("\n\n".join(statements) + "\n", encoding="utf-8")
    print(f"  wrote {path}  ({len(statements)} statement(s))")


# ---------------------------------------------------------------- topics

def build_topics_sql(topic_names):
    rows = []
    for name in sorted(topic_names):
        rows.append(
            f"INSERT INTO public.topics (name, name_hi) VALUES ({_s(name)}, {_s(TOPIC_HI.get(name))}) "
            f"ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;"
        )
    return rows


# ---------------------------------------------------------------- outlets

def _outlet_rows(referenced_names=None):
    """Unify sources.py (curated, voting per its own rules) and verified_registry.py
    (generated, vote flag already resolved) into one row shape. Curated always wins
    on name collision, matching sources.py's own precedence (setdefault).

    `referenced_names`, if given, limits the verified-registry (non-curated) portion
    to outlets that actually appear as a source among the events being migrated.
    The full 124-outlet curated roster is always included regardless (it's small
    and is the part the bias-bar arithmetic actually depends on). The verified
    registry has ~6,500 entries whose only current job is GDELT domain attribution
    during ingestion (unchanged, still Python-data-driven there) - for a partial
    content migration, shipping all of them to Supabase has no reader-facing
    benefit and produces multi-megabyte SQL for no reason. A full-corpus migration
    run (--limit 0) naturally references far more outlets and would include
    correspondingly more of the registry - this scoping is data-driven, not a
    hardcoded cap."""
    seen = set()
    rows = []
    for s in sources.SOURCES:
        name = s["name"]
        seen.add(name)
        rows.append({
            "name": name, "domain": sources._host(s.get("website", "")) or None,
            "owner": s.get("owner", name), "lean": s.get("lean"), "label": s.get("label"),
            "confidence": s.get("confidence"), "contested": bool(s.get("contested")),
            "review_status": s.get("review_status"), "last_reviewed": s.get("last_reviewed"),
            "region": s.get("region"), "country": None, "language": s.get("language"),
            "is_curated": True, "votes": s.get("region") != "International",
            "rank": None, "rationale": s.get("rationale"), "axes": s.get("axes"),
        })
    for v in VERIFIED_SOURCES:
        name = v["name"]
        if name in seen:
            continue
        if referenced_names is not None and name not in referenced_names:
            continue
        seen.add(name)
        rows.append({
            "name": name, "domain": v.get("domain"), "owner": name, "lean": v.get("lean"),
            "label": v.get("label"), "confidence": v.get("confidence"), "contested": False,
            "review_status": "provisional", "last_reviewed": None, "region": None,
            "country": v.get("country"), "language": v.get("language"), "is_curated": False,
            "votes": bool(v.get("vote")), "rank": v.get("rank"), "rationale": None,
            "axes": None,
        })
    return rows


def build_outlets_sql(rows):
    cols = ("name", "domain", "owner", "lean", "label", "confidence", "contested",
            "review_status", "last_reviewed", "region", "country", "language",
            "is_curated", "votes", "rank", "rationale")
    out = []
    for r in rows:
        vals = (
            _s(r["name"]), _s(r["domain"]), _s(r["owner"]), _s(r["lean"]), _s(r["label"]),
            _s(r["confidence"]), _b(r["contested"]), _s(r["review_status"]),
            _s(r["last_reviewed"]), _s(r["region"]), _s(r["country"]), _s(r["language"]),
            _b(r["is_curated"]), _b(r["votes"]), _n(r["rank"]), _s(r["rationale"]),
        )
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "name")
        out.append(
            f"INSERT INTO public.outlets ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
            f"ON CONFLICT (name) DO UPDATE SET {set_clause}, updated_at = now();"
        )
    return out


# ---------------------------------------------------------------- events / articles

def _event_row(row):
    """Shape one SQLite `events` row (+ parsed analysis_json) into the Supabase
    `events` column set, using database.py's OWN derived-field functions so the
    migrated values are guaranteed identical to what the site already computes."""
    data = json.loads(row["analysis_json"])
    lc = database.lean_counts_from(data)
    dominant = database.dominant_lean(lc)
    blindspot = database.compute_blindspot(lc)
    cov = data.get("coverage", {}) or {}
    region = data.get("region")
    if region not in ("India", "World"):
        region = "World" if data.get("topic") == "International" else "India"
    return {
        "id": row["id"], "title": data.get("title") or row["title"],
        "title_hi": data.get("title_hi"), "summary": data.get("summary"),
        "summary_hi": data.get("summary_hi"),
        "summary_points": data.get("summary_points") or [],
        "summary_points_hi": data.get("summary_points_hi") or [],
        "topic": data.get("topic") or "Society", "region": region,
        "lean_left": lc.get("left", 0), "lean_center": lc.get("center", 0),
        "lean_right": lc.get("right", 0),
        "international_count": cov.get("international", {}).get("count", 0),
        "unrated_count": cov.get("unrated", {}).get("count", 0),
        "total_sources": len(data.get("sources", [])),
        "dominant_lean": dominant["side"] if dominant else None,
        "dominant_pct": dominant["pct"] if dominant else None,
        "blindspot_side": blindspot["side"] if blindspot else None,
        "blindspot_pct": blindspot["pct"] if blindspot else None,
        "coverage": cov, "framing": data.get("framing") or {},
        "framing_hi": data.get("framing_hi") or {}, "sources": data.get("sources") or [],
        "analysis_json": data, "image_url": data.get("image_url") or None,
        "is_demo": bool(row["is_demo"]), "degraded": bool(data.get("degraded")),
        "summary_method": data.get("summary_method"),
        # Paksh 7B: pass through AS-IS, never recomputed here. None (an event whose
        # local analysis_json predates this field) stays None on sync - it must NOT
        # be resolved to a fresh True/False at sync time, or a re-sync of an already-
        # visible grandfathered row could silently flip it incomplete based on a
        # local-only re-derivation this migration script has no business making.
        "content_complete": data.get("content_complete"),
        "storyline_id": None,   # filled in after storyline linking, see main()
        "published_at": data.get("published_at"), "created_at": row["created_at"],
    }


def build_events_sql(rows):
    cols = ("id", "title", "title_hi", "summary", "summary_hi", "summary_points",
            "summary_points_hi", "topic", "region", "lean_left", "lean_center",
            "lean_right", "international_count", "unrated_count", "total_sources",
            "dominant_lean", "dominant_pct", "blindspot_side", "blindspot_pct",
            "coverage", "framing", "framing_hi", "sources", "analysis_json",
            "image_url", "is_demo", "degraded", "summary_method", "content_complete",
            "storyline_id", "published_at", "created_at")
    out = []
    for r in rows:
        vals = (
            _n(r["id"]), _s(r["title"]), _s(r["title_hi"]), _s(r["summary"]),
            _s(r["summary_hi"]), _j(r["summary_points"]), _j(r["summary_points_hi"]),
            _s(r["topic"]), _s(r["region"]), _n(r["lean_left"]), _n(r["lean_center"]),
            _n(r["lean_right"]), _n(r["international_count"]), _n(r["unrated_count"]),
            _n(r["total_sources"]), _s(r["dominant_lean"]), _n(r["dominant_pct"]),
            _s(r["blindspot_side"]), _n(r["blindspot_pct"]), _j(r["coverage"]),
            _j(r["framing"]), _j(r["framing_hi"]), _j(r["sources"]), _j(r["analysis_json"]),
            _s(r["image_url"]), _b(r["is_demo"]), _b(r["degraded"]), _s(r["summary_method"]),
            _nb(r["content_complete"]),
            _s(r["storyline_id"]), _ts(r["published_at"]), _ts(r["created_at"]),
        )
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        out.append(
            f"INSERT INTO public.events ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause}, synced_at = now();"
        )
    return out


def build_articles_sql(rows):
    cols = ("id", "event_id", "source", "language", "title", "url", "summary",
            "image_url", "published", "fetched_at")
    out = []
    for r in rows:
        vals = (
            _n(r["id"]), _n(r["event_id"]), _s(r["source"]), _s(r["language"]),
            _s(r["title"]), _s(r["url"]), _s(r["summary"]), _s(r["image_url"]),
            _s(r["published"]), _ts(r["fetched_at"]),
        )
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        out.append(
            f"INSERT INTO public.articles ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause};"
        )
    return out


def build_storylines_sql(storylines, touched_ids):
    out = []
    for s in storylines:
        if s["id"] not in touched_ids:
            continue
        cols = ("id", "title", "title_hi", "topic", "region", "n_events",
                "starts_at", "ends_at", "updated_at")
        vals = (
            _s(s["id"]), _s(s.get("title")), _s(s.get("title_hi")), _s(s.get("topic")),
            _s(s.get("region")), _n(s.get("n_events")), _ts(s.get("start")),
            _ts(s.get("end")), _ts(s.get("updated_at")),
        )
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        out.append(
            f"INSERT INTO public.storylines ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause};"
        )
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500,
                     help="most recent N non-demo events to migrate (0 = all)")
    ap.add_argument("--emit-dir", default="migration_sql", help="output directory for .sql files")
    ap.add_argument("--batch-events", type=int, default=10)
    ap.add_argument("--batch-articles", type=int, default=200)
    ap.add_argument("--batch-outlets", type=int, default=1500)
    ap.add_argument("--full-outlet-registry", action="store_true",
                     help="ship the ENTIRE verified_registry.py (~6,500 rows) instead of just "
                          "outlets actually referenced by the migrated events. Off by default "
                          "for a partial migration - see _outlet_rows()'s docstring.")
    args = ap.parse_args()

    emit_dir = Path(args.emit_dir)
    emit_dir.mkdir(parents=True, exist_ok=True)

    database.init_db()
    conn = database.get_connection()

    print("=== 1) events (queried first, so outlets can be scoped to what's referenced) ===")
    q = "SELECT id, title, analysis_json, is_demo, created_at FROM events WHERE COALESCE(is_demo,0)=0 ORDER BY id DESC"
    if args.limit:
        q += f" LIMIT {int(args.limit)}"
    event_sql_rows = conn.execute(q).fetchall()
    print(f"  migrating {len(event_sql_rows)} of {conn.execute('SELECT COUNT(*) c FROM events WHERE COALESCE(is_demo,0)=0').fetchone()['c']} total non-demo events")
    event_rows = [_event_row(r) for r in event_sql_rows]
    migrated_ids = {r["id"] for r in event_rows}

    print("\n=== 1b) outlets ===")
    referenced = None
    if not args.full_outlet_registry:
        referenced = set()
        for r in event_rows:
            for s in r["sources"]:
                referenced.add(s["source"])
    outlet_rows = _outlet_rows(referenced)
    print(f"  {len(outlet_rows)} outlets ({sum(1 for r in outlet_rows if r['is_curated'])} curated, "
          f"{sum(1 for r in outlet_rows if not r['is_curated'])} verified-registry"
          f"{' — scoped to referenced outlets' if referenced is not None else ' — FULL registry'})")
    for i, batch in enumerate(_batches(outlet_rows, args.batch_outlets)):
        _write(emit_dir, f"01_outlets_{i:03d}.sql", build_outlets_sql(batch))

    # topics MUST be written before storylines/events: both have a FK on topic ->
    # topics(name), so applying storylines/events first would fail with a foreign
    # key violation. Compute storylines first (needs the full corpus in memory
    # regardless), but WRITE topics' file ahead of it in application order.
    print("\n=== 3) storylines (computed over the FULL corpus for correct linkage) ===")
    storyline_map = {}
    storylines_out = []
    touched = set()
    if build_storylines is not None:
        try:
            all_events = database.get_all_events()
            storylines_out, story_map = build_storylines(all_events)
            storyline_map = story_map
            for r in event_rows:
                r["storyline_id"] = storyline_map.get(r["id"])
            touched = {sid for eid, sid in storyline_map.items() if eid in migrated_ids}
            print(f"  {len(storylines_out)} storylines total; {len(touched)} touch a migrated event")
        except Exception as e:
            print(f"  storylines: skipped ({e})")
    else:
        print("  storylines module unavailable, skipped")

    print("\n=== 4) topics (written BEFORE storylines/events - FK dependency) ===")
    topic_names = {r["topic"] for r in event_rows} | {s.get("topic") for s in storylines_out if s.get("topic")} | set(TOPIC_HI.keys())
    topic_names.discard(None)
    _write(emit_dir, "02_topics.sql", build_topics_sql(topic_names))
    for i, batch in enumerate(_batches(storylines_out, 500)):
        _write(emit_dir, f"03_storylines_{i:03d}.sql", build_storylines_sql(batch, touched))

    print("\n=== 5) events (SQL) ===")
    for i, batch in enumerate(_batches(event_rows, args.batch_events)):
        _write(emit_dir, f"04_events_{i:03d}.sql", build_events_sql(batch))

    print("\n=== 6) articles (for the migrated events only) ===")
    if migrated_ids:
        ph = ",".join(str(i) for i in migrated_ids)
        art_rows = conn.execute(
            f"SELECT id, event_id, source, language, title, url, summary, image_url, published, fetched_at "
            f"FROM articles WHERE event_id IN ({ph})"
        ).fetchall()
    else:
        art_rows = []
    print(f"  {len(art_rows)} articles belonging to the migrated events")
    for i, batch in enumerate(_batches([dict(r) for r in art_rows], args.batch_articles)):
        _write(emit_dir, f"05_articles_{i:03d}.sql", build_articles_sql(batch))

    conn.close()
    print(f"\nDone. SQL files written to {emit_dir}/ - apply them with a privileged "
          f"Postgres connection (service role). Nothing was sent over the network by this script.")


if __name__ == "__main__":
    main()
