"""BL-001 案B：AIの聞き取り（製品資料を踏まえて質問を作り、回答から要件の下書きを作る）。FakeAI を使い、有料APIは呼ばない。"""
from readyproof.ai.client import FakeAI
from readyproof.ai.tasks import (UNKNOWN_ANSWER, build_interview_input, interview_split_prompt, interview_transcript,
                                 run_interview, run_interview_split)


def test_interview_input_sends_only_selected_product_text(deck_project):
    """未選択の箇所（発表者ノートなど）は送らない。分析の対象に選んだ箇所と、聞き取る業務は送る。"""
    p, src = deck_project
    prompt = build_interview_input(p, "経費の申請・承認", "PR-001")
    assert "経費の申請・承認" in prompt and "テスト製品" in prompt
    sel = [g for g in src["segments"] if g.get("selected")]
    unsel = [g for g in src["segments"] if not g.get("selected")]
    assert sel and unsel
    assert sel[0]["text"] in prompt
    for g in unsel:
        assert g["text"] not in prompt
    assert "誘導しないでください" in prompt  # 製品に合わせて答えさせない


def test_run_interview_normalizes_questions(deck_project, settings):
    p, _ = deck_project
    ai = FakeAI({"interview": {"questions": [
        {"topic": "金額の境目", "question": "部長の承認が必要になる金額はいくらからですか。", "why": "資料に金額条件の設定がある",
         "answer_type": "number", "options": []},
        {"topic": "境目の扱い", "question": "ちょうどの金額は、部長の承認が必要ですか。", "why": "以上・超の設定がある",
         "answer_type": "choice", "options": ["必要", "不要", UNKNOWN_ANSWER]},
        {"topic": "例外", "question": "例外はありますか。", "why": "", "answer_type": "choice", "options": ["ある"]},
        {"topic": "空", "question": "  ", "why": "", "answer_type": "text", "options": []},
    ]}})
    qs = run_interview(p, "経費の申請・承認", "PR-001", ai, settings)
    assert len(qs) == 3  # 空の質問は除く
    assert qs[1]["options"] == ["必要", "不要"]  # 「分からない・未定」は画面で必ず足すので、AIの分は除く
    assert qs[2]["answer_type"] == "text"  # 選択肢が1つしかない選択式は自由記述にする
    assert ai.calls[0]["task"] == "interview"


def test_transcript_and_split_keep_unknown_as_open_issue(deck_project, settings):
    p, _ = deck_project
    qs = [{"question": "部長の承認が必要になる金額はいくらからですか。", "answer_type": "number", "unit": "円"},
          {"question": "代理承認の条件は決まっていますか。"},
          {"question": "回答していない質問"}]
    text = interview_transcript(qs, {0: 10000, 1: UNKNOWN_ANSWER})
    assert "回答：10000円" in text and f"回答：{UNKNOWN_ANSWER}" in text  # 数値には単位を付ける
    assert "回答していない質問" not in text
    assert "推測で埋めずに open_issues" in interview_split_prompt(text)
    ai = FakeAI({"split_requirements": {"requirements": [{
        "business": "経費申請の承認", "workflow": "金額で承認者を変える", "role": "上司・部長",
        "rules": "10000円以上は部長が承認する", "exceptions": "", "inputs": "", "outputs": "", "priority": "必須",
        "reason": "", "open_issues": "未定：代理承認の条件",
        "original_text": "質問：部長の承認が必要になる金額はいくらからですか。\n回答：10000"}]}})
    made = run_interview_split(p, text, ai, settings)
    assert len(made) == 1
    r = made[0]
    assert r["status"] == "下書き" and r["origin"] == "AIの聞き取り"  # AIは要件を確定しない
    assert "代理承認" in r["open_issues"]
    assert not any("見つかりません" in w for w in r.get("term_warnings", []))  # 引用は聞き取りの記録に実在する
