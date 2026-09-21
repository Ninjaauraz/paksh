"""
story_graph.py - the READ side of Story Intelligence: an internal, programmatic story graph. No UI, no writes.

    g = StoryGraph(conn, event_id)          # conn: any sqlite3 connection with sqlite3.Row rows
    g.independent_reports()                 # Q1  which reports are independent acts of reporting?
    g.derived_reports()                     # Q2  which merely repeat / derive from others?
    g.derives_from(article_id)              # Q3  what does this article derive from?
    g.earliest_report()                     # Q4  which report came first, on what evidence?
    g.developments()                        # Q5  what changed over time?
    g.figure_changes()                      # Q6  where do reported figures update or disagree?
    g.development_corroboration()           # Q7  which developments have one source vs several?
    g.related_stories()                     # Q8  which other stories is this one related to? (event_relationships)
    g.timeline()                            # Q9  chronology - published_at / first_seen_at / detected_at kept distinct
    g.provenance(article_id)                # Q10 article -> publisher -> owner -> lean -> reporting event -> origin
    g.summary()                             # counts (independent origins are NOT the article count)

Words matter and are fixed here: an "independent" report was not derived from another in this corpus as far as the text
shows; it is not "verified". A "contradiction" is two reports stating different figures; it is not "false". Every
answer carries its confidence and the evidence the engine used. Stories that have not been analysed answer with empty
lists (never an error) so the UI/contract can treat "no intelligence yet" as a normal state.
"""
import json


def _j(s):
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}


class StoryGraph:
    def __init__(self, conn, event_id):
        self.conn = conn
        self.event_id = event_id
        self._has = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # ---- helpers -------------------------------------------------------------
    def _rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)] if "si_story_state" in self._has else []

    def analysed(self):
        return bool(self._rows("SELECT 1 FROM si_story_state WHERE event_id=?", (self.event_id,)))

    def _articles(self):
        return self._rows("SELECT * FROM si_reporting_event_articles WHERE event_id=? ORDER BY order_time, article_id", (self.event_id,))

    def _titles(self):
        out = {}
        for r in self.conn.execute("SELECT id, title, source FROM articles WHERE event_id=?", (self.event_id,)) if "articles" in self._has else []:
            out[r[0]] = {"title": r[1], "source": r[2]}
        return out

    def _lean_owner(self, source):
        try:
            import sources
            lean = sources.LEAN_BY_SOURCE.get(source)
            return sources.OWNER_BY_SOURCE.get(source, source), lean
        except Exception:
            return source, None

    # ---- Q1 / Q2 ------------------------------------------------------------------
    def independent_reports(self):
        return [{"article_id": a["article_id"], "source": self._titles().get(a["article_id"], {}).get("source"), "reporting_event_root": a["reporting_event_root"],
                 "reason": a["reason"], "confidence": a["confidence"], "evidence": _j(a["evidence_json"])}
                for a in self._articles() if a["role"] == "INDEPENDENT"]

    def derived_reports(self):
        return [{"article_id": a["article_id"], "role": a["role"], "derives_from_article_id": a["derives_from_article_id"],
                 "derives_from_external": a["derives_from_external"], "reason": a["reason"], "confidence": a["confidence"],
                 "evidence": _j(a["evidence_json"])}
                for a in self._articles() if a["role"] in ("DERIVED", "ATTRIBUTED_REPETITION")]

    # ---- Q3 ---------------------------------------------------------------------
    def derives_from(self, article_id):
        for a in self._articles():
            if a["article_id"] == article_id:
                return {"article_id": article_id, "role": a["role"], "article": a["derives_from_article_id"], "external": a["derives_from_external"],
                        "reason": a["reason"], "confidence": a["confidence"], "evidence": _j(a["evidence_json"])}
        return None

    # ---- Q4 ---------------------------------------------------------------------
    def earliest_report(self):
        arts = self._articles()
        if not arts:
            return None
        a = arts[0]
        return {"article_id": a["article_id"], "published_at": a["published_at"], "first_seen_at": a["first_seen_at"],
                "order_time": a["order_time"], "order_basis": a["order_basis"],
                "note": "earliest in Paksh's corpus by " + ("its publish time" if a["order_basis"] == "published" else "a weaker basis (" + str(a["order_basis"]) + ")")
                        + "; not necessarily the first report anywhere"}

    # ---- Q5 / Q7 ----------------------------------------------------------------
    def developments(self):
        return self._rows("SELECT dev_key, type, description, trigger_article_id, event_time, published_at, first_seen_at, detected_at, "
                          "confidence, corroborating_owners, order_basis FROM si_developments WHERE event_id=? ORDER BY COALESCE(published_at, first_seen_at), dev_key",
                          (self.event_id,))

    def development_corroboration(self):
        ds = self.developments()
        return {"single_source": [d for d in ds if (d["corroborating_owners"] or 0) <= 1],
                "corroborated": [d for d in ds if (d["corroborating_owners"] or 0) >= 2]}

    # ---- Q6 ---------------------------------------------------------------------
    def figure_changes(self):
        return [{"rel_type": r["rel_type"], "confidence": r["confidence"], **_j(r["evidence_json"])}
                for r in self._rows("SELECT rel_type, confidence, evidence_json FROM si_relationships WHERE event_id=? AND rel_type IN ('UPDATES','CONTRADICTS')",
                                    (self.event_id,))]

    # ---- Q8 ---------------------------------------------------------------------
    def related_stories(self):
        if "event_relationships" not in self._has:
            return []
        out = []
        for r in self.conn.execute("SELECT previous_event_id, current_event_id, relationship_type FROM event_relationships "
                                   "WHERE status='accepted' AND (previous_event_id=? OR current_event_id=?)", (self.event_id, self.event_id)):
            other = r[0] if r[1] == self.event_id else r[1]
            out.append({"event_id": other, "relationship_type": r[2], "direction": "earlier" if r[1] == self.event_id else "later"})
        return out

    # ---- Q9 ---------------------------------------------------------------------
    def timeline(self):
        titles = self._titles()
        rows = []
        for a in self._articles():
            rows.append({"kind": "report", "article_id": a["article_id"], "role": a["role"], "title": titles.get(a["article_id"], {}).get("title"),
                         "event_time": None, "published_at": a["published_at"], "first_seen_at": a["first_seen_at"], "detected_at": None,
                         "order_time": a["order_time"], "order_basis": a["order_basis"]})
        for d in self.developments():
            rows.append({"kind": "development", "type": d["type"], "description": d["description"], "article_id": d["trigger_article_id"],
                         "event_time": d["event_time"], "published_at": d["published_at"], "first_seen_at": d["first_seen_at"],
                         "detected_at": d["detected_at"], "order_time": d["published_at"] or d["first_seen_at"], "order_basis": d["order_basis"]})
        rows.sort(key=lambda r: (str(r["order_time"] or ""), r["kind"] != "report"))
        return rows

    # ---- Q10 ---------------------------------------------------------------------
    def provenance(self, article_id):
        a = next((x for x in self._articles() if x["article_id"] == article_id), None)
        if not a:
            return None
        src = self._titles().get(article_id, {}).get("source")
        owner, lean = self._lean_owner(src)
        ev = self._rows("SELECT independence, confidence, origin_external FROM si_reporting_events WHERE event_id=? AND root_article_id=?",
                        (self.event_id, a["reporting_event_root"]))
        ev = ev[0] if ev else {}
        return {"article_id": article_id, "source": src, "owner": owner, "lean": lean, "role": a["role"],
                "reporting_event_root": a["reporting_event_root"], "reporting_event_independence": ev.get("independence"),
                "origin_external": ev.get("origin_external"), "derives_from_article_id": a["derives_from_article_id"]}

    # ---- summary ----------------------------------------------------------------
    def summary(self):
        arts = self._articles()
        evs = self._rows("SELECT independence, origin_external FROM si_reporting_events WHERE event_id=?", (self.event_id,))
        return {"analysed": self.analysed(), "articles": len(arts),
                "reporting_events": len(evs),
                "independent_origins": sum(1 for e in evs if e["independence"] == "INDEPENDENT"),
                "wire_or_external_origins": sum(1 for e in evs if e["origin_external"]),
                "uncertain_events": sum(1 for e in evs if e["independence"] == "UNCERTAIN"),
                "developments": len(self.developments()),
                "figure_disagreements": sum(1 for f in self.figure_changes() if f["rel_type"] == "CONTRADICTS")}
