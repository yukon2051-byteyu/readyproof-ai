"""AppTest 用：session_state["_page"] で指定した画面だけを描画する起動ファイル（テスト専用）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from readyproof.ui import state  # noqa: E402
from readyproof.ui.pages import home, settings_page, step1, step2, step3, step4, step5  # noqa: E402
from readyproof.ui.theme import inject_css  # noqa: E402

PAGES = {"home": home, "input1": step1, "input2": step2, "result": step3, "tests": step4, "decision": step5,
         "settings": settings_page}
inject_css()
state.show_flash()
PAGES[st.session_state.get("_page", "home")].render()
