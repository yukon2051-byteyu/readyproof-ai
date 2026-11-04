"""デモの出力（診断結果・受入テスト仕様）は、事前に本物のAI（Claude）で作って保存したものを使う。

- 保存場所：readyproof/demos/ai_results/<デモID>.json（scripts/make_demo_ai.py で作成）
- 画面でデモを開くときは、保存したAIの出力を貼るだけ（有料APIは呼ばない）
- AIに送った入力の指紋（SHA-256）も保存し、デモの入力が変わっていたら作り直しを求める
  （古い出力を、違う入力の結果として表示しないため）
"""
from __future__ import annotations

import hashlib
import json
import os

from ..ai.tasks import apply_diagnosis, apply_tests_multi, build_diagnosis_input, build_tests_input
from ..config import Settings
from ..logic import rules

DIR = os.path.join(os.path.dirname(__file__), "ai_results")
ORIGIN = "AI生成（デモ用に事前実行）"
REVIEWER = "デモ確認者（架空）"


class StaleDemoOutput(RuntimeError):
    pass


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def path(demo_id: str) -> str:
    return os.path.join(DIR, f"{demo_id}.json")


def target_reqs(p: dict) -> list[str]:
    return [r["id"] for r in p["requirements"] if r["status"] == "確定"]


def diagnosis_prompt(p: dict) -> tuple[str, dict]:
    prompt, refmap, _ = build_diagnosis_input(p, target_reqs(p), "PR-001", Settings())
    return prompt, refmap


def tests_prompt(p: dict) -> str:
    return build_tests_input(p, target_reqs(p))


def load(demo_id: str) -> dict:
    with open(path(demo_id), encoding="utf-8") as f:
        return json.load(f)


def apply_saved(p: dict, demo_id: str) -> None:
    saved = load(demo_id)
    prompt, refmap = diagnosis_prompt(p)
    if fingerprint(prompt) != saved["diagnosis"]["prompt_sha256"]:
        raise StaleDemoOutput(f"{demo_id}：デモの入力が変わっています。scripts/make_demo_ai.py で出力を作り直してください。")
    apply_diagnosis(p, saved["diagnosis"]["output"], refmap, "PR-001", origin=ORIGIN, allowed_req_ids=target_reqs(p))
    if fingerprint(tests_prompt(p)) != saved["tests"]["prompt_sha256"]:
        raise StaleDemoOutput(f"{demo_id}：診断が変わっています。scripts/make_demo_ai.py で出力を作り直してください。")
    for t in apply_tests_multi(p, saved["tests"]["output"], target_reqs(p), ORIGIN, Settings().limits.max_tests_per_generation):
        # デモでも結果を記録して試せるよう、期待結果は架空の確認者が確認済みにする（AIの出力内容は変えない）
        # 「要確認」が残るテストは業務ルールどおり下書きのまま（ベンダー確認が先）
        t["expected_confirmed"] = True
        try:
            rules.confirm_test(p, t, REVIEWER)
        except rules.RuleError:
            t["expected_confirmed"] = False
    p["project"]["demo_ai"] = {"model": saved.get("model"), "generated_at": saved.get("generated_at")}
