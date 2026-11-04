"""自社要件の質問形式の入力（AIなし）。残件 BL-001 の案A。

業務の種類ごとに用意した質問に1問ずつ答えると、要件の下書きを作る。
- 回答は原文として要件の「元の文章」に残す
- 「分からない・未定」は推測で埋めず、未確定事項にする
- 金額・以上／未満・禁止などの条件語は、回答から決まった表現だけを使う
"""
from __future__ import annotations

UNKNOWN = "分からない・未定"

# 質問：id, 種類（text / number / choice）, 文, 選択肢, 表示条件（他の回答）, 補足
TEMPLATES = {
    "approval": {
        "label": "申請・承認（経費精算・稟議・休暇申請など）",
        "keywords": ["経費", "承認", "稟議", "申請", "精算", "ワークフロー", "休暇"],
        "questions": [
            {"id": "business", "type": "text", "q": "対象の業務名を教えてください。", "default": "経費申請の承認"},
            {"id": "by_amount", "type": "choice", "q": "申請の金額によって、承認する人が変わりますか？",
             "options": ["はい", "いいえ", UNKNOWN]},
            {"id": "threshold", "type": "number", "q": "承認する人が変わる境目の金額は、いくらですか？（円）",
             "show_if": ("by_amount", "はい"), "allow_unknown": True},
            {"id": "boundary", "type": "choice", "q": "境目ちょうどの金額は、どちらの承認になりますか？",
             "options": ["上の承認（境目の金額「以上」が上位）", "下の承認（境目の金額「以下」が下位）", UNKNOWN],
             "show_if": ("by_amount", "はい"), "help": "例：10,000円ちょうどの申請は、部長承認が必要か"},
            {"id": "lower", "type": "text", "q": "境目より少ない金額は、誰が承認しますか？", "default": "直属の上司",
             "show_if": ("by_amount", "はい")},
            {"id": "upper", "type": "text", "q": "境目以上の金額は、誰が承認しますか？（順番があれば → でつなぐ）",
             "default": "直属の上司 → 部長", "show_if": ("by_amount", "はい")},
            {"id": "self", "type": "choice", "q": "申請した本人が、自分の申請を承認することは？",
             "options": ["禁止", "許可", UNKNOWN]},
            {"id": "proxy", "type": "choice", "q": "承認する人が不在のときは、どうしますか？",
             "options": ["代理の人が承認する（条件は決まっている）", "代理の人が承認する（条件はまだ決まっていない）",
                         "代理承認はしない（戻ってくるまで待つ）", UNKNOWN]},
            {"id": "proxy_rule", "type": "text", "q": "代理承認の条件を教えてください。（誰が・どの期間・金額の上限）",
             "show_if": ("proxy", "代理の人が承認する（条件は決まっている）")},
        ],
    },
    "account": {
        "label": "アカウント・権限管理（入退社・権限変更など）",
        "keywords": ["アカウント", "ID", "権限", "退職", "入社", "ログイン", "認証"],
        "questions": [
            {"id": "business", "type": "text", "q": "対象の業務名を教えてください。", "default": "退職者のアカウント停止"},
            {"id": "timing", "type": "choice", "q": "退職者のアカウントは、いつ止める必要がありますか？",
             "options": ["退職日の0時に自動で止める", "退職日の業務終了後に止める", "担当者が手作業で止めればよい", UNKNOWN]},
            {"id": "source", "type": "choice", "q": "退職の情報は、どこから届きますか？",
             "options": ["人事システムと連携したい", "表計算ファイル（CSV）で受け取る", "メールや口頭で受け取る", UNKNOWN]},
            {"id": "operator", "type": "text", "q": "アカウントを止める操作をしてよいのは誰ですか？", "default": "情報システム部の管理者"},
            {"id": "log_years", "type": "number", "q": "管理者の操作履歴は、何年保存する必要がありますか？",
             "allow_unknown": True},
            {"id": "plan", "type": "text", "q": "予算などで、使えるプランに制限はありますか？（なければ空欄）"},
        ],
    },
    "lot": {
        "label": "製造・在庫・ロット管理（トレーサビリティなど）",
        "keywords": ["ロット", "製造", "在庫", "生産", "原材料", "トレーサビリティ", "工場"],
        "questions": [
            {"id": "business", "type": "text", "q": "対象の業務名を教えてください。", "default": "ロットトレーサビリティ"},
            {"id": "direction", "type": "choice", "q": "どの方向に追跡する必要がありますか？",
             "options": ["製品から原材料へ", "原材料から製品へ", "両方", UNKNOWN]},
            {"id": "max_lots", "type": "number", "q": "1つの製造ロットに使う原材料ロットは、最大で何件ですか？",
             "allow_unknown": True},
            {"id": "offline", "type": "choice", "q": "通信が不安定な場所で、記録を入力することはありますか？",
             "options": ["ある", "ない", UNKNOWN]},
            {"id": "offline_how", "type": "text", "q": "その場所では、今はどのように記録していますか？",
             "show_if": ("offline", "ある"), "default": "紙に記入して、後で入力"},
            {"id": "correction", "type": "choice", "q": "誤って登録したロットを直したとき、直す前の内容を残す必要がありますか？",
             "options": ["必要（直した人・日時も残す）", "必要（直す前の内容だけ）", "不要", UNKNOWN]},
        ],
    },
    "general": {
        "label": "その他の業務（自由に入力）",
        "keywords": [],
        "questions": [
            {"id": "business", "type": "text", "q": "対象の業務名を教えてください。"},
            {"id": "who", "type": "text", "q": "誰が、その作業をしますか？"},
            {"id": "what", "type": "text", "q": "どんな作業ですか？（例：月末に請求書を発行する）"},
            {"id": "rule", "type": "text", "q": "必ず守るルールはありますか？（金額・期限・禁止事項などは数字や言葉をそのまま）"},
            {"id": "exception", "type": "text", "q": "例外はありますか？（なければ空欄）"},
            {"id": "priority", "type": "choice", "q": "この要件の重要度は？", "options": ["必須", "望ましい", "任意"]},
        ],
    },
}


def suggest_template(*texts: str) -> str:
    """案件名・対象業務・製品名から、近い質問の種類を選ぶ（キーワード一致）。"""
    joined = " ".join(t or "" for t in texts)
    best, score = "general", 0
    for tid, t in TEMPLATES.items():
        s = sum(1 for k in t["keywords"] if k in joined)
        if s > score:
            best, score = tid, s
    return best


def visible_questions(tid: str, answers: dict) -> list[dict]:
    out = []
    for q in TEMPLATES[tid]["questions"]:
        cond = q.get("show_if")
        if cond and answers.get(cond[0]) != cond[1]:
            continue
        out.append(q)
    return out


def _yen(v) -> str:
    return f"{int(v):,}円"


def _is_unknown(v) -> bool:
    return v in (None, "", UNKNOWN)


def transcript(tid: str, answers: dict) -> str:
    """質問と回答の原文（要件の「元の文章」に残す）。"""
    lines = []
    for q in visible_questions(tid, answers):
        a = answers.get(q["id"])
        a = UNKNOWN if a is None and q.get("allow_unknown") else a
        if q["type"] == "number" and isinstance(a, (int, float)):
            a = f"{a:g}"
        lines.append(f"問：{q['q']}　答：{a if a not in (None, '') else '（未回答）'}")
    return "\n".join(lines)


def build_requirements(tid: str, answers: dict) -> list[dict]:
    """回答から要件の下書きを作る。分からない点は推測せず未確定事項にする。"""
    a = answers
    business = (a.get("business") or TEMPLATES[tid]["label"]).strip()
    src = transcript(tid, a)
    reqs: list[dict] = []

    def add(**f):
        f.setdefault("business", business)
        f.setdefault("priority", "必須")
        f.setdefault("reason", "質問形式の回答による")
        f["original_text"] = src
        reqs.append(f)

    if tid == "approval":
        if a.get("by_amount") == "はい":
            open_ = []
            th = a.get("threshold")
            th_txt = _yen(th) if not _is_unknown(th) else "（境目の金額は未定）"
            if _is_unknown(th):
                open_.append("承認者が変わる境目の金額が未定")
            b = a.get("boundary")
            if b and b.startswith("上の承認"):
                rule = f"{th_txt}未満は{a.get('lower') or '（未定）'}が承認する。{th_txt}以上は{a.get('upper') or '（未定）'}の順に承認する。"
            elif b and b.startswith("下の承認"):
                rule = f"{th_txt}以下は{a.get('lower') or '（未定）'}が承認する。{th_txt}超は{a.get('upper') or '（未定）'}の順に承認する。"
            else:
                rule = f"境目（{th_txt}）より少ない金額は{a.get('lower') or '（未定）'}、多い金額は{a.get('upper') or '（未定）'}が承認する。"
                open_.append("境目ちょうどの金額がどちらの承認になるかが未定")
            add(workflow="申請金額に応じて承認者を切り替える", role="申請者・承認者", rules=rule,
                open_issues="／".join(open_))
        elif a.get("by_amount") == UNKNOWN:
            add(workflow="申請金額に応じて承認者を切り替えるか", role="申請者・承認者", rules="（未定）",
                open_issues="金額によって承認者が変わるかが未定", priority="望ましい")
        if a.get("self") == "禁止":
            add(workflow="申請者本人による承認を防ぐ", role="全利用者",
                rules="申請者本人が自分の申請を承認すること（自己承認）は禁止する。")
        elif a.get("self") == UNKNOWN:
            add(workflow="申請者本人による承認の扱い", role="全利用者", rules="（未定）",
                open_issues="自己承認を禁止するかが未定", priority="望ましい")
        p = a.get("proxy") or ""
        if p.startswith("代理の人が承認する（条件は決まっている）"):
            add(business="代理承認", workflow="承認者の不在時に代理の人が承認する", role="代理承認者",
                rules=a.get("proxy_rule") or "（条件の記入なし）", priority="望ましい",
                open_issues="" if a.get("proxy_rule") else "代理承認の条件が未記入")
        elif p.startswith("代理の人が承認する（条件はまだ"):
            add(business="代理承認", workflow="承認者の不在時に代理の人が承認する", role="代理承認者",
                rules="代理承認の条件は未定", priority="望ましい", open_issues="代理承認の条件（誰が・期間・金額の上限）が未定")
        elif p == UNKNOWN:
            add(business="代理承認", workflow="承認者の不在時の扱い", rules="（未定）", priority="望ましい",
                open_issues="承認者が不在のときの扱いが未定")

    elif tid == "account":
        t = a.get("timing")
        if t:
            open_ = "停止のタイミングが未定" if t == UNKNOWN else ""
            rules = {"退職日の0時に自動で止める": "退職日の0時に、利用停止が自動で反映されること。",
                     "退職日の業務終了後に止める": "退職日の業務終了後に、利用停止が反映されること。",
                     "担当者が手作業で止めればよい": "担当者が手作業で利用停止できること。"}.get(t, "（未定）")
            src_ = a.get("source")
            if src_ and src_ != UNKNOWN:
                rules += f"退職の情報は「{src_}」。"
            elif src_ == UNKNOWN:
                open_ = "／".join(x for x in [open_, "退職情報の受け取り方が未定"] if x)
            add(workflow="退職者のアカウントを止める", role=a.get("operator") or "管理者", rules=rules, open_issues=open_)
        if a.get("operator"):
            add(business="権限管理", workflow="アカウント停止の操作権限", role=a["operator"],
                rules=f"アカウント停止の操作は「{a['operator']}」だけができること。")
        y = a.get("log_years")
        add(business="操作履歴", workflow="管理者の操作履歴を保持する", role="監査担当",
            rules=f"管理者の操作履歴を{y:g}年以上保持すること。" if not _is_unknown(y) else "管理者の操作履歴を保持すること（期間は未定）。",
            open_issues="" if not _is_unknown(y) else "保存期間が未定")
        if (a.get("plan") or "").strip():
            add(business="契約プラン", workflow="利用できるプランの制約", role="情報システム部", rules=a["plan"].strip())

    elif tid == "lot":
        d = a.get("direction")
        if d:
            add(workflow="ロットを追跡する", role="品質保証担当",
                rules={"製品から原材料へ": "製品ロット番号から、使用したすべての原材料ロットを検索できること。",
                       "原材料から製品へ": "原材料ロット番号から、その原材料を使ったすべての製品ロットを検索できること。",
                       "両方": "製品ロットから原材料ロット、原材料ロットから製品ロットの両方向に検索できること。"}.get(d, "（未定）"),
                open_issues="追跡の方向が未定" if d == UNKNOWN else "")
        m = a.get("max_lots")
        add(business="製造実績入力", workflow="1つの製造ロットに原材料ロットを記録する", role="製造オペレーター",
            rules=f"1つの製造ロットに、原材料ロットを最大{m:g}件記録できること。" if not _is_unknown(m)
            else "1つの製造ロットに、原材料ロットを複数記録できること（最大件数は未定）。",
            open_issues="" if not _is_unknown(m) else "最大件数が未定")
        o = a.get("offline")
        if o == "ある":
            add(business="製造実績入力", workflow="通信が不安定な場所での記録", role="製造オペレーター",
                rules="通信が切れても、実績の記録が失われないこと。",
                exceptions=f"現在の記録方法：{a.get('offline_how') or '未記入'}")
        elif o == UNKNOWN:
            add(business="製造実績入力", workflow="通信が不安定な場所での記録", rules="（未定）", priority="望ましい",
                open_issues="通信が不安定な場所での入力があるかが未定")
        c = a.get("correction") or ""
        if c.startswith("必要"):
            add(business="ロット訂正", workflow="誤って登録したロットを直す", role="製造リーダー",
                rules="訂正前のロット番号・訂正者・訂正日時を履歴として保持すること。" if "直した人" in c
                else "訂正前のロット番号を履歴として保持すること。")
        elif c == UNKNOWN:
            add(business="ロット訂正", workflow="誤って登録したロットを直す", rules="（未定）", priority="望ましい",
                open_issues="訂正前の内容を残す必要があるかが未定")

    else:  # general
        if (a.get("what") or a.get("rule")):
            add(workflow=a.get("what") or "", role=a.get("who") or "", rules=a.get("rule") or "",
                exceptions=a.get("exception") or "", priority=a.get("priority") or "必須",
                open_issues="" if a.get("rule") else "守るべきルールが未記入")
    return reqs
