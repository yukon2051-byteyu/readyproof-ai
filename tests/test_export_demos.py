"""保存・Excel 出力・3件のデモ（必須検証：デモ・保存・UI）。"""
import io
import json

import openpyxl
import pytest

from readyproof.demos.builder import DEMOS, EXPECTED, build_scenario as build
from readyproof.export.excel import questionnaire_workbook, report_workbook, request_workbook, safe
from readyproof.export.jsonio import LoadError, from_json_bytes, to_json_bytes
from readyproof.logic import metrics, rules
from readyproof.logic.evidence import validate_evidence


@pytest.fixture(scope="module")
def demos():
    return {d["id"]: build(d["id"]) for d in DEMOS}


def test_three_demos_complete_and_distinct(demos):
    kinds = {k: {s["file_type"] for s in p["sources"]} for k, p in demos.items()}
    assert "pptx" in kinds["demo1"] and {"pdf", "xlsx", "txt"} <= kinds["demo2"]
    assert demos["demo3"]["recordings"] and not demos["demo1"]["recordings"]
    for k, p in demos.items():
        for rid, cat in EXPECTED[k]["categories"].items():
            assert rules.current_diagnosis(p, rid)["category"] == cat, (k, rid)
        m = metrics.compute(p)
        # 「合格だけ」の例にしない：未確認・不合格・残件を含む
        assert metrics.remaining_issues(p, m), k
        assert all(t["status"] in ("確定", "下書き") for t in p["tests"])


def test_demo_evidence_all_valid(demos):
    for k, p in demos.items():
        for dg in p["diagnoses"]:
            for ev in dg["evidence"]:
                assert validate_evidence(p, ev, "PR-001")["ok"], (k, dg["id"], ev)


def test_demo_specific_points(demos):
    d1, d2, d3 = demos["demo1"], demos["demo2"], demos["demo3"]
    runs = [r for r in d1["runs"] if r["test_id"] == "T-002"]
    assert [r["result"] for r in runs] == ["不合格", "合格"] and runs[1]["is_retest"]
    assert d1["requests"][0]["status"] == "完了" and d1["requests"][0]["kind"] == "設定変更依頼"
    deck = d1["sources"][0]
    assert all(not g["selected"] for g in deck["segments"] if g.get("is_note"))
    m2 = metrics.compute(d2)
    assert "T-004" in m2["blocked"] and "T-003" in m2["failed"] and "REQ-002" in m2["must_not_verified"]
    assert d2["requests"][0]["vendor"]["cost_amount"] is None
    assert any(d["superseded_by"] for d in d2["diagnoses"] if d["req_id"] == "REQ-003")
    u = {x["id"]: x for x in d3["recordings"][0]["utterances"]}
    assert u["U001"]["speaker_role"] == "自社担当者" and u["U001"]["utterance_type"] == "質問"
    assert u["U004"]["utterance_type"] == "未回答・調査中" and u["U005"]["utterance_type"] == "将来予定"
    assert not u["U007"]["speaker_confirmed"]
    assert "00:00:06～00:00:12" in d3["questions"][0]["background"]
    assert metrics.compute(d3)["passed"] == []


def test_demo_uses_no_paid_api():
    # conftest で anthropic.Anthropic を呼ぶと失敗するようにしてある。デモ作成で一度も呼ばれない
    for d in DEMOS:
        build(d["id"])


def test_json_roundtrip_keeps_relations(demos):
    p = demos["demo3"]
    data = to_json_bytes(p, include_unselected_notes=False)
    q = from_json_bytes(data)
    assert q["recordings"][0]["utterances"][1]["start"] == p["recordings"][0]["utterances"][1]["start"]
    assert q["diagnoses"][0]["evidence"] == p["diagnoses"][0]["evidence"]
    assert q["requirements"][0]["version"] == p["requirements"][0]["version"]
    assert json.loads(data)["schema_version"] == "1.0"
    d1 = from_json_bytes(to_json_bytes(demos["demo1"]))
    notes = [g for s in d1["sources"] for g in s["segments"] if g.get("is_note")]
    assert notes and all(g["text"] == "" and g["text_omitted"] for g in notes)  # 未選択ノートは保存しない
    assert len(d1["runs"]) == len(demos["demo1"]["runs"]) and d1["audit_log"]


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"schema_version": "1.0"}',
                                 b'{"schema_version": "9.9", "project": {}, "products": [], "sources": [], "recordings": [],'
                                 b' "requirements": [], "diagnoses": [], "questions": [], "actions": [], "requests": [],'
                                 b' "tests": [], "runs": [], "decision": {}}'])
def test_invalid_json_rejected(raw):
    with pytest.raises(LoadError):
        from_json_bytes(raw)


def test_broken_relation_rejected(demos):
    data = json.loads(to_json_bytes(demos["demo1"]))
    data["runs"][0]["test_id"] = "T-999"
    with pytest.raises(LoadError):
        from_json_bytes(json.dumps(data).encode())


def test_excel_readable_with_evidence(demos):
    wb = openpyxl.load_workbook(io.BytesIO(report_workbook(demos["demo3"])))
    assert {"概要", "資料と録画", "自社要件", "診断と根拠", "質問と回答", "対応と依頼", "テストと結果", "残件", "導入判断"} <= set(wb.sheetnames)
    text = "\n".join(str(c.value) for row in wb["診断と根拠"].iter_rows() for c in row if c.value)
    assert "00:00:06～00:00:12" in text and "営業担当者" in text and "利用者確認済み" in text
    assert "見出し「アカウント管理」" in text
    text1 = "\n".join(str(c.value) for row in openpyxl.load_workbook(io.BytesIO(report_workbook(demos["demo1"])))
                      ["診断と根拠"].iter_rows() for c in row if c.value)
    assert "スライド2" in text1
    wb = openpyxl.load_workbook(io.BytesIO(request_workbook(demos["demo1"], "CR-001")))
    body = "\n".join(str(c.value) for row in wb.active.iter_rows() for c in row if c.value)
    assert "受入条件" in body and "10,000円：上司→部長" in body and "第1版" in body
    wb = openpyxl.load_workbook(io.BytesIO(questionnaire_workbook(demos["demo3"])))
    assert "ご回答（記入欄）" in [c.value for c in wb.active[wb.active.max_row - len(demos["demo3"]["questions"])]]


def test_excel_formula_injection_escaped():
    assert safe("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert safe("+1") == "'+1" and safe("@cmd") == "'@cmd" and safe("-2") == "'-2"
    assert safe("通常の文字") == "通常の文字" and safe(5) == 5 and safe(None) == ""


def test_excel_unknown_cost_shown_as_unanswered(demos):
    wb = openpyxl.load_workbook(io.BytesIO(report_workbook(demos["demo2"])))
    text = "\n".join(str(c.value) for row in wb["対応と依頼"].iter_rows() for c in row if c.value)
    assert "未回答" in text and "0 円" not in text


def test_screen_demos_use_saved_real_ai_outputs():
    """画面のデモ：固定の入力 ＋ 事前に本物のAIで作った出力。表示時に有料APIは呼ばない（conftestで禁止済み）。"""
    from readyproof.demos.ai_outputs import ORIGIN
    from readyproof.demos.builder import build as build_screen
    from readyproof.logic.rules import current_diagnosis

    for d in DEMOS:
        p = build_screen(d["id"])
        confirmed = [r for r in p["requirements"] if r["status"] == "確定"]
        assert confirmed and all(current_diagnosis(p, r["id"]) for r in confirmed)
        assert all(x["origin"] == ORIGIN for x in p["diagnoses"] + p["tests"])
        assert p["tests"] and not p["runs"]  # テスト結果は見る人が記録する
        assert any(t["status"] == "確定" for t in p["tests"])
        assert all(t["status"] == "下書き" for t in p["tests"] if "要確認" in t["steps"] + t["expected"])
        assert p["project"]["demo_ai"]["model"]
        for dg in p["diagnoses"]:  # 参照キー（E3 など）が文中に残らない
            assert not __import__("re").search(r"(?<![A-Za-z0-9])E[0-9]+(?![0-9])", dg["reason"])


def test_saved_ai_output_rejects_changed_inputs():
    """入力が変わったら、古いAIの出力を貼らない。"""
    import pytest

    from readyproof.demos.ai_outputs import StaleDemoOutput, apply_saved
    from readyproof.demos.builder import build_inputs

    p = build_inputs("demo1")
    p["requirements"][0]["rules"] += "（変更）"
    with pytest.raises(StaleDemoOutput):
        apply_saved(p, "demo1")
