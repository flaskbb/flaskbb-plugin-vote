from vote.models import Poll, PollOption, PollVote


def test_poll_total_votes_with_no_votes(poll):
    assert poll.total_votes == 0


def test_poll_total_votes_counts_across_options(poll, user, admin_user):
    red, green = poll.options[0], poll.options[1]
    PollVote(poll_option_id=red.id, user_id=user.id).save()
    PollVote(poll_option_id=green.id, user_id=admin_user.id).save()

    poll = Poll.get(Poll.id == poll.id)
    assert poll.total_votes == 2


def test_option_vote_count(poll, user):
    red = poll.options[0]
    PollVote(poll_option_id=red.id, user_id=user.id).save()

    assert red.vote_count == 1
    assert poll.options[1].vote_count == 0


def test_option_ids_voted_by_returns_only_that_users_votes(poll, user, admin_user):
    red, green = poll.options[0], poll.options[1]
    PollVote(poll_option_id=red.id, user_id=user.id).save()
    PollVote(poll_option_id=green.id, user_id=admin_user.id).save()

    assert poll.option_ids_voted_by(user.id) == [red.id]
    assert poll.option_ids_voted_by(admin_user.id) == [green.id]


def test_option_ids_voted_by_empty_for_nonvoter(poll, admin_user):
    assert poll.option_ids_voted_by(admin_user.id) == []


def test_is_multiple_choice(poll, multi_poll):
    assert poll.is_multiple_choice is False
    assert multi_poll.is_multiple_choice is True


def test_deleting_post_cascades_to_poll_and_options(poll):
    post = poll.post
    option_ids = [option.id for option in poll.options]
    poll_id = poll.id

    post.delete()

    assert Poll.get(Poll.id == poll_id) is None
    assert PollOption.get_all(PollOption.id.in_(option_ids)) == []


def test_deleting_option_cascades_to_votes(poll, user):
    red = poll.options[0]
    vote = PollVote(poll_option_id=red.id, user_id=user.id).save()
    vote_id = vote.id

    red.delete()

    assert PollVote.get(PollVote.id == vote_id) is None
