"""状況の集計（プログラムで計算。AI は使わない）。

資料上の見込み・ベンダー説明・人の確認・実機テスト・依頼完了を混同しない。
率は必ず「分子／分母」を持ち、分母0は「対象なし」とする（0件を100%にしない）。
"""
from __future__ import annotations

from ..core import DIAG_CATEGORIES
from .rules import current_diagnosis, latest_run
from .stale import all_stale, run_stale_reasons


def ratio(num: int, den: int) -> dict:
    return {"num": num, "den": den, "text": "対象なし（分母0）" if den == 0 else f"{num}/{den}（{num / den:.0%}）"}


def compute(project: dict) -> dict:
    reqs = [r for r in project["requirements"] if r["status"] != "廃止"]
    must = [r for r in reqs if r.get("priority") == "必須"]
    by_cat = {c: 0 for c in DIAG_CATEGORIES}
    no_diag, reviewed = 0, 0
    must_unresolved = []
    for r in reqs:
        dg = current_diagnosis(project, r["id"])
        if not dg:
            no_diag += 1
            if r.get("priority") == "必須":
                must_unresolved.append(r["id"])
            continue
        by_cat[dg["category"]] += 1
        if dg["review_status"] == "人が確認済み":
            reviewed += 1
        if r.get("priority") == "必須" and dg["category"] not in DIAG_CATEGORIES[:2]:
            must_unresolved.append(r["id"])

    tests = [t for t in project["tests"] if t["status"] != "廃止"]
    confirmed_tests = [t for t in tests if t["status"] == "確定"]
    not_run, passed, failed, blocked, in_prog = [], [], [], [], []
    for t in tests:
        lr = latest_run(project, t["id"])
        if not lr or lr["status"] == "未実施":
            not_run.append(t["id"])
        elif lr["status"] == "実施不能":
            blocked.append(t["id"])
        elif lr["status"] == "実施中":
            in_prog.append(t["id"])
        elif lr["result"] == "合格" and not run_stale_reasons(project, lr):
            passed.append(t["id"])
        elif lr["result"] == "不合格":
            failed.append(t["id"])
    judged = len(passed) + len(failed)  # 実施不能・未判定は合否の分母に入れない
    # 必須要件のうち、実機テストで合格（最新版・最新結果）を確認できていないもの
    must_not_verified = []
    for r in must:
        rtests = [t for t in tests if r["id"] in t.get("req_ids", [])]
        if not rtests or any(t["id"] not in passed for t in rtests):
            must_not_verified.append(r["id"])

    qs = [q for q in project["questions"] if q["status"] != "取り下げ"]
    unanswered = [q["id"] for q in qs if q["status"] in ("下書き", "確定", "送付済み")]
    answer_unreviewed = [q["id"] for q in qs if q["status"] == "回答あり"]
    reqs_cr = project["requests"]
    cr_draft = [r["id"] for r in reqs_cr if r["status"] == "下書き"]
    cr_active = [r["id"] for r in reqs_cr if r["status"] in ("確定", "送付済み", "回答待ち", "対応検討中", "対応中", "テスト待ち")]
    cr_done = [r["id"] for r in reqs_cr if r["status"] == "完了"]
    cr_done_remaining = [r["id"] for r in reqs_cr if r["status"] == "完了" and r["completion"].get("with_remaining")]
    cr_skipped = [r["id"] for r in reqs_cr if r["status"] == "見送り"]
    stale = all_stale(project)
    contradictions = by_cat["根拠間に矛盾あり"]
    lack = by_cat["情報不足・ベンダー確認が必要"]

    return {
        "requirements": len(reqs), "must": len(must), "no_diagnosis": no_diag,
        "by_category": by_cat, "diag_reviewed": ratio(reviewed, len(reqs) - no_diag),
        "must_unresolved": must_unresolved, "must_not_verified": must_not_verified, "contradictions": contradictions, "lack_info": lack,
        "tests": len(tests), "tests_confirmed": len(confirmed_tests),
        "not_run": not_run, "passed": passed, "failed": failed, "blocked": blocked, "in_progress": in_prog,
        "pass_rate": ratio(len(passed), judged),
        "executed_rate": ratio(len(passed) + len(failed) + len(blocked), len(tests)),
        "unanswered": unanswered, "answer_unreviewed": answer_unreviewed,
        "cr_draft": cr_draft, "cr_active": cr_active, "cr_done": cr_done,
        "cr_done_remaining": cr_done_remaining, "cr_skipped": cr_skipped,
        "stale": stale,
    }


def remaining_issues(project: dict, m: dict | None = None) -> list[dict]:
    """残件の一覧（導入判断画面・Excel 共通）。隠さずすべて列挙する。"""
    m = m or compute(project)
    out = []
    for rid in m["must_unresolved"]:
        dg = current_diagnosis(project, rid)
        out.append({"種類": "必須要件：資料・説明上の見込みなし", "ID": rid,
                    "内容": dg["category"] if dg else "診断なし", "次の操作": "自社に合うかを確認"})
    for rid in m["must_not_verified"]:
        out.append({"種類": "必須要件：実機で合格未確認", "ID": rid,
                    "内容": "関連テストの最新結果が合格ではない、またはテストなし", "次の操作": "試すこと・実施結果"})
    for q in m["unanswered"]:
        out.append({"種類": "未回答の質問", "ID": q, "内容": "ベンダー回答待ち", "次の操作": "質問・対応依頼"})
    for q in m["answer_unreviewed"]:
        out.append({"種類": "回答の確認待ち", "ID": q, "内容": "回答を人が確認していません", "次の操作": "質問・対応依頼"})
    for r in m["cr_draft"]:
        out.append({"種類": "未確定の依頼書", "ID": r, "内容": "下書き", "次の操作": "質問・対応依頼"})
    for r in m["cr_active"]:
        out.append({"種類": "対応中の依頼", "ID": r, "内容": "完了していません", "次の操作": "質問・対応依頼"})
    for r in m["cr_done_remaining"]:
        out.append({"種類": "残件付き完了", "ID": r, "内容": "残件あり", "次の操作": "質問・対応依頼"})
    for t in m["failed"]:
        out.append({"種類": "不合格", "ID": t, "内容": "最新の実施が不合格", "次の操作": "試すこと・実施結果"})
    for t in m["not_run"]:
        out.append({"種類": "未実施", "ID": t, "内容": "実施結果なし", "次の操作": "試すこと・実施結果"})
    for t in m["blocked"]:
        out.append({"種類": "実施不能", "ID": t, "内容": "合否未判定", "次の操作": "試すこと・実施結果"})
    for s in m["stale"]:
        out.append({"種類": "再確認が必要", "ID": s["id"], "内容": " / ".join(s["reasons"]), "次の操作": s["type"]})
    return out


def decision_counts(m: dict, n_issues: int) -> dict:
    """導入判断と一緒に記録する、判断時点の件数（集計の分母などは除く）。"""
    skip = ("by_category", "diag_reviewed", "pass_rate", "executed_rate")
    return {**{k: (len(v) if isinstance(v, list) else v) for k, v in m.items() if k not in skip}, "remaining": n_issues}
