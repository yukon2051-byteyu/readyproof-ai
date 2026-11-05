"""③ 診断結果の画面に出す内容を、既存データから導き出す（プログラムで計算。AI は使わない）。

利用者の考える順序に合わせる：
  結局、使えるのか？ → 何が問題なのか？ → 何をすればよいのか？ → なぜその判断になったのか？

- 元データ（要件・診断・質問・テスト・判断）を正とし、ここで新しい事実や総合判定を作らない
- 「AIが診断した」「人が確認した」「ベンダーが回答した」「実機テストを実施した」「合格した」「要件が未確定」を混同しない
- 件数は metrics.compute と同じ current_diagnosis から数え、画面の内訳と必ず一致させる
"""
from __future__ import annotations

from ..core import DIAG_CATEGORIES, primary_product
from . import metrics as M
from .rules import current_diagnosis, latest_run
from .stale import diagnosis_stale_reasons

# 画面で使う短い言葉（区分そのものは変えない）
PLAIN = {
    DIAG_CATEGORIES[0]: "そのまま使える見込み",
    DIAG_CATEGORIES[1]: "設定で対応できる見込み",
    DIAG_CATEGORIES[2]: "追加の対応が必要",
    DIAG_CATEGORIES[3]: "使えない（記載・確認あり）",
    DIAG_CATEGORIES[4]: "確認が必要（情報不足）",
    DIAG_CATEGORIES[5]: "確認が必要（根拠が矛盾）",
}

# 絞り込みの区分と、既存の6区分の対応（どの区分も必ず1つのグループに入る）
GROUPS = {
    "likely": {"label": "対応可能な見込み", "cats": DIAG_CATEGORIES[:2]},
    "extra": {"label": "追加対応が必要", "cats": DIAG_CATEGORIES[2:3]},
    "hard": {"label": "対応困難", "cats": DIAG_CATEGORIES[3:4]},
    "check": {"label": "確認が必要", "cats": DIAG_CATEGORIES[4:6]},
    "none": {"label": "未診断", "cats": []},
}
GROUP_ORDER = ["hard", "extra", "check", "none", "likely"]  # 未解決の重要事項を先に
UNDIAGNOSED_DRAFT = "要件が未確定のため、診断していません。"
UNDIAGNOSED = "まだ診断していません。"

# 次にやることの優先度（小さいほど先）
R_HARD, R_FAILED, R_STALE, R_CONFLICT, R_DRAFT, R_DIAG, R_QUESTION, R_REVIEW, R_ACTION, R_TESTSPEC, R_RUN, R_DONE = range(12)


def group_of(dg: dict | None) -> str:
    if not dg:
        return "none"
    return next(k for k, g in GROUPS.items() if dg["category"] in g["cats"])


def _duplicated_names(reqs: list[dict]) -> set[str]:
    names = [r["business"] for r in reqs]
    return {n for n in names if names.count(n) > 1}


def req_title(r: dict, dup: set[str]) -> str:
    """要件名。業務名が同じ要件は、作業内容を足して見分けられるようにする。"""
    if r["business"] in dup and r.get("workflow"):
        return f"{r['business']}：{r['workflow']}"
    return r["business"]


def _vendor_state(project: dict, rid: str) -> dict:
    qs = [q for q in project["questions"] if rid in q.get("req_ids", []) and q["status"] != "取り下げ"]
    done = sum(1 for q in qs if q["status"] == "回答確認済み")
    if not qs:
        return {"text": "質問なし", "state": "none"}
    if done == len(qs):
        return {"text": f"回答を確認済み {done}/{len(qs)}", "state": "ok"}
    return {"text": f"回答を確認済み {done}/{len(qs)}", "state": "wait"}


def _test_state(project: dict, rid: str, m: dict) -> dict:
    tests = [t for t in project["tests"] if t["status"] != "廃止" and rid in t.get("req_ids", [])]
    ids = [t["id"] for t in tests]
    passed = [i for i in ids if i in m["passed"]]
    failed = [i for i in ids if i in m["failed"]]
    run = [i for i in ids if (lr := latest_run(project, i)) and lr["status"] != "未実施"]
    out = {"total": len(ids), "run": len(run), "passed": len(passed), "failed": len(failed),
           "not_run": [i for i in ids if i in m["not_run"]],
           "drafts": [t["id"] for t in tests if t["status"] == "下書き"]}
    if not ids:
        return {**out, "text": "テストなし", "state": "none"}
    if failed:
        return {**out, "text": f"実施 {len(run)}/{len(ids)}・不合格 {len(failed)}", "state": "bad"}
    if not run:
        return {**out, "text": f"未実施 0/{len(ids)}", "state": "wait"}
    if len(passed) == len(ids):
        return {**out, "text": f"実施 {len(run)}/{len(ids)}・全件合格", "state": "ok"}
    return {**out, "text": f"実施 {len(run)}/{len(ids)}・合格 {len(passed)}", "state": "wait"}


def _ai_state(project: dict, rid: str, dg: dict | None) -> dict:
    ai = any(d["req_id"] == rid and str(d.get("origin", "")).startswith("AI生成") for d in project["diagnoses"])
    if ai:
        return {"text": "済み", "state": "ok"}
    if dg:
        return {"text": "人が作成", "state": "none"}
    return {"text": "未実施", "state": "none"}


def _human_state(dg: dict | None) -> dict:
    if not dg:
        return {"text": "対象なし", "state": "none"}
    if dg["review_status"] == "人が確認済み":
        return {"text": "済み", "state": "ok"}
    if dg["review_status"] == "要修正":
        return {"text": "要修正", "state": "bad"}
    return {"text": "未確認", "state": "wait"}


def _need(project: dict, r: dict, dg: dict | None, test: dict) -> dict:
    """この要件に次に必要な対応を1つ決める。元データにある状態だけを根拠にする。"""
    must = "必須要件です。" if r.get("priority") == "必須" else ""
    rid = r["id"]
    if r["status"] != "確定":
        why = r.get("open_issues") or "要件が下書きのままです。"
        return {"rank": R_DRAFT, "text": "要件を確定する", "reason": why, "page": "input2", "status": "未確定"}
    if not dg:
        return {"rank": R_DIAG, "text": "AIで診断する", "reason": must + "確定済みですが、まだ診断していません。", "page": "result",
                "status": "未実施"}
    if test["failed"]:
        return {"rank": R_FAILED, "text": f"不合格のテスト {test['failed']}件に対応する",
                "reason": must + "実機テストの最新結果が不合格です。", "page": "tests", "status": "対応が必要"}
    if dg["category"] == DIAG_CATEGORIES[3] and not any(a["req_id"] == rid and a["status"] == "採用" for a in project["actions"]):
        return {"rank": R_HARD, "text": "代わりの対応を決める", "reason": must + "対応できないとの記載・確認があります。",
                "page": "result", "tab": "act", "status": "未決定"}
    stale = diagnosis_stale_reasons(project, dg)
    if stale:
        return {"rank": R_STALE, "text": "診断を見直す", "reason": stale[0], "page": "result", "tab": "main", "status": "再確認が必要"}
    if dg["category"] == DIAG_CATEGORIES[5] and dg["review_status"] != "人が確認済み":
        return {"rank": R_CONFLICT, "text": "資料と説明の食い違いを書面で確認する",
                "reason": must + "根拠の間に矛盾があります。", "page": "result", "tab": "log", "status": "未解決"}
    qs = [q for q in project["questions"] if rid in q.get("req_ids", []) and q["status"] != "取り下げ"]
    for status, text, label in (("回答あり", "ベンダーの回答を確認する", "確認待ち"), ("下書き", "ベンダーへの質問を確定して送る", "未送付"),
                                ("確定", "ベンダーへ質問を送る", "未送付"), ("送付済み", "ベンダーの回答を待つ", "回答待ち")):
        hits = [q for q in qs if q["status"] == status]
        if hits:
            return {"rank": R_QUESTION, "text": text, "reason": f"{must}{hits[0]['question']}", "page": "result", "tab": "log",
                    "status": label}
    if dg["remaining_conditions"] and not qs:  # 質問して回答を確認済みなら、もう一度は求めない
        return {"rank": R_QUESTION, "text": "ベンダーに確認する", "reason": must + dg["remaining_conditions"][0], "page": "result",
                "tab": "act", "status": "未確認"}
    if dg["review_status"] != "人が確認済み":
        return {"rank": R_REVIEW, "text": "AIの診断を人が確認する", "reason": must + "診断は下書きのままです。", "page": "result",
                "tab": "log", "status": "未確認"}
    if any(a["req_id"] == rid and a["status"] == "候補" for a in project["actions"]):
        return {"rank": R_ACTION, "text": "対応方法を決める", "reason": must + "対応方法の候補が未決定です。", "page": "result",
                "tab": "act", "status": "未決定"}
    if not test["total"]:
        return {"rank": R_TESTSPEC, "text": "受入テストを作る", "reason": must + "実機で確かめるテストがありません。", "page": "tests",
                "status": "未作成"}
    if test["drafts"]:
        return {"rank": R_TESTSPEC, "text": f"テスト {len(test['drafts'])}件を確定する", "reason": must + "下書きのテストがあります。",
                "page": "tests", "status": "未確定"}
    if test["not_run"]:
        first = (dg.get("test_conditions") or [""])[0]
        return {"rank": R_RUN, "text": f"実機テストを実施する（未実施 {len(test['not_run'])}件）",
                "reason": must + (first or "診断は見込みのため、実機での確認が必要です。"), "page": "tests", "status": "未実施"}
    if test["passed"] < test["total"]:
        return {"rank": R_RUN, "text": "テストの結果を見直す", "reason": must + "合格が確定していないテストがあります。", "page": "tests",
                "status": "確認中"}
    return {"rank": R_DONE, "text": "必要な対応はありません", "reason": "", "page": "", "status": "完了"}


def rows(project: dict, m: dict | None = None) -> list[dict]:
    """要件ごとの表示内容（第2階層）。"""
    m = m or M.compute(project)
    reqs = [r for r in project["requirements"] if r["status"] != "廃止"]
    dup = _duplicated_names(reqs)
    out = []
    for i, r in enumerate(reqs):
        dg = current_diagnosis(project, r["id"])
        test = _test_state(project, r["id"], m)
        g = group_of(dg)
        if dg:
            label, reason = PLAIN[dg["category"]], dg["reason"]
        else:
            draft = r["status"] != "確定"
            label, reason = "未診断", UNDIAGNOSED_DRAFT if draft else UNDIAGNOSED
        out.append({"req": r, "dg": dg, "title": req_title(r, dup), "group": g, "label": label, "reason": reason, "order": i,
                    "need": _need(project, r, dg, test), "test": test,
                    "checks": [("要件", {"text": "確定" if r["status"] == "確定" else "未確定",
                                         "state": "ok" if r["status"] == "確定" else "wait"}),
                               ("AI診断", _ai_state(project, r["id"], dg)), ("人の確認", _human_state(dg)),
                               ("ベンダー回答", _vendor_state(project, r["id"])), ("実機テスト", test)]})
    return out


def counts(rs: list[dict]) -> dict:
    """グループごとの件数（絞り込みの件数と同じ数え方）。"""
    return {k: sum(1 for x in rs if x["group"] == k) for k in GROUPS}


SORTS = ["対応優先度順", "要件番号順", "診断区分順"]


def filter_sort(rs: list[dict], group: str = "all", priority: str = "すべて", sort: str = SORTS[0]) -> list[dict]:
    out = [x for x in rs if (group == "all" or x["group"] == group) and (priority == "すべて" or x["req"].get("priority") == priority)]
    must_first = lambda x: 0 if x["req"].get("priority") == "必須" else 1
    if sort == SORTS[1]:
        return sorted(out, key=lambda x: x["order"])
    if sort == SORTS[2]:
        return sorted(out, key=lambda x: (GROUP_ORDER.index(x["group"]), x["order"]))
    return sorted(out, key=lambda x: (x["need"]["rank"], must_first(x), x["order"]))


def next_actions(project: dict, rs: list[dict]) -> list[dict]:
    """次にやるべきこと（第1階層）。各要件の「必要な対応」を、業務上の重要度の順に並べる。"""
    items = []
    for x in sorted(rs, key=lambda y: (y["need"]["rank"], 0 if y["req"].get("priority") == "必須" else 1, y["order"])):
        n = x["need"]
        if n["rank"] != R_DONE:
            items.append({**n, "req_id": x["req"]["id"], "title": x["title"]})
    if not [i for i in items if i["rank"] <= R_DIAG] and project["decision"]["value"] == "未判断":
        items.append({"rank": R_DONE, "text": "導入判断を記録する", "reason": "診断とテストの結果を確認して、人が判断します。",
                      "page": "decision", "status": "未判断", "req_id": "", "title": "案件全体"})
    return items


def _names(rs: list[dict]) -> str:
    return "・".join(f"「{x['title']}」" for x in rs)


def summary(project: dict, m: dict | None = None, rs: list[dict] | None = None) -> dict:
    """診断サマリー（第1階層）。結論 → 制約・未解決の順に、自然な日本語で組み立てる。"""
    m = m or M.compute(project)
    rs = rs if rs is not None else rows(project, m)
    must = [x for x in rs if x["req"].get("priority") == "必須"]
    scope, scope_name = (must, "必須要件") if must else (rs, "要件")
    n = len(scope)
    c = counts(scope)
    done_cats = {x["dg"]["category"] for x in scope if x["dg"]}
    if not any(x["dg"] for x in rs):
        head = "まだ診断していません"
    elif c["hard"]:
        head = f"{scope_name}{n}件のうち{c['hard']}件は、使えないとの記載・確認があります"
    elif c["extra"]:
        head = f"{scope_name}{n}件のうち{c['extra']}件は、追加の対応が必要です"
    elif c["check"]:
        head = f"{scope_name}{n}件のうち{c['check']}件は、確認が必要です"
    elif c["none"]:
        head = f"{scope_name}{n}件のうち{c['none']}件は、まだ診断していません"
    elif done_cats == {DIAG_CATEGORIES[1]}:
        head = f"{scope_name}{n}件は、製品の設定で対応できる見込みです"
    elif done_cats == {DIAG_CATEGORIES[0]}:
        head = f"{scope_name}{n}件は、そのまま対応できる見込みです"
    else:
        head = f"{scope_name}{n}件は、対応できる見込みです"

    subs = []
    tests = m["tests"]
    executed = m["executed_rate"]["num"]
    if m["failed"]:
        subs.append(f"実機テストで不合格が{len(m['failed'])}件あります。")
    if any(x["dg"] for x in rs):
        if not tests:
            subs.append("実機テストはまだありません。診断は見込みのため、実機での確認が必要です。")
        elif executed == 0:
            subs.append("ただし、実機テストは未実施です。診断は見込みのため、実機での確認が必要です。")
        elif len(m["passed"]) == tests:
            subs.append(f"実機テストは全{tests}件を実施し、すべて合格しました。")
        elif not m["failed"]:
            subs.append(f"実機テストは{tests}件中{executed}件を実施しました。")
    drafts = [x for x in rs if x["group"] == "none" and x["req"]["status"] != "確定"]
    waiting = [x for x in rs if x["group"] == "none" and x["req"]["status"] == "確定"]
    if drafts:
        subs.append(f"{_names(drafts)}は要件が未確定のため、診断していません。")
    if waiting and any(x["dg"] for x in rs):
        subs.append(f"{_names(waiting)}はまだ診断していません。")

    d = project["decision"]
    if d["value"] != "未判断":
        status = {"text": f"人の判断：{d['value']}", "tone": "ok" if d["value"] == "導入可" else "warn"}
    elif not any(x["dg"] for x in rs) or m["no_diagnosis"]:
        status = {"text": "診断途中", "tone": "muted"}
    elif counts(rs)["hard"] or counts(rs)["extra"] or counts(rs)["check"] or m["failed"]:
        status = {"text": "確認事項あり", "tone": "warn"}
    else:
        status = {"text": "人の判断はこれから", "tone": "muted"}

    points = []
    if d["value"] != "未判断":
        points.append(f"人の判断：{d['value']}（{d['by']}／{d['date']}）")
        points += [x for x in str(d.get("conditions") or "").splitlines() if x.strip()]
    for k, text in (("hard", "使えないとの記載・確認あり"), ("extra", "追加の対応が必要"), ("check", "確認が必要")):
        hit = [x for x in rs if x["group"] == k and x["req"].get("priority") == "必須"]
        if hit:
            points.append(f"必須要件：{_names(hit)}は{text}")
    if m["stale"]:
        points.append(f"再確認が必要な項目が{len(m['stale'])}件あります（古い根拠・旧版に基づく結果）")

    prod = primary_product(project) or {}
    return {"head": head, "subs": subs, "status": status, "points": points, "product": prod.get("name") or "製品未登録",
            "plan": prod.get("plan", ""), "total": len(rs), "must": len(must)}


def kpis(rs: list[dict], m: dict) -> dict:
    """件数の枠。件数がある区分を大きく、0件の区分はまとめる。分母は全要件。"""
    c = counts(rs)
    main = [{"key": k, "label": GROUPS[k]["label"], "value": c[k]} for k in ("likely", "extra", "hard", "check") if c[k]]
    zero = [GROUPS[k]["label"] for k in ("likely", "extra", "hard", "check") if not c[k]]
    return {"main": main, "zero": zero, "none": c["none"], "total": len(rs),
            "tests": {"total": m["tests"], "run": m["executed_rate"]["num"], "passed": len(m["passed"]), "failed": len(m["failed"])}}
