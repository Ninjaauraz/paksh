"""editorial/document.py - loading, canonical form and hashing of editorial documents.

`load_*` NEVER raises for bad input and never returns a half-validated document: the
caller gets a LoadResult whose status is exactly one of
    absent   - no document exists (normal; the site keeps its generated defaults)
    invalid  - unreadable, oversize, malformed JSON, duplicate keys, or fails validation
    ok       - parsed AND fully valid
Consumers treat anything but `ok` as "no editorial configuration".
"""
from __future__ import annotations

import hashlib
import json
import os

from .schema import validate_document

MAX_BYTES = 1024 * 1024  # a document this large is a bug or an attack, not editing


class LoadResult:
    def __init__(self, status, doc=None, errors=None, warnings=None, doc_hash=None, reason=""):
        self.status = status
        self.doc = doc
        self.errors = errors or []
        self.warnings = warnings or []
        self.doc_hash = doc_hash
        self.reason = reason

    @property
    def ok(self):
        return self.status == "ok"


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key %r" % k)
        out[k] = v
    return out


def _reject_constant(name):
    raise ValueError("non-finite number %s" % name)


def canonical_json(doc):
    """Deterministic serialisation: same document -> same bytes -> same hash, on any machine."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def document_hash(doc):
    return hashlib.sha256(canonical_json(doc)).hexdigest()


def _invalid(reason, errors=None):
    return LoadResult("invalid", errors=errors or [{"path": "", "code": "unreadable", "message": reason}],
                      reason=reason)


def load_text(text):
    if text is None:
        return LoadResult("absent", reason="no document")
    if isinstance(text, bytes):
        if len(text) > MAX_BYTES:
            return _invalid("document larger than %d bytes" % MAX_BYTES)
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return _invalid("document is not valid UTF-8")
    if len(text.encode("utf-8")) > MAX_BYTES:
        return _invalid("document larger than %d bytes" % MAX_BYTES)
    try:
        doc = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except (ValueError, RecursionError, MemoryError) as e:
        return _invalid("malformed or excessively nested JSON (%s)" % e.__class__.__name__)
    try:
        res = validate_document(doc)
    except (RecursionError, MemoryError):          # belt and braces: validate_document is also depth-limited
        return _invalid("document is nested too deeply or is too large to validate")
    if not res.ok:
        return LoadResult("invalid", errors=res.errors, warnings=res.warnings,
                          reason="failed validation: " + ", ".join(res.codes()))
    return LoadResult("ok", doc=doc, warnings=res.warnings, doc_hash=document_hash(doc))


def load_file(path):
    """A missing file is `absent` (normal). Any other read problem is `invalid`."""
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return LoadResult("absent", reason="file not found")
    except OSError as e:
        return _invalid("cannot stat file: %s" % e.__class__.__name__)
    if size > MAX_BYTES:
        return _invalid("document larger than %d bytes" % MAX_BYTES)
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_BYTES + 1)
    except OSError as e:
        return _invalid("cannot read file: %s" % e.__class__.__name__)
    return load_text(data)
