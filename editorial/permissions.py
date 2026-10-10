"""editorial/permissions.py - the role/permission policy (server-side contract).

IMPORTANT: this is the POLICY. It is not the enforcement point by itself. In Milestone 6
the same matrix is enforced in Postgres (row-level security + security-definer functions)
and again in the publishing worker. The browser is never an authority.

Trust rules encoded here and tested:
  * A role comes ONLY from a membership record in the editorial members table, looked up
    by a user id that the auth layer has already verified. `authorize` accepts nothing
    else: not user metadata, not a JWT claim, not a request field.
  * Default deny: unknown actions, unknown roles, inactive members and non-members are
    refused.
  * Roles are additive. Administrator does NOT silently include Editor: an administrator
    who should also publish simply holds both roles. (Easy to change, deliberately safe.)
  * Every approved Editor can publish directly. There is no approver step.
  * Open reader sign-up grants nothing: an account with no membership record has no
    editorial permission of any kind, including read.
"""
from __future__ import annotations

from dataclasses import dataclass

ROLES = ("administrator", "editor", "read_only")

READ_ACTIONS = frozenset({"story.read", "media.read", "layout.read", "pages.read",
                          "revision.read", "audit.read", "preview", "analytics.read"})
EDIT_ACTIONS = frozenset({"story.edit", "media.edit", "layout.edit", "pages.edit",
                          "draft.save", "draft.discard", "publish", "rollback",
                          "schedule.edit"})
ADMIN_ACTIONS = frozenset({"members.manage", "settings.manage"})

PERMISSIONS = {
    "read_only": READ_ACTIONS,
    "editor": READ_ACTIONS | EDIT_ACTIONS,
    "administrator": READ_ACTIONS | ADMIN_ACTIONS,
}
ALL_ACTIONS = READ_ACTIONS | EDIT_ACTIONS | ADMIN_ACTIONS


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Membership:
    user_id: str
    roles: tuple
    active: bool = True


def membership_from_record(record):
    """Build a Membership from one row of the editorial members table. Only whitelisted
    columns are read; unknown roles are dropped; anything malformed yields None."""
    if not isinstance(record, dict):
        return None
    uid = record.get("user_id")
    roles = record.get("roles")
    if not isinstance(uid, str) or not uid or not isinstance(roles, (list, tuple)):
        return None
    clean = tuple(sorted({r for r in roles if r in ROLES}))
    return Membership(uid, clean, record.get("active") is True)


def lookup_membership(members_table, verified_user_id):
    """members_table: iterable of records. verified_user_id: already authenticated."""
    for rec in members_table or ():
        if isinstance(rec, dict) and rec.get("user_id") == verified_user_id:
            return membership_from_record(rec)
    return None


def authorize(membership, action):
    if not isinstance(membership, Membership) or not membership.active:
        return False
    if action not in ALL_ACTIONS:
        return False
    return any(action in PERMISSIONS.get(r, ()) for r in membership.roles)


def require(membership, action):
    if not authorize(membership, action):
        raise PermissionDenied("not permitted: %s" % action)
