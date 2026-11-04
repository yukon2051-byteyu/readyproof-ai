"""① 製品の資料（入力1）：資料・録画・字幕を1か所で受け付け、読めた内容を確認する。"""
from __future__ import annotations

import os

import streamlit as st

from ...demos.builder import recording_path
from ...ingest import IngestError, ingest_bytes
from ...logic import rules
from ...logic.recordings import build_utterances
from ...media.subtitles import fmt_ts, parse_transcript
from .. import state
from ..layout import demo_note, header, next_button
from ..theme import box, chip, esc, section
from . import project_page, recordings_view, sources

DOC_EXT = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".doc", ".xls", ".ppt"}
MEDIA_EXT = {".mp4", ".webm", ".mov", ".m4a", ".mp3", ".wav"}
SUB_EXT = {".vtt", ".srt"}
FILE_LABEL = {"pdf": "PDF", "docx": "Word", "xlsx": "Excel", "pptx": "PowerPoint", "txt": "テキスト", "paste": "貼り付けた文章"}
STATUS = {"ok": ("読込完了", "ok"), "partial": ("一部未読込", "warn"), "empty": ("文字なし", "bad"), "failed": ("読込失敗", "bad")}


def render():
    p = header("input1", "製品の資料",
               "製品の説明資料・機能一覧・提案書・マニュアルや、営業説明の録画を入れてください。\n読めた内容と位置（ページ・スライド・発言時刻）を確認できます。")
    if not p:
        return
    if state.is_demo():
        demo_note()
        items(p)
        next_button("次へ：② 自社のルール", "input2")
        return
    with st.expander("案件と製品の情報", expanded=not p["products"]):
        project_page.project_form(p)

    has = any(x["owner"] == "製品" for x in p["sources"]) or p["recordings"]
    if has:
        items(p)
        pending_media(p)
        section("ファイルを追加する")
        if st.toggle("資料・録画・字幕を追加する", key="show_upload", value=bool(st.session_state.get("pending_media"))):
            upload(p)
    else:
        upload(p)
        pending_media(p)
        items(p)
    next_button("次へ：② 自社のルール", "input2")


def upload(p):
    lim = state.settings().limits
    with box():
        files = st.file_uploader(
            "ファイルをここに入れる（PDF・Word・Excel・PowerPoint・テキスト／録画 MP4・WebM・MOV／字幕 VTT・SRT）",
            type=[e[1:] for e in sorted(DOC_EXT | MEDIA_EXT | SUB_EXT)], accept_multiple_files=True, key="upl_all")
        has_rec = any(os.path.splitext(f.name)[1].lower() in MEDIA_EXT | SUB_EXT for f in files or [])
        consent = st.checkbox("録画・発言を使う許可を、参加者から得ています", key="upl_consent") if has_rec else True
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        go = c1.button("読み込む", type="primary", icon=":material/upload:", disabled=not files or not consent,
                       width="stretch")
        c2.caption(f"資料は1件{lim.max_file_mb}MBまで。画像のみのPDF（OCR）と、図・画像の意味は読み取りません。"
                   "録画は、読み込んだあと文字起こしの範囲を確認してから処理します。")
        if go:
            msgs = []
            for f in files:
                ext = os.path.splitext(f.name)[1].lower()
                if ext in MEDIA_EXT:
                    st.session_state.setdefault("pending_media", {})[f.name] = f.getvalue()
                    msgs.append(("info", f"{f.name}：録画です。下で処理する範囲を確認してください。"))
                elif ext in SUB_EXT:
                    cues, kind = parse_transcript(f.name, f.getvalue().decode("utf-8-sig", errors="replace"))
                    if not cues:
                        msgs.append(("error", f"{f.name}：発言を読み取れませんでした。"))
                        continue
                    rec = recordings_view._new_recording(
                        p, {"file_name": f.name, "meeting_name": os.path.splitext(f.name)[0], "consent": True},
                        build_utterances(cues), f"会議ツールの文字起こし読込（{kind}）", {"start": 0.0, "end": None}, None)
                    msgs.append(("success", f"{f.name}：{len(cues)}件の発言を読み込みました（{rec['id']}）。話者を確認してください。"))
                    st.session_state.open_item = ("rec", rec["id"])
                else:
                    try:
                        res = ingest_bytes(f.name, f.getvalue(), lim)
                    except IngestError as e:
                        msgs.append(("error", f"{f.name}：{e}"))
                        continue
                    src = rules.add_source(p, res.to_dict(), {"file_name": f.name, "name": os.path.splitext(f.name)[0],
                                                              "owner": "製品", "kind": "製品説明",
                                                              "product_id": state.product_id()})
                    msgs.append(("success", f"{f.name}：{len(src['segments'])}箇所を読み込みました（{src['id']}）。"))
            for kind, m in msgs:
                getattr(st, kind)(m)
        with st.expander("文章を直接貼り付ける"):
            txt = st.text_area("製品の説明文（段落ごとに位置を付けます）", key="upl_paste", height=100)
            if st.button("貼り付けた文章を読み込む", disabled=not txt.strip()):
                from ...ingest import ingest_text

                res = ingest_text(txt, lim)
                src = rules.add_source(p, res.to_dict(), {"file_name": "（貼り付け）", "name": "貼り付けた文章", "owner": "製品",
                                                          "kind": "その他", "product_id": state.product_id()})
                st.success(f"{src['id']} として読み込みました。")
        if p["project"].get("demo_id") == "demo3":
            if st.button("デモ用のサンプル録画（約40秒）で、録画の処理を試す", type="tertiary", icon=":material/movie:"):
                with open(recording_path("demo3"), "rb") as fh:
                    st.session_state.setdefault("pending_media", {})["demo3_sales_meeting.mp4"] = fh.read()


def pending_media(p):
    pend = st.session_state.get("pending_media") or {}
    for i, (name, data) in enumerate(list(pend.items())):
        with box():
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.markdown(f"**録画：{esc(name)}**")
            if c2.button("取り消す", key=f"pm_cancel_{i}", type="tertiary"):
                pend.pop(name, None)
                st.rerun()
            recordings_view.media_panel(p, data, name, key=f"pm{i}")


def items(p):
    srcs = [s for s in p["sources"] if s["owner"] == "製品"]
    recs = p["recordings"]
    section(f"読み込んだもの（資料 {len(srcs)}件・録画 {len(recs)}件）")
    if not srcs and not recs:
        st.info("まだ何も読み込んでいません。上の欄にファイルを入れてください。")
        return
    keys = [("src", s["id"]) for s in srcs] + [("rec", r["id"]) for r in recs]
    opened = st.session_state.get("open_item")
    if opened not in keys:  # 何も開いていなければ1件目を開く（「閉じる」は使わない）
        opened = keys[0]
    for s in srcs:
        cov = s.get("coverage", {})
        n_warn = len(s.get("warnings", [])) + (1 if cov.get("skipped") else 0)
        label, tone = STATUS[s["extract_status"]]
        sel = sum(1 for g in s["segments"] if g.get("selected"))
        _row(("src", s["id"]), f"{s['name']}",
             f"{FILE_LABEL.get(s['file_type'], s['file_type'])}・{s['kind']}／読込 {cov.get('read')}/{cov.get('total')}"
             f"{cov.get('unit', '')}／分析の対象 {sel}/{len(s['segments'])}箇所" + (f"／{s['status']}" if s["status"] != "有効" else ""),
             chip(label, tone) + (chip(f"注意 {n_warn}件", "warn") if n_warn else ""), opened)
        if opened == ("src", s["id"]):
            with box():
                sources.review(p, s)
    for r in recs:
        utts = r.get("utterances", [])
        conf = sum(1 for u in utts if u.get("speaker_confirmed") and u.get("review_status") == "確認済み")
        rng = r.get("range") or {}
        _row(("rec", r["id"]), r.get("meeting_name") or r.get("file_name") or r["id"],
             f"録画／発言 {len(utts)}件（話者・内容を確認済み {conf}件）／処理範囲 {fmt_ts(rng.get('start'))}〜"
             f"{fmt_ts(rng.get('end')) if rng.get('end') is not None else '末尾'}",
             chip("確認済み", "ok") if conf == len(utts) else chip(f"未確認 {len(utts) - conf}件", "warn"), opened)
        if opened == ("rec", r["id"]):
            with box():
                recordings_view.review(p, r["id"])


def _row(key, title, sub, badges, opened):
    with box():
        c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
        c1.markdown(f"{badges}<span class='rp-item'><span class='h'>{esc(title)}</span></span><br>"
                    f"<span class='rp-small'>{esc(sub)}</span>", unsafe_allow_html=True)
        if opened == key:
            c2.markdown("<div style='text-align:center' class='rp-small'>下に表示中</div>", unsafe_allow_html=True)
        elif c2.button("詳しく確認する", key=f"open_{key[0]}_{key[1]}", width="stretch"):
            st.session_state.open_item = key
            st.rerun()
