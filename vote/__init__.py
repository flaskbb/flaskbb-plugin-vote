"""
vote
~~~~

A polls plugin for FlaskBB. Lets a poster attach a single- or
multiple-choice poll to a topic or a reply, via a button on the markdown
editor's toolbar.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

import os

from flask import Flask
from flask_login import current_user
from flaskbb.forum.forms import NewTopicForm, ReplyForm
from flaskbb.forum.models import Post
from flaskbb.settings import BoolSetting, flaskbb_config, IntSetting, SettingGroup
from flaskbb.utils.helpers import real, render_template
from pluggy import HookimplMarker
from wtforms import HiddenField

from .forms import DeletePollForm, VoteForm
from .models import Poll
from .utils import can_delete_poll, create_poll_for_post, parse_poll_payload
from .views import vote_bp

__version__ = "1.0.0"

hookimpl = HookimplMarker("flaskbb")

# Stashes a pending poll payload on the Post between save and post-save hooks,
# until the post has an id to attach it to.
# Hooks: flaskbb_form_{topic,post}_save (before the post is saved) and
# flaskbb_event_post_save_after (once it has an id to attach to).
_PENDING_ATTR = "_vote_pending_payload"


@hookimpl
def flaskbb_load_migrations():
    return os.path.join(os.path.dirname(__file__), "migrations")


@hookimpl
def flaskbb_load_translations():
    return os.path.join(os.path.dirname(__file__), "translations")


@hookimpl
def flaskbb_load_blueprints(app: Flask):
    app.register_blueprint(vote_bp, url_prefix=app.config.get("PLUGIN_VOTE_URL_PREFIX", "/vote"))


SETTINGS = SettingGroup(
    key="vote",
    name="Vote Settings",
    description="Settings for the poll plugin.",
    settings=(
        IntSetting(
            key="MAX_OPTIONS",
            value=10,
            min=2,
            max=50,
            name="Maximum poll options",
            description="The maximum number of options a poll may have.",
        ),
        BoolSetting(
            key="TOPICS_ONLY",
            value=False,
            name="Only allow polls on topics",
            description=(
                "If enabled, a poll can only be attached to a topic's first "
                "post, not to a reply. Polls already attached to a reply "
                "are unaffected."
            ),
        ),
    ),
)


@hookimpl
def flaskbb_load_setting_groups():
    return SETTINGS


_DEFAULT_MAX_OPTIONS = SETTINGS.settings[0].value
_DEFAULT_TOPICS_ONLY = SETTINGS.settings[1].value


def _max_options() -> int:
    # Falls back to the setting's own default when the plugin hasn't been
    # installed yet (admin panel > Plugins > Install seeds it into the
    # settings table) - a poll shouldn't be impossible to create just
    # because nobody has visited that page yet.
    value = flaskbb_config["VOTE_MAX_OPTIONS"]
    return int(value) if value is not None else _DEFAULT_MAX_OPTIONS


def _topics_only() -> bool:
    value = flaskbb_config["VOTE_TOPICS_ONLY"]
    return bool(value) if value is not None else _DEFAULT_TOPICS_ONLY


# Attaching the hidden poll_data field to the topic/post forms
@hookimpl
def flaskbb_form_topic(form: type[NewTopicForm]):
    form.poll_data = HiddenField()


@hookimpl
def flaskbb_form_post(form: type[ReplyForm]):
    # Skipping the field entirely when polls are topics-only means a reply
    # form never has anything to submit or stash - no separate enforcement
    # needed at save time, and the toolbar button hides itself here the
    # same way it already does for the quick-reply box (see
    # flaskbb_tpl_form_new_post_after below).
    #
    # form is the *class*, shared and re-patched on every request - if the
    # setting was off on some earlier request, poll_data is still sitting
    # in form.__dict__ from that call and has to be explicitly removed, or
    # toggling the setting on would have no effect until the process
    # restarts.
    if _topics_only():
        if "poll_data" in form.__dict__:
            delattr(form, "poll_data")
        return
    form.poll_data = HiddenField()


@hookimpl
def flaskbb_form_topic_save(form, topic):
    poll_data = getattr(form, "poll_data", None)
    post = getattr(topic, "_post", None)
    if poll_data is not None and post is not None:
        setattr(post, _PENDING_ATTR, poll_data.data)


@hookimpl
def flaskbb_form_post_save(form, post: Post):
    poll_data = getattr(form, "poll_data", None)
    if poll_data is not None:
        setattr(post, _PENDING_ATTR, poll_data.data)


@hookimpl
def flaskbb_event_post_save_after(post: Post, is_new: bool):
    if not is_new:
        return

    raw = getattr(post, _PENDING_ATTR, None)
    if not raw:
        return

    payload = parse_poll_payload(raw, max_options=_max_options())
    if payload is None:
        return

    create_poll_for_post(post, payload)


# --- Rendering ---


def _render_existing_poll(post: Post | None):
    """Renders ``post``'s poll (if it has one) read-only, for display on an
    edit form - editing a post/topic never touches its poll, only the
    dedicated delete action does, so this never offers a voting UI.
    """
    if post is None:
        return None

    poll: Poll | None = post.poll  # type: ignore[attr-defined] # pyright: ignore[reportAttributeAccessIssue]
    if poll is None:
        return None

    user = real(current_user)
    return render_template(
        "vote/_poll_widget.html",
        poll=poll,
        user_vote_ids=[],
        can_vote=False,
        editing=True,
        can_delete=user.is_authenticated and can_delete_poll(user, poll),
        form=VoteForm(),
        delete_form=DeletePollForm(),
    )


@hookimpl
def flaskbb_tpl_form_new_topic_after(form):
    if hasattr(form, "poll_data"):
        return render_template("vote/_form_extra.html", form=form)

    # EditTopicForm - flaskbb_form_topic(form=NewTopicForm) above patches a
    # sibling class of EditTopicForm (both just subclass TopicForm), so an
    # EditTopicForm instance never has poll_data. Show its topic's existing
    # poll read-only instead, since flaskbb_form_topic_save never fires a
    # poll onto it either.
    topic = getattr(form, "topic", None)
    if topic is None:
        return None
    return _render_existing_poll(topic.first_post)


@hookimpl
def flaskbb_tpl_form_new_post_after(form):
    # ReplyForm is shared between NewPost and EditPost (see forum/views.py) -
    # form.post is only set when editing. A poll attached while editing
    # would never be created (flaskbb_event_post_save_after only fires for
    # is_new=True posts), so the create-poll field must not render there -
    # show the post's existing poll read-only instead.
    post = getattr(form, "post", None)
    if post is not None:
        return _render_existing_poll(post)
    if hasattr(form, "poll_data"):
        return render_template("vote/_form_extra.html", form=form)
    return None


@hookimpl
def flaskbb_tpl_markdown_toolbar_buttons():
    return render_template("vote/_toolbar_button.html")


@hookimpl
def flaskbb_tpl_markdown_cheatsheet():
    return render_template("vote/_cheatsheet.html")


@hookimpl
def flaskbb_tpl_scripts():
    return render_template("vote/_scripts.html")


@hookimpl
def flaskbb_tpl_post_content_before(post: Post):
    # Post doesn't declare `poll` itself - it's added by Poll.post's backref
    # in models.py, since Post is a core model this plugin doesn't own.
    poll: Poll | None = post.poll  # type: ignore[attr-defined] # pyright: ignore[reportAttributeAccessIssue]
    if poll is None:
        return None

    user = real(current_user)
    user_vote_ids = poll.option_ids_voted_by(user.id) if user.is_authenticated else []
    return render_template(
        "vote/_poll_widget.html",
        poll=poll,
        user_vote_ids=user_vote_ids,
        can_vote=user.is_authenticated,
        editing=False,
        can_delete=user.is_authenticated and can_delete_poll(user, poll),
        form=VoteForm(),
        delete_form=DeletePollForm(),
    )
