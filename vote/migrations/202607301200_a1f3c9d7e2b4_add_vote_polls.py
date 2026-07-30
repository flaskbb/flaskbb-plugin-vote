"""Add vote_polls, vote_poll_options and vote_poll_votes

Revision ID: a1f3c9d7e2b4
Revises:
Create Date: 2026-07-30 12:00:00.000000

"""

import flaskbb
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1f3c9d7e2b4"
down_revision = None
branch_labels = ("vote",)
depends_on = "8ad96e49dc6"  # flaskbb core init migration - creates posts/users


def upgrade():
    con = op.get_bind()

    if not sa.inspect(con.engine).has_table("vote_polls"):
        op.create_table(
            "vote_polls",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("post_id", sa.Integer(), nullable=False),
            sa.Column("question", sa.String(length=255), nullable=False),
            sa.Column("poll_type", sa.String(length=10), nullable=False),
            sa.Column(
                "date_created",
                flaskbb.utils.database.UTCDateTime(timezone=True),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["post_id"],
                ["posts.id"],
                name=op.f("fk_vote_polls_post_id_posts"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_vote_polls")),
            sa.UniqueConstraint("post_id", name=op.f("uq_vote_polls_post_id")),
        )

    if not sa.inspect(con.engine).has_table("vote_poll_options"):
        op.create_table(
            "vote_poll_options",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("poll_id", sa.Integer(), nullable=False),
            sa.Column("text", sa.String(length=255), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["poll_id"],
                ["vote_polls.id"],
                name=op.f("fk_vote_poll_options_poll_id_vote_polls"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_vote_poll_options")),
        )

    if not sa.inspect(con.engine).has_table("vote_poll_votes"):
        op.create_table(
            "vote_poll_votes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("poll_option_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column(
                "date_created",
                flaskbb.utils.database.UTCDateTime(timezone=True),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["poll_option_id"],
                ["vote_poll_options.id"],
                name=op.f("fk_vote_poll_votes_poll_option_id_vote_poll_options"),
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name=op.f("fk_vote_poll_votes_user_id_users"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_vote_poll_votes")),
        )


def downgrade():
    op.drop_table("vote_poll_votes")
    op.drop_table("vote_poll_options")
    op.drop_table("vote_polls")
