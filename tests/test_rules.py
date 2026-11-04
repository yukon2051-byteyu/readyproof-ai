"""根拠検証・診断・依頼・テストの業務ルール（必須検証：診断・依頼・テスト）。"""
import pytest

from readyproof.logic import metrics, rules
from readyproof.logic.evidence import VALIDITY_NOTE, validate_evidence
from readyproof.logic.recordings import build_utterances
from readyproof.logic.stale import all_stale, diagnosis_stale_reasons, run_stale_reasons


def seg_ev(src, needle):
    seg = next(g for g in src["segments"] if needle in g["text"])
    return {"ref_type": "source", "source_id": src["id"], "version": src["version"], "seg_id": seg["seg_id"],
            "quote": needle, "kind": "資料の記載"}


def add_req(p, **kw):
    r = rules.add_requirement(p, {"business": "承認", "rules": "10,000円以上は部長承認", **kw})
    rules.confirm_requirement(p, r, "確認者")
    return r


def add_rec(p, texts, roles=None, confirmed=True):
    utts = build_utterances([{"start": i * 10.0, "end": i * 10.0 + 5, "speaker_label": f"S{i}", "text": t}
                             for i, t in enumerate(texts)])
    for u, role in zip(utts, roles or ["営業担当者"] * len(utts)):
        u["speaker_role"], u["speaker_confirmed"] = role, confirmed
        u["review_status"] = "確認済み" if confirmed else "未確認"
    rec = {"id": "REC-001", "version": 1, "meeting_name": "説明会", "held_on": "2026-10-15", "product_id": "PR-001",
           "range": {"start": 0.0, "end": None}, "utterances": utts, "file_name": "m.mp4"}
    p["recordings"].append(rec)
    return rec


# ---------- 根拠の検証 ----------
def test_quote_must_exist(deck_project):
    p, src = deck_project
    ok = seg_ev(src, "10,000円以上")
    assert validate_evidence(p, ok, "PR-001")["ok"]
    bad = {**ok, "quote": "10,000円以上は自動で部長承認になります"}  # 言い換え・創作
    assert not validate_evidence(p, bad, "PR-001")["ok"]
    assert not validate_evidence(p, {**ok, "seg_id": "S9999"}, "PR-001")["ok"]  # 存在しない位置
    assert not validate_evidence(p, {**ok, "source_id": "DOC-999"}, "PR-001")["ok"]  # 存在しないID
    assert not validate_evidence(p, {**ok, "version": 2}, "PR-001")["ok"]  # 存在しない版
    assert "意味" in VALIDITY_NOTE  # 実在確認と意味の妥当性は別


def test_unselected_note_and_hidden_slide_rejected(deck_project):
    p, src = deck_project
    note = next(g for g in src["segments"] if g.get("is_note"))
    ev = {"ref_type": "source", "source_id": src["id"], "version": 1, "seg_id": note["seg_id"],
          "quote": note["text"][:10], "kind": "資料の記載"}
    v = validate_evidence(p, ev, "PR-001")
    assert not v["ok"] and any("未選択" in e for e in v["errors"])
    with pytest.raises(rules.RuleError):  # 内容確認前のノートは対象にできない
        rules.set_segment_selected(src, note["seg_id"], True)
    note["note_reviewed"] = True
    rules.set_segment_selected(src, note["seg_id"], True)
    assert validate_evidence(p, ev, "PR-001")["ok"]


def test_other_product_rejected(deck_project):
    p, src = deck_project
    assert not validate_evidence(p, seg_ev(src, "10,000円以上"), "PR-999")["ok"]


def test_utterance_question_and_unconfirmed_warned(project):
    rec = add_rec(project, ["標準プランで予約停止できますか？", "予約停止は上位プランで対応しています。"],
                  roles=["自社担当者", "営業担当者"], confirmed=False)
    rec["utterances"][0]["utterance_type"] = "質問"
    q = {"ref_type": "utterance", "rec_id": "REC-001", "rec_version": 1, "utt_id": "U001",
         "quote": "標準プランで予約停止できますか？", "kind": "営業・ベンダーの説明"}
    v = validate_evidence(project, q, "PR-001")
    assert any("自社担当者" in w for w in v["warnings"]) and any("質問" in w for w in v["warnings"])
    assert any("未確認" in w for w in v["warnings"])
    a = {**q, "utt_id": "U002", "quote": "予約停止は上位プランで対応しています。"}
    assert any("プラン" in w for w in validate_evidence(project, a, "PR-001")["warnings"])


def test_out_of_range_utterance_rejected(project):
    rec = add_rec(project, ["一つ目", "二つ目"])
    rec["range"] = {"start": 0.0, "end": 5.0}
    ev = {"ref_type": "utterance", "rec_id": "REC-001", "rec_version": 1, "utt_id": "U002", "quote": "二つ目"}
    assert not validate_evidence(project, ev, "PR-001")["ok"]


# ---------- 診断 ----------
def test_absence_is_not_unsupported(project):
    r = add_req(project)
    dg = rules.add_diagnosis(project, {"req_id": r["id"], "category": "対応不可との記載・確認済み発言あり",
                                       "reason": "記載がない", "evidence": []})
    assert dg["category"] == "情報不足・ベンダー確認が必要"
    assert dg["auto_adjustments"]


def test_ai_fabricated_quote_removed_and_downgraded(deck_project):
    p, src = deck_project
    r = add_req(p)
    ev = {**seg_ev(src, "10,000円以上"), "quote": "部長承認は標準で自動設定"}
    dg = rules.add_diagnosis(p, {"req_id": r["id"], "category": "そのまま対応できる見込み", "evidence": [ev]})
    assert dg["evidence"] == [] and dg["rejected_evidence"] and dg["category"] == "情報不足・ベンダー確認が必要"


def test_partial_match_not_whole(deck_project):
    p, src = deck_project
    r = add_req(p)
    dg = rules.add_diagnosis(p, {"req_id": r["id"], "category": "そのまま対応できる見込み",
                                 "evidence": [seg_ev(src, "10,000円以上")], "remaining_conditions": ["自己承認の禁止"]})
    assert dg["category"] == "情報不足・ベンダー確認が必要"


def test_unconfirmed_vendor_talk_cannot_be_confirmed(project):
    rec = add_rec(project, ["金額による承認分岐は、上位プランの設定で対応できます"], confirmed=False)
    r = add_req(project)
    ev = {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": 1, "utt_id": "U001",
          "quote": "金額による承認分岐は、上位プランの設定で対応できます", "kind": "営業・ベンダーの説明"}
    dg = rules.add_diagnosis(project, {"req_id": r["id"], "category": "標準設定で対応できる見込み", "evidence": [ev]},
                             origin="手動")
    with pytest.raises(rules.RuleError):
        rules.review_diagnosis(project, dg, "確認者", "人が確認済み")


def test_unsupported_needs_doc_or_confirmed_vendor(project):
    rec = add_rec(project, ["おそらくできません"], roles=["自社担当者"])
    r = add_req(project)
    ev = {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": 1, "utt_id": "U001", "quote": "おそらくできません"}
    dg = rules.add_diagnosis(project, {"req_id": r["id"], "category": "対応不可との記載・確認済み発言あり", "evidence": [ev]})
    assert dg["category"] == "情報不足・ベンダー確認が必要"


def test_old_diagnosis_not_reused_and_stale_detected(deck_project):
    p, src = deck_project
    r = add_req(p)
    dg = rules.add_diagnosis(p, {"req_id": r["id"], "category": "標準設定で対応できる見込み",
                                 "evidence": [seg_ev(src, "10,000円以上")]})
    rules.review_diagnosis(p, dg, "確認者", "人が確認済み")
    assert not diagnosis_stale_reasons(p, dg)
    rules.update_requirement(p, r, {"rules": "10,000円以上は部長と経理の承認"}, "確認者", "規程改定")
    assert r["version"] == 2 and r["status"] == "下書き" and r["history"][0]["version"] == 1
    reasons = diagnosis_stale_reasons(p, dg)
    assert any("第1版→第2版" in x for x in reasons)
    assert rules.current_diagnosis(p, r["id"])["req_version"] == 1  # 自動で新版に書き換えない
    p["products"][0]["plan"] = "エンタープライズ"
    assert any("プラン" in x for x in diagnosis_stale_reasons(p, dg))


def test_utterance_change_makes_diagnosis_stale(project):
    rec = add_rec(project, ["設定で対応できます"])
    r = add_req(project)
    ev = {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": 1, "utt_id": "U001", "quote": "設定で対応できます"}
    dg = rules.add_diagnosis(project, {"req_id": r["id"], "category": "標準設定で対応できる見込み", "evidence": [ev]},
                             origin="手動")
    rec["utterances"][0]["speaker_role"] = "自社担当者"  # 話者の修正
    assert diagnosis_stale_reasons(project, dg)


# ---------- テスト・実施 ----------
def make_test(p, r, confirm=True):
    t = rules.add_test(p, {"req_ids": [r["id"]], "title": "10,000円は部長承認", "steps": "申請", "expected": "部長承認待ち",
                           "expected_confirmed": confirm})
    if confirm:
        rules.confirm_test(p, t, "確認者")
    return t


def test_cannot_pass_unconfirmed_test(project):
    r = add_req(project)
    t = make_test(project, r, confirm=False)
    with pytest.raises(rules.RuleError):
        rules.record_run(project, t, {"tester": "A", "status": "完了", "result": "合格", "actual": "OK"})
    with pytest.raises(rules.RuleError):
        rules.confirm_test(project, t, "確認者")  # 期待結果が未確定
    t2 = rules.add_test(project, {"req_ids": [r["id"]], "title": "x", "steps": "画面は要確認", "expected": "y",
                                  "expected_confirmed": True})
    with pytest.raises(rules.RuleError):
        rules.confirm_test(project, t2, "確認者")  # 「要確認」が残る


def test_blocked_not_counted_and_retest_history(project):
    r = add_req(project)
    t1, t2 = make_test(project, r), make_test(project, r)
    with pytest.raises(rules.RuleError):
        rules.record_run(project, t1, {"tester": "A", "status": "実施不能", "result": "不合格", "actual": "x"})
    rules.record_run(project, t1, {"tester": "A", "status": "実施不能", "result": "未判定"})
    first = rules.record_run(project, t2, {"tester": "A", "status": "完了", "result": "不合格", "actual": "承認なしで完了"})
    m = metrics.compute(project)
    assert m["pass_rate"] == {"num": 0, "den": 1, "text": "0/1（0%）"}  # 実施不能は分母に入れない
    second = rules.record_run(project, t2, {"tester": "A", "status": "完了", "result": "合格", "actual": "部長承認待ち"})
    assert second["is_retest"] and second["previous_run_id"] == first["id"]
    assert project["runs"][1]["result"] == "不合格"  # 過去の結果は書き換えない


def test_zero_denominator(project):
    m = metrics.compute(project)
    assert m["pass_rate"]["text"] == "対象なし（分母0）" and m["executed_rate"]["den"] == 0


def test_old_version_pass_not_reused(project):
    r = add_req(project)
    t = make_test(project, r)
    run = rules.record_run(project, t, {"tester": "A", "status": "完了", "result": "合格", "actual": "OK"})
    rules.update_test(project, t, {"expected": "部長と経理の承認待ち"}, "確認者")
    assert t["version"] == 2 and run_stale_reasons(project, run)
    assert t["id"] not in metrics.compute(project)["passed"]
    assert any(s["type"] == "実施結果" for s in all_stale(project))


def test_sales_explanation_never_becomes_pass(project):
    rec = add_rec(project, ["標準設定で対応できます"])
    r = add_req(project)
    ev = {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": 1, "utt_id": "U001", "quote": "標準設定で対応できます"}
    dg = rules.add_diagnosis(project, {"req_id": r["id"], "category": "標準設定で対応できる見込み", "evidence": [ev]})
    rules.review_diagnosis(project, dg, "確認者", "人が確認済み")
    m = metrics.compute(project)
    assert r["id"] in m["must_not_verified"] and not m["passed"]


# ---------- 依頼 ----------
def make_request(p, r, t=None, kind="設定変更依頼"):
    return rules.add_request(p, {"title": "設定変更", "kind": kind, "req_ids": [r["id"]],
                                 "test_ids": [t["id"]] if t else [], "phase": "資料診断段階の懸念"})


def test_request_created_is_draft_and_not_sent(project):
    r = add_req(project)
    c = make_request(project, r)
    assert c["status"] == "下書き"
    with pytest.raises(rules.RuleError):
        rules.change_request_status(project, c, "送付済み", "A")  # 確定前に送付済みにできない


def test_vendor_done_is_not_completion(project):
    r = add_req(project)
    t = make_test(project, r)
    c = make_request(project, r, t)
    for s in ("確定", "送付済み", "回答待ち", "対応中", "テスト待ち"):
        rules.change_request_status(project, c, s, "A")
    rules.record_vendor_response(project, c, {"vendor_done": True}, "A")
    with pytest.raises(rules.RuleError):
        rules.change_request_status(project, c, "完了", "A")
    rules.record_run(project, t, {"tester": "A", "status": "完了", "result": "不合格", "actual": "NG"})
    with pytest.raises(rules.RuleError):
        rules.change_request_status(project, c, "完了", "A")
    rules.record_run(project, t, {"tester": "A", "status": "完了", "result": "合格", "actual": "OK"})
    rules.change_request_status(project, c, "完了", "A")
    assert c["completion"]["human_confirmed"]


def test_skip_does_not_change_failure(project):
    r = add_req(project)
    t = make_test(project, r)
    rules.record_run(project, t, {"tester": "A", "status": "完了", "result": "不合格", "actual": "NG"})
    c = make_request(project, r, t)
    with pytest.raises(rules.RuleError):
        rules.change_request_status(project, c, "見送り", "A")  # 理由が必要
    rules.change_request_status(project, c, "見送り", "A", "今回は見送り")
    assert rules.latest_run(project, t["id"])["result"] == "不合格"
    assert t["id"] in metrics.compute(project)["failed"]


def test_with_remaining_completion_requires_reason(project):
    r = add_req(project)
    t = make_test(project, r)
    c = make_request(project, r, t)
    for s in ("確定", "送付済み", "回答待ち", "対応中", "テスト待ち"):
        rules.change_request_status(project, c, s, "A")
    with pytest.raises(rules.RuleError):
        rules.change_request_status(project, c, "完了", "A", "", with_remaining=True)
    rules.change_request_status(project, c, "完了", "A", "訂正者表示は次期対応", with_remaining=True)
    assert c["id"] in metrics.compute(project)["cr_done_remaining"]


def test_investigation_completes_on_answer(project):
    r = add_req(project)
    q = rules.add_question(project, {"req_ids": [r["id"]], "question": "保存期間は？"})
    c = rules.add_request(project, {"title": "保存期間の調査", "kind": "調査依頼", "req_ids": [r["id"]],
                                    "question_ids": [q["id"]]})
    for s in ("確定", "送付済み", "回答待ち"):
        rules.change_request_status(project, c, s, "A")
    with pytest.raises(rules.RuleError):
        rules.change_request_status(project, c, "完了", "A")
    rules.record_answer(project, q, "1年間保存します。", "手動入力", "2026-10-20", "A")
    rules.confirm_answer(project, q, "B", "確認")
    rules.change_request_status(project, c, "完了", "A")


def test_unknown_cost_is_not_zero(project):
    r = add_req(project)
    c = make_request(project, r)
    rules.record_vendor_response(project, c, {"cost_amount": "", "effort": ""}, "A")
    assert c["vendor"]["cost_amount"] is None and c["vendor"]["effort"] is None
    with pytest.raises(rules.RuleError):
        rules.record_vendor_response(project, c, {"cost_amount": "100000"}, "A")  # 通貨なし
    with pytest.raises(rules.RuleError):
        rules.record_vendor_response(project, c, {"cost_amount": "十万円"}, "A")


def test_not_everything_is_a_request(project):
    r = add_req(project)
    a = rules.add_action(project, {"req_id": r["id"], "type": "手順・教育の改善", "reason": "運用で対応"})
    rules.decide_action(project, a, "採用", "A", "運用で十分")
    assert project["requests"] == []  # 対応方法の採用だけで依頼書は作られない


def test_test_failure_request_needs_run(project):
    r = add_req(project)
    with pytest.raises(rules.RuleError):
        rules.add_request(project, {"title": "x", "phase": "テストで発生した現象", "req_ids": [r["id"]]})


def test_question_sent_and_answer_rules(project):
    rec = add_rec(project, ["確認して回答します"], confirmed=False)
    q = rules.add_question(project, {"question": "保存期間は？"})
    with pytest.raises(rules.RuleError):
        rules.mark_question_sent(project, q, "A", "2026-10-01")  # 下書きのまま送付済みにしない
    ev = {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": 1, "utt_id": "U001", "quote": "確認して回答します"}
    with pytest.raises(rules.RuleError):
        rules.record_answer(project, q, "回答", "確認済み営業発言", "2026-10-01", "A", [ev])


def test_written_confirmation_question_has_time_and_quote(project):
    rec = add_rec(project, ["", "予約停止は上位プランで対応しています。"])
    rec["utterances"][1]["start"], rec["utterances"][1]["end"] = 1104.0, 1126.0
    q = rules.written_confirmation_question(project, {"ref_type": "utterance", "rec_id": "REC-001", "rec_version": 1,
                                                      "utt_id": "U002", "quote": "予約停止は上位プランで対応しています。"})
    assert "00:18:24～00:18:46" in q["background"] and "『予約停止は上位プランで対応しています。』" in q["background"]
    assert "営業担当者・利用者確認済み" in q["background"] and q["status"] == "下書き"


def test_requirement_terms_not_dropped(project):
    r = rules.add_requirement(project, {"business": "承認", "rules": "部長承認が必要",
                                        "original_text": "10,000円以上は部長承認。自己承認は禁止。"})
    assert "10,000" in r["term_warnings"] and "以上" in r["term_warnings"] and "禁止" in r["term_warnings"]


def test_decision_requires_reason_and_conditions(project):
    with pytest.raises(rules.RuleError):
        rules.record_decision(project, "導入可", "", "2026-11-01", "", "", {})
    with pytest.raises(rules.RuleError):
        rules.record_decision(project, "条件付き導入可", "A", "2026-11-01", "理由", "", {})
    rules.record_decision(project, "導入延期", "A", "2026-11-01", "必須要件が未確認", "", {"fp": "x"})
    rules.record_decision(project, "条件付き導入可", "A", "2026-11-02", "回答待ち", "書面回答", {"fp": "y"})
    assert project["decision"]["history"][0]["value"] == "導入延期"
