"""Unit tests for the unique testing module."""

import pytest


@pytest.mark.parametrize("kwargs, substring", [
    ({"C": "Test"}, "C=Test"),
    ({"ST": "Test"}, "ST=Test"),
    ({"L": "Test"}, "L=Test"),
    ({"O": "Test"}, "O=Test"),
    ({"OU": "Test"}, "OU=Test"),
    ({"CN": "Test"}, "CN=Test"),
])
def test_unique_subject_c(kwargs, substring, unique):
    """A unique subject with arguments should include the expected substring."""
    assert substring in unique("subject", **kwargs)


def test_unique_subject_twice(unique):
    """Getting a subject twice should not return the same value."""
    assert unique("subject") != unique("subject")
