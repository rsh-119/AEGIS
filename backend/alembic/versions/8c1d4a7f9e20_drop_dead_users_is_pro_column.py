"""drop dead users.is_pro column

Revision ID: 8c1d4a7f9e20
Revises: fecc0f480adc
Create Date: 2026-09-11

users.is_pro has not been read by application code since 32229b3de89f
introduced the `subscriptions` table. That migration also backfilled it: every
user with is_pro = true got a matching ('pro', 'active') subscription row, and
entitlement checks (app/core/entitlements.py) have read only that table since.

Keeping the column after that point was a liability rather than a safety net.
It was still writable (db/seed.py wrote it, the model exposed it, to_dict()
serialised it) while granting nothing, so the two could silently disagree — a
row reading is_pro = true that in fact had no Pro access. A regression test
existed purely to assert that the column was inert.

Safety before dropping:
  • upgrade() re-runs the same backfill as an idempotent INSERT ... SELECT,
    guarded on the column actually existing, so no user can lose access even
    if 32229b3de89f's backfill was incomplete or the column was edited by hand
    afterwards.
  • Existing subscription rows are never modified — a user already downgraded
    to free in `subscriptions` is not silently re-upgraded by a stale boolean.

downgrade() restores the column (NOT NULL DEFAULT false) and repopulates it
from `subscriptions`, so the schema and the data both round-trip.
"""

from alembic import op
import sqlalchemy as sa


revision = "8c1d4a7f9e20"
down_revision = "fecc0f480adc"
branch_labels = None
depends_on = None


def _has_is_pro(bind) -> bool:
    return "is_pro" in {c["name"] for c in sa.inspect(bind).get_columns("users")}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_is_pro(bind):
        return  # already dropped (e.g. a database built after this revision)

    # Belt-and-braces backfill: anyone still flagged Pro on the column but with
    # no subscription row gets one, so dropping the column cannot revoke access.
    op.execute(
        sa.text(
            """
            INSERT INTO subscriptions (user_id, plan, status, created_at, updated_at)
            SELECT u.id, 'pro', 'active', now(), now()
              FROM users u
             WHERE u.is_pro = true
               AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = u.id)
            """
        )
    )
    op.drop_column("users", "is_pro")


def downgrade() -> None:
    bind = op.get_bind()
    if _has_is_pro(bind):
        return

    op.add_column(
        "users",
        sa.Column("is_pro", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        sa.text(
            """
            UPDATE users u
               SET is_pro = true
              FROM subscriptions s
             WHERE s.user_id = u.id
               AND s.plan = 'pro'
               AND s.status = 'active'
               -- Mirror core/entitlements._is_pro exactly, expiry included.
               -- Without this clause an expired-but-still-'active' row
               -- repopulated is_pro = true on rollback, disagreeing with the
               -- entitlement check. Nothing reads the restored column, so this
               -- was cosmetic — but a rollback that reintroduces a
               -- contradiction is the opposite of what a rollback is for.
               AND (s.expires_at IS NULL OR s.expires_at > now())
            """
        )
    )
