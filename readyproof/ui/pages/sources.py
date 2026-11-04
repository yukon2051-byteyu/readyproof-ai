"""1 製品の資料・営業説明（資料の登録と確認）。録画は recordings_view.py。"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from ...core import SOURCE_KINDS, SOURCE_STATUS, log
from ...ingest import IngestError, ingest_bytes, ingest_text
from ...logic import rules
from .. import state
from ..components import context_bar, page_title
from ..theme import chip, esc, box
from . import recordings_view

VIEWS = ["資料を登録", "資料の確認", "録画を登録", "発言の確認"]
STATUS_TONE = {"ok": ("読込完了", "ok"), "partial": ("一部未読込", "warn"), "empty": ("文字なし", "bad"),
               "failed": ("読込失敗", "bad")}


def render():
    p = state.require_project()
    if not p:
        return
    context_bar("sources")
    page_title("1 製品の資料・営業説明",
               "製品の資料や営業説明の録画を登録し、読めた範囲・分析対象・発言を確認します。未確認の部分はAIに送りません。")
    if "_goto_view" in st.session_state:  # 他の操作からの表示切替（部品を描く前に反映）
        st.session_state.src_view = st.session_state.pop("_goto_view")
    view = st.segmented_control("表示", VIEWS, key="src_view", default=VIEWS[0], label_visibility="collapsed")
    view = view or VIEWS[0]
    if view == VIEWS[0]:
        register(p)
    elif view == VIEWS[1]:
        review(p)
    elif view == VIEWS[2]:
        recordings_view.register(p)
    else:
        recordings_view.review(p)


# ------------------------------------------------------------------
def register(p):
    s = state.settings()
    lim = s.limits
    with box():
        c1, c2, c3 = st.columns([1, 1, 2])
        owner = c1.radio("資料の区分", ["製品", "自社"], horizontal=True,
                         format_func=lambda x: "製品の資料" if x == "製品" else "自社の手順書・規程",
                         help="自社の手順書・規程も同じ読込機能で読めます。製品の資料とは分けて扱います。")
        kind = c2.selectbox("資料の種類", SOURCE_KINDS)
        existing = ["新しい資料として登録"] + sorted({f"{x['id']}：{x['name']}" for x in p["sources"]})
        base = c3.selectbox("版", existing, help="既存の資料の新しい版として登録すると、旧版は「旧版」になります。")
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("資料名（空欄ならファイル名）")
        issued = c2.text_input("発行日", placeholder="2026-10-01")
        received = c3.text_input("受領日", placeholder="2026-10-10")
        plan = c4.text_input("対象プラン・版", placeholder="例：スタンダード")
        files = st.file_uploader(
            f"ファイル（PDF・.docx・.xlsx・.pptx・.txt／最大{lim.max_files_per_upload}件・各{lim.max_file_mb}MB）",
            type=["pdf", "docx", "xlsx", "pptx", "txt", "doc", "xls", "ppt"], accept_multiple_files=True,
            key="src_files")
        pasted = st.text_area("または文章を直接貼り付け（段落ごとに位置を付けます）", height=100, key="src_paste")
        st.caption("画像のみのPDF（OCR）、画像・図の内容理解には対応していません。元ファイルは保存せず、抽出した文字と位置だけを保持します。")
        if st.button("読み込む", type="primary", icon=":material/upload:", disabled=not (files or pasted.strip())):
            if files and len(files) > lim.max_files_per_upload:
                st.error(f"一度に登録できるのは{lim.max_files_per_upload}件までです。")
                return
            new_ver = None if base.startswith("新しい") else base.split("：")[0]
            meta = {"owner": owner, "kind": kind, "issued_on": issued, "received_on": received, "plan": plan,
                    "product_id": state.product_id()}
            results = []
            for f in files or []:
                try:
                    res = ingest_bytes(f.name, f.getvalue(), lim)
                except IngestError as e:
                    results.append(("error", f.name, str(e)))
                    continue
                src = rules.add_source(p, res.to_dict(), {**meta, "file_name": f.name,
                                                          "name": name if (name and len(files) == 1) else os.path.splitext(f.name)[0]},
                                       new_version_of=new_ver)
                results.append(("ok", f.name, src))
            if pasted.strip():
                try:
                    res = ingest_text(pasted, lim)
                    src = rules.add_source(p, res.to_dict(), {**meta, "file_name": "（貼り付け）",
                                                              "name": name or "貼り付けた文章"}, new_version_of=new_ver)
                    results.append(("ok", "貼り付け", src))
                except IngestError as e:
                    results.append(("error", "貼り付け", str(e)))
            for kind_, fname, x in results:
                if kind_ == "error":
                    st.error(f"{fname}：{x}")
                else:
                    label, tone = STATUS_TONE[x["extract_status"]]
                    st.markdown(f"{chip(label, tone)} {esc(fname)} → {esc(x['id'])} 第{x['version']}版："
                                f"{len(x['segments'])}箇所を抽出、警告{len(x['warnings'])}件", unsafe_allow_html=True)
            if any(k == "ok" for k, _, _ in results):
                st.info("「資料の確認」で、抽出結果・警告・分析対象を確認してください。")


# ------------------------------------------------------------------
def review(p, src_fixed: dict | None = None):
    if not p["sources"]:
        st.info("資料がまだありません。「資料を登録」から読み込んでください。")
        return
    opts = {f"{x['id']} 第{x['version']}版：{x['name']}（{x['owner']}・{x['status']}）": i for i, x in enumerate(p["sources"])}
    c1, c2 = st.columns([3, 2])
    if src_fixed is not None:
        src = src_fixed
        c1.markdown(f"**{esc(src['name'])}**（{esc(src['id'])} 第{src['version']}版）")
    else:
        key = c1.selectbox("確認する資料", list(opts.keys()), key="sel_src")
        src = p["sources"][opts[key]]
    cov = src.get("coverage", {})
    groups = [g for g in dict.fromkeys(seg.get("group") or "（全体）" for seg in src["segments"])]
    slide_info = {f"スライド{x['slide']}": x for x in cov.get("slides", [])}
    gsel = c2.selectbox("表示する範囲（スライド・ページ・シート）", ["すべて"] + groups, key=f"sel_grp_{src['id']}")
    label, tone = STATUS_TONE[src["extract_status"]]
    sel_n = sum(1 for g in src["segments"] if g.get("selected"))
    n_warn = len(src.get("warnings", [])) + (1 if cov.get("skipped") else 0)
    st.markdown(f"{chip(label, tone)}" + (chip(f"注意 {n_warn}件", "warn") if n_warn else "")
                + f"<span class='rp-small'>読込 {esc(cov.get('read'))}/{esc(cov.get('total'))}{esc(cov.get('unit', ''))}"
                f"・分析の対象 {sel_n}/{len(src['segments'])}箇所</span>", unsafe_allow_html=True)
    if gsel in slide_info:
        si = slide_info[gsel]
        parts = [f"タイトル：{si['title']}"]
        if si["hidden"]:
            parts.append("非表示スライド")
        if si["unknown"]:
            parts.append("理解していない要素：" + "、".join(f"{k}{v}件" for k, v in si["unknown"].items()))
        if si["has_note"]:
            parts.append("発表者ノートあり（初期状態で対象外）")
        st.caption("／".join(parts))
    segs = [g for g in src["segments"] if gsel == "すべて" or (g.get("group") or "（全体）") == gsel]
    if not segs:
        st.info("この範囲には抽出された文字がありません。")
        return
    df = pd.DataFrame([{
        "対象": bool(g.get("selected")), "ID": g["seg_id"], "位置": g["loc_label"], "種類": g["kind"],
        "本文（原文）": g["text"] if not g.get("text_omitted") else "（本文は保存されていません）",
        "ノート確認済み": bool(g.get("note_reviewed")) if g.get("is_note") else None,
        "補足": g.get("user_note", ""),
    } for g in segs])
    st.caption("「対象」を外した箇所は、照合とAIに使いません。発表者ノートは内容を確認してから対象にします。")
    ro = state.is_demo()
    edited = st.data_editor(
        df, key=f"ed_segs_{src['id']}_{src['version']}_{gsel}", hide_index=True, width="stretch",
        disabled=True if ro else ["ID", "位置", "種類", "本文（原文）"],
        column_config={
            "対象": st.column_config.CheckboxColumn(width="small"),
            "ID": st.column_config.TextColumn(width="small"),
            "本文（原文）": st.column_config.TextColumn(width="large"),
            "ノート確認済み": st.column_config.CheckboxColumn(help="ノートの場合のみ使用"),
        })
    if ro:
        _details(p, src, cov, n_warn, ro=True)
        return
    c1, c2, c3 = st.columns([1, 1, 3])
    if c1.button("変更を反映", type="primary", key=f"apply_{src['id']}_{gsel}"):
        errors = []
        for row in edited.to_dict("records"):
            seg = next(g for g in src["segments"] if g["seg_id"] == row["ID"])
            if seg.get("is_note") and row["ノート確認済み"] is not None:
                seg["note_reviewed"] = bool(row["ノート確認済み"])
            seg["user_note"] = row["補足"] or ""
            if bool(row["対象"]) != bool(seg.get("selected")):
                try:
                    rules.set_segment_selected(src, seg["seg_id"], bool(row["対象"]))
                except rules.RuleError as e:
                    errors.append(f"{seg['seg_id']}：{e}")
        log(p, "分析対象の変更", f"{src['id']} v{src['version']}", state.user_name())
        for e in errors:
            st.error(e)
        if not errors:
            st.success("反映しました。")
    if c2.button("範囲をすべて対象外", key=f"none_{src['id']}_{gsel}"):
        for g in segs:
            g["selected"] = False
        st.rerun()
    _details(p, src, cov, n_warn)


def _details(p, src, cov, n_warn, ro: bool = False):
    """読込の状態・注意・資料の情報（補足情報なので、表の下にまとめて折りたたむ）。"""
    with st.expander(f"読込の状態と注意（{n_warn}件）" if n_warn else "読込の状態"):
        st.markdown(f"<span class='rp-small'>形式 {esc(src['file_type'])}／{esc(src['owner'])}の資料／状態 {esc(src['status'])}"
                    f"／元のファイルは保存していません</span>", unsafe_allow_html=True)
        if cov.get("notes"):
            st.markdown(f"<span class='rp-small'>読める範囲：{esc(cov['notes'])}</span>", unsafe_allow_html=True)
        if cov.get("skipped"):
            st.markdown(f":orange[未読込・対象外：{esc('、'.join(cov['skipped']))}]")
        for w in src.get("warnings", []):
            st.markdown(f":orange[{esc(w.get('where', ''))}　{esc(w['message'])}]")
    if ro:
        return
    with st.expander("資料の情報と補足メモ"):
        c1, c2 = st.columns([1, 3])
        status = c1.selectbox("状態", SOURCE_STATUS, index=SOURCE_STATUS.index(src["status"]) if src["status"] in SOURCE_STATUS else 0,
                              key=f"ed_status_{src['id']}_{src['version']}")
        notes = c2.text_area("補足メモ（原文とは分けて保存）", value=src.get("user_notes", ""), height=70,
                             key=f"ed_notes_{src['id']}_{src['version']}")
        if st.button("保存", key=f"save_meta_{src['id']}_{src['version']}"):
            src["status"], src["user_notes"] = status, notes
            log(p, "資料情報更新", f"{src['id']} v{src['version']}", state.user_name())
            st.success("保存しました。")
