from pathlib import Path

import pytest

from skills.build.evals.mock_dispatcher import (
    MockNotFound,
    MockUserInputMissing,
    load,
    load_user_input,
)


def test_load_finds_seq_specific(tmp_path: Path) -> None:
    (tmp_path / "1-plan-writer.md").write_text("PLAN OUT")
    assert load(tmp_path, 1, "plan-writer") == "PLAN OUT"


def test_load_falls_back_to_template_name(tmp_path: Path) -> None:
    (tmp_path / "implementer.md").write_text("IMPL OUT")
    assert load(tmp_path, 17, "implementer") == "IMPL OUT"


def test_load_prefers_seq_over_fallback(tmp_path: Path) -> None:
    (tmp_path / "2-x.md").write_text("SEQ")
    (tmp_path / "x.md").write_text("FALLBACK")
    assert load(tmp_path, 2, "x") == "SEQ"


def test_load_raises_when_neither_exists(tmp_path: Path) -> None:
    with pytest.raises(MockNotFound, match="no mock"):
        load(tmp_path, 1, "nope")


def test_load_user_input_reads_turn_file(tmp_path: Path) -> None:
    (tmp_path / "turn-1.md").write_text("USER SAYS GO")
    assert load_user_input(tmp_path, 1) == "USER SAYS GO"


def test_load_user_input_raises_when_dir_is_none() -> None:
    with pytest.raises(MockUserInputMissing, match="no mock user-input dir"):
        load_user_input(None, 1)


def test_load_user_input_raises_when_turn_missing(tmp_path: Path) -> None:
    with pytest.raises(MockUserInputMissing, match="missing turn-3"):
        load_user_input(tmp_path, 3)
