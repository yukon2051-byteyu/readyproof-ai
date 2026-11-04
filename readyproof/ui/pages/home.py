"""トップページ：3分で価値が伝わる構成。

1. 見出し帯（何をするアプリか）
2. 3分デモ：開始ボタン・操作の流れ（5ステップ）・最終的な成果物（根拠付きの診断と Excel レポートの見本）
3. できること・役割分担
4. 3件のデモの選択
5. 自分の案件で使う
"""
from __future__ import annotations

import streamlit as st

from ...config import APP_NAME_JA
from ...core import new_project
from ...demos.builder import DEMOS, build
from ...export.excel import acceptance_test_workbook
from ...export.jsonio import LoadError, from_json_bytes
from .. import state
from ..components import start_tour
from ..theme import esc, section

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 見出し帯のモチーフ：「根拠を確かめた書類」（書類＋引用の行＋チェック）
MOTIF = (
    '<svg class="motif" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<rect x="38" y="18" width="104" height="136" rx="12" fill="none" stroke="#38BDF8" stroke-opacity=".35" stroke-width="4"/>'
    '<rect x="54" y="42" width="56" height="7" rx="3.5" fill="#FFFFFF" fill-opacity=".35"/>'
    '<rect x="54" y="60" width="72" height="7" rx="3.5" fill="#FFFFFF" fill-opacity=".22"/>'
    '<rect x="54" y="78" width="64" height="7" rx="3.5" fill="#FFFFFF" fill-opacity=".22"/>'
    '<rect x="50" y="96" width="4" height="26" rx="2" fill="#38BDF8" fill-opacity=".8"/>'
    '<rect x="60" y="100" width="58" height="6" rx="3" fill="#38BDF8" fill-opacity=".45"/>'
    '<rect x="60" y="112" width="44" height="6" rx="3" fill="#38BDF8" fill-opacity=".45"/>'
    '<circle cx="142" cy="146" r="34" fill="#38BDF8"/>'
    '<path d="M126 147 l11 11 l22 -24" fill="none" stroke="#14263F" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>')

FLOW = [("入力1", "製品の資料", "提案書・機能一覧・マニュアル・営業説明の録画を入れる"),
        ("入力2", "自社のルール", "質問に答えて、守るルール・例外・条件をまとめる"),
        ("出力1", "診断結果", "要件ごとに、そのまま使えるかを根拠付きで判定"),
        ("出力2", "受入テスト書", "実機で試す項目と結果を、Excel の受入テスト書に")]
ROLES = [
    ("AI", "AI", "下書きを作る", "要件の分割、関連箇所の照合と診断、質問・対応案、依頼書とテストのたたき台"),
    ("PG", "プログラム", "確実に処理する", "読込と参照位置、版と状態の管理、引用の実在確認、古い根拠の検出、集計"),
    ("人", "人", "確定・判断する", "要件・話者・診断・依頼・テストの確定、実機テスト、導入判断"),
]
DEMO_POINTS = {
    "demo1": ["スライドの表から根拠を引用", "記載なし → 質問 → 回答で更新", "境界値テストの不合格 → 設定変更 → 再テスト"],
    "demo2": ["「ロット管理 ○」だけで判断しない", "対応方法を比べて改修依頼書", "一部合格を全体の合格にしない"],
    "demo3": ["録画の発言を時刻・話者付きで根拠に", "資料と営業説明の矛盾を表示", "口頭説明を書面で確認する質問"],
}


@st.cache_data(show_spinner=False)
def sample_report() -> bytes:
    """成果物の見本（デモ1の受入テスト書）。架空データ・料金なし。"""
    return acceptance_test_workbook(build("demo1"))


def _grid(items: list[str], cols: int | None = None) -> None:
    st.markdown(f'<div class="rp-grid" style="--cols:{cols or len(items)}">{"".join(items)}</div>', unsafe_allow_html=True)


def _open_demo(demo_id: str) -> None:
    with st.spinner("サンプル資料を、実際の読込機能で読み込んでいます…"):
        p = build(demo_id)
    state.set_project(p, demo_initial=p)
    start_tour(demo_id)


def render():
    st.markdown(
        f'<div class="rp-hero">{MOTIF}<div class="inner"><div class="eyebrow">{esc(APP_NAME_JA)}</div>'
        '<div class="name">ReadyProof <span>AI</span></div>'
        '<div class="tag"><em>「うちの会社で使える？」</em>に答える<em>AI</em></div>'
        '<div class="desc">製品の情報と自社の業務ルールを照合し、導入判断・受入テストまでつなげます。</div>'
        '</div></div>', unsafe_allow_html=True)

    # ---- 3分デモ：開始 → 流れ → 成果物 ----
    section("使い方は4段階：入力2つ → 出力2つ")
    left, right = st.columns([1.05, 1], gap="medium")
    with left:
        st.markdown('<div class="rp-flow">' + "".join(
            f'<div class="st"><span class="rp-num">{i + 1}</span><div><span class="rp-small">{esc(io)}</span>　<b>{esc(t)}</b><br>'
            f'<span class="rp-small">{esc(d)}</span></div></div>' for i, (io, t, d) in enumerate(FLOW)) + "</div>",
            unsafe_allow_html=True)
        if st.button("3分デモを始める（経費精算サービスの導入）", type="primary", icon=":material/play_arrow:",
                     width="stretch", key="open_main"):
            _open_demo("demo1")
        st.caption("架空の会社・資料で、画面の案内に沿って約3分。料金はかかりません。")
    with right:
        st.markdown(
            '<div class="rp-result"><div class="h">最終的に手に入るもの（デモ「経費精算サービスの導入」の結果）</div>'
            '<div class="row"><span class="lb">自社の要件</span><div>10,000円以上は、上司の承認後に部長が承認する</div></div>'
            '<div class="row"><span class="lb">出力1 診断</span><div><b class="ok">設定すれば使える見込み</b></div></div>'
            '<div class="row"><span class="lb">根拠</span><div>ご提案資料 スライド2「承認ワークフロー」表3行目<br>'
            '<span class="q">『10,000円以上 ｜ 承認ルート：上長 → 部長』</span></div></div>'
            '<div class="row"><span class="lb">出力2 テスト</span><div>9,999円／10,000円の境界値テスト：<b class="ng">不合格</b>'
            ' → 設定変更 → <b class="ok">再テスト合格</b></div></div>'
            '<div class="foot">診断結果と受入テスト書は、Excel でダウンロードできます。</div></div>',
            unsafe_allow_html=True)
        st.download_button("見本：受入テスト書（Excel）をダウンロード", sample_report(),
                           file_name="ReadyProof_サンプル_受入テスト書.xlsx", mime=XLSX, icon=":material/download:",
                           width="stretch")

    # ---- できること・役割分担 ----
    section("AI・プログラム・人の役割分担")
    _grid([f'<div class="rp-card role"><div class="t"><span class="rp-num">{esc(m)}</span>{esc(w)}：{esc(d)}</div>'
           f'<div class="b">{esc(x)}</div></div>' for m, w, d, x in ROLES])

    # ---- 3件のデモ ----
    section("ほかのデモ（各約4分・5ステップ）")
    _grid([f'<div class="rp-card"><div class="t">{esc(d["title"])}</div><div class="b">{esc(d["theme"])}</div>'
           f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in DEMO_POINTS[d["id"]])}</ul>'
           f'<div class="m">業務：{esc(d["business"])}</div></div>' for d in DEMOS])
    for col, d in zip(st.columns(len(DEMOS)), DEMOS):
        if col.button("このデモを始める", key=f"open_{d['id']}", icon=":material/play_arrow:", width="stretch"):
            _open_demo(d["id"])

    # ---- 自分の案件 ----
    section("自分の案件で使う")
    t1, t2 = st.tabs(["新しい案件を作る", "保存した案件を開く"])
    with t1:
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        name = c1.text_input("案件名", placeholder="例：勤怠管理サービスの導入", key="new_project_name")
        if c2.button("作成する", icon=":material/add:", disabled=not name.strip(), width="stretch"):
            st.session_state.pop("tour", None)
            state.set_project(new_project(name.strip()))
            state.flash("新しい案件を作成しました。まず製品の情報を登録してください。")
            state.goto("project")
    with t2:
        up = st.file_uploader("ReadyProof AI で保存した JSON ファイル", type=["json"], key="home_load")
        if up is not None and st.button("開く", icon=":material/folder_open:"):
            try:
                p = from_json_bytes(up.getvalue())
            except LoadError as e:
                st.error(f"開けませんでした：{e}（今の作業はそのままです）")
            else:
                st.session_state.pop("tour", None)
                state.set_project(p)
                state.flash("案件を開きました。資料・録画の元ファイルは含まれていません。")
                state.goto("decision")
    st.caption("公開版では、外部に送ってよい資料・録画（または匿名化した情報）だけを使ってください。"
               "認証はなく、作業者名は自己申告です。AI に文字を送る前には、送信先と内容を必ず表示します。")
