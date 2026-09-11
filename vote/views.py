"""
vote.views
~~~~~~~~~~

The views for casting a vote in a poll and for deleting one.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

import logging

from flask import abort, Blueprint, flash, redirect, request
from flask.views import MethodView
from flask_babelplus import gettext as _
from flask_login import current_user, login_required
from flaskbb.utils.helpers import real, register_view

from .forms import DeletePollForm, VoteForm
from .models import Poll
from .utils import can_access_poll, can_delete_poll, cast_vote, poll_type_is_valid_for

logger = logging.getLogger(__name__)

vote_bp = Blueprint("vote", __name__, template_folder="templates", static_folder="static")


class CastVote(MethodView):
    decorators = [login_required]

    def post(self, poll_id: int):
        poll = Poll.get_or_404(Poll.id == poll_id)
        user = real(current_user)

        if not can_access_poll(user, poll):
            abort(404)

        form = VoteForm()
        if not form.validate_on_submit():
            flash(_("Could not verify the vote request, please try again."), "danger")
            return redirect(poll.post.url)

        option_ids = [int(v) for v in request.form.getlist("option_id") if v.isdigit()]

        if not poll_type_is_valid_for(poll, option_ids):
            flash(_("That is not a valid choice for this poll."), "danger")
            return redirect(poll.post.url)

        cast_vote(poll, user, option_ids)
        flash(_("Your vote has been recorded."), "success")
        return redirect(poll.post.url)


class DeletePoll(MethodView):
    decorators = [login_required]

    def post(self, poll_id: int):
        poll = Poll.get_or_404(Poll.id == poll_id)
        user = real(current_user)

        if not can_delete_poll(user, poll):
            abort(404)

        form = DeletePollForm()
        if not form.validate_on_submit():
            flash(_("Could not verify the delete request, please try again."), "danger")
            return redirect(poll.post.url)

        post_url = poll.post.url
        poll.delete()
        flash(_("The poll has been deleted."), "success")
        return redirect(post_url)


register_view(
    vote_bp,
    routes=["/<int:poll_id>/vote"],
    view_func=CastVote.as_view("cast_vote"),
)
register_view(
    vote_bp,
    routes=["/<int:poll_id>/delete"],
    view_func=DeletePoll.as_view("delete_poll"),
)
