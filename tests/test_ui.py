"""画面（Streamlit AppTest）。ブラウザは使わず、画面の描画と主要操作を確認する。"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from readyproof.config import TAGLINE
from readyproof.demos.builder import build

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
    assert "デモのため" in texts(at)
    assert not [b for b in at.button if "AI" in b.label]
    at = page("tests", p)
    assert not [b for b in at.button if "AI" in b.label]
    at = page("input2", p)
    assert not at.exception and "デモのため" in texts(at)
    assert not [b for b in at.button if b.label in ("確定", "編集", "登録")]
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
