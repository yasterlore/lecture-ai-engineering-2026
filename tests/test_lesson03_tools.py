"""APIキー不要の単体テスト。公式リポジトリの既存 pytest と併用可能。"""

import json
from pathlib import Path

import pytest

from app import lesson03_tools as target


SAMPLE = [
    {"term": "LoRA", "definition": "低ランクのアダプタを学習する手法", "lecture": 2},
    {"term": "QLoRA", "definition": "量子化を組み合わせる手法", "lecture": "第2回"},
    {"term": "Agent", "definition": "LLMとツール等の組合せ", "lecture": [3]},
]


@pytest.fixture
def glossary(monkeypatch):
    from app import tools
    monkeypatch.setattr(tools, "load_glossary", lambda: SAMPLE)


def test_make_quiz_normal(glossary):
    result = json.loads(target.make_quiz(2))
    assert "question" in result and "answer" in result
    assert any(term in result["question"] for term in ("LoRA", "QLoRA"))
    assert result["answer"] in {SAMPLE[0]["definition"], SAMPLE[1]["definition"]}


@pytest.mark.parametrize("lecture", [0, -1, True, "2", None])
def test_make_quiz_invalid(lecture):
    assert "error" in json.loads(target.make_quiz(lecture))


def test_make_quiz_unknown_lecture(glossary):
    assert "error" in json.loads(target.make_quiz(99))


def test_make_quiz_dict_glossary(monkeypatch):
    from app import tools
    monkeypatch.setattr(tools, "load_glossary", lambda: {"entries": SAMPLE})
    assert "question" in json.loads(target.make_quiz(3))


def test_save_learning_log(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "LOG_DIR", tmp_path / "learning_log")
    monkeypatch.setattr(target, "REPO_ROOT", tmp_path)
    result = json.loads(target.save_learning_log("第3回", "ハーネスを学習"))
    path = tmp_path / result["path"]
    assert result["saved"] is True
    assert path.parent == tmp_path / "learning_log"
    assert json.loads(path.read_text(encoding="utf-8"))["note"] == "ハーネスを学習"
    assert len(list(path.parent.iterdir())) == 1


def test_save_learning_log_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "LOG_DIR", tmp_path / "learning_log")
    monkeypatch.setattr(target, "REPO_ROOT", tmp_path)
    target.save_learning_log("a", "b")
    target.save_learning_log("a", "b")
    assert len(list((tmp_path / "learning_log").iterdir())) == 2


def test_save_learning_log_reject_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "LOG_DIR", tmp_path / "learning_log")
    assert "error" in json.loads(target.save_learning_log("", "text"))
    assert "error" in json.loads(target.save_learning_log("topic", ""))
    assert "error" in json.loads(target.save_learning_log("topic", "x" * 4001))
    assert not (tmp_path / "learning_log").exists()


def test_save_learning_log_path_is_fixed(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "LOG_DIR", tmp_path / "learning_log")
    monkeypatch.setattr(target, "REPO_ROOT", tmp_path)
    result = json.loads(target.save_learning_log("../../etc/passwd", "text"))
    assert Path(result["path"]).parts[0] == "learning_log"
    assert len(list(tmp_path.rglob("*.json"))) == 1
