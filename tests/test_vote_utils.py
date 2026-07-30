import json

import pytest

from vote.models import Poll, PollVote
from vote.utils import (
    can_access_poll,
    can_delete_poll,
    cast_vote,
    create_poll_for_post,
    parse_poll_payload,
    poll_type_is_valid_for,
)


def valid_payload(**overrides):
    data = {"question": "Favorite color?", "type": "single", "options": ["Red", "Blue"]}
    data.update(overrides)
    return json.dumps(data)


def test_parse_poll_payload_valid():
    payload = parse_poll_payload(valid_payload(), max_options=10)
    assert payload is not None
    assert payload.question == "Favorite color?"
    assert payload.poll_type == "single"
    assert payload.options == ("Red", "Blue")


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_parse_poll_payload_empty_is_none(raw):
    assert parse_poll_payload(raw, max_options=10) is None


def test_parse_poll_payload_invalid_json():
    assert parse_poll_payload("not json", max_options=10) is None


def test_parse_poll_payload_not_an_object():
    assert parse_poll_payload("[1, 2, 3]", max_options=10) is None


def test_parse_poll_payload_blank_question():
    assert parse_poll_payload(valid_payload(question="   "), max_options=10) is None


def test_parse_poll_payload_question_too_long():
    assert parse_poll_payload(valid_payload(question="x" * 256), max_options=10) is None


def test_parse_poll_payload_invalid_type():
    assert parse_poll_payload(valid_payload(type="quiz"), max_options=10) is None


def test_parse_poll_payload_too_few_options():
    payload = valid_payload(options=["Only one"])
    assert parse_poll_payload(payload, max_options=10) is None


def test_parse_poll_payload_too_many_options():
    options = [f"Option {i}" for i in range(11)]
    assert parse_poll_payload(valid_payload(options=options), max_options=10) is None


def test_parse_poll_payload_respects_max_options():
    options = [f"Option {i}" for i in range(5)]
    assert parse_poll_payload(valid_payload(options=options), max_options=4) is None
    assert parse_poll_payload(valid_payload(options=options), max_options=5) is not None


def test_parse_poll_payload_strips_and_drops_blank_options():
    payload = parse_poll_payload(
        valid_payload(options=[" Red ", "", "  ", "Blue"]), max_options=10
    )
    assert payload.options == ("Red", "Blue")


def test_parse_poll_payload_option_too_long():
    assert (
        parse_poll_payload(valid_payload(options=["Red", "x" * 256]), max_options=10)
        is None
    )


def test_parse_poll_payload_non_string_option():
    assert parse_poll_payload(valid_payload(options=["Red", 5]), max_options=10) is None


def test_create_poll_for_post(topic, user):
    from flaskbb.forum.models import Post

    post = Post(content="reply").save(user=user, topic=topic)
    payload = parse_poll_payload(valid_payload(), max_options=10)

    poll = create_poll_for_post(post, payload)

    assert poll.id is not None
    assert poll.post_id == post.id
    assert [o.text for o in poll.options] == ["Red", "Blue"]
    assert [o.position for o in poll.options] == [0, 1]


def test_can_access_poll_true_for_member_of_forum_group(poll, user):
    assert can_access_poll(user, poll) is True


def test_can_access_poll_false_when_forum_has_no_matching_group(category, user):
    from flaskbb.forum.models import Forum, Post, Topic

    restricted_forum = Forum(title="Restricted", category_id=category.id)
    # Forum.save() defaults an unsaved forum's groups to *every* group when
    # `groups` is omitted (its own documented behavior) - pass explicitly.
    restricted_forum.save(groups=[])

    topic = Topic(title="Restricted topic")
    topic = topic.save(
        forum=restricted_forum, user=user, post=Post(content="Restricted post")
    )
    poll = Poll(
        post_id=topic.first_post.id, question="Favorite color?", poll_type="single"
    )
    poll.save()

    assert can_access_poll(user, poll) is False


def test_poll_type_is_valid_for_single_choice(poll):
    red, green = poll.options[0], poll.options[1]
    assert poll_type_is_valid_for(poll, [red.id]) is True
    assert poll_type_is_valid_for(poll, [red.id, green.id]) is False


def test_poll_type_is_valid_for_multiple_choice(multi_poll):
    cheese, pepperoni = multi_poll.options[0], multi_poll.options[1]
    assert poll_type_is_valid_for(multi_poll, [cheese.id]) is True
    assert poll_type_is_valid_for(multi_poll, [cheese.id, pepperoni.id]) is True


def test_poll_type_is_valid_for_rejects_empty(poll):
    assert poll_type_is_valid_for(poll, []) is False


def test_poll_type_is_valid_for_rejects_foreign_option_id(poll, multi_poll):
    foreign_option_id = multi_poll.options[0].id
    assert poll_type_is_valid_for(poll, [foreign_option_id]) is False


def test_cast_vote_records_a_vote(poll, user):
    red = poll.options[0]
    cast_vote(poll, user, [red.id])

    assert poll.option_ids_voted_by(user.id) == [red.id]


def test_cast_vote_replaces_previous_vote(poll, user):
    red, green = poll.options[0], poll.options[1]
    cast_vote(poll, user, [red.id])
    cast_vote(poll, user, [green.id])

    assert poll.option_ids_voted_by(user.id) == [green.id]
    assert red.vote_count == 0
    assert green.vote_count == 1


def test_cast_vote_does_not_touch_other_users_votes(poll, user, admin_user):
    red = poll.options[0]
    cast_vote(poll, admin_user, [red.id])
    cast_vote(poll, user, [poll.options[1].id])

    assert PollVote.count() == 2


def test_can_delete_poll_false_for_normal_user(poll, user):
    assert can_delete_poll(user, poll) is False


def test_can_delete_poll_false_for_the_poll_author(poll):
    assert can_delete_poll(poll.post.user, poll) is False


def test_can_delete_poll_true_for_admin(poll, admin_user):
    assert can_delete_poll(admin_user, poll) is True


def test_can_delete_poll_true_for_super_moderator(poll, super_moderator_user):
    assert can_delete_poll(super_moderator_user, poll) is True


def test_can_delete_poll_true_for_moderator_of_the_polls_forum(poll, moderator_user):
    assert can_delete_poll(moderator_user, poll) is True


def test_can_delete_poll_false_for_moderator_of_a_different_forum(
    poll, other_moderator_user
):
    assert can_delete_poll(other_moderator_user, poll) is False
