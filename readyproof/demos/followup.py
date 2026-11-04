"""デモを「完了した案件の見本」にするための、人の作業の記録（すべて架空）。

AIの出力（診断結果・テスト仕様・質問・対応方法の候補）は ai_results のまま変えない。
ここにあるのは、AIの出力のあとに人が行う作業の見本：
  ベンダーへの質問の送付と回答 → 回答の確認 → 診断の確認（区分の見直し）
  → 「要確認」が残るテストの修正・確定 → 実機テストの結果（不合格→再テストを含む）
  → 対応方法の採否 → 導入判断
画面・Excel では、記録した人の名前に（架空）を付けて、人の記録であることが分かるようにする。
"""
from __future__ import annotations

from ..core import find, now_iso
from ..logic import metrics as M
from ..logic import rules
from ..logic.stale import decision_snapshot

PASS_TEXT = "期待結果のとおりに動作した。画面の記録を保存した。"

FOLLOWUP = {
    "demo1": {
        "sender": "情報システム部 田中（架空）", "reviewer": "経理部 佐藤（架空）", "tester": "経理部 鈴木（架空）",
        "answers": {
            "Q-001": "部長は組織マスタの「部門長」から自動で割り当てられます。兼務者は、主務の部門の上長・部門長が承認者になります。"
                     "承認者を個別に指定することもできます（スタンダードプランの標準機能）。",
            "Q-002": "金額条件は「以上／超」を選んで設定します。10,000円ちょうどを部長承認にする場合は「以上」を選んでください。"
                     "判定に使う金額は税込金額です。",
            "Q-003": "承認ルート設定の「申請者本人による承認を禁止」をオンにすると、上長・部長本人の申請、代理承認、"
                     "手動設定のいずれでも、本人は承認できなくなります。スタンダードプランの標準機能です。",
        },
        "reviews": {
            "REQ-001": ("標準設定で対応できる見込み", "Q-001・Q-002の回答で、部長の自動割当と「以上」の設定ができると確認。実機テストで確認する。"),
            "REQ-002": ("標準設定で対応できる見込み", "Q-003の回答で、自己承認を禁止する設定があると確認。実機テストで確認する。"),
        },
        "runs": {
            "T-003": [("不合格", "10,000円ちょうどの申請が、上司の承認だけで完了した。金額条件が「超」で設定されていた。",
                       "承認ルートの金額条件が「超」になっていた（設定漏れ）"),
                      ("合格", "金額条件を「以上」に直して再テスト。9,999円は上司のみ、10,000円・10,001円は上司→部長の順で承認された。", "")],
        },
        "actions": {"ACT-001": ("採用", "質問 Q-001 で確認済み"), "ACT-002": ("採用", "質問 Q-003 で確認済み"),
                    "ACT-003": ("採用", "代理承認のルールは経理部で決めてから設定する")},
        "decision": ("条件付き導入可", "経理部長 佐藤（架空）",
                     "必須の要件2件（金額別の承認、自己承認の禁止）は、ベンダー回答と実機テストで確認できた。"
                     "境目の10,000円は設定漏れで一度不合格になったが、設定を直して再テストで合格した。"
                     "代理承認（REQ-003）は社内ルールが未確定のため、条件として残す。",
                     "① 代理承認のルール（REQ-003）を経理部で決め、設定して受入テストに合格すること\n"
                     "② 本番の承認ルートの金額条件を「以上」にしたことを、稼働前にもう一度確認すること"),
    },
    "demo2": {
        "sender": "製造部 山本（架空）", "reviewer": "品質保証部 山本（架空）", "tester": "製造部 加藤（架空）",
        "answers": {
            "Q-001": "マルチロット投入オプションを使うと、製品ロット番号で検索したときに、紐づくすべての原材料ロットが表示されます。",
            "Q-002": "マルチロット投入オプションは、初期費用30万円・年額6万円（いずれも架空）です。v5.2の標準パッケージに追加できます。"
                     "1つの製造ロットを1つの製造指図として運用できます。",
            "Q-003": "オフライン入力の個別開発は、概算で費用150万円・期間3か月（いずれも架空）です。"
                     "次期バージョンでの標準対応は検討段階で、時期は未定です。",
            "Q-004": "標準パッケージでも、訂正前ロット番号・訂正者・訂正日時を履歴として保持します（オプションは不要です）。",
        },
        "reviews": {
            "REQ-001": ("追加対応の検討が必要", "Q-001の回答で、マルチロット投入オプションを使えば全件表示できると確認。"),
            "REQ-002": ("追加対応の検討が必要", "Q-002の回答で、オプション費用（架空）を確認。"),
            "REQ-003": ("対応不可との記載・確認済み発言あり", "Q-003の回答で、現行版は対応していないことを確認。個別開発は高額。"),
            "REQ-004": ("そのまま対応できる見込み", "Q-004の回答で、標準でも訂正履歴を保持すると確認。"),
        },
        "runs": {
            "T-011": [("不合格", "実績入力中にWi-Fiを切ると、送信前の入力内容が失われた（回答書のとおり現行版は未対応）。",
                       "オフライン入力に未対応（製品の仕様）")],
        },
        "actions": {"ACT-001": ("採用", "質問 Q-001 で確認済み"), "ACT-002": ("採用", "マルチロット投入オプションを購入する"),
                    "ACT-003": ("採用", "質問 Q-002 で確認済み"),
                    "ACT-004": ("不採用", "個別開発は費用（約150万円・架空）に見合わない"),
                    "ACT-005": ("採用", "倉庫棟はWi-Fiを増設し、工事までは紙に記録して通信できる場所で入力する"),
                    "ACT-006": ("採用", "質問 Q-004 で確認済み")},
        "decision": ("条件付き導入可", "製造部長 山本（架空）",
                     "ロットの追跡と複数ロットの記録は、マルチロット投入オプションを使えば実機テストで合格した。"
                     "通信が不安定な工程のオフライン入力（REQ-003）は製品が対応しておらず、テストも不合格だった。"
                     "個別開発は高額なため、倉庫棟のWi-Fi増設と紙での一時記録で運用する。",
                     "① マルチロット投入オプションを契約すること\n"
                     "② 倉庫棟のWi-Fi増設が終わるまで、紙での一時記録と後からの入力の手順を作り、現場に教えること"),
    },
    "demo3": {
        "sender": "情報システム部 田中（架空）", "reviewer": "情報システム部 田中（架空）", "tester": "情報システム部 伊藤（架空）",
        "answers": {
            "Q-001": "2026年版では、予約停止はスタンダードプランから利用できます。製品説明ミーティングでの「上位プランのみ」は、"
                     "2025年版の説明でした。訂正します。",
            "Q-002": "予約停止は、指定日の0時（日本時間）に反映されます。時刻の指定はできません。",
            "Q-003": "人事システムから出力したCSVを取り込んで、退職日の予約停止を一括で設定できます（スタンダードプランの標準機能）。",
            "Q-004": "2026年版のスタンダードプランでは、管理者操作ログを400日保存します。延長はプレミアムプランのみです。",
        },
        "reviews": {
            "REQ-001": ("標準設定で対応できる見込み", "Q-001の書面回答で矛盾が解消（営業の説明は旧版のもの）。Q-002・Q-003も確認。"),
            "REQ-002": ("そのまま対応できる見込み", "Q-004の回答で、保存期間400日（1年以上）を確認。"),
            "REQ-003": ("そのまま対応できる見込み", "REQ-001・REQ-002ともスタンダードで満たせると確認。従業員数は250名で対象内。"),
        },
        "runs": {},
        "actions": {"ACT-001": ("採用", "質問 Q-001 で確認済み"), "ACT-002": ("採用", "質問 Q-004 で確認済み"),
                    "ACT-003": ("不採用", "保存期間が400日あり、不要"), "ACT-004": ("採用", "従業員数250名で対象内と確認")},
        "decision": ("導入可", "情報システム部長 田中（架空）",
                     "資料と営業説明の食い違い（予約停止の対象プラン）は、ベンダーの書面回答で解消した。"
                     "操作ログの保存期間も400日で要件を満たす。必須の要件3件とも、スタンダードプランの実機テストで合格した。", ""),
    },
}


def _fix_draft_test(p: dict, t: dict, f: dict) -> None:
    """「要確認」が残るテストを、ベンダー回答をもとに人が直して確定する。"""
    vals = {}
    for k in ("steps", "expected", "test_data", "preconditions", "open_issues"):
        v = t.get(k) or ""
        if "要確認" in v:
            vals[k] = v.replace("要確認", "ベンダー回答で確認済み")
    if vals:
        rules.update_test(p, t, vals, f["reviewer"])
    t["expected_confirmed"] = True
    rules.confirm_test(p, t, f["reviewer"])


def apply(p: dict, demo_id: str) -> None:
    f = FOLLOWUP.get(demo_id)
    if not f:
        return
    day = now_iso()[:10]
    # 1. 質問を確定して送り、回答を記録・確認する
    for qid, text in f["answers"].items():
        q = find(p, "questions", qid)
        if not q:
            continue
        q["status"] = "確定"
        rules.mark_question_sent(p, q, f["sender"], day)
        rules.record_answer(p, q, text, "手動入力", day, f["sender"])  # メールの回答を手で入力した想定
        rules.confirm_answer(p, q, f["reviewer"], "回答を確認した。")
    # 2. ベンダー回答を根拠に、人が診断を見直す（AIの診断は「以前の診断」として残る）
    for rid, (cat, comment) in f["reviews"].items():
        old = rules.current_diagnosis(p, rid)
        if not old:
            continue
        qs = [q for q in p["questions"] if rid in q["req_ids"] and q.get("answer_text")]
        ev = [{"ref_type": "answer", "question_id": q["id"], "quote": q["answer_text"].split("。")[0] + "。",
               "kind": "ベンダー回答"} for q in qs]
        ok = cat in ("そのまま対応できる見込み", "標準設定で対応できる見込み")
        dg = rules.add_diagnosis(p, {
            "req_id": rid, "product_id": old.get("product_id"), "category": cat, "reason": comment,
            "met_conditions": old["met_conditions"] + (old["remaining_conditions"] if ok else []),
            "remaining_conditions": [] if ok else old["remaining_conditions"],
            "evidence": ev + old["evidence"], "plan_conditions": old.get("plan_conditions", ""),
            "constraints": old.get("constraints", ""), "next_check": "実機テストで確認する",
        }, origin="手動（ベンダー回答を踏まえた見直し）")
        rules.review_diagnosis(p, dg, f["reviewer"], "人が確認済み", comment)
    # 3. 「要確認」が残るテストを直して確定する
    for t in p["tests"]:
        if t["status"] == "下書き":
            _fix_draft_test(p, t, f)
    # 4. 実機テストの結果（指定がないテストは合格）
    prod = p["products"][0]
    for t in p["tests"]:
        for i, (result, actual, defect) in enumerate(f["runs"].get(t["id"], [("合格", PASS_TEXT, "")])):
            rules.record_run(p, t, {"tester": f["tester"], "status": "完了", "result": result, "actual": actual,
                                    "executed_at": now_iso(), "product_version": prod.get("edition", ""),
                                    "plan": prod.get("plan", ""), "environment": "検証環境（架空）", "defect": defect,
                                    "evidence_memo": "画面の記録（架空）"})
    # 5. 対応方法の候補の採否
    for aid, (val, why) in f["actions"].items():
        a = find(p, "actions", aid)
        if a and a["status"] == "候補":
            rules.decide_action(p, a, val, f["reviewer"], why)
    # 6. 導入判断
    value, by, reason, cond = f["decision"]
    m = M.compute(p)
    rules.record_decision(p, value, by, day, reason, cond,
                          decision_snapshot(p, M.decision_counts(m, len(M.remaining_issues(p, m)))))
