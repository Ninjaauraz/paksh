"""
test_editorial_revisions_permissions.py - Milestone 1: immutable revisions, the audit chain,
truthful publish states, concurrency/idempotency, rollback, the shared preview/publish gate
and the role policy. Pure and isolated: nothing here builds, writes, commits, pushes or
contacts anything; the gate only DECIDES.

Run:  py test_editorial_revisions_permissions.py
"""
import copy
import dataclasses
import sys

from editorial import gate as G
from editorial import permissions as P
from editorial import revisions as V
from editorial.document import document_hash
from editorial.schema import empty_document

FAILURES = []


def check(label, cond, detail=""):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def doc(title="Headline"):
    return {"schema_version": 1, "stories": {"7": {"title": {"en": title}}}, "placements": []}


T0, T1, T2 = "2026-10-10T06:00:00Z", "2026-10-10T07:00:00Z", "2026-10-10T08:00:00Z"
ED = P.Membership("u-editor", ("editor",))
ADM = P.Membership("u-admin", ("administrator",))
RO = P.Membership("u-reader", ("read_only",))

print("1. immutable, content-addressed revisions")
r1 = V.seal(doc("A"), None, "u-editor", T0)
r2 = V.seal(doc("B"), r1.revision_id, "u-editor", T1)
check("1a: a revision verifies", V.verify(r1) and V.verify(r2))
check("1b: revisions are frozen dataclasses", raises(dataclasses.FrozenInstanceError, lambda: setattr(r1, "doc_json", "{}")))
check("1c: parent links are recorded", r2.parent_id == r1.revision_id and r1.parent_id == "")
check("1d: same content, author and time -> same id (idempotent)", V.seal(doc("A"), None, "u-editor", T0) == r1)
check("1e: hash equals the document hash", r1.doc_hash == document_hash(doc("A")))
tampered = dataclasses.replace(r1, doc_json=r1.doc_json.replace("A", "Z"))
check("1f: tampering with stored content is detected", not V.verify(tampered))
check("1g: ...and refused when reading the document back", raises(V.InvalidDocument, lambda: V.revision_document(tampered)))
tampered2 = dataclasses.replace(r1, author="someone-else")
check("1h: tampering with the author is detected", not V.verify(tampered2))
bad = doc(); bad["stories"]["7"]["lean_counts"] = {"left": 9}
check("1i: an invalid / protected-field document can never become a revision", raises(V.InvalidDocument, lambda: V.seal(bad, None, "u", T0)))
check("1j: the empty document can be sealed", V.verify(V.seal(empty_document(), None, "u", T0)))

print("2. audit trail is append-only and tamper-evident")
c0 = ()
c1 = V.append_audit(c0, "u-editor", "draft.save", "draft-1", {"hash": "a"}, T0)
c2 = V.append_audit(c1, "u-editor", "publish", r1.revision_id, {"hash": "b"}, T1)
check("2a: appending leaves the old chain untouched", c0 == () and len(c1) == 1 and c2[:1] == c1)
check("2b: a valid chain verifies; the empty chain verifies", V.verify_audit(c2) and V.verify_audit(()))
forged = (dataclasses.replace(c2[0], actor="u-admin"),) + c2[1:]
check("2c: editing an earlier entry breaks the chain", not V.verify_audit(forged))
check("2d: deleting an entry from the middle breaks the chain", not V.verify_audit(V.append_audit(c2, "x", "y", "z", {}, T2)[:1] + V.append_audit(c2, "x", "y", "z", {}, T2)[2:]))
check("2e: reordering breaks the chain", not V.verify_audit((c2[1], c2[0])))
check("2f: every entry names who did it", all(e.actor for e in c2))

print("3. publication status is truthful")
S = V.PublishState
path = [S.DRAFT_SAVED, S.QUEUED, S.BUILDING, S.BUILT_LOCAL, S.PUSHED, S.LIVE_CONFIRMED]
s = path[0]
for nxt in path[1:]:
    s = V.advance(s, nxt)
check("3a: the full happy path is legal, ending in live_confirmed", s == S.LIVE_CONFIRMED)
check("3b: cannot be 'live' straight from a draft", raises(V.IllegalTransition, lambda: V.advance(S.DRAFT_SAVED, S.LIVE_CONFIRMED)))
check("3c: a local build is not 'live'", raises(V.IllegalTransition, lambda: V.advance(S.BUILT_LOCAL, S.LIVE_CONFIRMED)))
check("3d: a push is not 'live' until confirmed (must pass through PUSHED -> LIVE_CONFIRMED explicitly)",
      V.advance(S.PUSHED, S.LIVE_CONFIRMED) == S.LIVE_CONFIRMED and S.LIVE_CONFIRMED not in V.TRANSITIONS[S.BUILT_LOCAL])
check("3e: a failed deployment cannot jump to live", raises(V.IllegalTransition, lambda: V.advance(S.DEPLOYMENT_FAILED, S.LIVE_CONFIRMED)))
check("3f: a failed deployment can be retried (push again) or re-queued",
      {S.PUSHED, S.QUEUED} <= V.TRANSITIONS[S.DEPLOYMENT_FAILED])
check("3g: a failed build returns to queue/draft, never forward", V.TRANSITIONS[S.BUILD_FAILED] == {S.QUEUED, S.DRAFT_SAVED})
check("3h: validation failure cannot be queued", raises(V.IllegalTransition, lambda: V.advance(S.VALIDATION_FAILED, S.QUEUED)))
check("3i: unknown states are refused", raises(V.IllegalTransition, lambda: V.advance("???", S.QUEUED)))
check("3j: only LIVE_CONFIRMED may be presented as live (no other state can reach it except PUSHED)",
      [k for k, v in V.TRANSITIONS.items() if S.LIVE_CONFIRMED in v] == [S.PUSHED])

print("4. concurrency, idempotency, rollback")
check("4a: draft based on the current published revision passes", V.check_base(r1.revision_id, r1.revision_id) is None)
check("4b: stale base is a conflict, never a silent overwrite", raises(V.ConflictError, lambda: V.check_base(r1.revision_id, r2.revision_id)))
check("4c: first-ever publish (no base, nothing published) passes", V.check_base(None, None) is None)
check("4d: a first publish against an existing published revision conflicts", raises(V.ConflictError, lambda: V.check_base(None, r1.revision_id)))
check("4e: publishing what is already live is a no-op", V.is_noop_publish(r1.doc_hash, r1.doc_hash) and not V.is_noop_publish(r1.doc_hash, r2.doc_hash))
store = {r1.revision_id: r1, r2.revision_id: r2}
rb = V.make_rollback(store, r2.revision_id, r1.revision_id, "u-editor", T2)
check("4f: rollback seals a NEW revision whose content equals the old one", rb.doc_hash == r1.doc_hash and rb.revision_id not in store)
check("4g: rollback parents the current revision and is marked as a rollback", rb.parent_id == r2.revision_id and rb.kind == "rollback")
check("4h: history is untouched by rollback", store[r1.revision_id] is r1 and store[r2.revision_id] is r2 and len(store) == 2)
store[r1.revision_id] = tampered
check("4i: cannot roll back to a tampered revision", raises(V.InvalidDocument, lambda: V.make_rollback(store, r2.revision_id, r1.revision_id, "u", T2)))
check("4j: unknown rollback target is refused", raises(KeyError, lambda: V.make_rollback({r2.revision_id: r2}, r2.revision_id, "rXXX", "u", T2)))

print("5. roles: server-side policy, default deny")
check("5a: every action is covered by at least one role", all(any(a in P.PERMISSIONS[r] for r in P.ROLES) for a in P.ALL_ACTIONS))
for action in sorted(P.EDIT_ACTIONS):
    check(f"5b: editor may {action}", P.authorize(ED, action))
    check(f"5c: read-only may NOT {action}", not P.authorize(RO, action))
    check(f"5d: administrator alone may NOT {action} (roles are additive)", not P.authorize(ADM, action))
for action in sorted(P.READ_ACTIONS):
    check(f"5e: read-only may {action}", P.authorize(RO, action))
for action in sorted(P.ADMIN_ACTIONS):
    check(f"5f: only administrator may {action}", P.authorize(ADM, action) and not P.authorize(ED, action) and not P.authorize(RO, action))
both = P.Membership("u-both", ("administrator", "editor"))
check("5g: a user may hold several roles (union of permissions)", P.authorize(both, "publish") and P.authorize(both, "members.manage"))
check("5h: unknown action denied", not P.authorize(both, "delete.everything"))
check("5i: no membership denied", not P.authorize(None, "story.read"))
check("5j: inactive member denied everything", not P.authorize(P.Membership("u", ("editor",), active=False), "story.read"))
check("5k: a forged role string is not a role", not P.authorize(P.Membership("u", ("superuser",)), "publish"))
check("5l: require() raises PermissionDenied", raises(P.PermissionDenied, lambda: P.require(RO, "publish")))
check("5m: a plain dict / string is never accepted as a membership", not P.authorize({"roles": ["editor"]}, "publish") and not P.authorize("editor", "publish"))

print("6. a role can only come from the members table")
table = [{"user_id": "u-editor", "roles": ["editor"], "active": True},
         {"user_id": "u-old", "roles": ["editor"], "active": False},
         {"user_id": "u-junk", "roles": ["editor", "root", 5], "active": True}]
check("6a: lookup returns the table's membership", P.lookup_membership(table, "u-editor") == P.Membership("u-editor", ("editor",), True))
check("6b: a user absent from the table has NO membership (open reader sign-up grants nothing)", P.lookup_membership(table, "new-reader") is None)
check("6c: and therefore not even read access", not P.authorize(P.lookup_membership(table, "new-reader"), "story.read"))
check("6d: deactivated members are denied", not P.authorize(P.lookup_membership(table, "u-old"), "publish"))
check("6e: unknown roles in a record are dropped", P.lookup_membership(table, "u-junk").roles == ("editor",))
check("6f: authorize() takes no user metadata or claims at all (signature accepts only membership+action)",
      P.authorize.__code__.co_varnames[:P.authorize.__code__.co_argcount] == ("membership", "action"))
check("6g: lookup ignores extra record keys such as user_metadata",
      P.membership_from_record({"user_id": "u", "roles": ["read_only"], "active": True,
                                "user_metadata": {"role": "administrator"}}).roles == ("read_only",))
check("6h: 'active' must be literally true (a truthy string is not enough)",
      not P.membership_from_record({"user_id": "u", "roles": ["editor"], "active": "false"}).active)
check("6i: malformed records yield no membership", P.membership_from_record({"roles": ["editor"]}) is None and P.membership_from_record(None) is None)

print("7. one gate for preview and publish")
ROWS = [{"id": 7, "title": "T", "summary": "S"}]
NOW = "2026-10-10T12:00:00Z"
d = doc("C")
rel = G.check_release(d, ROWS)
check("7a: release check passes a valid document", rel["ok"] and rel["doc_hash"] == document_hash(d))
check("7b: preview and publish give the same verdict for the same document",
      G.check_preview(RO, d, ROWS)["ok"] == G.check_publish(ED, d, "", "", "", ROWS)["ok"] == rel["ok"])
bad = doc(); bad["stories"]["7"]["lean_counts"] = 1
check("7c: preview reports a protected-field edit as invalid", not G.check_preview(RO, bad)["ok"])
check("7d: publish refuses the same document", raises(V.InvalidDocument, lambda: G.check_publish(ED, bad, "", "", "")))
check("7e: read-only can preview", G.check_preview(RO, d)["ok"])
check("7f: read-only can NOT publish", raises(P.PermissionDenied, lambda: G.check_publish(RO, d, "", "", "")))
check("7g: a non-member can neither preview nor publish",
      raises(P.PermissionDenied, lambda: G.check_preview(None, d)) and raises(P.PermissionDenied, lambda: G.check_publish(None, d, "", "", "")))
check("7h: administrator-only (no editor role) can NOT publish", raises(P.PermissionDenied, lambda: G.check_publish(ADM, d, "", "", "")))
res = G.check_publish(ED, d, r1.revision_id, r1.revision_id, r1.doc_hash)
check("7i: an approved editor publishes directly - no second approver anywhere in the gate", res["decision"] == "proceed")
check("7j: publishing identical content decides 'noop'", G.check_publish(ED, d, r1.revision_id, r1.revision_id, document_hash(d))["decision"] == "noop")
check("7k: a stale base is refused by the gate", raises(V.ConflictError, lambda: G.check_publish(ED, d, r1.revision_id, r2.revision_id, r2.doc_hash)))
check("7l: permission is checked BEFORE the document is even validated (read-only + invalid -> PermissionDenied)",
      raises(P.PermissionDenied, lambda: G.check_publish(RO, bad, "", "", "")))
orph = doc(); orph["stories"] = {"999": {"title": {"en": "gone story"}}}
res = G.check_publish(ED, orph, "", "", "", ROWS)
check("7m: an orphan reference is a finding, not a blocker (stories churn)", res["decision"] == "proceed" and res["findings"][0]["kind"] == "orphan_story")
frozen = copy.deepcopy(d)
G.check_publish(ED, d, "", "", "", ROWS); G.check_preview(RO, d, ROWS)
check("7n: the gate never mutates the document", d == frozen)
import editorial.gate as _g, inspect
src = inspect.getsource(_g)
check("7o: the gate module contains no build/git/file/network operations",
      not any(w in src for w in ("subprocess", "open(", "git ", "shutil", "socket", "requests")))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("=" * 60)
print("ALL EDITORIAL REVISION / PERMISSION CHECKS PASSED")
