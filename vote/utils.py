"""
vote.utils
~~~~~~~~~~

Helpers for parsing and validating polls and for creating polls.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

import json
import logging
from dataclasses import dataclass

from flask_allows2 import And, Or, Permission
from flaskbb.extensions import db
from flaskbb.forum.models import Forum, Post
from flaskbb.user.models import User
from flaskbb.utils.requirements import Has, IsAtleastSuperModerator, IsModeratorInForum

from .models import MULTIPLE_CHOICE, Poll, POLL_TYPES, PollOption, PollVote

logger = logging.getLogger(__name__)

MIN_OPTIONS = 2
QUESTION_MAX_LENGTH = 255
OPTION_MAX_LENGTH = 255


@dataclass(frozen=True)
class PollPayload:
    question: str
    poll_type: str
    options: tuple[str, ...]


def parse_poll_payload(raw: str | None, max_options: int) -> PollPayload | None:
    """Parses and validates the JSON poll payload submitted alongside a post.

    Returns ``None`` if ``raw`` is empty or fails validation - callers treat
    that the same as "no poll was attached", since the field is optional and
    a malformed payload (a tampered request, most likely) shouldn't block
    the post/topic it rode in on from being created.
    """
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except ValueError:
        logger.info("Discarding poll payload: invalid JSON")
        return None

    if not isinstance(data, dict):
        return None

    question = data.get("question")
    poll_type = data.get("type")
    options = data.get("options")

    if not isinstance(question, str) or not isinstance(poll_type, str):
        return None

    question = question.strip()
    if not question or len(question) > QUESTION_MAX_LENGTH:
        return None

    if poll_type not in POLL_TYPES:
        return None

    if not isinstance(options, list):
        return None

    cleaned_options: list[str] = []
    for option in options:
        if not isinstance(option, str):
            return None
        option = option.strip()
        if not option:
            continue
        if len(option) > OPTION_MAX_LENGTH:
            return None
        cleaned_options.append(option)

    if not (MIN_OPTIONS <= len(cleaned_options) <= max_options):
        return None

    return PollPayload(question=question, poll_type=poll_type, options=tuple(cleaned_options))


def create_poll_for_post(post: Post, payload: PollPayload) -> Poll:
    """Creates a poll and its options for ``post`` in a single transaction."""
    poll = Poll(post_id=post.id, question=payload.question, poll_type=payload.poll_type)
    db.session.add(poll)
    db.session.flush()

    for position, text in enumerate(payload.options):
        db.session.add(PollOption(poll_id=poll.id, text=text, position=position))

    db.session.commit()
    return poll


def can_access_poll(user: User, poll: Poll) -> bool:
    """Mirrors ``CanAccessForum.fulfill`` for a forum reached via a poll,
    rather than via the current request's URL - the vote endpoint has no
    ``current_forum`` to check against.
    """
    forum: Forum = poll.post.topic.forum
    forum_group_ids = {group.id for group in forum.groups}
    user_group_ids = {group.id for group in user.groups}
    return bool(forum_group_ids & user_group_ids)


def cast_vote(poll: Poll, user: User, option_ids: list[int]) -> None:
    """Replaces ``user``'s vote(s) in ``poll`` with ``option_ids``.

    Callers are expected to have already validated that every id in
    ``option_ids`` belongs to ``poll``, and that ``option_ids`` has exactly
    one entry for a single-choice poll.
    """
    valid_option_ids = {option.id for option in poll.options}
    existing = PollVote.get_all(
        PollVote.user_id == user.id, PollVote.poll_option_id.in_(valid_option_ids)
    )
    for vote in existing:
        db.session.delete(vote)

    for option_id in option_ids:
        db.session.add(PollVote(poll_option_id=option_id, user_id=user.id))

    db.session.commit()


def can_delete_poll(user: User, poll: Poll) -> bool:
    """Mirrors flaskbb's staff branches of ``CanDeletePost`` - only an
    admin, a super moderator, or a moderator of the poll's forum with the
    ``editpost`` permission may delete a poll. Unlike editing/deleting a
    post, the poster themselves is never allowed to delete their own poll.
    """
    forum = poll.post.topic.forum
    requirement = Or(
        IsAtleastSuperModerator,
        And(IsModeratorInForum(forum=forum), Has("editpost")),
    )
    return bool(Permission(requirement, identity=user))


def poll_type_is_valid_for(poll: Poll, option_ids: list[int]) -> bool:
    valid_option_ids = {option.id for option in poll.options}
    if not option_ids:
        return False
    if not set(option_ids) <= valid_option_ids:
        return False
    if poll.poll_type != MULTIPLE_CHOICE and len(option_ids) > 1:
        return False
    return True
