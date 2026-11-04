"""録画の登録・文字起こし・発言の確認。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ...core import CONTENT_REVIEW, SPEAKER_ROLES, UTTERANCE_TYPES, log, next_id, now_iso
from ...demos.builder import recording_path
from ...logic import rules
from ...logic.recordings import (apply_speaker_map, build_utterances, edit_utterance_text, find_reusable_transcript,
                                 media_hash, set_speaker)
from ...media.probe import MediaError, extract_audio_wav, probe_media
from ...media.subtitles import fmt_ts, parse_transcript
from ...media.transcribe import ENGINES, local_whisper_available, transcribe_local
from .. import state
from ..theme import chip, esc

MEASURED = "実測：開発PC（Windows・CPU）で small モデル、40秒の音声に約39秒（モデル読込を含む）。公開環境（最大2コア）では遅くなる見込み。"


def _new_recording(p, meta: dict, utterances: list, method: str, rng: dict, probe: dict | None, file_hash: str = ""):
    rec = {"id": next_id(p, "recordings"), "version": 1, "file_name": meta.get("file_name", ""),
           "meeting_name": meta.get("meeting_name", ""), "held_on": meta.get("held_on", ""),
           "product_id": state.product_id(), "plan": meta.get("plan", ""), "participants": meta.get("participants", []),
           "duration_sec": (probe or {}).get("duration_sec"), "range": rng, "method": method, "processed_at": now_iso(),
           "media_retained": False, "file_sha256": file_hash, "utterances": utterances, "probe": probe,
           "consent_confirmed": meta.get("consent", False)}
    p["recordings"].append(rec)
    log(p, "録画登録", rec["id"], state.user_name(), method)
    return rec


def _meta_inputs(prefix: str) -> dict:
    c1, c2, c3 = st.columns([2, 1, 1])
    meeting = c1.text_input("ミーティング名", key=f"{prefix}_meeting", placeholder="例：製品説明ミーティング")
    held = c2.text_input("開催日", key=f"{prefix}_held", placeholder="2026-10-15")
    plan = c3.text_input("説明の対象プラン・版", key=f"{prefix}_plan")
    parts = st.text_area("参加者と役割（1行に「名前：役割」）", key=f"{prefix}_parts", height=70,
                         placeholder="田中：自社担当者\n鈴木：営業担当者")
    participants = []
    for line in parts.splitlines():
        if "：" in line or ":" in line:
            n, r = line.replace(":", "：").split("：", 1)
            participants.append({"name": n.strip(), "role": r.strip()})
    consent = st.checkbox("参加者から録画・発言の利用（このアプリでの処理）の許可を得ています", key=f"{prefix}_consent")
    return {"meeting_name": meeting, "held_on": held, "plan": plan, "participants": participants, "consent": consent}


def register(p):
    s = state.settings()
    lim = s.limits
    st.markdown("**録画（MP4・WebM・MOV）を登録して文字起こしする**")
    st.caption("アップロードしただけでは処理を始めません。内容・範囲・処理方法を確認してから実行します。")
    ok, why = local_whisper_available()
    eng = ENGINES["local_whisper"]
    with st.container(border=True):
        up = st.file_uploader(f"録画ファイル（最大{lim.max_media_mb}MB・{lim.max_media_minutes}分）",
                              type=["mp4", "webm", "mov", "m4a", "mp3", "wav"], key="rec_file")
        if state.is_demo() and p["project"].get("demo_id") == "demo3":
            st.caption("デモ3では、架空の営業説明動画（約40秒）で音声チェックを試せます（料金なし）。")
            if st.button("サンプル動画を読み込む", key="rec_demo_media"):
                with open(recording_path("demo3"), "rb") as f:
                    st.session_state.rec_demo_bytes = f.read()
        data, fname = None, ""
        if up is not None:
            data, fname = up.getvalue(), up.name
        elif st.session_state.get("rec_demo_bytes"):
            data, fname = st.session_state.rec_demo_bytes, "demo3_sales_meeting.mp4"
        if data is None:
            st.info("録画を選ぶと、長さ・容量・音声の有無を確認します。")
        else:
            try:
                info = probe_media(data, fname, lim)
            except MediaError as e:
                st.error(str(e))
                info = None
            if info:
                dur = info["duration_sec"] or 0
                st.markdown(
                    f"{chip('音声トラックあり', 'ok')}<span class='rp-small'>{esc(fname)}／長さ {fmt_ts(dur)}／"
                    f"{info['size_mb']}MB／形式 {esc(info['container'])}／音声 {esc(info['audio_streams'][0]['codec'])} "
                    f"{info['audio_streams'][0]['sample_rate']}Hz</span>", unsafe_allow_html=True)
                for issue in info["issues"]:
                    st.warning(issue)
                meta = _meta_inputs("rec")
                max_min = min(dur / 60, lim.max_transcribe_minutes_per_run) if dur else lim.max_transcribe_minutes_per_run
                c1, c2 = st.columns(2)
                start_m = c1.number_input("処理する開始（分）", 0.0, max(dur / 60, 0.0), 0.0, 0.5, key="rec_start")
                end_m = c2.number_input("処理する終了（分）", 0.0, max(dur / 60, 0.1), round(min(dur / 60, start_m + max_min), 2),
                                        0.5, key="rec_end")
                minutes = max(end_m - start_m, 0)
                st.markdown(
                    f"- 処理方法：{eng['label']}\n- 送信先：{eng['destination']}\n- 話者の区別：{eng['diarization']}\n"
                    f"- 対象時間：{fmt_ts(start_m * 60)}〜{fmt_ts(end_m * 60)}（{minutes:.1f}分）。範囲外は分析対象外として記録します\n"
                    f"- 費用見込み：{eng['cost']}\n- 処理時間の目安：{MEASURED}")
                h = media_hash(data)
                reuse = find_reusable_transcript(p, h, round(start_m * 60, 1), round(end_m * 60, 1))
                blockers = []
                if not ok:
                    blockers.append(why)
                if minutes <= 0:
                    blockers.append("処理する時間範囲を指定してください。")
                if minutes > lim.max_transcribe_minutes_per_run:
                    blockers.append(f"1回の文字起こしは{lim.max_transcribe_minutes_per_run}分までです。範囲を分けて実行してください。")
                used = st.session_state.get("session_transcribe_min", 0.0)
                if used + minutes > s.budget.transcribe_minutes_per_code_per_month:
                    blockers.append("このセッションの文字起こし枠を超えます。")
                if not meta["consent"]:
                    blockers.append("録画・発言の利用許可を確認してください。")
                if reuse:
                    st.success(f"同じ録画・同じ範囲の文字起こし（{reuse['id']}）があります。再処理せずに再利用します。")
                    if st.button("既存の文字起こしを開く"):
                        st.session_state.media = st.session_state.get("media", {})
                        st.session_state.media[reuse["id"]] = data
                        st.session_state.sel_rec = reuse["id"]
                        st.session_state._goto_view = "発言の確認"
                        st.rerun()
                for b in blockers:
                    st.caption(f"実行できません：{b}")
                busy = st.session_state.get("tr_busy", False)
                if not reuse and st.button("文字起こしを実行", type="primary", disabled=bool(blockers) or busy,
                                           icon=":material/graphic_eq:"):
                    st.session_state.tr_busy = True
                    try:
                        bar = st.progress(0.0, text="音声を取り出しています…")
                        wav = extract_audio_wav(data, fname, start_m * 60, end_m * 60)
                        bar.progress(0.1, text="文字起こし中（このサーバー内で処理）…")
                        segs = transcribe_local(wav, s.whisper_model, offset_sec=start_m * 60,
                                                progress=lambda x: bar.progress(0.1 + 0.9 * x, text="文字起こし中…"))
                        lg = state.ledger()
                        if lg:  # 永続記録がある環境では文字起こし時間も記録（API料金 0 円）
                            rid = lg.reserve(s.budget, "transcribe", st.session_state.get("access_code", ""), 0.0,
                                             "transcribe", minutes)
                            lg.finalize(rid, "成功", 0.0, minutes=minutes)
                        st.session_state.session_transcribe_min = used + minutes
                        rec = _new_recording(p, {**meta, "file_name": fname}, build_utterances(segs),
                                             f"{eng['label']}（モデル {s.whisper_model}）",
                                             {"start": round(start_m * 60, 1), "end": round(end_m * 60, 1)}, info, h)
                        st.session_state.setdefault("media", {})[rec["id"]] = data
                        state.flash(f"{rec['id']} の文字起こしが完了しました（{len(rec['utterances'])}区間）。話者と内容を確認してください。")
                        st.session_state.sel_rec = rec["id"]
                        st.session_state._goto_view = "発言の確認"
                    except (MediaError, ValueError) as e:
                        st.error(str(e))
                    except Exception as e:  # モデル取得失敗・メモリ不足など
                        st.error(f"文字起こしに失敗しました（{type(e).__name__}）。代替として会議ツールの文字起こしを読み込めます。")
                    finally:
                        st.session_state.tr_busy = False
                        st.session_state.pop("rec_demo_bytes", None)
                    if st.session_state.get("_goto_view") == "発言の確認":
                        st.rerun()

    st.markdown("**代替：会議ツールの文字起こし・SRT・VTT・時刻付き文章を読み込む**")
    with st.container(border=True):
        tf = st.file_uploader("文字起こしファイル（.vtt / .srt / .txt）", type=["vtt", "srt", "txt"], key="tr_file")
        pasted = st.text_area("または時刻付きの文章を貼り付け（例：00:01:23 鈴木: 発言）", key="tr_paste", height=90)
        meta2 = _meta_inputs("tr")
        fname2 = st.text_input("元の録画ファイル名（分かれば）", key="tr_fname")
        if st.button("文字起こしを取り込む", disabled=not (tf or pasted.strip()) or not meta2["consent"]):
            raw = tf.getvalue().decode("utf-8-sig", errors="replace") if tf else pasted
            cues, kind = parse_transcript(tf.name if tf else "", raw)
            if not cues:
                st.error("発言を読み取れませんでした。形式を確認してください。")
            else:
                no_time = sum(1 for c in cues if c["start"] is None)
                rec = _new_recording(p, {**meta2, "file_name": fname2}, build_utterances(cues),
                                     f"会議ツールの文字起こし読込（{kind}）", {"start": 0.0, "end": None}, None)
                state.flash(f"{rec['id']} に{len(cues)}件の発言を取り込みました。"
                            + (f"時刻のない発言が{no_time}件あります（時刻は作成していません）。" if no_time else ""))
                st.session_state.sel_rec = rec["id"]
                st.session_state._goto_view = "発言の確認"
                st.rerun()
        st.caption("字幕を取り込んだだけでは、録画の音声処理を行ったことにはなりません（処理方法に「文字起こし読込」と記録されます）。")


# ------------------------------------------------------------------
def review(p):
    recs = p["recordings"]
    if not recs:
        st.info("録画・文字起こしがまだありません。「録画を登録」から追加してください。")
        return
    ids = [r["id"] for r in recs]
    cur = st.session_state.get("sel_rec")
    rid = st.selectbox("確認する録画", ids, index=ids.index(cur) if cur in ids else 0,
                       format_func=lambda i: f"{i}：{next(r for r in recs if r['id'] == i).get('meeting_name') or '（名称なし）'}")
    st.session_state.sel_rec = rid
    rec = next(r for r in recs if r["id"] == rid)
    media = st.session_state.get("media", {})
    if p["project"].get("demo_id") == "demo3" and rid == "REC-001" and rid not in media:
        with open(recording_path("demo3"), "rb") as f:
            media[rid] = f.read()
        st.session_state.media = media
    rng = rec.get("range") or {}
    st.markdown(
        f"{chip(rec['method'], 'info')}<span class='rp-small'>ファイル {esc(rec.get('file_name') or '不明')}／開催日 "
        f"{esc(rec.get('held_on') or '未記入')}／処理範囲 {fmt_ts(rng.get('start'))}〜"
        f"{fmt_ts(rng.get('end')) if rng.get('end') is not None else '末尾'}／処理日時 {esc(rec.get('processed_at'))}</span>",
        unsafe_allow_html=True)
    st.caption("動画本体：" + ("このセッションでのみ再生できます（保存したJSONには含まれません）" if rid in media
                            else "保持していません（ファイル名と時刻のみ）。再生するには同じ録画を再度アップロードしてください。"))
    utts = rec["utterances"]
    if not utts:
        st.info("発言がありません。")
        return

    with st.expander("話者をまとめて設定する（自動ラベルごと）", expanded=False):
        st.caption("「話者A」などの自動ラベルが誰かは、AIは決めません。人が分類・確認してください。")
        labels = list(dict.fromkeys(u.get("speaker_label") or "" for u in utts))
        for lb in labels:
            c1, c2, c3, c4, c5 = st.columns([1.2, 1.4, 1.6, 1, 1])
            c1.markdown(f"**{esc(lb or '（ラベルなし）')}**")
            role = c2.selectbox("役割", SPEAKER_ROLES, key=f"form_role_{rid}_{lb}", label_visibility="collapsed")
            name = c3.text_input("氏名", key=f"form_name_{rid}_{lb}", label_visibility="collapsed", placeholder="氏名")
            conf = c4.checkbox("確認済み", key=f"form_conf_{rid}_{lb}")
            if c5.button("適用", key=f"form_apply_{rid}_{lb}"):
                n = apply_speaker_map(rec, lb, role, name, conf, state.user_name())
                log(p, "話者設定", rid, state.user_name(), f"{lb}→{role}")
                state.flash(f"{n}件の発言に話者を設定しました。")
                st.rerun()

    df = pd.DataFrame([{
        "対象": bool(u.get("selected", True)), "ID": u["id"], "開始": fmt_ts(u.get("start")), "終了": fmt_ts(u.get("end")),
        "ラベル": u.get("speaker_label") or "", "話者の役割": u.get("speaker_role") or "未分類", "氏名": u.get("speaker_name", ""),
        "話者確認": bool(u.get("speaker_confirmed")), "自動文字起こし（原文）": u.get("raw_text", ""),
        "人が修正した文章": u.get("edited_text", ""), "発言の種類": u.get("utterance_type") or "未分類",
        "種類の候補": u.get("type_suggestion", ""), "内容確認": u.get("review_status", "未確認"),
        "注意": "、".join(u.get("flags", [])),
    } for u in utts])
    st.caption("質問と回答、要望と確約、可能と不可、標準と追加開発、現在と将来予定、条件付きを区別してください。"
               "数値・金額・否定表現・製品名は特に確認し、聞き取れない箇所は創作せず「聞き取り不能」としてください。")
    edited = st.data_editor(
        df, key=f"ed_utts_{rid}", hide_index=True, width="stretch",
        disabled=["ID", "開始", "終了", "ラベル", "自動文字起こし（原文）", "種類の候補", "注意"],
        column_config={
            "対象": st.column_config.CheckboxColumn(width="small"),
            "話者の役割": st.column_config.SelectboxColumn(options=SPEAKER_ROLES),
            "発言の種類": st.column_config.SelectboxColumn(options=UTTERANCE_TYPES),
            "内容確認": st.column_config.SelectboxColumn(options=CONTENT_REVIEW),
            "自動文字起こし（原文）": st.column_config.TextColumn(width="large"),
            "人が修正した文章": st.column_config.TextColumn(width="large"),
        })
    if st.button("発言の変更を反映", type="primary", key=f"apply_utts_{rid}"):
        by = state.user_name()
        for row in edited.to_dict("records"):
            u = next(x for x in utts if x["id"] == row["ID"])
            u["selected"] = bool(row["対象"])
            if (row["人が修正した文章"] or "").strip():
                edit_utterance_text(u, row["人が修正した文章"], by)
            set_speaker(u, row["話者の役割"], row["氏名"] or "", bool(row["話者確認"]), by)
            if row["発言の種類"] != u.get("utterance_type"):
                u.setdefault("history", []).append({"at": now_iso(), "by": by, "field": "種類",
                                                    "from": u.get("utterance_type"), "to": row["発言の種類"]})
                u["utterance_type"] = row["発言の種類"]
            if row["内容確認"] != u.get("review_status"):
                u["review_status"] = row["内容確認"]
        log(p, "発言の確認・修正", rid, by)
        st.success("反映しました。原文は残り、修正は履歴に記録されています。")

    st.markdown("**発言を聞き直す・前後を確認する**")
    uid = st.selectbox("発言", [u["id"] for u in utts], key=f"sel_utt_{rid}",
                       format_func=lambda i: f"{i} {fmt_ts(next(x for x in utts if x['id'] == i).get('start'))} "
                                             f"{(next(x for x in utts if x['id'] == i).get('edited_text') or next(x for x in utts if x['id'] == i)['raw_text'])[:40]}")
    idx = next(i for i, u in enumerate(utts) if u["id"] == uid)
    u = utts[idx]
    c1, c2 = st.columns([1, 1])
    with c1:
        if rid in media and u.get("start") is not None:
            st.video(media[rid], start_time=int(u["start"]))
            st.caption(f"{fmt_ts(u['start'])} から再生します（ブラウザの再生位置はおおよそです）。")
        else:
            st.caption("再生できる動画がありません。ファイル名と時刻で元の録画を確認してください。")
    with c2:
        for j in range(max(0, idx - 2), min(len(utts), idx + 3)):
            x = utts[j]
            mark = "▶ " if j == idx else ""
            st.markdown(f"<div class='rp-small'>{mark}{fmt_ts(x.get('start'))} {esc(x.get('speaker_role'))}"
                        f"{'（確認済み）' if x.get('speaker_confirmed') else '（未確認）'}／{esc(x.get('utterance_type'))}</div>"
                        f"<div class='rp-quote'>{esc(x.get('edited_text') or x['raw_text'])}</div>", unsafe_allow_html=True)
        if u.get("history"):
            with st.expander(f"{uid} の修正履歴（{len(u['history'])}件）"):
                st.dataframe(pd.DataFrame(u["history"]), hide_index=True)
    st.markdown("**重要な口頭説明を書面で確認する**")
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    rsel = st.multiselect("関連する要件", [r["id"] for r in reqs], key=f"form_wq_reqs_{rid}")
    if st.button("この発言から書面確認の質問を作る", key=f"wq_{rid}", icon=":material/mail:"):
        q = rules.written_confirmation_question(p, {"ref_type": "utterance", "rec_id": rid, "rec_version": rec["version"],
                                                    "utt_id": uid, "quote": u.get("edited_text") or u["raw_text"],
                                                    "kind": "営業・ベンダーの説明"}, rsel)
        state.flash(f"{q['id']}（下書き）を作成しました。「4 質問・対応依頼」で確認・確定してください。")
        st.rerun()
