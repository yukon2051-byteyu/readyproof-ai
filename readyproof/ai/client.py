"""AI 呼び出し（Claude）と、テスト・デモ用の代替応答（FakeAI）。

Claude API は音声・動画を受け付けない（公式：入力はテキスト・PDF・画像）。
このアプリは「人が選択・確認した文字」だけを送る。AI に外部操作の権限（ツール）は与えない。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


class AIError(Exception):
    """AI 実行の失敗（利用者向けメッセージ）。入力や手動機能は失われない。

    tokens_known=False のときは課金額が不明なので、利用記録では見積額のまま残す。
    """

    def __init__(self, message: str, input_tokens: int = 0, output_tokens: int = 0, tokens_known: bool = False):
        super().__init__(message)
        self.input_tokens, self.output_tokens, self.tokens_known = input_tokens, output_tokens, tokens_known


@dataclass
class AIResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 1
    model: str = ""
    paid: bool = False


class FakeAI:
    """自動テスト・オフライン用の代替応答。有料APIを呼ばない。

    responses: {タスク名: dict または (prompt) -> dict の関数}
    """

    paid = False
    label = "代替応答（テスト用・料金なし）"

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []

    def run(self, task: str, prompt: str, schema: dict, max_tokens: int) -> AIResult:
        self.calls.append({"task": task, "prompt": prompt})
        r = self.responses.get(task)
        if r is None:
            raise AIError(f"代替応答が未定義です：{task}")
        if isinstance(r, Exception):
            raise r
        data = r(prompt) if callable(r) else r
        return AIResult(data=json.loads(json.dumps(data, ensure_ascii=False)), paid=False, api_calls=0)


def get_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def valid_access_codes() -> set[str]:
    raw = os.environ.get("RP_ACCESS_CODES")
    if raw is None:
        try:
            import streamlit as st

            raw = st.secrets.get("RP_ACCESS_CODES", "")
        except Exception:
            raw = ""
    return {c.strip() for c in str(raw).split(",") if c.strip()}


def setup_blockers(settings) -> list[str]:
    """管理者の設定が足りないために、有料AIを実行できない理由（パスワード以外）。"""
    return [r for r in paid_ai_blockers(settings, None) if "が正しくありません" not in r]


def paid_ai_blockers(settings, code: str | None) -> list[str]:
    """有料AIを実行できない理由。空なら実行可能。"""
    reasons = []
    if not get_api_key():
        reasons.append("APIキーが設定されていません（ANTHROPIC_API_KEY）。")
    if not settings.budget.usage_store_persistent:
        reasons.append("永続的な利用記録の保存先が設定されていないため、有料処理を停止しています（RP_USAGE_STORE_PERSISTENT）。")
    codes = valid_access_codes()
    if not codes:
        reasons.append("AIパスワードが設定されていません（RP_ACCESS_CODES）。")
    elif (code or "").strip() not in codes:
        reasons.append("AIパスワードが正しくありません。")
    return reasons


class ClaudeClient:
    paid = True

    def __init__(self, settings):
        import anthropic

        key = get_api_key()
        if not key:
            raise AIError("APIキーが設定されていません。")
        self.settings = settings
        self.model = settings.budget.model
        self.label = f"Claude API（{self.model}）"
        # 再試行は1回まで（失敗時の費用も見込みに含める）
        self.client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=180)

    def run(self, task: str, prompt: str, schema: dict, max_tokens: int) -> AIResult:
        import anthropic

        from .prompts import SYSTEM

        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
                # 安全判定による拒否時はサーバー側で推奨モデルに切り替える
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise AIError("AI の利用が混み合っています。しばらくしてから再実行してください。") from e
        except anthropic.AuthenticationError as e:
            raise AIError("APIキーが無効です。管理者に確認してください。") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"AI の呼び出しに失敗しました（{e.status_code}）。入力内容は保持されています。") from e
        except anthropic.APIConnectionError as e:
            raise AIError("AI に接続できませんでした。ネットワークを確認してください。") from e
        usage = resp.usage
        result = AIResult(data={}, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                          model=resp.model, paid=True)
        used = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "tokens_known": True}
        if resp.stop_reason == "refusal":
            raise AIError("AI が処理を断りました。資料の内容を確認してください。", **used)
        if resp.stop_reason == "max_tokens":
            raise AIError("AI の出力が上限で途切れました。対象件数を減らして再実行してください。", **used)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            result.data = json.loads(text)
        except json.JSONDecodeError as e:
            raise AIError("AI の出力を読み取れませんでした。", **used) from e
        return result
