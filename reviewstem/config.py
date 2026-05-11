import os
from dataclasses import dataclass, replace

from .logger import logger


def get_int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment."""
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        logger.warning("%s is invalid. Using default value %s.", name, default)
        return default


def get_float_env(name: str, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Read a bounded float from the environment."""
    try:
        return min(maximum, max(minimum, float(os.getenv(name, str(default)))))
    except ValueError:
        logger.warning("%s is invalid. Using default value %s.", name, default)
        return default


@dataclass(frozen=True)
class ReviewStemConfig:
    """Runtime configuration for ReviewStem."""

    model: str
    max_iterations: int
    target_score: float
    temperature: float
    diff_limit: int
    repo_map_max_files: int
    file_read_limit: int
    quiet: bool = False

    @classmethod
    def from_env(cls) -> "ReviewStemConfig":
        """Load configuration from environment variables."""
        return cls(
            model=os.getenv("REVIEWSTEM_MODEL", "gpt-5.4-mini"),
            max_iterations=get_int_env("REVIEWSTEM_MAX_ITERATIONS", 2),
            target_score=get_float_env("REVIEWSTEM_TARGET_SCORE", 0.90),
            temperature=get_float_env("REVIEWSTEM_TEMPERATURE", 0.0, maximum=2.0),
            diff_limit=get_int_env("REVIEWSTEM_DIFF_LIMIT", 12000),
            repo_map_max_files=get_int_env("REVIEWSTEM_REPO_MAP_MAX_FILES", 150),
            file_read_limit=get_int_env("REVIEWSTEM_FILE_READ_LIMIT", 8000),
        )

    def with_overrides(
        self,
        model: str | None = None,
        max_iterations: int | None = None,
        target_score: float | None = None,
        quiet: bool | None = None,
    ) -> "ReviewStemConfig":
        """Return a copy with CLI overrides applied."""
        return replace(
            self,
            model=model or self.model,
            max_iterations=max_iterations or self.max_iterations,
            target_score=self.target_score if target_score is None else target_score,
            quiet=self.quiet if quiet is None else quiet,
        )
