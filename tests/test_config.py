from reviewstem.config import ReviewStemConfig, get_float_env, get_int_env


def test_config_defaults(monkeypatch):
    for key in [
        "REVIEWSTEM_MODEL",
        "REVIEWSTEM_MAX_ITERATIONS",
        "REVIEWSTEM_TARGET_SCORE",
        "REVIEWSTEM_TEMPERATURE",
        "REVIEWSTEM_DIFF_LIMIT",
        "REVIEWSTEM_REPO_MAP_MAX_FILES",
        "REVIEWSTEM_FILE_READ_LIMIT",
    ]:
        monkeypatch.delenv(key, raising=False)

    config = ReviewStemConfig.from_env()

    assert config.model == "gpt-5.4-mini"
    assert config.max_iterations == 2
    assert config.target_score == 0.90
    assert config.temperature == 0.0


def test_invalid_env_values_fall_back(monkeypatch):
    monkeypatch.setenv("BAD_INT", "abc")
    monkeypatch.setenv("BAD_FLOAT", "abc")

    assert get_int_env("BAD_INT", 7) == 7
    assert get_float_env("BAD_FLOAT", 0.25) == 0.25


def test_cli_overrides_do_not_mutate_original_config():
    config = ReviewStemConfig.from_env()
    overridden = config.with_overrides(model="test-model", max_iterations=3, target_score=0.95, quiet=True)

    assert overridden.model == "test-model"
    assert overridden.max_iterations == 3
    assert overridden.target_score == 0.95
    assert overridden.quiet is True
    assert config.model != ""
