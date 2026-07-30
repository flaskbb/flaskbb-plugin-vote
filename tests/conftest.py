import pytest
from flaskbb.forum.models import Post
from tests.fixtures.app import *
from tests.fixtures.forum import *
from tests.fixtures.user import *

from vote.models import Poll, PollOption


def _reply(topic, user):
    """A reply post in ``topic`` - polls attach to this, not the first
    post, so cascade-delete tests don't get entangled with Post.delete()
    redirecting to Topic.delete() for a topic's first post."""
    return Post(content="Test reply").save(user=user, topic=topic)


@pytest.fixture
def poll(topic, user):
    post = _reply(topic, user)
    poll = Poll(post_id=post.id, question="Favorite color?", poll_type="single")
    poll.save()
    PollOption(poll_id=poll.id, text="Red", position=0).save()
    PollOption(poll_id=poll.id, text="Green", position=1).save()
    PollOption(poll_id=poll.id, text="Blue", position=2).save()
    return Poll.get(Poll.id == poll.id)


@pytest.fixture
def multi_poll(topic, user):
    post = _reply(topic, user)
    poll = Poll(post_id=post.id, question="Favorite toppings?", poll_type="multiple")
    poll.save()
    PollOption(poll_id=poll.id, text="Cheese", position=0).save()
    PollOption(poll_id=poll.id, text="Pepperoni", position=1).save()
    PollOption(poll_id=poll.id, text="Mushroom", position=2).save()
    return Poll.get(Poll.id == poll.id)
