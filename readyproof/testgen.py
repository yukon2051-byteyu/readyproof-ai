"""受入テスト仕様を、確定した要件から作る（AIなし）。

1つの要件から、根拠のある観点ごとにテストを作る。
- 通常操作：要件のとおりに業務ができる
- 境界値：金額の境目（以上／未満など）、最大件数、保存年数があるとき
- 例外：要件に例外が書かれているとき
- 権限：操作できる人が決まっているとき
- 禁止事項：「禁止」と書かれているとき
各テストに、事前条件・テストデータ・番号付き手順・期待結果・合否判定基準・根拠を付ける。
製品の画面名・ボタン名は推測で書かない（業務の操作として書き、画面の場所は未確定事項に残す）。
期待結果は人が確認するまで「未確定」。既にテストがある要件には作らない（上書きしない）。
"""
from __future__ import annotations

import re

from .core import primary_product
from .logic import rules
from .logic.evidence import evidence_label
from .logic.rules import current_diagnosis

ORIGIN = "自動作成（AIなし）"
PASS = "期待結果のすべてを満たした場合のみ合格。1点でも異なる場合は不合格とし、実際の結果と画面の記録（証跡）を残す。試せなかった場合は「実施不能」とし、理由を記録する（合否に数えない）。"
SCREEN_NOTE = "製品の画面名・メニューの場所は、実際の製品で確認して手順に追記する"

_AMOUNT = re.compile(r"([0-9][0-9,]*)円(以上|未満|以下|超)")
_MAXN = re.compile(r"最大\s*([0-9]+)\s*件")
_YEARS = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*年以上")


def _env(project: dict) -> str:
    prod = primary_product(project) or {}
    return (f"検証環境：{prod.get('name', '対象製品')}"
            f"（版：{prod.get('edition') or '未記入'}／プラン：{prod.get('plan') or '未記入'}）")


def _basis(project: dict, req: dict) -> str:
    dg = current_diagnosis(project, req["id"])
    b = f"要件 {req['id']} 第{req['version']}版"
    if dg:
        b += f"／診断：{dg['category']}"
        if dg["evidence"]:
            b += f"／根拠：{evidence_label(project, dg['evidence'][0], with_quote=False)}"
    return b


def _steps(*lines: str) -> str:
    return "\n".join(f"{i}. {x}" for i, x in enumerate(lines, start=1))


def _base(project: dict, req: dict, **kw) -> dict:
    role = req.get("role") or "対象業務の担当者"
    d = {
        "role": role,
        "preconditions": f"{_env(project)}\n{role}のテスト用アカウントがある\n要件 {req['id']} に関係する設定が、導入時の設定どおりに済んでいる",
        "expected_basis": _basis(project, req),
        "pass_criteria": PASS,
        "importance": "高" if req.get("priority") == "必須" else "中",
        "importance_reason": f"要件の重要度：{req.get('priority', '')}",
        "open_issues": "／".join(x for x in [SCREEN_NOTE, req.get("open_issues", "")] if x),
    }
    d.update(kw)
    return d


def specs_for(project: dict, req: dict) -> list[dict]:
    """1つの要件から作るテスト仕様の一覧（まだ登録しない）。"""
    rule = req.get("rules", "") or req.get("workflow", "")
    role = req.get("role") or "対象業務の担当者"
    work = req.get("workflow") or req["business"]
    out = [_base(project, req, title=f"{req['business']}：要件どおりに{work}ができる"[:70], viewpoint="通常操作",
                 purpose=f"要件 {req['id']} の基本の流れを確認する",
                 test_data=req.get("inputs") or "業務で通常使う値（例：実際によくある申請・登録の内容）",
                 steps=_steps("事前条件を整える", f"{role}で、{work}を行う", "処理後の状態・記録を確認する"),
                 expected=f"次のとおりに処理される：{rule}")]

    m = _AMOUNT.search(rule)
    if m:
        v = int(m.group(1).replace(",", ""))
        cases = [(v - 1, "境目の直前"), (v, "境目ちょうど")] if m.group(2) in ("以上", "未満") else \
                [(v, "境目ちょうど"), (v + 1, "境目の直後")]
        for amount, label in cases:
            out.append(_base(project, req, title=f"{req['business']}：{amount:,}円のとき（{label}）", viewpoint="境界値",
                             purpose="金額の境目の設定が、要件どおりかを確認する",
                             test_data=f"金額 {amount:,}円（{label}）",
                             steps=_steps("事前条件を整える", f"{role}で、金額 {amount:,}円 として{work}を行う",
                                          "どの承認・処理の流れになったかを確認する"),
                             expected=f"金額 {amount:,}円 は、次のルールどおりに扱われる：{rule}",
                             importance="高", importance_reason="境目の設定誤り（「以上」と「超」など）は見落としやすい"))
    m = _MAXN.search(rule)
    if m:
        n = int(m.group(1))
        for k, label, exp in [(n, "上限ちょうど", "すべて登録できる"), (n + 1, "上限を1件超える", "上限を超える登録はできず、分かる表示がある")]:
            out.append(_base(project, req, title=f"{req['business']}：{k}件のとき（{label}）", viewpoint="境界値",
                             purpose="件数の上限が要件どおりかを確認する", test_data=f"{k}件分のデータ",
                             steps=_steps("事前条件を整える", f"{role}で、{k}件を登録する", "登録結果を確認する"),
                             expected=f"{k}件の場合、{exp}（要件：{rule}）"))
    m = _YEARS.search(rule)
    if m:
        y = m.group(1)
        out.append(_base(project, req, title=f"{req['business']}：{y}年前の記録を参照できる", viewpoint="境界値",
                         purpose="保存期間が要件どおりかを確認する",
                         test_data=f"{y}年前の日付の記録（検証環境で用意できない場合は、ベンダーの仕様書・設定画面で確認）",
                         steps=_steps("事前条件を整える", f"{y}年前の記録を検索・表示する", "表示内容を確認する"),
                         expected=f"{y}年前の記録が参照できる（要件：{rule}）",
                         open_issues=f"{SCREEN_NOTE}／古い日付のデータを検証環境で用意できるか確認する"))
    if req.get("exceptions"):
        out.append(_base(project, req, title=f"{req['business']}：例外のとき", viewpoint="例外・エラー",
                         purpose="要件に書かれた例外の扱いを確認する", test_data=f"例外に当たる条件：{req['exceptions']}",
                         steps=_steps("事前条件を整える", f"例外の条件（{req['exceptions']}）で{work}を行う", "処理結果を確認する"),
                         expected=f"例外として、要件どおりに扱われる：{req['exceptions']}"))
    if "禁止" in rule:
        out.append(_base(project, req, title=f"{req['business']}：禁止されている操作ができない", viewpoint="権限",
                         purpose="禁止事項が守られることを確認する",
                         test_data="禁止されている操作に当たるデータ（例：申請者本人が承認しようとする）",
                         steps=_steps("事前条件を整える", "禁止されている操作を試みる", "操作が止められるか、記録が残るかを確認する"),
                         expected=f"禁止された操作は実行できない：{rule}", importance="高",
                         importance_reason="統制上の禁止事項"))
    elif req.get("role") and "だけ" in rule:
        out.append(_base(project, req, title=f"{req['business']}：権限のない人は操作できない", viewpoint="権限",
                         purpose="操作できる人の制限を確認する", test_data=f"{req['role']}以外のテスト用アカウント",
                         steps=_steps("事前条件を整える（権限のないアカウントも用意する）",
                                      f"{req['role']}以外のアカウントで、{work}を試みる", "操作できないことを確認する"),
                         expected=f"{req['role']}以外は操作できない（要件：{rule}）"))
    return out


def draft_tests(project: dict) -> list[dict]:
    created = []
    for req in project["requirements"]:
        if req["status"] != "確定":
            continue
        if any(req["id"] in t["req_ids"] and t["status"] != "廃止" for t in project["tests"]):
            continue
        for spec in specs_for(project, req):
            created.append(rules.add_test(project, {**spec, "req_ids": [req["id"]], "expected_confirmed": False},
                                          origin=ORIGIN))
    return created
