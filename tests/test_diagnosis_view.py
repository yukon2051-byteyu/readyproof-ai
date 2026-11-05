"""③ 診断結果の表示内容（logic/diagnosis_view.py）。元データと一致し、状態を混同しないこと。"""
import copy

import pytest

from readyproof.core import DIAG_CATEGORIES
from readyproof.demos.builder import DEMOS, build
from readyproof.export.jsonio import from_json_bytes, to_json_bytes
from readyproof.logic import diagnosis_view as V
from readyproof.logic import metrics as M
from readyproof.logic import rules
from readyproof.logic.rules import current_diagnosis


def by_id(rs, rid):
    return next(x for x in rs if x["req"]["id"] == rid)


def check(x, name):
    return dict(x["checks"])[name]


def test_every_category_belongs_to_exactly_one_group():
    grouped = [c for g in V.GROUPS.values() for c in g["cats"]]
    assert sorted(grouped) == sorted(DIAG_CATEGORIES)


@pytest.mark.parametrize("demo", [d["id"] for d in DEMOS])
def test_counts_match_source_data(demo):
    p = build(demo)
    m = M.compute(p)
    rs = V.rows(p, m)
    c = V.counts(rs)
    assert sum(c.values()) == m["requirements"] == len(rs)
    assert c["none"] == m["no_diagnosis"]
    for k, g in V.GROUPS.items():
        if k != "none":
            assert c[k] == sum(m["by_category"][x] for x in g["cats"])
        assert len(V.filter_sort(rs, k)) == c[k]  # 絞り込みの件数と、札の件数が一致する
    k = V.kpis(rs, m)
    assert sum(x["value"] for x in k["main"]) + k["none"] == k["total"]


def test_demo1_summary_states_conclusion_and_limits():
    p = build("demo1")
    m = M.compute(p)
    rs = V.rows(p, m)
    s = V.summary(p, m, rs)
    assert s["head"] == "必須要件2件は、製品の設定で対応できる見込みです"
    assert s["total"] == 3 and s["must"] == 2
    assert any("全9件を実施し、すべて合格" in x for x in s["subs"])
    assert any("代理承認" in x and "未確定" in x for x in s["subs"])
    assert s["status"]["text"] == "人の判断：条件付き導入可"  # 総合判定を作らず、人の判断をそのまま示す
    assert V.kpis(rs, m)["tests"] == {"total": 9, "run": 9, "passed": 9, "failed": 0}


def test_demo1_requirements_and_next_action():
    p = build("demo1")
    rs = V.rows(p, M.compute(p))
    r1, r2, r3 = by_id(rs, "REQ-001"), by_id(rs, "REQ-002"), by_id(rs, "REQ-003")
    assert r1["label"] == r2["label"] == "設定で対応できる見込み" and r1["group"] == "likely"
    assert r3["label"] == "未診断" and r3["group"] == "none" and "未確定" in r3["reason"]
    assert len(r1["dg"]["evidence"]) == 7
    assert r1["title"] != r2["title"]  # 業務名が同じ要件は見分けられる
    acts = V.next_actions(p, rs)
    assert [a["text"] for a in acts] == ["要件を確定する"]
    assert acts[0]["req_id"] == "REQ-003" and acts[0]["page"] == "input2" and "経理部で検討中" in acts[0]["reason"]


def test_states_are_not_confused():
    """人の確認済みでも、実機未実施なら実機は「済み」にしない。未診断を見込みにしない。"""
    p = build("demo1")
    p["runs"] = []
    m = M.compute(p)
    rs = V.rows(p, m)
    x = by_id(rs, "REQ-001")
    assert check(x, "人の確認")["state"] == "ok"
    assert check(x, "ベンダー回答")["state"] == "ok"
    assert check(x, "実機テスト")["state"] == "wait" and "未実施" in check(x, "実機テスト")["text"]
    assert x["need"]["text"].startswith("実機テストを実施する")
    s = V.summary(p, m, rs)
    assert any("実機テストは未実施" in t for t in s["subs"])
    assert s["head"].endswith("見込みです")  # 合格とは言わない
    y = by_id(rs, "REQ-003")
    assert check(y, "人の確認")["state"] == "none" and check(y, "AI診断")["state"] == "none"


def test_priority_order_puts_serious_issues_first():
    p = build("demo2")
    rs = V.rows(p, M.compute(p))
    ids = [x["req"]["id"] for x in V.filter_sort(rs)]
    assert ids[0] == "REQ-003"  # 不合格のテストがある要件が先頭
    assert [x["req"]["id"] for x in V.filter_sort(rs, sort="要件番号順")] == ["REQ-001", "REQ-002", "REQ-003", "REQ-004"]
    grouped = V.filter_sort(rs, sort="診断区分順")
    assert grouped[0]["group"] == "hard"
    assert [x["group"] for x in V.filter_sort(rs, "likely")] == ["likely"]
    assert {x["req"]["priority"] for x in V.filter_sort(rs, priority="必須")} == {"必須"}
    assert V.filter_sort(rs, priority="任意") == []


def test_answered_questions_are_not_asked_again(monkeypatch):
    p = build("demo2")
    rs = V.rows(p, M.compute(p))
    assert by_id(rs, "REQ-001")["dg"]["remaining_conditions"]  # 記録として条件は残っている
    assert "ベンダーに確認する" not in [a["text"] for a in V.next_actions(p, rs)]
    # 質問していない場合は確認を促す（質問を消すと根拠の参照先も消えるので、古さの判定は切り離す）
    monkeypatch.setattr(V, "diagnosis_stale_reasons", lambda *a: [])
    p["questions"] = [q for q in p["questions"] if "REQ-001" not in q["req_ids"]]
    assert by_id(V.rows(p, M.compute(p)), "REQ-001")["need"]["text"] == "ベンダーに確認する"


def test_actions_only_come_from_existing_state():
    """問題がなければ次のアクションを作らない。判断も記録済みなら空。"""
    p = build("demo3")
    rs = V.rows(p, M.compute(p))
    assert V.next_actions(p, rs) == []
    p["decision"]["value"] = "未判断"
    assert [a["text"] for a in V.next_actions(p, V.rows(p, M.compute(p)))] == ["導入判断を記録する"]


def test_empty_and_undiagnosed_project(project):
    assert V.summary(project)["head"] == "まだ診断していません"
    r = rules.add_requirement(project, {"business": "勤怠の承認", "rules": "残業は上長が承認する", "priority": "必須"})
    rules.confirm_requirement(project, r, "確認者")
    m = M.compute(project)
    rs = V.rows(project, m)
    assert rs[0]["need"]["text"] == "AIで診断する" and rs[0]["need"]["rank"] == V.R_DIAG
    assert V.summary(project, m, rs)["status"]["text"] == "診断途中"


def test_evidence_quotes_are_not_rewritten_by_view():
    p = build("demo1")
    before = copy.deepcopy(current_diagnosis(p, "REQ-001")["evidence"])
    V.summary(p)
    V.next_actions(p, V.rows(p))
    assert current_diagnosis(p, "REQ-001")["evidence"] == before


def test_saved_project_reloads_with_same_view():
    p = build("demo2")
    q = from_json_bytes(to_json_bytes(p))
    assert V.summary(q)["head"] == V.summary(p)["head"]
    assert V.counts(V.rows(q)) == V.counts(V.rows(p))
    old = copy.deepcopy(q)  # 以前の保存データ（実機テストで確認することの項目がない）
    for d in old["diagnoses"]:
        d.pop("test_conditions", None)
    assert V.rows(old)
