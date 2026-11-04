"""質問形式の要件入力（AIなし）と、根拠の原文表示。"""
from readyproof.demos.builder import build_scenario as build
from readyproof.intake import (TEMPLATES, UNKNOWN, build_requirements, suggest_template, transcript,
                               visible_questions)
from readyproof.logic import rules
from readyproof.logic.evidence import context_rows
from readyproof.logic.rules import missing_terms


def test_suggest_template_from_project_words():
    assert suggest_template("経費精算サービスの導入") == "approval"
    assert suggest_template("", "退職者のアカウント停止") == "account"
    assert suggest_template("生産管理", "ロットトレーサビリティ") == "lot"
    assert suggest_template("会議室予約") == "general"


def test_conditional_questions():
    assert "threshold" not in [q["id"] for q in visible_questions("approval", {"by_amount": "いいえ"})]
    assert "threshold" in [q["id"] for q in visible_questions("approval", {"by_amount": "はい"})]


def test_approval_answers_keep_amount_and_boundary(project):
    ans = {"business": "経費申請の承認", "by_amount": "はい", "threshold": 10000.0,
           "boundary": TEMPLATES["approval"]["questions"][3]["options"][0], "lower": "直属の上司",
           "upper": "直属の上司 → 部長", "self": "禁止", "proxy": "代理の人が承認する（条件はまだ決まっていない）"}
    reqs = build_requirements("approval", ans)
    rules_text = [r["rules"] for r in reqs]
    assert "10,000円未満は直属の上司が承認する。10,000円以上は直属の上司 → 部長の順に承認する。" in rules_text
    assert any("自己承認）は禁止" in t for t in rules_text)
    proxy = next(r for r in reqs if r["business"] == "代理承認")
    assert proxy["open_issues"] and proxy["priority"] == "望ましい"
    # 回答の原文が残り、登録すると下書きになる
    assert "答：10000" in reqs[0]["original_text"]
    made = rules.add_requirement(project, reqs[0], origin="質問形式")
    assert made["status"] == "下書き" and made["origin"] == "質問形式"


def test_unknown_is_not_guessed():
    ans = {"by_amount": "はい", "threshold": UNKNOWN, "boundary": UNKNOWN, "lower": "上司", "upper": "部長",
           "self": UNKNOWN, "proxy": UNKNOWN}
    reqs = build_requirements("approval", ans)
    amount = reqs[0]
    assert "未定" in amount["rules"] and "円以上" not in amount["rules"] and "円未満" not in amount["rules"]
    assert "境目の金額が未定" in amount["open_issues"] and "どちらの承認" in amount["open_issues"]
    assert all(r["open_issues"] for r in reqs[1:])
    acc = build_requirements("account", {"timing": UNKNOWN, "log_years": UNKNOWN})
    assert any("期間は未定" in r["rules"] for r in acc) and not any("年以上" in r["rules"] for r in acc)
    lot = build_requirements("lot", {"direction": "両方", "max_lots": UNKNOWN, "offline": "ある", "correction": UNKNOWN})
    assert any("最大件数は未定" in r["rules"] for r in lot)


def test_numbers_survive_term_check():
    reqs = build_requirements("account", {"timing": "退職日の0時に自動で止める", "operator": "管理者", "log_years": 3.0})
    log = next(r for r in reqs if r["business"] == "操作履歴")
    assert log["rules"] == "管理者の操作履歴を3年以上保持すること。"
    assert "答：3" in transcript("account", {"log_years": 3.0})
    assert missing_terms("3年以上", log) == []


def test_context_rows_highlight_target():
    p = build("demo1")
    dg = rules.current_diagnosis(p, "REQ-001")
    ev = next(e for e in dg["evidence"] if "10,000円以上" in e["quote"])
    rows = context_rows(p, ev)
    hit = [r for r in rows if r["target"]]
    assert len(hit) == 1 and ev["quote"] in hit[0]["text"]
    assert len(rows) >= 3  # 同じスライドの前後の行も見せる（表の見出し行など）
    p3 = build("demo3")
    ev3 = next(e for e in rules.current_diagnosis(p3, "REQ-001")["evidence"] if e["ref_type"] == "utterance")
    rows3 = context_rows(p3, ev3)
    assert any("自社担当者" in r["loc"] for r in rows3)  # 直前の質問も一緒に見える
