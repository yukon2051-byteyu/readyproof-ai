"""Claude API の実呼び出し検証（有料・手動実行専用。自動テストからは呼ばない）。

3件のデモから「準備済みのデモ結果（診断）」を取り除き、実際の Claude API で診断し直して、
期待区分と比べる。根拠の検証結果（除外された引用の数など）も表示する。

実行：.venv\\Scripts\\python scripts\\live_api_check.py
APIキー：環境変数 ANTHROPIC_API_KEY、または .streamlit/secrets.toml の ANTHROPIC_API_KEY（表示しない）
結果：docs/live_api_results.json（キーや資料本文は含めない）
"""
from __future__ import annotations

import json
import os
import sys
import time
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    path = os.path.join(ROOT, ".streamlit", "secrets.toml")
    if os.path.exists(path):
        with open(path, "rb") as f:
            key = tomllib.load(f).get("ANTHROPIC_API_KEY")
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
            return
    sys.exit("APIキーが見つかりません（ANTHROPIC_API_KEY または .streamlit/secrets.toml）。")


# デモの準備済み結果のうち、資料・録画だけから判断できる区分（質問への回答を使うものは除く）
AI_EXPECTED = {
    "demo1": {"REQ-001": ["標準設定で対応できる見込み"],
              "REQ-002": ["情報不足・ベンダー確認が必要"]},  # 自己承認の禁止は資料に記載なし
    "demo2": {"REQ-001": ["そのまま対応できる見込み", "標準設定で対応できる見込み"],
              "REQ-002": ["追加対応の検討が必要"],
              "REQ-003": ["対応不可との記載・確認済み発言あり", "追加対応の検討が必要"],  # 回答書（資料）に記載あり
              "REQ-004": ["そのまま対応できる見込み", "標準設定で対応できる見込み"]},
    "demo3": {"REQ-001": ["根拠間に矛盾あり"],
              "REQ-002": ["情報不足・ベンダー確認が必要"]},
}


def main() -> None:
    load_key()
    from readyproof.ai.client import ClaudeClient
    from readyproof.ai.tasks import run_diagnosis
    from readyproof.config import load_settings
    from readyproof.demos.builder import build
    from readyproof.usage import Ledger

    s = load_settings()
    s.budget.usage_store_persistent = True
    s.budget.ai_runs_per_code_per_month = 100  # 検証用の上限（利用者の了承済み）
    s.budget.monthly_budget_jpy = max(s.budget.monthly_budget_jpy, 10_000)
    ledger = Ledger(os.path.join(ROOT, "data", "usage_ledger.jsonl"))
    client = ClaudeClient(s)
    report = {"model": s.budget.model, "at": time.strftime("%Y-%m-%d %H:%M"), "demos": {}}
    total_ok = total = 0
    for demo, expected in AI_EXPECTED.items():
        p = build(demo)
        p["project"]["demo_id"] = None  # デモ扱いを外して AI を実行
        p["diagnoses"], p["questions"], p["actions"] = [], [], []
        req_ids = list(expected.keys())
        t0 = time.time()
        created = run_diagnosis(p, req_ids, "PR-001", client, s, ledger, "live-check")
        sec = round(time.time() - t0, 1)
        rows = []
        for dg in created:
            ok = dg["category"] in expected[dg["req_id"]]
            total_ok += ok
            total += 1
            rows.append({"req": dg["req_id"], "category": dg["category"], "expected": expected[dg["req_id"]],
                         "match": ok, "evidence_valid": len(dg["evidence"]),
                         "evidence_rejected": len(dg.get("rejected_evidence", [])),
                         "auto_adjustments": dg.get("auto_adjustments", []),
                         "remaining": dg["remaining_conditions"], "reason": dg["reason"][:200]})
        report["demos"][demo] = {"seconds": sec, "results": rows,
                                 "questions": len(p["questions"]), "actions": len(p["actions"])}
        print(f"== {demo}（{sec}秒）")
        for r in rows:
            print(f"  {r['req']} {'一致' if r['match'] else '不一致'}：{r['category']}"
                  f"（有効な根拠 {r['evidence_valid']}・除外 {r['evidence_rejected']}）")
    summ = ledger.summary("live-check")
    report["summary"] = {"match": f"{total_ok}/{total}", "cost_jpy": summ["code"]["cost_jpy"],
                         "api_calls": summ["code"]["api_calls"]}
    print(f"一致 {total_ok}/{total}　費用（記録上）約{summ['code']['cost_jpy']:.0f}円")
    with open(os.path.join(ROOT, "docs", "live_api_results.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
