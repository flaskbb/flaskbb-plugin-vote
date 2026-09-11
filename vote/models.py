"""
vote.models
~~~~~~~~~~~

The models for polls, their options and votes.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

import datetime
import logging

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
    post: Mapped["Post"] = relationship(
        "Post",
        backref=db.backref("poll", uselist=False, cascade="all, delete-orphan", single_parent=True),
    )

    options: Mapped[list["PollOption"]] = relationship(
        "PollOption",
        back_populates="poll",
        cascade="all, delete-orphan",
        order_by="PollOption.position",
    )

    @property
    def is_multiple_choice(self) -> bool:
        return self.poll_type == MULTIPLE_CHOICE

    @property
    def total_votes(self) -> int:
        return sum(option.vote_count for option in self.options)

    def option_ids_voted_by(self, user_id: int) -> list[int]:
        """Returns the ids of the options ``user_id`` has voted for."""
        option_ids = [option.id for option in self.options]
        if not option_ids:
            return []
        votes = PollVote.get_all(
            PollVote.user_id == user_id, PollVote.poll_option_id.in_(option_ids)
        )
        return [vote.poll_option_id for vote in votes]


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
