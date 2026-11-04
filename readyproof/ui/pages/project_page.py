"""案件・製品の登録。"""
from __future__ import annotations

import streamlit as st

from ...core import log, primary_product
from .. import state
from ..theme import section
from ..components import context_bar, page_title


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("")
    page_title("案件・製品", "最初の版は1案件1候補製品を扱います。根拠（資料・録画）はこの製品に関連付けられます。")
    pj = p["project"]
    with st.form("form_project"):
        section("案件")
        c1, c2 = st.columns([1, 3])
        c1.text_input("案件ID", value=pj["id"], disabled=True)
        name = c2.text_input("案件名", value=pj["name"])
        c1, c2 = st.columns(2)
        target = c1.text_input("対象業務", value=pj["target_business"], placeholder="例：経費の申請・承認")
        dept = c2.text_input("担当部門", value=pj["department"])
        purpose = st.text_area("導入目的", value=pj["purpose"], height=70)
        constraints = st.text_area("制約条件", value=pj["constraints"], height=70,
                                   placeholder="例：予算、稼働時期、使える端末、社内規程を変更しない など")
        prod = primary_product(p) or {"id": "PR-001", "name": "", "vendor": "", "plan": "", "edition": "",
                                       "delivery": "SaaS", "as_of": "", "notes": ""}
        section("候補製品")
        c1, c2, c3 = st.columns([1, 2, 2])
        c1.text_input("製品ID", value=prod["id"], disabled=True)
        pname = c2.text_input("製品名", value=prod["name"])
        vendor = c3.text_input("ベンダー名", value=prod["vendor"])
        c1, c2, c3, c4 = st.columns(4)
        plan = c1.text_input("対象プラン", value=prod["plan"], help="プランが変わると、関連する診断は「再確認が必要」になります。")
        edition = c2.text_input("版（バージョン）", value=prod["edition"])
        options = ["SaaS", "オンプレミス", "クラウド（IaaS上に構築）", "個別開発", "その他"]
        delivery = c3.selectbox("提供形態", options,
                                index=options.index(prod["delivery"]) if prod["delivery"] in options else 0)
        as_of = c4.text_input("検討時点", value=prod["as_of"], placeholder="例：2026-11")
        notes = st.text_area("補足", value=prod["notes"], height=60)
        if st.form_submit_button("保存", type="primary"):
            if not name.strip():
                st.error("案件名を入力してください。")
            else:
                pj.update({"name": name.strip(), "target_business": target, "department": dept, "purpose": purpose,
                           "constraints": constraints})
                newp = {"id": prod["id"], "name": pname, "vendor": vendor, "plan": plan, "edition": edition,
                        "delivery": delivery, "as_of": as_of, "notes": notes}
                if p["products"]:
                    p["products"][0].update(newp)
                elif pname.strip():
                    p["products"].append(newp)
                    p["id_counters"]["products"] = 1
                log(p, "案件・製品の更新", pj["id"], state.user_name())
                st.success("保存しました。")
    if p["products"] and st.button("次へ：製品の資料・営業説明を登録", icon=":material/arrow_forward:"):
        state.goto("sources")
