"""editorial/gate.py - the single decision point every preview and publish must pass.

Preview and publish call the SAME `check_release`, so a document that previews cleanly
cannot fail validation at publish time for a different reason (and vice-versa).
`check_publish` is what the Milestone 6 worker must call BEFORE it touches any output:
if it raises, nothing may be built, committed or pushed.

This module only DECIDES. It performs no build, no file write, no git, no network.
"""
from __future__ import annotations

from .document import document_hash
from .permissions import require
from .resolve import audit_references
from .revisions import InvalidDocument, check_base, is_noop_publish
from .schema import validate_document


def check_release(doc, rows=None, existing_ids=None, now=None):
    """Structural validation (errors block) plus reference findings (never block)."""
    res = validate_document(doc)
    findings = []
    if res.ok and rows is not None:
        from .document import LoadResult
        findings = audit_references(
            LoadResult("ok", doc=doc, doc_hash=document_hash(doc)), rows, existing_ids, now)
    return {"ok": res.ok, "errors": list(res.errors), "warnings": list(res.warnings),
            "findings": findings, "doc_hash": document_hash(doc) if res.ok else None}


def check_preview(membership, doc, rows=None, existing_ids=None, now=None):
    require(membership, "preview")
    return check_release(doc, rows, existing_ids, now)


def check_publish(membership, doc, base_revision_id, current_published_id,
                  current_published_hash, rows=None, existing_ids=None, now=None):
    """Authorisation -> validation -> concurrency -> idempotency, in that order.
    Raises PermissionDenied / InvalidDocument / ConflictError; otherwise returns a
    decision of 'proceed' or 'noop'. Any approved editor passes the permission step:
    there is no second-approver requirement."""
    require(membership, "publish")
    rel = check_release(doc, rows, existing_ids, now)
    if not rel["ok"]:
        raise InvalidDocument(rel["errors"])
    check_base(base_revision_id, current_published_id)
    decision = "noop" if is_noop_publish(rel["doc_hash"], current_published_hash) else "proceed"
    return dict(rel, decision=decision)
