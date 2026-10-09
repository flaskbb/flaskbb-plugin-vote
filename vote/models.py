"""
vote.models
~~~~~~~~~~~

The models for polls, their options and votes.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

import datetime
import logging
from dataclasses import dataclass

import sqlalchemy as sa
from flaskbb.extensions import db
from flaskbb.forum.models import Post
from flaskbb.utils.database import BaseModel, UTCDateTime
from flaskbb.utils.helpers import time_utcnow
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)

SINGLE_CHOICE = "single"
MULTIPLE_CHOICE = "multiple"
POLL_TYPES = (SINGLE_CHOICE, MULTIPLE_CHOICE)


@dataclass(frozen=True)
class VoteSummary:
    """Everything the poll widget needs to know about a poll's votes,
    gathered by ``Poll.vote_summary`` in a single query."""

    counts: dict[int, int]
    total: int
    user_option_ids: list[int]


class Poll(BaseModel):
    __tablename__ = "vote_polls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    question: Mapped[str] = mapped_column(String(255), nullable=False)
    poll_type: Mapped[str] = mapped_column(String(10), nullable=False)
    date_created: Mapped[datetime.datetime] = mapped_column(
        UTCDateTime(timezone=True), default=time_utcnow, nullable=False
    )

    # ``single_parent`` is required by SQLAlchemy for a delete-orphan cascade
    # on a one-to-one backref. Declared here (not on Post) since Post is a
    # core model this plugin doesn't own - see docs/development/plugin/editor.rst
    # in flaskbb for why plugins extend core models this way instead of
    # patching flaskbb.forum.models.
    #
    # The backref and ``options`` load via ``selectin``, so a topic page
    # fetches the polls of all its posts, and then their options, in one
    # query each instead of one per post. Never ``joined`` - that folds
    # into whatever query loads a Post, including flaskbb's hand-built
    # outerjoin in Topic.get_posts, and corrupts its column layout (see
    # https://github.com/flaskbb/flaskbb/issues/503).
    post: Mapped["Post"] = relationship(
        "Post",
        backref=db.backref(
            "poll",
            uselist=False,
            lazy="selectin",
            cascade="all, delete-orphan",
            single_parent=True,
        ),
    )

    options: Mapped[list["PollOption"]] = relationship(
        "PollOption",
        back_populates="poll",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PollOption.position",
    )

    @property
    def is_multiple_choice(self) -> bool:
        return self.poll_type == MULTIPLE_CHOICE

    @property
    def total_votes(self) -> int:
        stmt = (
            sa.select(sa.func.count(PollVote.id))
            .join(PollOption, PollOption.id == PollVote.poll_option_id)
            .where(PollOption.poll_id == self.id)
        )
        return db.session.execute(stmt).scalar_one()

    def option_ids_voted_by(self, user_id: int) -> list[int]:
        """Returns the ids of the options ``user_id`` has voted for."""
        return self.vote_summary(user_id).user_option_ids

    def vote_summary(self, user_id: int | None) -> VoteSummary:
        """Per-option vote counts plus the options ``user_id`` voted for, in
        one query. Every option of the poll has an entry in ``counts``, even
        with no votes. ``user_id=None`` (a guest) leaves ``user_option_ids``
        empty."""
        voted_by_user = (
            sa.case((PollVote.user_id == user_id, 1), else_=0)
            if user_id is not None
            else sa.literal(0)
        )
        stmt = (
            sa.select(
                PollOption.id,
                sa.func.count(PollVote.id),
                sa.func.coalesce(sa.func.sum(voted_by_user), 0),
            )
            .outerjoin(PollVote, PollVote.poll_option_id == PollOption.id)
            .where(PollOption.poll_id == self.id)
            .group_by(PollOption.id)
            .order_by(PollOption.position)
        )
        counts: dict[int, int] = {}
        user_option_ids: list[int] = []
        for option_id, count, user_votes in db.session.execute(stmt):
            counts[option_id] = count
            if user_votes:
                user_option_ids.append(option_id)
        return VoteSummary(
            counts=counts, total=sum(counts.values()), user_option_ids=user_option_ids
        )


class PollOption(BaseModel):
    __tablename__ = "vote_poll_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poll_id: Mapped[int] = mapped_column(
        ForeignKey("vote_polls.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    poll: Mapped["Poll"] = relationship("Poll", back_populates="options")
    votes: Mapped[list["PollVote"]] = relationship(
        "PollVote", back_populates="option", cascade="all, delete-orphan"
    )

    @property
    def vote_count(self) -> int:
        return PollVote.count(PollVote.poll_option_id == self.id)


class PollVote(BaseModel):
    __tablename__ = "vote_poll_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poll_option_id: Mapped[int] = mapped_column(
        ForeignKey("vote_poll_options.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date_created: Mapped[datetime.datetime] = mapped_column(
        UTCDateTime(timezone=True), default=time_utcnow, nullable=False
    )

    option: Mapped["PollOption"] = relationship("PollOption", back_populates="votes")
