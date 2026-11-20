"""Unit tests for the logger module."""

import logging
import sys
from argparse import ArgumentParser
from contextlib import contextmanager
from io import StringIO

import pytest
from hamcrest import (
    assert_that,
    equal_to,
    has_properties,
    is_,
    matches_regexp,
)

from tarameteo.logger import (
    LoggerFormatter,
    LoggerHandlerAction,
    LoggerLevelAction,
    setup_logger,
)

DATE_PATTERN = r"\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}"


@contextmanager
def logger_stream(formatter):
    """Context manager for a stream used by a logger handler at debug level."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)

    setup_logger(logging.DEBUG, handler, formatter)
    try:
        yield stream
    finally:
        setup_logger()


def test_logger_formatter_default():
    """The LoggerFormatter should include microseconds by default."""
    with logger_stream(LoggerFormatter()) as stream:
        message = "message"
        logging.debug(message)
        stream.seek(0)

        assert_that(
            stream.readline(),
            matches_regexp(f'{DATE_PATTERN} {"DEBUG":<7} root {message}\n'),
        )


def test_logger_formatter_non_root_logger():
    """The LoggerFormatter includes the name even for non-root loggers."""
    with logger_stream(LoggerFormatter()) as stream:
        message = "message"
        logger = logging.getLogger("deeply.nested.logger")
        logger.error(message)
        stream.seek(0)

        assert_that(
            stream.readline(),
            matches_regexp(f'{DATE_PATTERN} {"ERROR":<7} deeply.nested.logger {message}\n'),
        )


def test_logger_formatter_custom_fmt():
    """The LoggerFormatter can take fmt as argument."""
    with logger_stream(LoggerFormatter(fmt="%(message)s")) as stream:
        message = "message"
        logging.info(message)
        stream.seek(0)

        assert_that(
            stream.readline(),
            f"{message}\n",
        )


def test_logger_formatter_custom_datefmt():
    """The LoggerFormatter can also take datefmt as argument."""
    with logger_stream(LoggerFormatter(datefmt="%a, %d %b %Y %H:%M:%S")) as stream:
        date_pattern = r"\w{3}, \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2}"
        message = "message"
        logging.info(message)
        stream.seek(0)

        assert_that(
            stream.readline(),
            matches_regexp(f'{date_pattern} {"INFO":<7} root {message}\n'),
        )


def test_logger_handler_action_default():
    """A LoggerHandlerAction should default to stderr."""
    parser = ArgumentParser()
    parser.add_argument("--handler", action=LoggerHandlerAction)

    result = parser.parse_args([])

    assert_that(
        result,
        has_properties(
            handler=has_properties(
                stream=sys.stderr,
                formatter=is_(LoggerFormatter),
            )
        ),
    )


def test_logger_handler_action_stdout():
    """A LoggerHandlerAction should use stdout with -."""
    parser = ArgumentParser()
    parser.add_argument("--handler", action=LoggerHandlerAction)

    result = parser.parse_args(["--handler", "-"])

    assert_that(
        result,
        has_properties(
            handler=has_properties(
                stream=sys.stdout,
                formatter=is_(LoggerFormatter),
            )
        ),
    )


def test_logger_handler_action_file(tmpdir):
    """A LoggerHandlerAction should use file stream with a filename."""
    parser = ArgumentParser()
    parser.add_argument("--handler", action=LoggerHandlerAction)
    filename = str(tmpdir.join("test.log"))

    result = parser.parse_args(["--handler", filename])

    assert_that(
        result,
        has_properties(
            handler=has_properties(
                baseFilename=filename,
                formatter=is_(LoggerFormatter),
            )
        ),
    )


def test_logger_level_action_default():
    """A LoggerLevelAction should default to INFO."""
    parser = ArgumentParser()
    parser.add_argument("--level", action=LoggerLevelAction)

    result = parser.parse_args([])

    assert_that(result, has_properties(level=logging.INFO))


@pytest.mark.parametrize(
    "choice, level",
    [
        ("debug", logging.DEBUG),
        ("Debug", logging.DEBUG),
        ("DEBUG", logging.DEBUG),
    ],
)
def test_logger_level_action_valid_choice(choice, level):
    """A LoggerLevelAction should set on a valid choice."""
    parser = ArgumentParser()
    parser.add_argument("--level", action=LoggerLevelAction)

    result = parser.parse_args(["--level", choice])

    assert_that(result, has_properties(level=level))


def test_logger_level_action_invalid_choice():
    """A LoggerLevelAction should exit on an invalid choice."""
    parser = ArgumentParser()
    parser.add_argument("--level", action=LoggerLevelAction)

    with pytest.raises(SystemExit):
        parser.parse_args(["--level", "test"])


def test_logger_level_action_unsupported_choice():
    """A LoggerLevelAction should exit on an unsupported choice."""
    parser = ArgumentParser()
    parser.add_argument("--level", action=LoggerLevelAction, choices=["test"])

    with pytest.raises(SystemExit):
        parser.parse_args(["--level", "test"])


@pytest.mark.parametrize(
    "level, records",
    [
        pytest.param(
            logging.ERROR,
            [
                has_properties(levelname="ERROR"),
            ],
            id="ERROR",
        ),
        pytest.param(
            logging.WARNING,
            [
                has_properties(levelname="ERROR"),
                has_properties(levelname="WARNING"),
            ],
            id="WARNING",
        ),
        pytest.param(
            logging.INFO,
            [
                has_properties(levelname="ERROR"),
                has_properties(levelname="WARNING"),
                has_properties(levelname="INFO"),
            ],
            id="INFO",
        ),
        pytest.param(
            logging.DEBUG,
            [
                has_properties(levelname="ERROR"),
                has_properties(levelname="WARNING"),
                has_properties(levelname="INFO"),
                has_properties(levelname="DEBUG"),
            ],
            id="DEBUG",
        ),
    ],
)
def test_setup_logger_level(level, records, logger_handler):
    """The log level should output expected records."""
    logger = setup_logger(level, logger_handler)
    logger.error("This is error")
    logger.warning("This is warning")
    logger.info("This is info")
    logger.debug("This is debug")

    result = logger_handler.records

    assert_that(result, records)


def test_setup_logger_formatter(logger_handler):
    message = "message"
    logger = setup_logger(logging.DEBUG, logger_handler, LoggerFormatter(fmt="%(levelname)s %(message)s"))
    logger.debug(message)

    record = logger_handler.records[0]
    result = logger_handler.format(record)

    assert_that(result, equal_to(f"DEBUG {message}"))
