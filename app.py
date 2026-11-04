"""ReadyProof AI（AI受入テスト・導入確認支援システム）起動ファイル。

起動：streamlit run app.py
"""
import os

import streamlit as st

from readyproof.config import APP_NAME_EN
from readyproof.ui import state
from readyproof.ui.pages import (data_page, decision, diagnosis, home, project_page, questions, requirements,
                                 settings_page, sources, tests)
from readyproof.ui.theme import inject_css

st.set_page_config(page_title=APP_NAME_EN, page_icon=":material/fact_check:", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()
_ASSETS = os.path.join(os.path.dirname(__file__), "readyproof", "ui", "assets")
st.logo(os.path.join(_ASSETS, "logo.svg"), size="large", icon_image=os.path.join(_ASSETS, "icon.svg"))

P = st.Page
pages = {
    "home": P(home.render, title="ホーム", icon=":material/home:", url_path="home", default=True),
    "project": P(project_page.render, title="案件・製品", icon=":material/business_center:", url_path="project"),
    "sources": P(sources.render, title="1 製品の資料・営業説明", icon=":material/description:", url_path="sources"),
    "requirements": P(requirements.render, title="2 自社の仕事・ルール", icon=":material/rule:", url_path="requirements"),
    "diagnosis": P(diagnosis.render, title="3 自社に合うかを確認", icon=":material/fact_check:", url_path="diagnosis"),
    "questions": P(questions.render, title="4 質問・対応依頼", icon=":material/forum:", url_path="questions"),
    "tests": P(tests.render, title="5 試すこと・実施結果", icon=":material/science:", url_path="tests"),
    "decision": P(decision.render, title="6 残った問題と導入判断", icon=":material/gavel:", url_path="decision"),
    "data": P(data_page.render, title="保存・Excel出力", icon=":material/save:", url_path="data"),
    "settings": P(settings_page.render, title="設定・利用枠", icon=":material/tune:", url_path="settings"),
}
state.PAGES.update(pages)

nav = st.navigation({
    "": [pages["home"]],
    "作業": [pages[k] for k in ("project", "sources", "requirements", "diagnosis", "questions", "tests", "decision")],
    "管理": [pages["data"], pages["settings"]],
})

with st.sidebar:
    st.text_input("作業者名（自己申告）", key="user_name", placeholder="例：情報システム部 田中",
                  help="確定・確認・実施の記録に残ります。認証はないため、本人確認や正式な承認ではありません。")
    p = state.project()
    if p:
        st.caption("編集内容はこの画面を開いている間だけ保持されます。続きから使うときは「保存・Excel出力」で保存してください。")

state.show_flash()
nav.run()
