"""Integration tests for the Redis service."""


def test_redis_service(redis_client):
    """The Redis service should return true on PING."""
    assert redis_client.ping()
