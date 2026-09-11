from contextlib import contextmanager

import pytest
from flask_login import login_user, logout_user
from werkzeug.exceptions import NotFound

from vote.models import Poll, PollVote
from vote.views import CastVote, DeletePoll


@contextmanager
def _csrf_disabled(application):
    """CastVote builds a real VoteForm() to validate the request, which
    would otherwise reject a test-built POST for lacking a CSRF token -
    see tests/unit/forum/test_search_forms.py in flaskbb core for the
    same pattern.
    """
    original = application.config["WTF_CSRF_ENABLED"]
    application.config["WTF_CSRF_ENABLED"] = False
    try:
        yield
    finally:
        application.config["WTF_CSRF_ENABLED"] = original


def _post(application, poll, user, **form_data):
    view = CastVote.as_view("cast_vote")
    with (
        _csrf_disabled(application),
        application.test_request_context(
            method="POST", data=form_data, path=f"/vote/{poll.id}/vote"
        ),
    ):
        login_user(user)
        # login_user writes g._login_user onto the app context, which
        # outlives this request context and would leak into later
        # tests otherwise - see member_request in
        # tests/unit/forum/test_attachments.py in flaskbb core for the
        # same pattern. try/finally since the view can raise (abort).
        try:
            return view(poll_id=poll.id)
        finally:
            logout_user()


def test_cast_vote_requires_login(application, poll):
    view = CastVote.as_view("cast_vote")
    with application.test_request_context(method="POST", path=f"/vote/{poll.id}/vote"):
        resp = view(poll_id=poll.id)
    assert resp.status_code == 302


def test_cast_vote_records_single_choice(application, poll, user):
    red = poll.options[0]
    resp = _post(application, poll, user, option_id=str(red.id))

    assert resp.status_code == 302
    assert poll.option_ids_voted_by(user.id) == [red.id]


def test_cast_vote_rejects_two_options_for_single_choice(application, poll, user):
    red, green = poll.options[0], poll.options[1]
    _post(application, poll, user, option_id=[str(red.id), str(green.id)])

    assert poll.option_ids_voted_by(user.id) == []


def test_cast_vote_accepts_multiple_options_for_multiple_choice(application, multi_poll, user):
    cheese, pepperoni = multi_poll.options[0], multi_poll.options[1]
    _post(application, multi_poll, user, option_id=[str(cheese.id), str(pepperoni.id)])

    assert sorted(multi_poll.option_ids_voted_by(user.id)) == sorted([cheese.id, pepperoni.id])


def test_cast_vote_rejects_option_from_a_different_poll(application, poll, multi_poll, user):
    foreign_option = multi_poll.options[0]
    _post(application, poll, user, option_id=str(foreign_option.id))

    assert poll.option_ids_voted_by(user.id) == []
    assert PollVote.count() == 0


def test_cast_vote_rejects_no_selection(application, poll, user):
    _post(application, poll, user)
    assert PollVote.count() == 0


def test_cast_vote_replaces_previous_vote(application, poll, user):
    red, green = poll.options[0], poll.options[1]
    _post(application, poll, user, option_id=str(red.id))
    _post(application, poll, user, option_id=str(green.id))

    assert poll.option_ids_voted_by(user.id) == [green.id]


def _delete(application, poll, user):
    view = DeletePoll.as_view("delete_poll")
    with (
        _csrf_disabled(application),
        application.test_request_context(method="POST", path=f"/vote/{poll.id}/delete"),
    ):
        login_user(user)
        try:
            return view(poll_id=poll.id)
        finally:
            logout_user()


def test_delete_poll_requires_login(application, poll):
    view = DeletePoll.as_view("delete_poll")
    with application.test_request_context(method="POST", path=f"/vote/{poll.id}/delete"):
        resp = view(poll_id=poll.id)
    assert resp.status_code == 302
    assert Poll.get(Poll.id == poll.id) is not None


def test_delete_poll_rejects_normal_user(application, poll, user):
    with pytest.raises(NotFound):
        _delete(application, poll, user)
    assert Poll.get(Poll.id == poll.id) is not None


def test_delete_poll_rejects_poll_author(application, poll):
    """Even the user who posted the poll cannot delete it - unlike editing
    or deleting a post, this is a staff-only action.
    """
    with pytest.raises(NotFound):
        _delete(application, poll, poll.post.user)
    assert Poll.get(Poll.id == poll.id) is not None


def test_delete_poll_allows_admin(application, poll, admin_user):
    resp = _delete(application, poll, admin_user)
    assert resp.status_code == 302
    assert Poll.get(Poll.id == poll.id) is None


def test_delete_poll_allows_super_moderator(application, poll, super_moderator_user):
    resp = _delete(application, poll, super_moderator_user)
    assert resp.status_code == 302
    assert Poll.get(Poll.id == poll.id) is None


def test_delete_poll_allows_moderator_of_the_polls_forum(application, poll, moderator_user):
    resp = _delete(application, poll, moderator_user)
    assert resp.status_code == 302
    assert Poll.get(Poll.id == poll.id) is None


def test_delete_poll_rejects_moderator_of_a_different_forum(
    application, poll, other_moderator_user
):
    with pytest.raises(NotFound):
        _delete(application, poll, other_moderator_user)
    assert Poll.get(Poll.id == poll.id) is not None
