"""③ 診断結果（出力1）：利用者の考える順序に合わせて、3階層で示す。

第1階層 診断サマリー：結局使えるのか、何が問題か、次に何をするか（長文・根拠は出さない）
第2階層 要件カード：要件ごとの結論・短い理由・必要な対応・確認状態。絞り込みと並び替え
第3階層 詳細：開いたときだけ、4つの面（diagnosis_panels.py）で根拠や履歴を確認する

表示する内容は logic/diagnosis_view.py が既存データから導き出す。画面に業務判断を書かない。
"""
from __future__ import annotations

import streamlit as st

from ...core import DIAG_CATEGORIES, REQ_PRIORITY
from ...export.excel import questionnaire_workbook
from ...logic import diagnosis_view as V
from ...logic import metrics as M
from ...logic import rules
from .. import state
from ..layout import header, next_button
from ..theme import box, check_chip, esc, section, status_pill, tiles
from . import diagnosis, diagnosis_panels

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLOR = {"green": "#1E7B45", "orange": "#B45309", "red": "#B42318", "gray": "#5B6574", "navy": "#1D4E89"}
TILE_COLOR = {"likely": COLOR["green"], "extra": COLOR["orange"], "hard": COLOR["red"], "check": COLOR["orange"]}
TILE_NOTE = {"likely": "資料・回答からの見込み", "extra": "オプション・改修などが必要", "hard": "使えないとの記載・確認あり",
             "check": "情報不足・根拠の矛盾"}
PAGE_LABEL = {"input2": "② 自社のルールへ", "tests": "④ 受入テストへ", "decision": "⑤ 導入判断へ", "result": "詳細を開く"}
SHOW_ACTIONS = 5


def render():
    p = header("result", "診断結果",
               "資料と営業説明から見た「見込み」です。実際に動くかは ④ の受入テストで確かめます。")
    if not p:
        return
    reqs = [r for r in p["requirements"] if r["status"] != "廃止"]
    if not reqs:
        st.info("まだ自社の要件がありません。② 自社のルールで作ってください。")
        if st.button("② 自社のルールへ"):
            state.goto("input2")
        return
    m = M.compute(p)
    rs = V.rows(p, m)
    _summary(p, m, rs)
    if not state.is_demo():  # デモは見るだけ（AIは実行しない）
        ai_box(p, reqs)
    _cards(p, rs)
    next_button("次へ：④ 受入テスト", "tests", left=lambda: st.download_button(
        "ベンダーへの質問書（Excel）をダウンロード", questionnaire_workbook(p), width="stretch",
        file_name=f"{p['project']['id']}_質問書.xlsx", mime=XLSX, icon=":material/download:", key="dl_q_bottom"))


# ---------------- 第1階層：診断サマリー ----------------
def _summary(p, m, rs):
    s = V.summary(p, m, rs)
    plan = f"（{s['plan']}）" if s["plan"] else ""
    st.markdown(
        f"<div class='rp-sum'><div class='meta'><span>{esc(s['product'])}{esc(plan)}　自社の要件 {s['total']}件（必須 {s['must']}件）</span>"
        f"<span class='st {s['status']['tone']}'>{esc(s['status']['text'])}</span></div>"
        f"<div class='head'>{esc(s['head'])}</div>"
        + "".join(f"<div class='sub'>{esc(x)}</div>" for x in s["subs"]) + "</div>", unsafe_allow_html=True)
    _kpis(m, rs)
    if s["points"]:
        section("導入判断に影響すること", size="md")
        st.markdown("<ul class='rp-points'>" + "".join(f"<li>{esc(x)}</li>" for x in s["points"]) + "</ul>", unsafe_allow_html=True)
    _next_actions(p, rs)


def _kpis(m, rs):
    k = V.kpis(rs, m)
    base = f"全要件 {k['total']}件のうち"
    items = [{"label": x["label"], "value": f"{x['value']}件", "note": f"{base}・{TILE_NOTE[x['key']]}", "color": TILE_COLOR[x["key"]]}
             for x in k["main"]]
    items.append({"label": "未診断", "value": f"{k['none']}件", "note": base, "color": COLOR["gray"]})
    t = k["tests"]
    test_note = (f"合格 {t['passed']}件・不合格 {t['failed']}件" if t["run"] else "まだ実機で確かめていません") if t["total"] else "テストはまだありません"
    items.append({"label": "実機テスト（実施）", "value": f"{t['run']}/{t['total']}件", "note": test_note, "color": COLOR["navy"],
                  "alert": bool(t["failed"])})
    tiles(items)
    if k["zero"]:
        st.caption("0件：" + "、".join(k["zero"]))
    with st.expander(f"診断区分の内訳（全6区分・全要件 {k['total']}件）"):
        lines = [f"<tr><td>{esc(V.PLAIN[c])}</td><td class='n'>{m['by_category'][c]}件</td></tr>" for c in DIAG_CATEGORIES]
        lines.append(f"<tr><td>未診断</td><td class='n'>{m['no_diagnosis']}件</td></tr>")
        st.markdown("<table class='rp-tbl'>" + "".join(lines) + "</table>", unsafe_allow_html=True)


def _next_actions(p, rs):
    items = V.next_actions(p, rs)
    section("次にやるべきこと", size="md")
    if not items:
        st.markdown("<div class='rp-body'>いま必要な対応はありません。</div>", unsafe_allow_html=True)
        return
    for i, a in enumerate(items[:SHOW_ACTIONS], start=1):
        c1, c2 = st.columns([5, 1.5], vertical_alignment="center")
        c1.markdown(f"<div class='rp-act'><span class='no'>{i}</span><div><div class='t'>{esc(a['text'])}"
                    f"<span class='s'>{esc(a['status'])}</span></div>"
                    f"<div class='d'>対象：{esc(a['title'])}" + (f"　理由：{esc(a['reason'])}" if a["reason"] else "") + "</div></div></div>",
                    unsafe_allow_html=True)
        if c2.button(PAGE_LABEL[a["page"]], key=f"na_{i}", width="stretch"):
            if a["page"] == "result":
                state.focus_requirement(a["req_id"], a.get("tab"))
                st.rerun()
            state.goto(a["page"])
    if len(items) > SHOW_ACTIONS:
        st.caption(f"ほか {len(items) - SHOW_ACTIONS}件は、下の要件の一覧で確認できます。")


# ---------------- AIの実行欄（自分の案件のみ） ----------------
def ai_box(p, reqs):
    """診断は常にAIで行う。未診断があれば実行欄を表示、すべて診断済みなら「やり直す」だけ表示。"""
    confirmed = [r for r in reqs if r["status"] == "確定"]
    undiag = [r["id"] for r in confirmed if not rules.current_diagnosis(p, r["id"])]
    if undiag:
        with box():
            diagnosis.ai_section(p, reqs, default=undiag, title=f"AIで診断する（未診断 {len(undiag)}件）",
                                 button_label="AIで診断する")
        return
    if not confirmed:
        return
    if st.session_state.get("rediag"):
        with box():
            diagnosis.ai_section(p, reqs, default=[r["id"] for r in confirmed], title="AIで診断をやり直す",
                                 button_label="AIで診断をやり直す")
            if st.button("やり直さない", key="rediag_close", type="tertiary"):
                st.session_state.rediag = False
                st.rerun()
    elif st.button("AIで診断をやり直す", icon=":material/refresh:", key="rediag_open"):
        st.session_state.rediag = True
        st.rerun()


# ---------------- 第2階層：要件カード ----------------
def _cards(p, rs):
    section("要件ごとの診断", size="md")
    if st.session_state.pop("_rq_jump", False):  # 別の場所から要件を開いたときは、隠れないよう絞り込みを解除
        st.session_state.rq_filter = "all"
        st.session_state.rq_prio = "すべて"
    st.session_state.setdefault("rq_filter", "all")
    c = V.counts(rs)
    labels = {"all": f"すべて（{len(rs)}）", **{k: f"{V.GROUPS[k]['label']}（{c[k]}）" for k in V.GROUPS}}
    group = st.segmented_control("診断で絞り込む", list(labels), format_func=lambda k: labels[k], key="rq_filter",
                                 label_visibility="collapsed")
    f1, f2, _ = st.columns([1, 1, 1.4])
    prio = f1.selectbox("重要度", ["すべて"] + REQ_PRIORITY, key="rq_prio")
    sort = f2.selectbox("並び順", V.SORTS, key="rq_sort")
    shown = V.filter_sort(rs, group or "all", prio, sort)
    if not shown:
        st.caption("条件に合う要件はありません。")
    focus = st.session_state.get("focus_req")
    for x in shown:
        _card(p, x, focus == x["req"]["id"])


def _card(p, x, opened: bool):
    r = x["req"]
    with box():
        c1, c2 = st.columns([5, 1.3], vertical_alignment="top")
        need = x["need"]["text"]
        checks = "".join(check_chip(k, v["text"], v["state"]) for k, v in x["checks"])
        c1.markdown(
            f"<div class='rp-rq'><div class='hd'><span class='t'>{esc(x['title'])}</span><span class='id'>{esc(r['id'])}</span></div>"
            f"<div class='pl'>{status_pill(x['label'], x['group'])}<span class='prio'>{esc(r.get('priority', ''))}</span></div>"
            f"<div class='why'>{esc(x['reason'])}</div>"
            f"<div class='nd'><span class='lb'>必要な対応</span>{esc(need)}</div>"
            f"<div class='ck'>{checks}</div></div>", unsafe_allow_html=True)
        if c2.button("閉じる" if opened else "詳細を見る", key=f"fr_{r['id']}", width="stretch"):
            st.session_state.focus_req = None if opened else r["id"]
            st.rerun()
        if opened:
            st.divider()
            diagnosis_panels.render(p, r, x["dg"])


# ---------------- ⑤ 導入判断でも使う：必須要件の判定の件数 ----------------
def summary(p, reqs):
    must = [r for r in reqs if r["priority"] == "必須"]
    cnt = {c: 0 for c in DIAG_CATEGORIES}
    none = 0
    for r in must:
        dg = rules.current_diagnosis(p, r["id"])
        if dg:
            cnt[dg["category"]] += 1
        else:
            none += 1
    check = cnt[DIAG_CATEGORIES[4]] + cnt[DIAG_CATEGORIES[5]]
    st.markdown(f"**必須の要件 {len(must)}件の判定**（そのほかの要件 {len(reqs) - len(must)}件は ③ 診断結果の一覧にあります）")
    tiles([
        {"label": V.PLAIN[DIAG_CATEGORIES[0]], "value": f"{cnt[DIAG_CATEGORIES[0]]}件", "color": COLOR["green"]},
        {"label": V.PLAIN[DIAG_CATEGORIES[1]], "value": f"{cnt[DIAG_CATEGORIES[1]]}件", "color": COLOR["green"]},
        {"label": V.PLAIN[DIAG_CATEGORIES[2]], "value": f"{cnt[DIAG_CATEGORIES[2]]}件", "color": COLOR["orange"]},
        {"label": V.PLAIN[DIAG_CATEGORIES[3]], "value": f"{cnt[DIAG_CATEGORIES[3]]}件", "color": COLOR["red"]},
        {"label": "確認が必要（情報不足・矛盾）", "value": f"{check}件", "color": COLOR["orange"]},
        {"label": "まだ診断していない", "value": f"{none}件", "color": COLOR["gray"]},
    ])
