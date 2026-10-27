from unittest.mock import patch

import pytest

from ytscript.cli import main
from infra.errors import (
    InvalidUrlError,
    NetworkError,
    TranscriptNotFoundError,
    UnsupportedDomainError,
)
from ytscript.models.segment import Segment

URL = "https://youtu.be/dQw4w9WgXcQ"


def test_missing_argument_exits_with_usage_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "url" in captured.err


def test_success_prints_only_transcript_to_stdout(capsys):
    segments = [Segment(12.7, "Olá,\nmundo"), Segment(65, "Fim")]
    with patch("ytscript.cli.get_transcript", return_value=segments) as get:
        code = main([URL])

    captured = capsys.readouterr()
    assert code == 0
    get.assert_called_once_with(URL)
    assert captured.out == "[00:00:12] Olá,\nmundo\n\n[00:01:05] Fim\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "error_class",
    [InvalidUrlError, UnsupportedDomainError, TranscriptNotFoundError, NetworkError],
)
def test_known_errors_go_to_stderr_with_exit_code_1(capsys, error_class):
    with patch("ytscript.cli.get_transcript", side_effect=error_class()):
        code = main([URL])

    captured = capsys.readouterr()
    expected = error_class()
    assert code == 1
    assert captured.out == ""
    assert captured.err == f"ytscript: erro: {expected.message} {expected.action}\n"


def test_invalid_url_end_to_end(capsys):
    code = main(["https://evil.com/watch?v=dQw4w9WgXcQ"])
    captured = capsys.readouterr()
    expected = UnsupportedDomainError()
    assert code == 1
    assert captured.out == ""
    assert captured.err == f"ytscript: erro: {expected.message} {expected.action}\n"
