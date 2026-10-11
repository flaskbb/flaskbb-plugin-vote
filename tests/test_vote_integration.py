"""
End-to-end tests for the flaskbb_form_topic/flaskbb_form_post +
flaskbb_event_post_save_after hook chain that turns a submitted poll_data
payload into a real Poll row. This only works if the `vote` package is
installed into flaskbb's environment (so its entry point is discovered by
create_app() and its hookimpls actually run) - see README.md.
"""

import json
import re
from contextlib import contextmanager
from html import unescape

import pytest
from flask import url_for
from flask_login import login_user, logout_user
from flaskbb.extensions import pluggy
from flaskbb.forum.forms import EditTopicForm, NewTopicForm, ReplyForm
from flaskbb.forum.models import Post
from flaskbb.settings import flaskbb_config
from werkzeug.datastructures import MultiDict

import vote as vote_plugin
from vote.models import Poll, PollOption
from vote.utils import cast_vote


def poll_json(**overrides):
    data = {
        "question": "Favorite color?",
        "type": "single",
        "options": ["Red", "Blue"],
    }
    data.update(overrides)
    return json.dumps(data)


def new_topic_form(**kwargs):
    # flaskbb_form_topic is only invoked by NewTopic.form()/EditTopic.form()
    # in flaskbb/forum/views.py, once per request - never automatically -
    # so a test constructing NewTopicForm() directly has to trigger it
    # first, exactly like those views do.
    pluggy.hook.flaskbb_form_topic(form=NewTopicForm)
    return NewTopicForm(**kwargs)


def reply_form(**kwargs):
    pluggy.hook.flaskbb_form_post(form=ReplyForm)
    return ReplyForm(**kwargs)


@contextmanager
def topics_only(enabled):
    # default_settings (pulled in transitively by the forum/topic fixtures)
    # already seeds vote's settings group, so this is just a normal update.
    original = flaskbb_config["VOTE_TOPICS_ONLY"]
    flaskbb_config["VOTE_TOPICS_ONLY"] = enabled
    try:
        yield
    finally:
        flaskbb_config["VOTE_TOPICS_ONLY"] = original


def test_new_topic_form_has_poll_data_field(request_context):
    assert hasattr(new_topic_form(), "poll_data")


def test_reply_form_has_poll_data_field(request_context, default_settings):
    # reply_form() now reads the TOPICS_ONLY setting, which needs the
    # settings table to exist.
    assert hasattr(reply_form(), "poll_data")


def test_submitting_a_new_topic_with_poll_data_creates_a_poll(request_context, forum, user):
    form = new_topic_form(
        title="A topic with a poll", content="See the attached poll", track_topic=False
    )
    form.poll_data.data = poll_json()

    topic = form.save(user, forum)

    poll = Poll.get(Poll.post_id == topic.first_post.id)
    assert poll is not None
    assert poll.question == "Favorite color?"
    assert [o.text for o in poll.options] == ["Red", "Blue"]


def test_submitting_a_new_topic_without_poll_data_creates_no_poll(request_context, forum, user):
    form = new_topic_form(title="A plain topic", content="No poll here", track_topic=False)

    topic = form.save(user, forum)

    assert Poll.get(Poll.post_id == topic.first_post.id) is None


def test_submitting_a_reply_with_poll_data_creates_a_poll(request_context, topic, user):
    form = reply_form(content="A reply with a poll", track_topic=False)
    form.poll_data.data = poll_json(question="Pick one", options=["A", "B", "C"])

    post = form.save(user, topic)

    poll = Poll.get(Poll.post_id == post.id)
    assert poll is not None
    assert poll.question == "Pick one"
    assert [o.text for o in poll.options] == ["A", "B", "C"]


def edit_reply_form(post, **formdata):
    # A submitted edit - only a poll_data that was part of the request
    # changes the post's poll.
    return reply_form(obj=post, formdata=MultiDict({"content": "Edited content", **formdata}))


def edit_topic_form(topic, **formdata):
    pluggy.hook.flaskbb_form_topic(form=NewTopicForm)
    return EditTopicForm(
        obj=topic,
        formdata=MultiDict({"title": topic.title, "content": "Edited content", **formdata}),
    )


def test_editing_a_reply_with_poll_data_creates_a_poll(request_context, topic, user):
    post = Post(content="A reply").save(user=user, topic=topic)

    edit_reply_form(post, poll_data=poll_json()).save(user, topic)

    poll = Poll.get(Poll.post_id == post.id)
    assert poll is not None
    assert poll.question == "Favorite color?"
    assert [o.text for o in poll.options] == ["Red", "Blue"]


def test_editing_a_reply_replaces_a_poll_without_votes(request_context, poll, user):
    payload = poll_json(question="Pick one", type="multiple", options=["A", "B", "C"])

    edit_reply_form(poll.post, poll_data=payload).save(user, poll.post.topic)

    edited = Poll.get(Poll.post_id == poll.post_id)
    assert edited.question == "Pick one"
    assert edited.is_multiple_choice
    assert [(o.text, o.position) for o in edited.options] == [("A", 0), ("B", 1), ("C", 2)]
    assert PollOption.count() == 3


def test_editing_a_reply_with_empty_poll_data_removes_a_poll_without_votes(
    request_context, poll, user
):
    post_id = poll.post_id

    edit_reply_form(poll.post, poll_data="").save(user, poll.post.topic)

    assert Poll.get(Poll.post_id == post_id) is None
    assert PollOption.count() == 0


def test_editing_a_reply_with_malformed_poll_data_keeps_its_poll(request_context, poll, user):
    edit_reply_form(poll.post, poll_data="not json").save(user, poll.post.topic)

    assert Poll.get(Poll.post_id == poll.post_id).question == "Favorite color?"


def test_editing_a_reply_without_poll_data_in_the_request_keeps_its_poll(
    request_context, poll, user
):
    edit_reply_form(poll.post).save(user, poll.post.topic)

    assert Poll.get(Poll.post_id == poll.post_id) is not None


@pytest.mark.parametrize("payload", ["", poll_json(question="Pick one")])
def test_editing_a_reply_leaves_a_poll_with_votes_alone(
    request_context, poll, user, admin_user, payload
):
    cast_vote(poll, admin_user, [poll.options[0].id])

    edit_reply_form(poll.post, poll_data=payload).save(user, poll.post.topic)

    kept = Poll.get(Poll.post_id == poll.post_id)
    assert kept.question == "Favorite color?"
    assert kept.total_votes == 1


def test_edit_topic_form_has_poll_data_field(request_context, topic):
    assert hasattr(edit_topic_form(topic), "poll_data")


def test_editing_a_topic_with_poll_data_creates_a_poll(request_context, topic, user):
    edit_topic_form(topic, poll_data=poll_json()).save(user, topic.forum)

    poll = Poll.get(Poll.post_id == topic.first_post.id)
    assert poll is not None
    assert [o.text for o in poll.options] == ["Red", "Blue"]


def test_editing_a_topic_with_empty_poll_data_removes_its_poll(request_context, topic, user):
    Poll(post_id=topic.first_post.id, question="Best pizza?", poll_type="single").save()

    edit_topic_form(topic, poll_data="").save(user, topic.forum)

    assert Poll.get(Poll.post_id == topic.first_post.id) is None


def test_malformed_poll_data_does_not_prevent_topic_creation(request_context, forum, user):
    form = new_topic_form(
        title="A topic with junk poll data", content="Still works", track_topic=False
    )
    form.poll_data.data = "not json"

    topic = form.save(user, forum)

    assert topic is not None
    assert topic.id is not None
    assert Poll.get(Poll.post_id == topic.first_post.id) is None


def test_topics_only_removes_poll_data_from_reply_form(request_context, default_settings):
    with topics_only(True):
        assert not hasattr(reply_form(), "poll_data")


def test_topics_only_does_not_affect_new_topic_form(request_context, default_settings):
    with topics_only(True):
        assert hasattr(new_topic_form(), "poll_data")


def test_topics_only_disabled_again_restores_the_field(request_context, default_settings):
    with topics_only(True):
        assert not hasattr(reply_form(), "poll_data")
    with topics_only(False):
        assert hasattr(reply_form(), "poll_data")


def test_topics_only_prevents_a_reply_poll_end_to_end(request_context, topic, user):
    with topics_only(True):
        form = reply_form(content="Trying to attach a poll anyway")
        assert not hasattr(form, "poll_data")

        post = form.save(user, topic)

        assert Poll.get(Poll.post_id == post.id) is None


def rendered_poll_data(html):
    match = re.search(
        r'<input id="poll_data" name="poll_data" type="hidden" value="([^"]*)">', html
    )
    assert match is not None
    return unescape(match.group(1))


def test_hidden_tag_leaves_poll_data_to_the_plugin(request_context, default_settings):
    form = new_topic_form()

    assert "poll_data" not in form.hidden_tag()
    assert rendered_poll_data(vote_plugin.flaskbb_tpl_form_new_topic_after(form)) == ""


def test_editing_a_reply_starts_with_its_poll_in_the_dialog(request_context, poll):
    form = reply_form(obj=poll.post)

    html = vote_plugin.flaskbb_tpl_form_new_post_after(form)

    assert 'id="vote-poll-dialog"' in html
    assert "data-vote-poll-locked" not in html
    assert json.loads(rendered_poll_data(html)) == {
        "question": "Favorite color?",
        "type": "single",
        "options": ["Red", "Green", "Blue"],
    }


def test_a_resubmitted_edit_form_keeps_the_submitted_poll_data(request_context, poll):
    form = edit_reply_form(poll.post, poll_data="")

    html = vote_plugin.flaskbb_tpl_form_new_post_after(form)

    assert rendered_poll_data(html) == ""


def test_editing_a_reply_shows_a_poll_with_votes_read_only(request_context, poll, admin_user):
    cast_vote(poll, admin_user, [poll.options[0].id])
    form = reply_form(obj=poll.post)

    html = vote_plugin.flaskbb_tpl_form_new_post_after(form)

    assert poll.question in html
    assert "data-vote-poll-locked" in html
    assert "This poll has votes and can no longer be changed." in html
    assert 'name="option_id"' not in html
    # for once a moderator deleted the poll
    assert 'id="vote-poll-dialog"' in html
    assert rendered_poll_data(html) == ""


def test_editing_a_reply_offers_poll_deletion_without_a_nested_form(
    request_context, poll, admin_user
):
    """The edit page renders the poll inside its own form - a form in there
    would be dropped by the browser, and its delete button would submit the
    edit form instead."""
    cast_vote(poll, admin_user, [poll.options[0].id])
    login_user(admin_user)
    try:
        form = reply_form(obj=poll.post, content="Edited content")
        html = vote_plugin.flaskbb_tpl_form_new_post_after(form)
    finally:
        logout_user()

    assert html is not None
    assert "<form" not in html
    assert f'hx-post="{url_for("vote.delete_poll", poll_id=poll.id)}"' in html
    assert 'hx-params="none"' in html


def test_editing_a_reply_without_a_poll_renders_an_empty_dialog(request_context, topic, user):
    post = Post(content="No poll here").save(user=user, topic=topic)
    form = reply_form(obj=post, content="Edited content")

    html = vote_plugin.flaskbb_tpl_form_new_post_after(form)

    assert 'id="vote-poll-dialog"' in html
    assert rendered_poll_data(html) == ""


def test_editing_a_reply_while_topics_only_shows_its_poll_read_only(request_context, poll):
    with topics_only(True):
        form = reply_form(obj=poll.post)
        html = vote_plugin.flaskbb_tpl_form_new_post_after(form)

    assert poll.question in html
    assert "This poll cannot be changed here." in html
    assert 'id="vote-poll-dialog"' not in html


def test_editing_a_topic_starts_with_its_poll_in_the_dialog(request_context, topic, user):
    poll = Poll(post_id=topic.first_post.id, question="Best pizza?", poll_type="single")
    poll.save()
    PollOption(poll_id=poll.id, text="Margherita", position=0).save()
    PollOption(poll_id=poll.id, text="Pepperoni", position=1).save()

    html = vote_plugin.flaskbb_tpl_form_new_topic_after(edit_topic_form(topic))

    assert json.loads(rendered_poll_data(html))["options"] == ["Margherita", "Pepperoni"]


def test_editing_a_topic_without_a_poll_renders_an_empty_dialog(request_context, topic):
    html = vote_plugin.flaskbb_tpl_form_new_topic_after(edit_topic_form(topic))

    assert 'id="vote-poll-dialog"' in html
    assert rendered_poll_data(html) == ""
