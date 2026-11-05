"""画面（Streamlit AppTest）。ブラウザは使わず、画面の描画と主要操作を確認する。"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from readyproof.config import TAGLINE
from readyproof.demos.builder import build_scenario as build

HARNESS = os.path.join(os.path.dirname(__file__), "ui_harness.py")
APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")
PAGES = ["home", "input1", "input2", "result", "tests", "decision", "settings"]


def page(name, project=None, **state):
    at = AppTest.from_file(HARNESS, default_timeout=120)
    if project is not None:
        at.session_state["project"] = project
    at.session_state["_page"] = name
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def texts(at):
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
                     + [w.value for w in at.warning] + [e.value for e in at.error])


@pytest.mark.parametrize("demo", ["demo1", "demo2", "demo3", None])
def test_all_pages_render(demo):
    for name in PAGES:
        at = page(name, build(demo) if demo else None)
        assert not at.exception, (demo, name, [e.value for e in at.exception])


def test_home_shows_tagline_and_demos():
    at = AppTest.from_file(APP, default_timeout=120).run()
    t = texts(at)
    assert TAGLINE.replace("「", "").split("」")[0][:8] in t.replace("「", "")
    assert "ReadyProof" in t and "AI受入テスト・導入確認支援システム" in t
    assert "3分デモを始める" in [b.label for b in at.button]
    assert len(at.selectbox(key="demo_pick").options) == 3


def test_open_demo_from_home():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.selectbox(key="demo_pick").set_value("demo2")
    at.button(key="open_main").click().run()
    assert not at.exception
    assert at.session_state["project"]["project"]["demo_id"] == "demo2"


def test_demo_is_view_only():
    """デモは見るだけ：AIの実行・資料の追加・要件の確定や編集はできない。"""
    p = build("demo1")
    at = page("result", p, rediag=True)
    assert not at.exception
    assert not [b for b in at.button if "AI" in b.label]
    at = page("tests", p)
    assert not [b for b in at.button if "AI" in b.label]
    at = page("input2", p)
    assert not at.exception
    decide = [b for b in at.button if b.label in ("確定", "編集", "登録")]
    assert decide and all(b.disabled for b in decide)  # 押せない状態で表示
    assert not at.toggle
    at = page("input1", p, open_item=("src", p["sources"][0]["id"]))
    assert not at.exception
    assert not [b for b in at.button if b.label in ("読み込む", "変更を反映", "保存")]


def test_no_api_key_explains_and_manual_still_works():
    from readyproof.core import new_project

    p = new_project("手動案件")
    at = page("input2", p)
    assert not at.exception
    at = page("settings", p)
    assert "APIキーが設定されていません" in texts(at)


def test_pass_without_confirmed_expected_blocked_in_ui():
    p = build("demo3")  # T-002 は期待結果が未確定の下書き
    at = page("tests", p, sel_test="T-002", user_name="テスト実施者")  # ④ 受入テストでT-002を開いた状態
    at.selectbox[[s.label for s in at.selectbox].index("合否")].set_value("合格")
    at.text_area[[t.label for t in at.text_area].index("実際の結果（何が起きたか）")].set_value("ログインできなかった")
    at.button[[b.label for b in at.button].index("記録する")].click().run()
    assert any("期待結果が確定していない" in e.value for e in at.error)
    assert not [r for r in at.session_state["project"]["runs"] if r["test_id"] == "T-002"]


def test_sidebar_has_no_save_or_upload():
    """サイドバーには作業の保存・読込を置かない（作業はURLの識別子で自動復元する）。"""
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["project"] = build("demo1")
    at.run()
    assert not at.exception
    assert not at.sidebar.get("download_button") and not at.sidebar.get("file_uploader")
    assert at.session_state["project"]["project"]["demo_id"] == "demo1"


def test_status_not_color_only():
    """状態ラベルは色だけでなく文字を持つ。"""
    from readyproof.ui.theme import category_chip, chip, review_chip

    assert "情報不足" in category_chip("情報不足・ベンダー確認が必要")
    assert "AIの下書き・未確認" in review_chip("未確認", "AI生成")
    assert "&lt;script&gt;" in chip("<script>")  # HTML はエスケープ
    assert "[" not in chip("a]b[c").split("[", 1)[1].rsplit("]", 1)[0]  # バッジ記法を壊す文字を置き換える


def test_own_project_asks_ai_password(monkeypatch, tmp_path):
    """自分の案件では、AIパスワードを入れたときだけAIを実行できる。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-used")
    monkeypatch.setenv("RP_ACCESS_CODES", "secret-pw")
    monkeypatch.setenv("RP_USAGE_STORE_PERSISTENT", "true")
    monkeypatch.setenv("RP_USAGE_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    p = build("demo1")
    p["project"]["demo_id"] = None  # 自分の案件として扱う
    p["diagnoses"] = []
    at = page("result", p)
    assert not at.exception
    assert at.text_input(key="ai_pw_diag_AIで診断する").label == "AIパスワード"
    assert not [b for b in at.button if b.label == "AIで診断する"]
    at.text_input(key="ai_pw_diag_AIで診断する").input("wrong").run()
    assert "AIパスワードが正しくありません" in texts(at)
    at.text_input(key="ai_pw_diag_AIで診断する").input("secret-pw").run()
    assert [b for b in at.button if b.label == "AIで診断する"]


def test_demo_decision_widgets_disabled_but_own_project_enabled():
    """デモ：確認・確定・保存・記録・判断の部品はすべて非活性。自分の案件では使える。"""
    from readyproof.demos.builder import build as build_screen

    p = build_screen("demo1")
    t = p["tests"][0]["id"]
    r = next(x["id"] for x in p["requirements"] if x["status"] == "確定")
    nav_keys = ("fr_", "na_", "to_rule_", "rq_", "next_")  # 詳細の開閉・絞り込み・移動はデモでも使う
    cases = [("tests", {"sel_test": t}), ("decision", {})]
    cases += [("result", {"focus_req": r, f"dtab_{r}": tab}) for tab in ("main", "evidence", "log", "act")]
    for pg, extra in cases:
        at = page(pg, p, **extra)
        assert not at.exception
        widgets = list(at.button) + list(at.text_input) + list(at.text_area) + list(at.selectbox) + list(at.radio) + list(at.checkbox)
        decide = [w for w in widgets if not str(getattr(w, "key", "") or "").startswith(nav_keys)
                  and getattr(w, "label", "") not in ("詳しく確認する", "閉じる", "詳しく見る")
                  and not getattr(w, "label", "").startswith(("次へ", "デモはここまで"))
                  and not getattr(w, "label", "").endswith("の画面へ移動")]
        if pg != "result" or extra[f"dtab_{r}"] != "main":  # 「診断と対応」は読むだけの面で、決定の部品がない
            assert decide, (pg, extra)
        assert all(w.disabled for w in decide), (pg, [w.label for w in decide if not w.disabled])
    p["project"]["demo_id"] = None  # 自分の案件
    at = page("tests", p, sel_test=t)
    assert [b for b in at.button if b.label == "記録する" and not b.disabled]


def test_create_own_project_requires_ai_password(monkeypatch):
    """自分の案件の作成は、AIパスワードが正しいときだけ押せる。"""
    monkeypatch.setenv("RP_ACCESS_CODES", "secret-pw")
    at = page("home", None)
    at.text_input(key="new_project_name").input("勤怠管理の導入").run()
    create = lambda: next(b for b in at.button if b.label == "作成する")
    assert create().disabled
    at.text_input(key="home_ai_pw").input("wrong").run()
    assert create().disabled and "AIパスワードが正しくありません" in texts(at)
    at.text_input(key="home_ai_pw").input("secret-pw").run()
    assert not create().disabled


def test_recording_decision_shows_completion_message():
    """導入判断を記録すると、導入確認が完了したことを伝える。"""
    from readyproof.demos.builder import build as build_screen

    p = build_screen("demo3")
    p["project"]["demo_id"] = None  # 自分の案件として
    at = page("decision", p)
    at.text_area[0].input("書面回答で解消し、全テストに合格した。").run()
    next(b for b in at.button if b.label == "判断を記録").click().run()
    assert not at.exception
    assert any("導入確認が完了しました" in s.value for s in at.success)


def test_ai_interview_answers_one_by_one():
    """AIの聞き取り：1問ずつ答え、「分からない・未定」も選べ、最後に回答の一覧が出る。"""
    p = build("demo1")
    p["project"]["demo_id"] = None  # 自分の案件として
    qs = [{"topic": "金額", "question": "部長の承認が必要になる金額は？", "why": "資料に金額条件の設定がある",
           "answer_type": "number", "options": []},
          {"topic": "境目", "question": "ちょうどの金額は部長の承認が必要？", "why": "", "answer_type": "choice",
           "options": ["必要", "不要"]}]
    at = page("input2", p, show_intake=True, aiq={"questions": qs, "answers": {}, "i": 0})
    assert not at.exception
    assert "部長の承認が必要になる金額は？" in texts(at) and "なぜ聞くか" in texts(at)
    assert at.number_input(key="aiq_0") and at.checkbox(key="aiq_0_unk").label == "分からない・未定"
    at = page("input2", p, show_intake=True, aiq={"questions": qs, "answers": {0: 10000}, "i": 1})
    assert "分からない・未定" in at.radio(key="aiq_1").options  # 選択式にも必ず付く
    at = page("input2", p, show_intake=True, aiq={"questions": qs, "answers": {0: 10000, 1: "分からない・未定"}, "i": 2})
    assert not at.exception
    t = texts(at)
    assert "回答から要件の下書きを作る" in t and "10000" in t and "分からない・未定" in t


def test_result_page_layers_and_controls():
    """③：最初は結論だけ。詳細は開いたときだけ。絞り込み・面の切り替えはデモでも使え、根拠7件を確認できる。"""
    from readyproof.demos.builder import build as build_screen

    p = build_screen("demo1")
    at = page("result", p)
    assert not at.exception
    t = texts(at)
    assert "必須要件2件は、製品の設定で対応できる見込みです" in t and "次にやるべきこと" in t
    assert "9/9件" in t and "未診断" in t
    assert "承認ルート設定" not in t.split("要件ごとの診断")[0]  # サマリーに根拠原文を出さない
    assert not [b for b in at.button if b.label == "閉じる"]  # 最初はすべて閉じている
    group = at.button_group(key="rq_filter")
    assert not group.disabled and "対応可能な見込み（2）" in group.options and "未診断（1）" in group.options
    at = page("result", p, focus_req="REQ-001", **{"dtab_REQ-001": "evidence"})
    assert not at.exception
    t = texts(at)
    assert "AIの要約ではありません" in t and t.count("ベンダー回答") >= 2
    at = page("result", p, focus_req="REQ-001", **{"dtab_REQ-001": "log"})
    t = texts(at)
    assert "Q-001" in t and "Q-002" in t and "部門長" in t  # 質問と実際の回答
    assert "実機で動作を確かめたことにはなりません" in t
    at = page("result", p, focus_req="REQ-003")
    assert not at.exception and "要件が未確定のため、診断していません" in texts(at)


def test_next_action_opens_page_and_filter_resets_on_jump():
    from readyproof.demos.builder import build as build_screen

    p = build_screen("demo1")
    at = page("result", p, rq_filter="check", _rq_jump=True, focus_req="REQ-001")
    assert not at.exception
    assert [b for b in at.button if b.label == "閉じる"]  # 絞り込みで隠れず、指定の要件が開く
    at = page("result", p, rq_filter="hard")
    assert "条件に合う要件はありません" in texts(at)


def test_update_from_answer_keeps_test_conditions():
    """回答からの更新候補で「実機テストで確認すること」を失わず、③ で対象の要件を開く。"""
    from readyproof.demos.builder import build as build_screen
    from readyproof.logic.rules import current_diagnosis

    p = build_screen("demo1")
    p["project"]["demo_id"] = None  # 自分の案件として
    before = current_diagnosis(p, "REQ-001")["test_conditions"]
    assert before
    at = page("result", p, focus_req="REQ-001", **{"dtab_REQ-001": "log"})
    at.button(key="upd_Q-001").click().run()
    assert not at.exception
    pj = at.session_state["project"]
    assert current_diagnosis(pj, "REQ-001")["test_conditions"] == before
    assert at.session_state["focus_req"] == "REQ-001"


def test_demo_restore_shows_no_notice(tmp_path):
    """デモを復元しても「接続が切れた」の案内を出さない。自分の案件では出す。"""
    import json
    import uuid

    from readyproof.export.jsonio import to_json_bytes
    from readyproof.ui import state as ui_state

    os_dir = ui_state._SESS_DIR
    import os
    os.makedirs(os_dir, exist_ok=True)
    for demo_id, notice in (("demo1", False), (None, True)):
        p = build("demo1")
        p["project"]["demo_id"] = demo_id
        sid = uuid.uuid4().hex
        path = os.path.join(os_dir, sid + ".json")
        with open(path, "wb") as f:
            f.write(to_json_bytes(p))
        try:
            at = AppTest.from_file(APP, default_timeout=120)
            at.query_params["s"] = sid
            at.run()
            assert not at.exception
            assert at.session_state["project"]["project"]["demo_id"] == demo_id
            assert ("作業を自動で復元しました" in texts(at)) is notice
        finally:
            if os.path.exists(path):
                os.remove(path)
