"""
End-to-end tests for the flaskbb_form_topic/flaskbb_form_post +
flaskbb_event_post_save_after hook chain that turns a submitted poll_data
payload into a real Poll row. This only works if the `vote` package is
installed into flaskbb's environment (so its entry point is discovered by
create_app() and its hookimpls actually run) - see README.md.
"""

import json
from contextlib import contextmanager

from flask import url_for
from flask_login import login_user, logout_user
from flaskbb.extensions import pluggy
from flaskbb.forum.forms import EditTopicForm, NewTopicForm, ReplyForm
from flaskbb.settings import flaskbb_config

import vote as vote_plugin
from vote.models import Poll, PollOption


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


def test_editing_a_reply_with_poll_data_creates_no_poll(request_context, topic, user):
    """ReplyForm is shared between NewPost and EditPost - poll_data is only
    ever meant to be honored for a brand new post (see the comment on
    flaskbb_tpl_form_new_post_after in vote/__init__.py). Simulating an
    edit here by passing obj=<an existing post> exercises the is_new=False
    guard in flaskbb_event_post_save_after directly, regardless of
    whether the template actually renders the field for edits.
    """
    existing_post = topic.first_post
    form = reply_form(obj=existing_post, content="Edited content", track_topic=False)
    form.poll_data.data = poll_json()

    form.save(user, topic)

    assert Poll.get(Poll.post_id == existing_post.id) is None


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


def test_editing_a_reply_shows_its_poll_read_only(request_context, poll):
    form = reply_form(obj=poll.post, content="Edited content")

    html = vote_plugin.flaskbb_tpl_form_new_post_after(form)

    assert html is not None
    assert poll.question in html
    assert 'name="option_id"' not in html


def test_editing_a_reply_offers_poll_deletion_without_a_nested_form(
    request_context, poll, admin_user
):
    """The edit page renders the poll inside its own form - a form in there
    would be dropped by the browser, and its delete button would submit the
    edit form instead."""
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


def test_editing_a_reply_without_a_poll_renders_nothing(request_context, topic, user):
    from flaskbb.forum.models import Post

    post = Post(content="No poll here").save(user=user, topic=topic)
    form = reply_form(obj=post, content="Edited content")

    assert vote_plugin.flaskbb_tpl_form_new_post_after(form) is None


def test_editing_a_topic_shows_its_poll_read_only(request_context, topic, user):
    poll = Poll(post_id=topic.first_post.id, question="Best pizza?", poll_type="single")
    poll.save()
    PollOption(poll_id=poll.id, text="Margherita", position=0).save()
    PollOption(poll_id=poll.id, text="Pepperoni", position=1).save()

    form = EditTopicForm(obj=topic.first_post, title=topic.title)
    html = vote_plugin.flaskbb_tpl_form_new_topic_after(form)

    assert html is not None
    assert "Best pizza?" in html
    assert 'name="option_id"' not in html


def test_editing_a_topic_without_a_poll_renders_nothing(request_context, topic):
    form = EditTopicForm(obj=topic.first_post, title=topic.title)

    assert vote_plugin.flaskbb_tpl_form_new_topic_after(form) is None
