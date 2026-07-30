"""
vote.forms
~~~~~~~~~~

Forms used to cast a vote or delete a poll. Their only real job is to
carry the CSRF token - a vote's option ids are read straight from
``request.form`` in the view since the set of valid choices is only known
once the poll is loaded, and depends on whether it's single or multiple
choice.

:copyright: (c) 2026 by Peter Justin.
:license: BSD License, see LICENSE for more details.
"""

from flask_wtf import FlaskForm


class VoteForm(FlaskForm):
    """Used in _poll_widget.html to cast the vote.
    It just contains the hidden CSRF field
    """

    pass


class DeletePollForm(FlaskForm):
    """Used in _poll_widget.html to delete a poll.
    It just contains the hidden CSRF field
    """
