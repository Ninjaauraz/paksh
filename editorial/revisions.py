"""editorial/revisions.py - immutable revisions, the audit chain, publish states, conflicts.

These are the DATA CONTRACTS the storage layer (Supabase, Milestone 6) and the
publishing worker (Milestone 6/7) must honour. Nothing here touches a database,
a file, the network or git.

  Revision      frozen; content-addressed (doc_hash). Once sealed it is never edited.
  AuditEntry    append-only; each entry hashes the previous one, so deleting or editing
                history is detectable.
  PublishState  the explicit, truthful publication status ladder. 'live_confirmed' is the
                ONLY state that may be shown to editors as "live"; a database write, a
                local build, or even a git push is not "live".
  check_base    optimistic concurrency: a publish is refused if it was based on a revision
                that is no longer the published one (nobody's work is silently overwritten).
  make_rollback rollback never rewrites history: it seals a NEW revision whose document is
                a copy of an older one.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .document import canonical_json, document_hash
from .schema import validate_document


class InvalidDocument(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join("%s: %s" % (e["path"] or "<root>", e["code"]) for e in errors[:5]))
        self.errors = errors


class ConflictError(RuntimeError):
    pass


class IllegalTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class Revision:
    revision_id: str
    parent_id: str          # "" for the first revision
    doc_hash: str
    doc_json: str           # canonical JSON text of the document
    author: str
    created_at: str         # caller-supplied ISO timestamp
    kind: str = "snapshot"  # snapshot | rollback


def _rid(parent_id, doc_hash, author, created_at):
    return "r" + hashlib.sha256(
        ("%s|%s|%s|%s" % (parent_id, doc_hash, author, created_at)).encode("utf-8")).hexdigest()[:20]


def seal(doc, parent_id, author, created_at, kind="snapshot"):
    """Validate, then freeze `doc` into an immutable Revision. An invalid document can
    never become a revision, so it can never be published or rolled back to."""
    res = validate_document(doc)
    if not res.ok:
        raise InvalidDocument(res.errors)
    h = document_hash(doc)
    return Revision(_rid(parent_id or "", h, author, created_at), parent_id or "", h,
                    canonical_json(doc).decode("utf-8"), author, created_at, kind)


def verify(rev):
    """True only if the stored document still matches its recorded hash and id."""
    import json
    try:
        doc = json.loads(rev.doc_json)
    except ValueError:
        return False
    return (document_hash(doc) == rev.doc_hash
            and _rid(rev.parent_id, rev.doc_hash, rev.author, rev.created_at) == rev.revision_id)


def revision_document(rev):
    import json
    if not verify(rev):
        raise InvalidDocument([{"path": "", "code": "revision_tampered", "message": rev.revision_id}])
    return json.loads(rev.doc_json)


def check_base(base_revision_id, current_published_id):
    """Refuse to publish work based on something other than what is published now."""
    if (base_revision_id or "") != (current_published_id or ""):
        raise ConflictError("draft is based on revision %r but the published revision is now %r; "
                            "reload and merge before publishing"
                            % (base_revision_id or "<none>", current_published_id or "<none>"))


def is_noop_publish(doc_hash, current_published_hash):
    """Publishing the document that is already live changes nothing (idempotent)."""
    return doc_hash == current_published_hash


def make_rollback(revisions_by_id, current_id, target_id, author, created_at):
    """A NEW revision whose content equals `target_id`'s. History is never rewritten and
    the target must verify as untampered. The caller publishes it through the normal path."""
    if target_id not in revisions_by_id or current_id not in revisions_by_id:
        raise KeyError("unknown revision")
    doc = revision_document(revisions_by_id[target_id])
    return seal(doc, current_id, author, created_at, kind="rollback")


# --- audit chain ------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEntry:
    seq: int
    actor: str
    action: str
    target: str
    detail_hash: str
    at: str
    prev_hash: str
    entry_hash: str


def _entry_hash(seq, actor, action, target, detail_hash, at, prev_hash):
    return hashlib.sha256(("%d|%s|%s|%s|%s|%s|%s" % (
        seq, actor, action, target, detail_hash, at, prev_hash)).encode("utf-8")).hexdigest()


def append_audit(chain, actor, action, target, detail, at):
    """Return a new tuple with one more entry; the old chain is untouched."""
    prev = chain[-1].entry_hash if chain else ""
    seq = len(chain) + 1
    dh = hashlib.sha256(canonical_json(detail)).hexdigest()
    e = AuditEntry(seq, actor, action, target, dh, at, prev,
                   _entry_hash(seq, actor, action, target, dh, at, prev))
    return tuple(chain) + (e,)


def verify_audit(chain):
    prev = ""
    for i, e in enumerate(chain, 1):
        if e.seq != i or e.prev_hash != prev or e.entry_hash != _entry_hash(
                e.seq, e.actor, e.action, e.target, e.detail_hash, e.at, e.prev_hash):
            return False
        prev = e.entry_hash
    return True


# --- publication status ------------------------------------------------------------------

class PublishState:
    DRAFT_SAVED = "draft_saved"
    VALIDATION_FAILED = "validation_failed"
    QUEUED = "queued"
    BUILDING = "building"
    BUILT_LOCAL = "built_local"            # written to local static output only
    PUSHED = "pushed"                      # committed and pushed; deployment unknown
    DEPLOYMENT_FAILED = "deployment_failed"
    LIVE_CONFIRMED = "live_confirmed"      # the public URL was observed serving this revision
    BUILD_FAILED = "build_failed"
    SUPERSEDED = "superseded"


_T = PublishState
TRANSITIONS = {
    _T.DRAFT_SAVED: {_T.VALIDATION_FAILED, _T.QUEUED},
    _T.VALIDATION_FAILED: {_T.DRAFT_SAVED},
    _T.QUEUED: {_T.BUILDING, _T.SUPERSEDED, _T.DRAFT_SAVED},
    _T.BUILDING: {_T.BUILT_LOCAL, _T.BUILD_FAILED},
    _T.BUILD_FAILED: {_T.QUEUED, _T.DRAFT_SAVED},
    _T.BUILT_LOCAL: {_T.PUSHED, _T.BUILD_FAILED},
    _T.PUSHED: {_T.LIVE_CONFIRMED, _T.DEPLOYMENT_FAILED},
    _T.DEPLOYMENT_FAILED: {_T.QUEUED, _T.PUSHED},
    _T.LIVE_CONFIRMED: {_T.SUPERSEDED},
    _T.SUPERSEDED: set(),
}


def advance(state, new_state):
    """Only legal moves are possible; in particular nothing can jump to LIVE_CONFIRMED
    without first being PUSHED, and PUSHED requires BUILT_LOCAL."""
    if new_state not in TRANSITIONS.get(state, set()):
        raise IllegalTransition("%s -> %s is not allowed" % (state, new_state))
    return new_state
