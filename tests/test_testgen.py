"""受入テスト仕様の自動作成（AIなし）と、受入テスト仕様書（Excel）。"""
import io

import openpyxl

from readyproof.core import find
from readyproof.demos.builder import build_scenario as build
from readyproof.export.excel import acceptance_test_workbook
from readyproof.logic import rules
from readyproof.testgen import draft_tests, specs_for


def _fresh(demo):
    p = build(demo)
    p["tests"], p["runs"] = [], []
    for c in p["requests"]:
        c["test_ids"] = []
    return p


def test_boundary_and_prohibition_specs():
    p = _fresh("demo1")
    r1, r2 = find(p, "requirements", "REQ-001"), find(p, "requirements", "REQ-002")
    s1 = specs_for(p, r1)
    data = [s["test_data"] for s in s1 if s["viewpoint"] == "境界値"]
    assert data == ["金額 9,999円（境目の直前）", "金額 10,000円（境目ちょうど）"]
    s2 = specs_for(p, r2)
    assert any(s["viewpoint"] == "権限" and "禁止" in s["expected"] for s in s2)


def test_every_spec_is_complete_and_has_no_invented_screens():
    p = _fresh("demo2")
    made = draft_tests(p)
    assert made
    for t in made:
        for k in ("preconditions", "test_data", "steps", "expected", "pass_criteria", "expected_basis"):
            assert t.get(k), (t["id"], k)
        assert t["steps"].startswith("1. ")
        assert "画面" not in t["steps"]  # 画面名・ボタン名を推測で書かない
        assert t["status"] == "下書き" and not t["expected_confirmed"]
        assert "製品で確認" in t["open_issues"]
    assert any(t["test_data"] == "16件分のデータ" for t in made)  # 最大15件 → 上限を1件超える


def test_generated_spec_can_be_confirmed_after_review():
    p = _fresh("demo1")
    t = draft_tests(p)[0]
    t["expected_confirmed"] = True  # 人が期待結果を確認した
    rules.confirm_test(p, t, "確認者")
    assert t["status"] == "確定"


def test_no_overwrite_of_existing_tests():
    p = build("demo1")
    before = len(p["tests"])
    assert draft_tests(p) == [] and len(p["tests"]) == before


def test_spec_workbook_sheets_and_traceability():
    p = _fresh("demo1")
    draft_tests(p)
    wb = openpyxl.load_workbook(io.BytesIO(acceptance_test_workbook(p)))
    assert wb.sheetnames == ["表紙", "概要", "テスト項目", "要件との対応表", "実施記録"]
    head = [c.value for c in wb["テスト項目"][next(i for i, r in enumerate(wb["テスト項目"].iter_rows(values_only=True), 1)
                                                if r[0] == "No")]]
    for col in ("テストデータ", "手順", "期待結果", "合否判定基準", "根拠", "結果（合格／不合格／実施不能）", "証跡"):
        assert col in head
    text = "\n".join(str(c.value) for row in wb["要件との対応表"].iter_rows() for c in row if c.value)
    assert "REQ-003" in text and "テストなし" in text  # 未確定の要件はテストなしとして見える


def test_workbook_works_as_test_report():
    """アプリで記録した結果が Excel に入り、テスト成績書として残せる。結果のある行は記入欄（黄色）にしない。"""
    p = build("demo1")  # 筋書き版：T-001 合格、T-002 不合格→再テスト合格
    wb = openpyxl.load_workbook(io.BytesIO(acceptance_test_workbook(p)))
    assert wb["表紙"]["A1"].value == "受入テスト仕様書 兼 成績書"
    cover = {r[0]: r[1] for r in wb["表紙"].iter_rows(values_only=True) if r[0]}
    assert cover["テスト結果（最新）"].startswith("合格 2件／不合格 0件")
    assert "再テストを含む" in cover["実施期間"]
    ws = wb["テスト項目"]
    rows = list(ws.iter_rows())
    head_i = next(i for i, r in enumerate(rows) if r[0].value == "No")
    head = [c.value for c in rows[head_i]]
    res_col = head.index("結果（合格／不合格／実施不能）")
    by_id = {r[1].value: r for r in rows[head_i + 1:]}
    assert by_id["T-002"][res_col].value == "合格"  # 最新の結果
    assert by_id["T-002"][res_col].fill.fgColor.rgb != "00FFF8DC"
    t3 = by_id["T-003"][res_col]
    assert t3.value in (None, "") and t3.fill.fgColor.rgb == "00FFF8DC"  # 未実施は記入欄
    assert len(list(wb["実施記録"].iter_rows())) > 3
