"""Tests for MotorCortex.

We don't exercise the full LLM tool-loop here (that would need a real or
extensive fake of the openai chat completions interface). Instead we test
the parts that have real logic: the `_read_file_event` sandbox check and
the iteration/reviewer wiring on tool events.
"""

from pathlib import Path

from reviewstem.config import ReviewStemConfig
from reviewstem.motor_cortex import MotorCortex
from reviewstem.schemas import ToolUseEvent


class StubLLM:
    def __init__(self):
        self.config = ReviewStemConfig.from_env()
        self.model = "stub"


def _motor(tmp_path: Path) -> MotorCortex:
    return MotorCortex(StubLLM(), repo_path=str(tmp_path))


def test_read_file_event_rejects_traversal(tmp_path):
    motor = _motor(tmp_path)
    content, event = motor._read_file_event("../escape.txt", reviewer="X", iteration=1)
    assert event.success is False
    assert "outside the repository" in (event.error or "")
    assert "Error reading file" in content


def test_read_file_event_reads_existing_file(tmp_path):
    target = tmp_path / "a.py"
    target.write_text("hello world", encoding="utf-8")
    motor = _motor(tmp_path)

    content, event = motor._read_file_event("a.py", reviewer="X", iteration=2)

    assert event.success is True
    assert event.reviewer == "X"
    assert event.iteration == 2
    assert event.path == "a.py"
    assert content == "hello world"
    assert event.characters_returned == len("hello world")


def test_read_file_event_truncates_large_file(tmp_path):
    motor = _motor(tmp_path)
    motor.file_read_limit = 5  # force truncation
    target = tmp_path / "long.py"
    target.write_text("0123456789", encoding="utf-8")

    content, event = motor._read_file_event("long.py", reviewer="X", iteration=0)

    assert content == "01234"
    assert event.characters_returned == 5


def test_read_file_event_reports_missing_file(tmp_path):
    motor = _motor(tmp_path)
    content, event = motor._read_file_event("missing.py", reviewer="X", iteration=0)
    assert event.success is False
    assert content.startswith("Error reading file")


def test_tool_events_list_starts_empty(tmp_path):
    motor = _motor(tmp_path)
    assert motor.tool_events == []
