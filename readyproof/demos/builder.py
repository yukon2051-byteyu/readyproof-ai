"""3件の無料デモ（架空の会社・製品・人物・資料・録画）。

- 資料は実際の読込部品（ingest）でサンプルファイルを読み込む
- 画面のデモ（build）：AI の結果は、事前に本物のAIで作って保存したもの（画面表示時に有料APIは呼ばない）
- 筋書き版（build_scenario）：手で作った結果。業務ルールの自動テスト用
- 状態の変更は業務ルール層（rules）を通すので、本番と同じ検証がかかる
"""
from __future__ import annotations

import json
import os

from ..config import Limits
from ..core import find, new_project
from ..ingest import ingest_bytes
from ..logic import rules
from ..logic.recordings import apply_speaker_map, build_utterances
from ..media.subtitles import parse_transcript

FILES = os.path.join(os.path.dirname(__file__), "files")
DEMO = "準備済みのデモ結果"

DEMOS = [
    {
        "id": "demo1",
        "title": "経費精算サービスの導入",
        "business": "経費の申請・承認（経理部）",
        "theme": "PowerPoint 資料と社内規程を照合し、標準機能・設定・情報不足を見分ける",
        "highlights": ["スライドの表から根拠を引用（金額別承認は設定で対応見込み）",
                       "自己承認の禁止は資料に記載なし → 質問 → 回答で更新",
                       "ノート・非表示スライドは初期状態で分析対象外",
                       "9,999円／10,000円の境界値テスト → 設定漏れで不合格 → 設定変更依頼 → 再テスト合格"],
        "strength": "PowerPoint の根拠追跡、境界値、設定変更での解決",
        "start_page": "diagnosis",
    },
    {
        "id": "demo2",
        "title": "製造業の生産・在庫管理システムの導入",
        "business": "ロットトレーサビリティ・現場の実績入力（製造部・品質保証部）",
        "theme": "現場の作業方法とパッケージ仕様の差を整理し、追加対応の依頼へつなげる",
        "highlights": ["機能一覧の「ロット管理 ○」だけでは詳細要件の適合を確定しない",
                       "複数原材料ロットは有償オプションが条件 → 追加対応の検討",
                       "オフライン入力は記載不足 → 質問 → 回答で「対応不可の記載あり」へ更新",
                       "標準設定・運用変更・追加開発の候補を比較し、改修依頼書（費用は未回答のまま）",
                       "登録・検索・誤登録訂正・境界値のテスト（一部合格でも要件全体は未確認）"],
        "strength": "製造現場の要件整理、抽象的な機能説明の見極め、改修依頼と受入条件",
        "start_page": "diagnosis",
    },
    {
        "id": "demo3",
        "title": "社内アカウント管理サービスの導入",
        "business": "退職者のアカウント停止・管理者操作履歴（情報システム部）",
        "theme": "Webミーティングの営業発言と資料を照合し、条件や矛盾を確認する",
        "highlights": ["自社の質問を営業の確約と誤認しない（話者は人が確認）",
                       "「上位プランで対応」を標準プランの機能として扱わない",
                       "資料（スタンダードから利用可）と営業説明（上位プランのみ）の矛盾を表示",
                       "「確認して回答します」は未回答、「予定」は将来予定として区別",
                       "発言時刻と引用付きの書面確認の質問を作成"],
        "strength": "営業説明のエビデンス化、条件付き回答、プラン差・未回答・矛盾の管理",
        "start_page": "sources",
    },
]

# 各デモの期待結果と確認ポイント（自動テストでも使う）
EXPECTED = {
    "demo1": {
        "categories": {"REQ-001": "標準設定で対応できる見込み", "REQ-002": "標準設定で対応できる見込み"},
        "checks": ["ノート2件・非表示スライドが分析対象外", "T-002 は不合格→再テスト合格の履歴が残る",
                   "自己承認の禁止（T-003）は未実施のため実機未確認", "代理承認（REQ-003）は要件が未確定"],
    },
    "demo2": {
        "categories": {"REQ-001": "そのまま対応できる見込み", "REQ-002": "追加対応の検討が必要",
                       "REQ-003": "対応不可との記載・確認済み発言あり", "REQ-004": "そのまま対応できる見込み"},
        "checks": ["REQ-003 の旧診断（情報不足）が履歴に残る", "改修依頼の費用・工数は未回答（0円にしない）",
                   "T-004 は実施不能で合否に数えない", "T-003 不合格", "REQ-002 は一部合格でも実機未確認"],
    },
    "demo3": {
        "categories": {"REQ-001": "根拠間に矛盾あり", "REQ-002": "情報不足・ベンダー確認が必要"},
        "checks": ["U001・U003 は自社担当者の質問", "U004 は未回答・調査中、U005 は将来予定",
                   "U006・U007 は未確認の文字起こし", "書面確認の質問に時刻と引用が入る", "テストはすべて未実施"],
    },
}

REVIEWER = "デモ確認者（架空）"


def _read(name: str) -> bytes:
    with open(os.path.join(FILES, name), "rb") as f:
        return f.read()


def _source(project, fname, **meta):
    res = ingest_bytes(fname, _read(fname), Limits()).to_dict()
    return rules.add_source(project, res, {"file_name": fname, **meta})


def ev_src(project, src, needle, kind="資料の記載"):
    seg = next((g for g in src["segments"] if needle in g["text"]), None)
    if seg is None:
        raise ValueError(f"デモ根拠が見つかりません：{needle}")
    return {"ref_type": "source", "source_id": src["id"], "version": src["version"], "seg_id": seg["seg_id"],
            "quote": needle, "kind": kind}


def ev_utt(rec, utt_id, quote):
    return {"ref_type": "utterance", "rec_id": rec["id"], "rec_version": rec["version"], "utt_id": utt_id,
            "quote": quote, "kind": "営業・ベンダーの説明"}


def _req(project, **f):
    r = rules.add_requirement(project, f, origin=DEMO)
    return r


def _review(project, dg, comment=""):
    rules.review_diagnosis(project, dg, REVIEWER, "人が確認済み", comment)


def _test(project, req_ids, confirm=True, **f):
    t = rules.add_test(project, {"req_ids": req_ids, "expected_confirmed": confirm, **f}, origin=DEMO)
    if confirm:
        rules.confirm_test(project, t, REVIEWER)
    return t


def _run(project, t, result, actual, tester="デモ実施者（架空）", status="完了", **extra):
    return rules.record_run(project, t, {"tester": tester, "status": status, "result": result, "actual": actual,
                                         "executed_at": extra.pop("at", "2026-10-28T10:00:00+09:00"), **extra})


# ======================================================================
def build_demo1(inputs_only: bool = False) -> dict:
    p = new_project("【デモ1】経費精算サービスの導入（架空）", demo_id="demo1")
    p["project"].update({"target_business": "経費の申請・承認", "purpose": "紙とExcelの経費精算をクラウドに移行し、承認ルールを統制する",
                         "department": "経理部（架空）", "constraints": "2027年4月稼働。既存の経費精算規程は変更しない前提"})
    prod = {"id": "PR-001", "name": "ケイヒナビ Cloud（架空）", "vendor": "みらい業務システム株式会社（架空）",
            "plan": "スタンダード", "edition": "2026年10月版", "delivery": "SaaS", "as_of": "2026-10", "notes": ""}
    p["products"].append(prod)
    p["id_counters"]["products"] = 1
    deck = _source(p, "demo1_keihinavi_proposal.pptx", name="ケイヒナビ Cloud ご提案資料（架空）", kind="ベンダー提案書",
                   product_id="PR-001", received_on="2026-10-10", plan="全プラン")
    rules_doc = _source(p, "demo1_expense_rules.docx", name="経費精算規程（抜粋・架空）", kind="その他", owner="自社")

    r1 = _req(p, business="経費申請の承認", workflow="申請金額に応じて承認者を切り替える", role="申請者・上司・部長",
              rules="10,000円未満は直属の上司が承認する。10,000円以上は直属の上司の承認後に部長が承認する。",
              exceptions="", priority="必須", reason="経費精算規程 第3条",
              basis="経費精算規程 第3条1・2", original_text="経費申請の金額が10,000円未満の場合は、申請者の直属の上司が承認する。"
              "経費申請の金額が10,000円以上の場合は、直属の上司が承認した後、部長が承認する。")
    r2 = _req(p, business="経費申請の承認", workflow="申請者本人による承認を防ぐ", role="全利用者",
              rules="申請者本人が自分の申請を承認すること（自己承認）は禁止する。", priority="必須",
              reason="内部統制（不正防止）", basis="経費精算規程 第3条3",
              original_text="申請者本人が自分の申請を承認すること（自己承認）は禁止する。")
    r3 = _req(p, business="代理承認", workflow="上司不在時に代理者が承認する", role="代理承認者",
              rules="代理承認の条件は未確定", priority="望ましい", reason="承認の停滞防止",
              open_issues="代理承認の条件（誰が・いつ・金額上限）が経理部で検討中",
              original_text="上司が不在の場合の代理承認の条件は、経理部で検討中であり未確定とする。")
    for r in (r1, r2):
        rules.confirm_requirement(p, r, "経理部 佐藤（架空）")
    if inputs_only:  # 固定の入力（資料・録画・自社の要件）だけ
        return p

    d1 = rules.add_diagnosis(p, {
        "req_id": r1["id"], "product_id": "PR-001", "category": "標準設定で対応できる見込み",
        "reason": "金額条件で承認ルートを切り替える機能があり、表の設定例が自社ルール（10,000円未満／以上）と一致する。初期値ではなく設定が必要。",
        "met_conditions": ["金額条件による承認ルートの切り替え", "10,000円以上で上長→部長の2段階承認（設定例）"],
        "remaining_conditions": [],
        "evidence": [ev_src(p, deck, "金額条件と承認者は管理画面の「承認ルート設定」で設定します（スタンダードプラン以上）"),
                     ev_src(p, deck, "10,000円以上 | 承認ルート（設定例）: 上長 → 部長"),
                     ev_src(p, deck, "金額別の承認ルート、代理承認")],
        "plan_conditions": "スタンダードプラン以上（検討中のプランはスタンダード）", "constraints": "設定例は導入時に設定が必要",
        "next_check": "境界の 10,000円ちょうどが「以上」側になる設定かをテストで確認する",
    }, origin=DEMO)
    _review(p, d1, "表の設定例と規程が一致。境界値はテストで確認する。")

    d2a = rules.add_diagnosis(p, {
        "req_id": r2["id"], "product_id": "PR-001", "category": "情報不足・ベンダー確認が必要",
        "reason": "承認者の自動設定の記載はあるが、申請者本人の承認を禁止できるかの記載がない（記載がない＝対応不可ではない）。",
        "met_conditions": [], "remaining_conditions": ["上長本人が申請した場合に自己承認を禁止できるか"],
        "evidence": [ev_src(p, deck, "承認者は申請者の所属部門の上長が自動で設定されます。")],
        "next_check": "ベンダーに自己承認の禁止設定の有無を質問する",
    }, origin=DEMO)
    q1 = rules.add_question(p, {"req_ids": [r2["id"]], "diag_id": d2a["id"],
                                "background": "社内規程で自己承認を禁止しています。資料には承認者の自動設定のみ記載があります。",
                                "question": "上長本人が経費を申請した場合に、本人が自分の申請を承認できないように設定できますか。",
                                "points": "・設定の有無と設定場所\n・対象プラン\n・追加費用の有無"}, origin=DEMO)
    q1["status"] = "確定"
    rules.mark_question_sent(p, q1, "情報システム部 田中（架空）", "2026-10-14")
    rules.record_answer(p, q1, "承認ルート設定の「申請者本人による承認を禁止」をオンにすると、自己承認を禁止できます。スタンダードプランの標準機能です。",
                        "手動入力", "2026-10-17", "情報システム部 田中（架空）")
    rules.confirm_answer(p, q1, REVIEWER, "メール回答を確認。テストで実機確認が必要。")
    d2 = rules.add_diagnosis(p, {
        "req_id": r2["id"], "product_id": "PR-001", "category": "標準設定で対応できる見込み",
        "reason": "ベンダー回答で、標準機能の設定により自己承認を禁止できると確認（回答による見込み。実機未確認）。",
        "met_conditions": ["自己承認の禁止設定（ベンダー回答）"], "remaining_conditions": [],
        "evidence": [{"ref_type": "answer", "question_id": q1["id"], "quote": "自己承認を禁止できます", "kind": "ベンダー回答"}],
        "next_check": "自己承認ができないことを実機テストで確認する",
    }, origin=DEMO)
    _review(p, d2, "回答確認済み。実機テスト T-003 で確認する。")
    rules.add_action(p, {"req_id": r3["id"], "type": "社内ルールの確認・見直し",
                         "reason": "代理承認の条件が社内で未確定のため、製品の機能確認より先に経理部の決定が必要",
                         "unknowns": "代理者の範囲・期間・金額上限"}, origin=DEMO)

    t1 = _test(p, [r1["id"]], title="9,999円の申請は上司の承認だけで完了する", viewpoint="境界値", role="申請者・上司",
               purpose="10,000円未満の承認ルート", preconditions="承認ルート設定済み。申請者・上司・部長のテスト用アカウント",
               inputs="申請金額 9,999円", steps="1. 申請者で9,999円の経費を申請\n2. 上司で承認\n3. 申請の状態を確認",
               expected="上司の承認で「承認済み」になり、部長には承認依頼が届かない", expected_basis="経費精算規程 第3条1",
               importance="高", importance_reason="承認漏れ・過剰承認の防止")
    t2 = _test(p, [r1["id"]], title="10,000円の申請は上司と部長の承認が必要", viewpoint="境界値", role="申請者・上司・部長",
               purpose="10,000円以上の承認ルート（境界ちょうど）", preconditions="T-001 と同じ", inputs="申請金額 10,000円",
               steps="1. 申請者で10,000円の経費を申請\n2. 上司で承認\n3. 状態を確認\n4. 部長で承認",
               expected="上司の承認後は「部長承認待ち」になり、部長の承認で「承認済み」になる", expected_basis="経費精算規程 第3条2",
               importance="高", importance_reason="境界値の誤設定が起きやすい")
    t3 = _test(p, [r2["id"]], title="上長本人の申請を本人が承認できない", viewpoint="権限", role="上長",
               purpose="自己承認の禁止", preconditions="「申請者本人による承認を禁止」をオン", inputs="上長が自分で申請",
               steps="1. 上長アカウントで申請\n2. 同じ上長アカウントで承認一覧を開く",
               expected="自分の申請が承認対象に表示されない、または承認操作でエラーになる", expected_basis="経費精算規程 第3条3・Q-001回答",
               importance="高", importance_reason="内部統制")
    _test(p, [r1["id"]], title="部長が差し戻すと申請者に戻る", viewpoint="承認・差し戻し", role="部長・申請者",
          purpose="差し戻しの動作", preconditions="10,000円以上の申請が部長承認待ち", inputs="差し戻し理由「領収書不足」",
          steps="1. 部長で差し戻し\n2. 申請者で申請一覧を確認", expected="申請が「差し戻し」状態で申請者に戻り、理由が表示される",
          expected_basis="業務フロー", importance="中", importance_reason="通常業務で発生")

    _run(p, t1, "合格", "上司の承認で承認済みになった。部長への依頼なし。", product_version="2026年10月版", plan="スタンダード",
         environment="検証テナント")
    run2 = _run(p, t2, "不合格", "10,000円の申請が上司の承認だけで「承認済み」になった。承認ルート設定の条件が「10,000円を超える」になっていた。",
                product_version="2026年10月版", plan="スタンダード", environment="検証テナント",
                defect="承認ルートの金額条件が「超」になっている（設定漏れ）")
    cr = rules.add_request(p, {
        "title": "承認ルートの金額条件を「10,000円以上」に変更", "kind": "設定変更依頼", "phase": "テストで発生した現象",
        "to": "みらい業務システム 導入支援担当（架空）", "background": "受入テスト T-002 で、10,000円ちょうどの申請が部長承認なしで完了した。",
        "purpose": "経費精算規程 第3条2（10,000円以上は部長承認）を満たす", "req_ids": [r1["id"]], "diag_ids": [d1["id"]],
        "test_ids": [t2["id"]], "run_ids": [run2["id"]],
        "spec_in_docs": "スライド2：金額条件と承認者は承認ルート設定で設定する。設定例「10,000円以上 上長→部長」",
        "actual_behavior": run2["actual"], "conditions": "申請金額がちょうど10,000円", "repro_steps": t2["steps"],
        "needed_behavior": "10,000円以上（10,000円を含む）で部長承認が必要になる", "gap": "境界の10,000円が「未満」側に入っている",
        "impact": "部長承認が必要な申請が承認なしで支払われる", "scope": "承認ルート設定の金額条件のみ", "out_of_scope": "承認画面の変更",
        "priority": "高", "priority_reason": "規程違反の支払いにつながる", "desired_date": "2026-11-15",
        "desired_date_reason": "11月の並行稼働に間に合わせる", "assumptions": "設定変更のみで対応できる想定（要確認）",
        "questions_to_vendor": "設定変更で対応可能か。他の承認ルートへの影響はあるか。",
        "acceptance_criteria": "・9,999円：上司のみで承認完了\n・10,000円：上司→部長の承認が必要\n・既存の差し戻し動作に影響がない",
        "test_candidates": "T-001、T-002、差し戻しテスト", "evidence": [ev_src(p, deck, "10,000円以上 | 承認ルート（設定例）: 上長 → 部長")],
    }, origin=DEMO)
    by = "情報システム部 田中（架空）"
    for st in ("確定", "送付済み", "回答待ち", "対応中"):
        rules.change_request_status(p, cr, st, by)
    rules.record_vendor_response(p, cr, {"answer": "設定値を「10,000円以上」に修正しました。", "settings_possible": "可能",
                                         "modification_needed": "不要（設定変更）", "cost_amount": "", "effort": "",
                                         "vendor_done": True}, by)
    rules.change_request_status(p, cr, "テスト待ち", by)
    _run(p, t2, "合格", "10,000円の申請は上司承認後に部長承認待ちになり、部長承認で承認済みになった。",
         product_version="2026年10月版", plan="スタンダード", environment="検証テナント", at="2026-10-30T15:00:00+09:00")
    rules.change_request_status(p, cr, "完了", by, "再テスト T-002 合格を確認")
    _ = (rules_doc, t3)
    return p


# ======================================================================
def build_demo2(inputs_only: bool = False) -> dict:
    p = new_project("【デモ2】生産・在庫管理システムの導入（架空）", demo_id="demo2")
    p["project"].update({"target_business": "製造実績・ロットトレーサビリティ", "purpose": "品質問題発生時に、製品ロットから原材料ロットを即時に追跡する",
                         "department": "製造部・品質保証部（架空）", "constraints": "一部工程（屋外の倉庫棟）は通信が不安定"})
    p["products"].append({"id": "PR-001", "name": "ツクルン生産管理（架空）", "vendor": "東和ファクトリーソリューションズ株式会社（架空）",
                          "plan": "標準パッケージ", "edition": "v5.2", "delivery": "オンプレミス", "as_of": "2026-10",
                          "notes": "オプション「マルチロット投入」は見積依頼中"})
    p["id_counters"]["products"] = 1
    pdf = _source(p, "demo2_tsukurun_overview.pdf", name="ツクルン生産管理 製品説明（架空）", kind="製品説明", product_id="PR-001",
                  issued_on="2026-09-01", plan="標準パッケージ")
    xls = _source(p, "demo2_feature_list.xlsx", name="ツクルン生産管理 機能一覧（架空）", kind="機能一覧", product_id="PR-001",
                  issued_on="2026-09-01")
    ans = _source(p, "demo2_vendor_answers.txt", name="ご質問への回答書（架空）", kind="質問と回答", product_id="PR-001",
                  received_on="2026-10-20")
    mk = lambda **f: _req(p, **f)
    r1 = mk(business="ロットトレーサビリティ", workflow="製品ロット番号から使用した原材料ロットを検索する", role="品質保証担当",
            rules="製品ロット番号を入力すると、使用したすべての原材料ロットが表示されること", priority="必須", reason="品質問題時の回収範囲の特定",
            original_text="製品ロットから使用原材料ロットを追跡したい。")
    r2 = mk(business="製造実績入力", workflow="1つの製造ロットに複数の原材料ロットを記録する", role="製造オペレーター",
            rules="1つの製造ロットに原材料ロットを複数（最大15件程度）記録できること", priority="必須",
            reason="配合工程で複数ロットを投入する", original_text="1つの製造ロットに複数の原材料ロットを記録したい。")
    r3 = mk(business="製造実績入力", workflow="通信が不安定な工程での実績記録", role="製造オペレーター",
            rules="通信が切れても実績の記録が失われないこと", priority="必須", reason="倉庫棟はWi-Fiが不安定",
            open_issues="記録方法（端末で一時保存／紙で後入力）は検討が必要",
            original_text="一部工程は通信が不安定なため、記録方法の検討が必要。")
    r4 = mk(business="ロット訂正", workflow="誤登録した原材料ロットを訂正し、訂正前の内容を残す", role="製造リーダー",
            rules="訂正前のロット番号・訂正者・訂正日時を履歴として保持すること", priority="必須", reason="品質記録の改ざん防止",
            original_text="誤登録を訂正でき、履歴が残ること。")
    for r in (r1, r2, r3, r4):
        rules.confirm_requirement(p, r, "品質保証部 山本（架空）")
    if inputs_only:  # 固定の入力（資料・録画・自社の要件）だけ
        return p

    d1 = rules.add_diagnosis(p, {
        "req_id": r1["id"], "product_id": "PR-001", "category": "そのまま対応できる見込み",
        "reason": "製品説明に、製品ロット番号から原材料ロットを検索できると明記。機能一覧も標準機能。",
        "met_conditions": ["製品ロット→原材料ロットの検索（標準）"], "remaining_conditions": [],
        "evidence": [ev_src(p, pdf, "製品ロット番号から、製造に使用した原材料ロットを検索できます。"),
                     ev_src(p, xls, "機能: トレーサビリティ | 提供: ○ | 標準/オプション: 標準")],
        "next_check": "複数ロット投入時にすべて表示されるかはテストで確認",
    }, origin=DEMO)
    _review(p, d1)
    d2 = rules.add_diagnosis(p, {
        "req_id": r2["id"], "product_id": "PR-001", "category": "追加対応の検討が必要",
        "reason": "機能一覧の「ロット管理 ○」だけでは複数ロットの記録可否は判断できない。製品説明では標準は1指図1ロットで、複数ロットは有償オプションが必要。",
        "met_conditions": ["有償オプションで1指図あたり最大20ロット"],
        "remaining_conditions": ["標準パッケージでは1件のみ（オプション契約が必要）", "オプション費用は未提示"],
        "evidence": [ev_src(p, pdf, "標準機能では、1つの製造指図に対して原材料ロットを1件登録します。"),
                     ev_src(p, pdf, "有償オプション「マルチロット投入」が必要です（1指図あたり最大20ロット）。"),
                     ev_src(p, xls, "機能: マルチロット投入 | 提供: ○ | 標準/オプション: オプション")],
        "plan_conditions": "有償オプション「マルチロット投入」", "next_check": "オプション費用の見積を依頼する",
    }, origin=DEMO)
    _review(p, d2, "「ロット管理あり」は抽象的な記載のため根拠にしない。")
    d3a = rules.add_diagnosis(p, {
        "req_id": r3["id"], "product_id": "PR-001", "category": "情報不足・ベンダー確認が必要",
        "reason": "資料にはWi-Fi接続での利用のみ記載。オフライン時の扱いの記載がない（記載がない＝対応不可ではない）。",
        "met_conditions": [], "remaining_conditions": ["通信断時に実績を記録できるか"],
        "evidence": [ev_src(p, pdf, "タブレット端末は工場内のWi-Fiに接続して利用します。")],
        "next_check": "オフライン入力の可否を質問する",
    }, origin=DEMO)
    q1 = rules.add_question(p, {"req_ids": [r3["id"]], "diag_id": d3a["id"],
                                "background": "倉庫棟はWi-Fiが不安定です。資料にはWi-Fi接続での利用のみ記載があります。",
                                "question": "通信が不安定な工程で、オフラインのまま実績を入力できますか。",
                                "points": "・オフライン入力の可否\n・通信復旧後の同期方法\n・対応できない場合の代替策"}, origin=DEMO)
    q1["status"] = "確定"
    rules.mark_question_sent(p, q1, "情報システム部 小林（架空）", "2026-10-15")
    rules.record_answer(p, q1, "現行版ではオフラインでの実績入力には対応していません。通信復旧後に一括登録する機能は次期バージョンで検討中です。",
                        "資料", "2026-10-20", "情報システム部 小林（架空）",
                        evidence=[ev_src(p, ans, "現行版ではオフラインでの実績入力には対応していません。", kind="ベンダー回答")])
    rules.confirm_answer(p, q1, REVIEWER, "回答書（DOC-003）で確認。次期バージョンは将来予定のため評価に含めない。")
    d3 = rules.add_diagnosis(p, {
        "req_id": r3["id"], "product_id": "PR-001", "category": "対応不可との記載・確認済み発言あり",
        "reason": "ベンダー回答書に、現行版はオフライン入力に対応していないと明記。次期バージョンの検討は将来予定で現時点の機能ではない。",
        "met_conditions": [], "remaining_conditions": ["オフライン時の記録方法"],
        "evidence": [ev_src(p, ans, "現行版ではオフラインでの実績入力には対応していません。", kind="ベンダー回答"),
                     ev_src(p, ans, "個別開発としてお見積りが可能です。", kind="ベンダー回答")],
        "next_check": "対応方法（運用・追加開発）を比較する",
    }, origin=DEMO)
    _review(p, d3)
    d4 = rules.add_diagnosis(p, {
        "req_id": r4["id"], "product_id": "PR-001", "category": "そのまま対応できる見込み",
        "reason": "製品説明に訂正と履歴保持の記載。回答書でマルチロット投入時も訂正者・日時を記録すると回答。",
        "met_conditions": ["訂正できる", "訂正前の内容を履歴として保持"], "remaining_conditions": [],
        "evidence": [ev_src(p, pdf, "誤って登録したロットは訂正でき、訂正前の内容は履歴として保持されます。"),
                     ev_src(p, ans, "訂正前のロット番号、訂正者、訂正日時を記録します。", kind="ベンダー回答")],
        "next_check": "訂正履歴の内容をテストで確認",
    }, origin=DEMO)
    _review(p, d4)

    by = "製造部 中村（架空）"
    a = rules.add_action(p, {"req_id": r2["id"], "diag_id": d2["id"], "type": "機能追加・カスタマイズ",
                             "reason": "有償オプション「マルチロット投入」を契約する（パッケージ標準のオプション）", "unknowns": "オプション費用"}, origin=DEMO)
    rules.decide_action(p, a, "採用", by, "配合工程で複数ロット投入は必須のため")
    a = rules.add_action(p, {"req_id": r2["id"], "diag_id": d2["id"], "type": "手順・教育の改善",
                             "reason": "製造指図をロットごとに分割して1指図1ロットで運用する", "unknowns": ""}, origin=DEMO)
    rules.decide_action(p, a, "不採用", by, "指図が数倍に増え、現場負担が大きい")
    a = rules.add_action(p, {"req_id": r3["id"], "diag_id": d3["id"], "type": "手順・教育の改善",
                             "reason": "通信断時は紙の記録票に記入し、復旧後に入力する", "unknowns": "入力漏れの防止策"}, origin=DEMO)
    rules.decide_action(p, a, "採用", by, "稼働時の暫定運用として採用")
    a = rules.add_action(p, {"req_id": r3["id"], "diag_id": d3["id"], "type": "機能追加・カスタマイズ",
                             "reason": "端末内に一時保存し、通信復旧後に送信する機能の個別開発", "unknowns": "費用・期間（未提示）"}, origin=DEMO)
    rules.decide_action(p, a, "採用", by, "恒久対応として見積を依頼する")
    rules.add_action(p, {"req_id": r3["id"], "diag_id": d3["id"], "type": "外部連携・別手段",
                         "reason": "倉庫棟のWi-Fi増設（製品外の対応）", "unknowns": "設備工事の可否"}, origin=DEMO)

    cr = rules.add_request(p, {
        "title": "通信断時の実績入力（端末内一時保存と復旧後の送信）", "kind": "改修依頼", "phase": "資料診断段階の懸念",
        "to": "東和ファクトリーソリューションズ 営業担当（架空）", "background": "倉庫棟は通信が不安定。回答書で現行版はオフライン入力非対応と確認。",
        "purpose": "通信断時にも製造実績を失わずに記録する", "req_ids": [r3["id"]], "diag_ids": [d3["id"]], "question_ids": [q1["id"]],
        "spec_in_docs": "タブレット端末は工場内のWi-Fiに接続して利用（製品説明3ページ）",
        "sales_explanation": "回答書：現行版はオフライン入力非対応。次期バージョンで一括登録を検討中（将来予定）。",
        "actual_behavior": "", "needed_behavior": "通信断中も実績を端末に保存し、復旧後に重複なく送信できる",
        "gap": "現行版は通信断時に入力できない", "impact": "倉庫棟の実績記録が漏れ、トレーサビリティが途切れる",
        "scope": "実績入力画面（倉庫棟で使用する工程のみ）", "out_of_scope": "Wi-Fi設備の工事", "priority": "高",
        "priority_reason": "必須要件で、暫定運用（紙）は入力漏れのリスクがある", "desired_date": "", "desired_date_reason": "見積後に決定",
        "assumptions": "費用・期間・実装方式はベンダー提示待ち（このアプリでは想定しない）",
        "questions_to_vendor": "・対応可否と方式\n・費用と期間\n・次期バージョンの一括登録との関係",
        "acceptance_criteria": "・通信断中に入力した実績が端末に保存される\n・復旧後に送信され、二重登録されない\n・送信前の実績は端末で一覧確認できる\n・既存の実績入力の動作に影響がない",
        "test_candidates": "通信断→入力→復旧→送信、二重送信防止、既存入力の再確認",
        "evidence": [ev_src(p, ans, "現行版ではオフラインでの実績入力には対応していません。", kind="ベンダー回答")],
    }, origin=DEMO)
    by2 = "情報システム部 小林（架空）"
    for st in ("確定", "送付済み", "回答待ち"):
        rules.change_request_status(p, cr, st, by2)
    rules.record_vendor_response(p, cr, {"answer": "個別開発として対応可能。費用と期間は要件確認後に提示予定。", "settings_possible": "不可",
                                         "modification_needed": "必要", "cost_amount": "", "effort": ""}, by2)
    rules.change_request_status(p, cr, "対応検討中", by2)

    t1 = _test(p, [r2["id"]], title="1つの製造ロットに原材料ロットを3件登録できる", viewpoint="通常操作", role="製造オペレーター",
               purpose="複数ロット投入", preconditions="マルチロット投入オプションを有効化した検証環境", inputs="原材料ロット M-001, M-002, M-003",
               steps="1. 製造指図を開く\n2. 原材料ロットを3件登録\n3. 保存", expected="3件すべてが製造ロットに紐づいて保存される",
               expected_basis="REQ-002", importance="高", importance_reason="必須要件")
    t2 = _test(p, [r1["id"]], title="製品ロットから原材料ロット3件を検索できる", viewpoint="通常操作", role="品質保証担当",
               purpose="トレーサビリティ", preconditions="T-001 の登録済みデータ", inputs="製品ロット番号",
               steps="1. トレーサビリティ検索を開く\n2. 製品ロット番号を入力して検索", expected="原材料ロット M-001〜M-003 がすべて表示される",
               expected_basis="REQ-001", importance="高", importance_reason="回収範囲の特定")
    t3 = _test(p, [r4["id"]], title="誤登録した原材料ロットを訂正すると履歴が残る", viewpoint="例外・エラー", role="製造リーダー",
               purpose="訂正と履歴保持", preconditions="M-002 を誤って登録済み", inputs="M-002 → M-012 に訂正",
               steps="1. 実績を開きロットを訂正\n2. 履歴を表示", expected="訂正前ロット番号・訂正者・訂正日時が履歴に表示される",
               expected_basis="REQ-004・回答書A2", importance="高", importance_reason="品質記録")
    t4 = _test(p, [r2["id"]], title="21件目の原材料ロットは登録できない（上限20件）", viewpoint="境界値", role="製造オペレーター",
               purpose="上限の確認", preconditions="オプション有効", inputs="原材料ロット21件",
               steps="1. 20件登録\n2. 21件目を登録", expected="20件まで登録でき、21件目はエラーメッセージが表示される",
               expected_basis="製品説明2ページ（最大20ロット）", importance="中", importance_reason="現場の最大は15件程度")
    _test(p, [r3["id"]], confirm=False, title="通信断中に入力した実績が復旧後に送信される", viewpoint="設定・改修箇所",
          role="製造オペレーター", purpose="改修依頼 CR-001 の受入", preconditions="改修版が導入された検証環境",
          inputs="通信を切断した端末", steps="1. 端末の通信を切る\n2. 実績を入力（保存方法は要確認）\n3. 通信を戻す",
          expected="送信され、二重登録されない（画面・操作は改修内容の確定後に要確認）", expected_basis="CR-001 受入条件",
          importance="高", importance_reason="必須要件", open_issues="改修方式が未確定", request_ids=[cr["id"]])

    env = dict(product_version="v5.2", plan="標準パッケージ＋マルチロット投入（評価版）", environment="ベンダー検証環境")
    _run(p, t1, "合格", "3件とも保存された。", **env)
    _run(p, t2, "合格", "原材料ロット3件が表示された。", **env)
    _run(p, t3, "不合格", "訂正前ロット番号と日時は表示されたが、訂正者が表示されなかった。", defect="訂正履歴に訂正者が記録されない",
         **env)
    _run(p, t4, "未判定", "", status="実施不能", open_points="評価版のオプション設定が上限10件で構成されており、21件目を試せない", **env)
    return p


# ======================================================================
def build_demo3(inputs_only: bool = False) -> dict:
    p = new_project("【デモ3】社内アカウント管理サービスの導入（架空）", demo_id="demo3")
    p["project"].update({"target_business": "退職者のアカウント停止・管理者の操作監査", "purpose": "退職日に確実にアカウントを停止し、操作履歴を監査に使う",
                         "department": "情報システム部（架空）", "constraints": "予算上、現在検討中の標準（スタンダード）プランで利用したい"})
    p["products"].append({"id": "PR-001", "name": "IDガード（架空）", "vendor": "ネクストID株式会社（架空）", "plan": "スタンダード",
                          "edition": "2026年版", "delivery": "SaaS", "as_of": "2026-10", "notes": ""})
    p["id_counters"]["products"] = 1
    doc = _source(p, "demo3_idguard_overview.docx", name="IDガード 製品概要（架空）", kind="製品説明", product_id="PR-001",
                  received_on="2026-10-01")

    cues, fmt = parse_transcript("demo3_sales_meeting.vtt", _read("demo3_sales_meeting.vtt").decode("utf-8"))
    rec = {"id": "REC-001", "version": 1, "file_name": "demo3_sales_meeting.mp4", "meeting_name": "IDガード 製品説明ミーティング（架空）",
           "held_on": "2026-10-15", "product_id": "PR-001", "plan": "スタンダード",
           "participants": [{"name": "田中（架空）", "role": "自社担当者"}, {"name": "鈴木（架空）", "role": "営業担当者"}],
           "duration_sec": 40.5, "range": {"start": 0.0, "end": None}, "method": f"会議ツールの文字起こし読込（{fmt}）",
           "processed_at": "2026-10-15T17:00:00+09:00", "media_retained": False, "file_sha256": "",
           "utterances": build_utterances(cues), "probe": None, "consent_confirmed": True}
    p["recordings"].append(rec)
    p["id_counters"]["recordings"] = 1
    apply_speaker_map(rec, "話者1", "自社担当者", "田中（架空）", True, REVIEWER)
    apply_speaker_map(rec, "話者2", "営業担当者", "鈴木（架空）", True, REVIEWER)
    types = {"U001": "質問", "U002": "回答（条件付き）", "U003": "質問", "U004": "未回答・調査中", "U005": "将来予定"}
    for u in rec["utterances"]:
        if u["id"] in types:
            u["utterance_type"] = types[u["id"]]
            u["review_status"] = "確認済み"
        else:  # U006・U007 は未確認のまま（未確認の文字起こしの扱いを見せる）
            u["speaker_confirmed"] = False

    r1 = _req(p, business="退職者のアカウント停止", workflow="人事から通知された退職日に、アカウントを自動で停止する", role="情報システム部 管理者",
              rules="退職日（指定日）の0時に利用停止が反映されること。手動操作の忘れを防ぐ。", priority="必須", reason="退職者による不正アクセス防止",
              original_text="退職者の利用停止を指定日に反映したい。")
    r2 = _req(p, business="管理者操作の監査", workflow="管理者の操作履歴を保持し、監査時に参照する", role="監査担当",
              rules="管理者の操作履歴を1年以上保持すること", priority="必須", reason="内部監査の要求",
              original_text="管理者による操作履歴を保持したい。")
    r3 = _req(p, business="契約プラン", workflow="現在検討中の標準プランで上記を満たす", role="情報システム部",
              rules="スタンダードプランの範囲で利用する（上位プランは予算外）", priority="必須", reason="予算",
              original_text="現在検討中の標準プランで利用したい。")
    for r in (r1, r2, r3):
        rules.confirm_requirement(p, r, "情報システム部 田中（架空）")
    if inputs_only:  # 固定の入力（資料・録画・自社の要件）だけ
        return p

    d1 = rules.add_diagnosis(p, {
        "req_id": r1["id"], "product_id": "PR-001", "category": "根拠間に矛盾あり",
        "reason": "資料は「予約停止はスタンダードプランから利用可」、営業説明（確認済み）は「予約停止は上位プラン、標準プランは手動操作」。どちらも優先せず書面で確認する。来年度の対応は将来予定で現在の機能ではない。",
        "met_conditions": ["即時の利用停止（手動）は可能"], "remaining_conditions": ["スタンダードプランで予約停止が使えるか"],
        "evidence": [ev_src(p, doc, "予約停止（指定日にアカウントを自動で停止する機能）は、スタンダードプランから利用できます。"),
                     ev_utt(rec, "U002", "予約停止は上位プランで対応しています。標準プランは手動操作です。"),
                     ev_utt(rec, "U005", "来年度には標準プランでも予約停止に対応する予定です。")],
        "plan_conditions": "営業説明では上位プランのみ（資料と矛盾）", "next_check": "書面で正式回答を得る",
    }, origin=DEMO)
    _review(p, d1, "U001 は自社の質問のため根拠にしない。")
    d2 = rules.add_diagnosis(p, {
        "req_id": r2["id"], "product_id": "PR-001", "category": "情報不足・ベンダー確認が必要",
        "reason": "操作ログの保存はあるが、保存期間はプランにより異なるとだけ記載。営業も「確認して回答」で未回答。",
        "met_conditions": ["管理者の操作ログを保存する"], "remaining_conditions": ["スタンダードプランの保存期間が1年以上か"],
        "evidence": [ev_src(p, doc, "管理者の操作ログを保存します。保存期間はプランによって異なります。"),
                     ev_utt(rec, "U004", "操作履歴の保存期間は、確認して回答します。")],
        "next_check": "保存期間を質問する（回答待ち）",
    }, origin=DEMO)
    _review(p, d2)

    rules.written_confirmation_question(p, ev_utt(rec, "U002", "予約停止は上位プランで対応しています。標準プランは手動操作です。"),
                                        [r1["id"], r3["id"]])
    q2 = rules.add_question(p, {"req_ids": [r2["id"]], "diag_id": d2["id"], "background": "ミーティングで「確認して回答します」とのことでした（00:00:19頃）。",
                                "question": "スタンダードプランでの管理者操作ログの保存期間を教えてください。",
                                "points": "・保存期間\n・期間を延長する方法と費用\n・ログの出力形式",
                                "evidence": [ev_utt(rec, "U004", "操作履歴の保存期間は、確認して回答します。")]}, origin=DEMO)
    q2["status"] = "確定"
    rules.mark_question_sent(p, q2, "情報システム部 田中（架空）", "2026-10-16")

    for typ, reason, unk in [
        ("別製品の検討", "上位プランへの変更（予算の再確認が必要）", "上位プランの費用"),
        ("手順・教育の改善", "退職日の朝に管理者が手動で停止する運用（チェックリスト化）", "停止漏れの防止策"),
        ("外部連携・別手段", "人事システムからのCSV取り込みで停止する案（営業発言は推測・未確認）", "CSV取り込みで停止できるか（要確認）"),
    ]:
        rules.add_action(p, {"req_id": r1["id"], "diag_id": d1["id"], "type": typ, "reason": reason, "unknowns": unk}, origin=DEMO)

    _test(p, [r1["id"]], title="一般利用者の権限ではアカウント停止を操作できない", viewpoint="権限", role="一般利用者",
          purpose="停止操作の権限制御", preconditions="一般利用者アカウント", inputs="", steps="1. 一般利用者でログイン\n2. 利用者管理メニューを探す",
          expected="停止操作のメニューが表示されない", expected_basis="REQ-001（管理者のみ操作）", importance="高", importance_reason="不正な停止の防止")
    _test(p, [r1["id"]], confirm=False, title="指定日の0時にアカウントが停止される", viewpoint="通常操作", role="管理者",
          purpose="予約停止", preconditions="予約停止が使えるプラン（プランは要確認）", inputs="停止日：翌日",
          steps="1. 予約停止の設定画面を開く（画面名は要確認）\n2. 停止日を指定\n3. 翌日0時以降にログインを試す",
          expected="0時以降はログインできない", expected_basis="REQ-001", importance="高", importance_reason="必須要件",
          open_issues="スタンダードプランで使えるか書面確認待ち")
    _test(p, [r2["id"]], title="停止操作が操作履歴に記録される", viewpoint="既存動作の再確認", role="管理者・監査担当",
          purpose="操作履歴", preconditions="管理者アカウント", inputs="テスト用アカウントを停止",
          steps="1. 管理者でテスト用アカウントを停止\n2. 操作ログを表示", expected="操作者・日時・対象アカウントが記録されている",
          expected_basis="REQ-002", importance="高", importance_reason="監査要件")
    return p


BUILDERS = {"demo1": build_demo1, "demo2": build_demo2, "demo3": build_demo3}


def build_scenario(demo_id: str) -> dict:
    """手で作った筋書き（質問・回答・不合格→再テストなど）を含む版。業務ルールの自動テスト用。"""
    return BUILDERS[demo_id]()


def build_inputs(demo_id: str) -> dict:
    """デモの固定の入力だけ（資料・録画・自社の要件）。"""
    return BUILDERS[demo_id](inputs_only=True)


def build(demo_id: str) -> dict:
    """画面で使うデモ：固定の入力 ＋ 事前に本物のAI（Claude）で作った出力（診断結果・テスト仕様）。"""
    from .ai_outputs import apply_saved

    p = build_inputs(demo_id)
    apply_saved(p, demo_id)
    return p


def demo_info(demo_id: str) -> dict:
    return next(d for d in DEMOS if d["id"] == demo_id)


def recording_path(demo_id: str) -> str | None:
    return os.path.join(FILES, "demo3_sales_meeting.mp4") if demo_id == "demo3" else None


def cues_json() -> list:
    with open(os.path.join(FILES, "demo3_cues.json"), encoding="utf-8") as f:
        return json.load(f)


__all__ = ["DEMOS", "EXPECTED", "build", "build_inputs", "build_scenario", "demo_info", "find"]
