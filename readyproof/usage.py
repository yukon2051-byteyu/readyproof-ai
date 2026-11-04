"""利用回数・費用の管理（本文を含まない永続記録）。

- 実行前に「予約」を書き込み、終了後に実績で「確定」する。予約中も枠を消費する（並行実行対策）
- 失敗・再試行も記録する（API が課金した可能性があるため、実績不明なら見積額のまま残す）
- AIパスワードは平文で保存しない（ハッシュのみ）
- 永続的な記録先がない環境（例：Community Cloud の一時ディスク）では有料処理を止める
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime

from .core import JST, now_iso

_LOCK = threading.Lock()


def code_hash(code: str) -> str:
    return hashlib.sha256(("readyproof:" + (code or "").strip()).encode()).hexdigest()[:16]


def month_key(dt: datetime | None = None) -> str:
    return (dt or datetime.now(JST)).strftime("%Y-%m")


class Ledger:
    def __init__(self, path: str):
        self.path = path

    def _read(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out

    def _append(self, rec: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def entries(self, month: str | None = None) -> list[dict]:
        """予約と確定を突き合わせ、実行1回=1行にまとめる。"""
        month = month or month_key()
        rows: dict[str, dict] = {}
        for e in self._read():
            row = rows.setdefault(e.get("run_id", ""), {})
            month_of_reserve = row.get("month")
            row.update(e)
            if month_of_reserve:  # 月は予約時点で決める（月末をまたいでも二重計上しない）
                row["month"] = month_of_reserve
        return [r for r in rows.values() if r.get("month") == month]

    def summary(self, code: str | None = None, month: str | None = None) -> dict:
        rows = self.entries(month)
        ch = code_hash(code) if code else None

        def agg(rs):
            ai = [r for r in rs if r.get("kind") == "ai"]
            tr = [r for r in rs if r.get("kind") == "transcribe"]
            return {
                "ai_runs": len(ai),
                "api_calls": sum(int(r.get("api_calls", 0)) for r in ai),
                "transcribe_minutes": round(sum(float(r.get("minutes", 0)) for r in tr), 1),
                "cost_jpy": round(sum(float(r.get("cost_jpy", r.get("reserved_jpy", 0))) for r in rs), 1),
                "failed": sum(1 for r in rs if r.get("status") == "失敗"),
                "pending": sum(1 for r in rs if r.get("status") == "予約中"),
            }

        out = {"month": month or month_key(), "all": agg(rows)}
        if ch:
            out["code"] = agg([r for r in rows if r.get("code_hash") == ch])
        return out

    def check(self, budget, kind: str, code: str, est_jpy: float, minutes: float = 0.0) -> list[str]:
        """実行前の枠確認。問題があれば理由のリストを返す（空なら実行可）。"""
        s = self.summary(code)
        reasons = []
        if s["all"]["cost_jpy"] + est_jpy > budget.monthly_budget_jpy:
            reasons.append(f"今月のアプリ予算（{budget.monthly_budget_jpy:,}円）を超える見込みです"
                           f"（使用済み・予約 {s['all']['cost_jpy']:,.0f}円 + 今回見込み {est_jpy:,.0f}円）。")
        if kind == "ai":
            if s["code"]["ai_runs"] >= budget.ai_runs_per_code_per_month:
                reasons.append(f"このAIパスワードの今月のAI生成回数（{budget.ai_runs_per_code_per_month}回）を使い切りました。")
            if s["all"]["ai_runs"] >= budget.ai_runs_global_per_month:
                reasons.append(f"アプリ全体の今月のAI生成回数上限（{budget.ai_runs_global_per_month}回）に達しました。")
        if kind == "transcribe":
            if s["code"]["transcribe_minutes"] + minutes > budget.transcribe_minutes_per_code_per_month:
                reasons.append(f"このAIパスワードの今月の文字起こし枠（{budget.transcribe_minutes_per_code_per_month}分）を超えます。")
            if s["all"]["transcribe_minutes"] + minutes > budget.transcribe_minutes_global_per_month:
                reasons.append(f"アプリ全体の今月の文字起こし枠（{budget.transcribe_minutes_global_per_month}分）を超えます。")
        return reasons

    def reserve(self, budget, kind: str, code: str, est_jpy: float, task: str, minutes: float = 0.0) -> str:
        with _LOCK:
            reasons = self.check(budget, kind, code, est_jpy, minutes)
            if reasons:
                raise PermissionError(" / ".join(reasons))
            run_id = uuid.uuid4().hex[:12]
            self._append({"run_id": run_id, "month": month_key(), "at": now_iso(), "kind": kind, "task": task,
                          "code_hash": code_hash(code), "reserved_jpy": round(est_jpy, 2), "minutes": minutes,
                          "status": "予約中", "api_calls": 0})
            return run_id

    def finalize(self, run_id: str, status: str, cost_jpy: float | None, api_calls: int = 0,
                 input_tokens: int = 0, output_tokens: int = 0, minutes: float | None = None,
                 error: str = "") -> None:
        rec = {"run_id": run_id, "finished_at": now_iso(), "status": status,
               "api_calls": api_calls, "input_tokens": input_tokens, "output_tokens": output_tokens,
               "error": error[:120]}
        if cost_jpy is not None:  # None のときは予約額（見積）を費用として残す
            rec["cost_jpy"] = round(cost_jpy, 2)
        if minutes is not None:
            rec["minutes"] = minutes
        with _LOCK:
            self._append(rec)


class HubLedger(Ledger):
    """利用記録を Hugging Face の非公開データ置き場（dataset リポジトリ）に保存する。

    公開サイト（Hugging Face Spaces）のディスクは再起動で消えるため、月の上限が効かなくなるのを防ぐ。
    - 読むたびに最新の記録を取得し、書くたびに全体を送り直す（記録は小さく、1台で動かすため十分）
    - 送れなかった場合は例外にする（予約できない＝有料処理を実行しない、安全側）
    """

    FILE = "usage_ledger.jsonl"

    def __init__(self, repo_id: str, token: str, cache_path: str = "data/usage_ledger_cache.jsonl"):
        super().__init__(cache_path)
        self.repo_id, self.token = repo_id, token

    def _download(self) -> str:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import EntryNotFoundError

        try:
            p = hf_hub_download(self.repo_id, self.FILE, repo_type="dataset", token=self.token, force_download=True)
        except EntryNotFoundError:
            return ""
        with open(p, encoding="utf-8") as f:
            return f.read()

    def _read(self) -> list[dict]:
        out = []
        for line in self._download().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def _append(self, rec: dict) -> None:
        from huggingface_hub import HfApi

        body = self._download()
        if body and not body.endswith("\n"):
            body += "\n"
        body += json.dumps(rec, ensure_ascii=False) + "\n"
        HfApi(token=self.token).upload_file(path_or_fileobj=body.encode("utf-8"), path_in_repo=self.FILE,
                                            repo_id=self.repo_id, repo_type="dataset",
                                            commit_message=f"利用記録 {rec.get('status', '')}")
