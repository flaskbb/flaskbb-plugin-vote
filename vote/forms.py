"""
vote.forms
~~~~~~~~~~

Forms used to cast a vote or delete a poll. Their only real job is to
carry the CSRF token - a vote's option ids are read straight from
``request.form`` in the view since the set of valid choices is only known
once the poll is loaded, and depends on whether it's single or multiple
choice.

Also the ``poll_data`` field the plugin adds to the topic and post forms.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.widgets import Input


class PollDataInput(Input):
    """A hidden input that ``form.hidden_tag()`` leaves out, since it only
    picks up ``HiddenInput`` widgets. The page renders that tag before any
    plugin hook runs - rendering the field next to the poll dialog instead
    lets an edit form start out with the post's current poll.
    """

    input_type = "hidden"
    validation_attrs = ["disabled"]


def poll_data_field() -> StringField:
    return StringField(widget=PollDataInput())


class VoteForm(FlaskForm):
    """Used in _poll_widget.html to cast the vote.
    It just contains the hidden CSRF field
    """

    pass


class DeletePollForm(FlaskForm):
    """Used in _poll_widget.html to delete a poll.
    It just contains the hidden CSRF field
    """
