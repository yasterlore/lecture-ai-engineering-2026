"""AIE2026 DAY3 解答用CLI。

既存 app/agent.py は変更せず、同じ INSTRUCTIONS と検索ツールを利用する。
復習クイズの追加と、学習記録保存時の Human-in-the-Loop を実装する。
実行: uv run python -m app.lesson03_agent --trace '第2回の確認問題を出して'
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from app.agent import INSTRUCTIONS
from app.tools import get_lecture_summary, search_glossary
from app.lesson03_tools import make_quiz, save_learning_log

TOOLS = (search_glossary, get_lecture_summary, make_quiz, save_learning_log)
EXTRA_INSTRUCTIONS = """
- 「確認問題」「復習クイズ」を依頼されたら make_quiz を使う。
- ユーザーが学習内容の保存を明示的に依頼した場合、topic と note を整理し、必ず save_learning_log ツールを呼び出す。
- 文章だけで保存の承認を求めない。承認確認はハーネス側が requires_approval=True によって行う。
- ツールが呼び出されても、利用者が承認するまでは実際のファイル保存は行われない。
- 承認されなかった場合は、保存されなかったと正直に伝える。
"""


def build_agent() -> Agent:
    # 本講座は GEMINI_API_KEY を Codespaces Secret として渡す。
    model_name = os.environ.get("AIE_MODEL", "gemini-3.5-flash-lite")
    model = model_name if ":" in model_name else f"google:{model_name}"
    agent = Agent(
        model,
        instructions=INSTRUCTIONS + EXTRA_INSTRUCTIONS,
        output_type=[str, DeferredToolRequests],
    )
    agent.tool_plain(search_glossary)
    agent.tool_plain(get_lecture_summary)
    agent.tool_plain(make_quiz)
    # ここが課題の中心。承認前に関数を実行させない。
    agent.tool_plain(save_learning_log, requires_approval=True)
    return agent


def _print_trace(messages, requests: int) -> None:
    print("--- trace ---")
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                print(f"[tool call]   {part.tool_name}({part.args!r})")
            elif isinstance(part, ToolReturnPart):
                print(f"[tool return] {part.tool_name} -> {str(part.content)[:500]}")
    print(f"[usage] requests={requests}")


def _approve(call) -> bool:
    print("\n--- 保存の確認 ---")
    print("ツール名:", call.tool_name)
    try:
        print("保存内容:", json.dumps(call.args_as_dict(), ensure_ascii=False, indent=2))
    except Exception:
        print("保存内容:", call.args)
    print("ファイルへの保存を許可しますか？ [yes/NO]: ", end="", flush=True)
    try:
        return input().strip().lower() in {"yes", "y", "はい"}
    except EOFError:
        return False  # 非対話実行は明示承認がないので拒否


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", help="エージェントに渡す質問")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--list-tools", action="store_true")
    args = parser.parse_args(argv)

    if args.list_tools:
        for tool in TOOLS:
            print(f"{tool.__name__}: {inspect.getdoc(tool) or '(説明なし)'}\n")
        return 0
    if not args.question:
        parser.error("question か --list-tools を指定してください")

    agent = build_agent()
    result = agent.run_sync(args.question)
    requests = result.usage.requests
    # 書き込み承認を何度も求めるループを避ける。
    for _ in range(5):
        if not isinstance(result.output, DeferredToolRequests):
            print(result.output)
            if args.trace:
                _print_trace(result.all_messages(), requests)
            return 0
        pending = result.output
        if pending.calls:
            print("未対応の外部ツールがあります。安全のため停止します。", file=sys.stderr)
            return 2
        decisions = DeferredToolResults()
        for call in pending.approvals:
            decisions.approvals[call.tool_call_id] = _approve(call)
        result = agent.run_sync(
            message_history=result.all_messages(),
            deferred_tool_results=decisions,
        )
        requests += result.usage.requests
    print("承認の繰り返し上限に到達しました。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
