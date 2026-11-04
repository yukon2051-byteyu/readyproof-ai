"""受入テストの下書きを、確定した要件から作る（AIなし）。

- 金額の境目（例：10,000円以上／未満）があれば、境目の直前と境目ちょうどの境界値テストを作る
- 画面名・操作手順は製品ごとに違うため「要確認」とし、存在しない画面やボタンを書かない
- 期待結果は要件のルールの文をそのまま使い、人が確認するまで「未確定」
- 既にテストがある要件には作らない（上書きしない）
"""
from __future__ import annotations

import re

from .logic import rules
from .logic.rules import current_diagnosis

_AMOUNT = re.compile(r"([0-9][0-9,]*)円(以上|未満|以下|超)")
STEPS_TBD = "要確認（製品の画面・操作手順は、実際の製品で確認して記入）"
ORIGIN = "自動作成（AIなし）"


def _boundary_tests(req: dict) -> list[dict]:
    m = _AMOUNT.search(req.get("rules", ""))
    if not m:
        return []
    v = int(m.group(1).replace(",", ""))
    cases = [(v - 1, "境目の直前"), (v, "境目ちょうど")] if m.group(2) in ("以上", "未満") else [(v, "境目ちょうど"), (v + 1, "境目の直後")]
    return [{
        "title": f"{amount:,}円のとき（{label}）", "viewpoint": "境界値", "purpose": f"{req['business']}の金額の境目の確認",
        "role": req.get("role", ""), "inputs": f"金額 {amount:,}円", "steps": STEPS_TBD,
        "expected": f"ルールどおりに処理される：{req['rules']}", "expected_basis": f"{req['id']} 第{req['version']}版",
        "importance": "高", "importance_reason": "境目の設定誤りは見落としやすい",
    } for amount, label in cases]


def draft_tests(project: dict) -> list[dict]:
    created = []
    for req in project["requirements"]:
        if req["status"] != "確定":
            continue
        if any(req["id"] in t["req_ids"] and t["status"] != "廃止" for t in project["tests"]):
            continue
        dg = current_diagnosis(project, req["id"])
        items = _boundary_tests(req)
        items.append({
            "title": f"{req['business']}：{req.get('workflow') or 'ルールどおりに動く'}"[:60],
            "viewpoint": "通常操作", "purpose": f"{req['id']} の要件を満たすことの確認", "role": req.get("role", ""),
            "inputs": "", "steps": STEPS_TBD, "expected": req.get("rules", ""),
            "expected_basis": f"{req['id']} 第{req['version']}版" + (f"／診断 {dg['category']}" if dg else ""),
            "importance": "高" if req.get("priority") == "必須" else "中", "importance_reason": f"要件の重要度：{req.get('priority')}",
            "open_issues": req.get("open_issues", ""),
        })
        if "禁止" in req.get("rules", ""):
            items.append({
                "title": f"{req['business']}：禁止されている操作ができない", "viewpoint": "権限", "purpose": "禁止事項の確認",
                "role": req.get("role", ""), "steps": STEPS_TBD, "expected": f"禁止された操作は実行できない：{req['rules']}",
                "expected_basis": f"{req['id']} 第{req['version']}版", "importance": "高", "importance_reason": "統制上の禁止事項",
            })
        for it in items:
            created.append(rules.add_test(project, {**it, "req_ids": [req["id"]], "expected_confirmed": False},
                                          origin=ORIGIN))
    return created
