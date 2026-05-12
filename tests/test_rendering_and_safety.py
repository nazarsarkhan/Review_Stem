from reviewstem.__main__ import polish_suggested_fix
from reviewstem.config import ReviewStemConfig
from reviewstem.llm_client import LLMClient
from reviewstem.motor_cortex import MotorCortex


class DummyLLM(LLMClient):
    def __init__(self):
        self.config = ReviewStemConfig.from_env()
        self.model = "dummy"
        self.temperature = 0
        self.client = None


def test_polish_suggested_fix_preserves_bound_parameter():
    text = "Fix with await db.query('SELECT * FROM users WHERE name = $1', );"

    assert "[name]" in polish_suggested_fix(text)


def test_read_file_blocks_path_traversal():
    motor = MotorCortex(DummyLLM(), repo_path="benchmark_repo")

    content, event = motor._read_file_event("../pyproject.toml", reviewer="test", iteration=0)

    assert "outside the repository" in content
    assert event.success is False
