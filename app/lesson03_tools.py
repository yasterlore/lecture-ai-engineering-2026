"""AIE2026 DAY3: 復習クイズと承認付き学習ログツールの実体。

承認そのものはこのモジュールで行わない。Pydantic AI の
requires_approval=True により、関数の実行前にハーネス側で確認する。
"""

from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 保存先をこのフォルダの外から変更できる引数は提供しない。
REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "learning_log"
MAX_TEXT_LENGTH = 4000


def _glossary_entries(data: Any) -> list[dict[str, Any]]:
    """list/dict いずれの用語集形式でも、用語エントリの配列に変換する。"""
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = None
        for key in ("entries", "terms", "glossary", "items"):
            if isinstance(data.get(key), list):
                raw = data[key]
                break
            if isinstance(data.get(key), dict):
                raw = list(data[key].values())
                break
        if raw is None:
            raw = list(data.values()) if all(isinstance(v, dict) for v in data.values()) else []
    else:
        raw = []
    return [entry for entry in raw if isinstance(entry, dict)]


def _belongs_to_lecture(value: Any, lecture: int) -> bool:
    """2, '2', '第2回', [1, 2] などを扱う（文字列に別の桁が含まれる時は誤一致させない）。"""
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return value == lecture
    if isinstance(value, list):
        return any(_belongs_to_lecture(v, lecture) for v in value)
    if isinstance(value, str):
        return lecture in (int(x) for x in re.findall(r"\d+", value))
    return False


def make_quiz(lecture: int) -> str:
    """指定した講義回に登場する用語から復習用クイズを1問作り、JSON文字列を返す。

    「第2回の確認問題を作って」などの依頼で使用する。
    lecture は講義の回数を表す正の整数（例: 2）。
    用語がない回や不正な入力では、例外ではなく error キーを持つJSONを返す。
    """
    if isinstance(lecture, bool) or not isinstance(lecture, int) or lecture <= 0:
        return json.dumps({"error": "lecture は1以上の整数で指定してください"}, ensure_ascii=False)

    # 既存の用語集読み込み処理を必ず再利用する。
    from app.tools import load_glossary

    entries = _glossary_entries(load_glossary())
    candidates = []
    for entry in entries:
        lectures = entry.get("lecture", entry.get("lectures", entry.get("lecture_number")))
        if not _belongs_to_lecture(lectures, lecture):
            continue
        term = entry.get("term") or entry.get("name")
        definition = entry.get("definition") or entry.get("description")
        if isinstance(term, str) and term.strip() and isinstance(definition, str) and definition.strip():
            candidates.append((term.strip(), definition.strip()))

    if not candidates:
        return json.dumps({"error": f"第{lecture}回の用語が見つかりません"}, ensure_ascii=False)
    term, definition = random.choice(candidates)
    return json.dumps({"question": f"「{term}」の意味は？", "answer": definition}, ensure_ascii=False)


def save_learning_log(topic: str, note: str) -> str:
    """承認済みの学習記録を learning_log/ に1件保存する。

    ユーザーが「今日学習した内容を保存して」と依頼し、保存内容の確認後、
    Pydantic AI 側で承認が得られた場合にのみ実行すること。
    この関数単体には承認機能がないので、必ず requires_approval=True で登録する。
    topic: 学習テーマ。note: 学習した内容の要約。
    """
    if not isinstance(topic, str) or not topic.strip():
        return json.dumps({"error": "topic が空です"}, ensure_ascii=False)
    if not isinstance(note, str) or not note.strip():
        return json.dumps({"error": "note が空です"}, ensure_ascii=False)
    if len(topic) > 200 or len(note) > MAX_TEXT_LENGTH:
        return json.dumps({"error": "保存内容が長すぎます"}, ensure_ascii=False)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    filename = now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12] + ".json"
    path = LOG_DIR / filename
    record = {
        "topic": topic.strip(),
        "note": note.strip(),
        "saved_at_utc": now.isoformat(timespec="seconds"),
    }
    # x は上書き禁止。ユーザー入力をファイル名に使わず、パストラバーサルを防ぐ。
    with path.open("x", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return json.dumps({"saved": True, "path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else filename}, ensure_ascii=False)
