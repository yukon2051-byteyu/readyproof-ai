"""AppTest 用：session_state["_page"] で指定した画面だけを描画する起動ファイル（テスト専用）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from readyproof.ui import state  # noqa: E402
from readyproof.ui.pages import (data_page, decision, diagnosis, home, project_page, questions,  # noqa: E402
                                 requirements, settings_page, sources, tests)
from readyproof.ui.theme import inject_css  # noqa: E402

PAGES = {"home": home, "project": project_page, "sources": sources, "requirements": requirements,
         "diagnosis": diagnosis, "questions": questions, "tests": tests, "decision": decision,
         "data": data_page, "settings": settings_page}
inject_css()
state.show_flash()
PAGES[st.session_state.get("_page", "home")].render()
