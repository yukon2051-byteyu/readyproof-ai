"""ReadyProof AI（AI受入テスト・導入確認支援システム）起動ファイル。

起動：streamlit run app.py
"""
import os

import streamlit as st

from readyproof.ai.client import get_api_key
from readyproof.config import APP_NAME_EN
from readyproof.ui import state
from readyproof.ui.pages import data_page, home, settings_page, step1, step2, step3, step4
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
    "data": P(data_page.render, title="保存・Excel出力", icon=":material/save:", url_path="data"),
    "settings": P(settings_page.render, title="設定・利用枠", icon=":material/tune:", url_path="settings"),
}
state.PAGES.update(pages)

nav = st.navigation({
    "": [pages["home"]],
    "導入確認の流れ": [pages[k] for k in ("input1", "input2", "result", "tests")],
    # 設定・利用枠は運用者向け（有料AIを使う場合だけ必要）。APIキーがない公開版では表示しない
    "管理": [pages["data"]] + ([pages["settings"]] if get_api_key() else []),
})

with st.sidebar:
    st.text_input("作業者名（自己申告）", key="user_name", placeholder="例：情報システム部 田中",
                  help="確定・確認・実施の記録に残ります。認証はないため、本人確認や正式な承認ではありません。")
    p = state.project()
    if p:
        st.caption("編集内容はこの画面を開いている間だけ保持されます。続きから使うときは「保存・Excel出力」で保存してください。")

state.show_flash()
nav.run()
