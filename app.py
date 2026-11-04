"""ReadyProof AI（AI受入テスト・導入確認支援システム）起動ファイル。

起動：streamlit run app.py
"""
import os

import streamlit as st

from readyproof.ai.client import get_api_key
from readyproof.config import APP_NAME_EN
from readyproof.ui import state
from readyproof.ui.pages import home, settings_page, step1, step2, step3, step4, step5
from readyproof.ui.theme import inject_css

st.set_page_config(page_title=APP_NAME_EN, page_icon=":material/fact_check:", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()
_ASSETS = os.path.join(os.path.dirname(__file__), "readyproof", "ui", "assets")
st.logo(os.path.join(_ASSETS, "logo.svg"), size="large", icon_image=os.path.join(_ASSETS, "icon.svg"))

P = st.Page
pages = {
    "home": P(home.render, title="ホーム", icon=":material/home:", url_path="home", default=True),
    "input1": P(step1.render, title="① 製品の資料", icon=":material/description:", url_path="product"),
    "input2": P(step2.render, title="② 自社のルール", icon=":material/rule:", url_path="rules"),
    "result": P(step3.render, title="③ 診断結果", icon=":material/fact_check:", url_path="result"),
    "tests": P(step4.render, title="④ 受入テスト", icon=":material/task_alt:", url_path="tests"),
    "decision": P(step5.render, title="⑤ 導入判断", icon=":material/gavel:", url_path="decision"),
    "settings": P(settings_page.render, title="設定・利用枠", icon=":material/tune:", url_path="settings"),
}
state.PAGES.update(pages)
state.restore()  # 接続が切れて新しい画面になった場合、URLの識別子から作業を復元する

sections = {"": [pages["home"]],
            "導入確認の流れ": [pages[k] for k in ("input1", "input2", "result", "tests", "decision")]}
# 設定・利用枠は運用者向け（有料AIを使う場合だけ必要）。APIキーがない公開版では表示しない
if get_api_key():
    sections["管理"] = [pages["settings"]]
nav = st.navigation(sections)

state.show_flash()
nav.run()
state.persist()
