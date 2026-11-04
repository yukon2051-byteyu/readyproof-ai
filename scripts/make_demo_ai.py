"""デモの出力（診断結果・受入テスト仕様）を、本物のAI（Claude）で作って保存する。【有料】

実行：.venv\\Scripts\\python scripts\\make_demo_ai.py [demo1 demo2 demo3]
- 1デモにつき2回（診断・テスト仕様）APIを呼ぶ。費用は利用記録（data/usage_ledger.jsonl）に残る
- 結果は readyproof/demos/ai_results/<デモID>.json に保存。画面はこれを貼るだけで、APIは呼ばない
- APIキーは .streamlit/secrets.toml または環境変数 ANTHROPIC_API_KEY（画面・記録には出さない）
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as f:
            key = tomllib.load(f).get("ANTHROPIC_API_KEY", "")
        if not key:
            sys.exit("APIキーがありません。")
        os.environ["ANTHROPIC_API_KEY"] = key

    from readyproof.ai.client import ClaudeClient
    from readyproof.ai.prompts import DIAG_SCHEMA, TEST_MULTI_SCHEMA
    from readyproof.ai.tasks import actual_cost_jpy, apply_diagnosis, execute
    from readyproof.config import Settings
    from readyproof.demos import ai_outputs as A
    from readyproof.demos.builder import build_inputs
    from readyproof.usage import Ledger

    s = Settings()
    s.budget.usage_store_persistent = True
    s.budget.ai_runs_per_code_per_month = 30  # 開発者による事前作成（月の全体予算の上限は有効のまま）
    ledger = Ledger(os.path.join(ROOT, "data", "usage_ledger.jsonl"))
    client = ClaudeClient(s)
    os.makedirs(A.DIR, exist_ok=True)
    total = 0.0
    for demo_id in sys.argv[1:] or ["demo1", "demo2", "demo3"]:
        p = build_inputs(demo_id)
        prompt, refmap = A.diagnosis_prompt(p)
        d = execute(client, "diagnose", prompt, DIAG_SCHEMA, s.limits.max_ai_output_tokens, s, ledger, "demo-prep")
        apply_diagnosis(p, d.data, refmap, "PR-001", origin=A.ORIGIN, allowed_req_ids=A.target_reqs(p))
        tprompt = A.tests_prompt(p)
        t = execute(client, "generate_tests", tprompt, TEST_MULTI_SCHEMA, 16000, s, ledger, "demo-prep")
        cost = actual_cost_jpy(d.input_tokens, d.output_tokens, s.budget) + actual_cost_jpy(t.input_tokens, t.output_tokens, s.budget)
        total += cost
        out = {"model": s.budget.model, "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "note": "本物のAI（Claude）の出力をそのまま保存。デモ画面はこれを表示するだけで、APIは呼ばない。",
               "diagnosis": {"prompt_sha256": A.fingerprint(prompt), "input_tokens": d.input_tokens,
                             "output_tokens": d.output_tokens, "output": d.data},
               "tests": {"prompt_sha256": A.fingerprint(tprompt), "input_tokens": t.input_tokens,
                         "output_tokens": t.output_tokens, "output": t.data},
               "cost_jpy": round(cost, 1)}
        with open(A.path(demo_id), "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"{demo_id}：診断 {len(d.data.get('diagnoses', []))}件・テスト {len(t.data.get('tests', []))}件・約{cost:.0f}円")
    print(f"合計 約{total:.0f}円")


if __name__ == "__main__":
    main()
