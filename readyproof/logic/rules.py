"""業務ルール（状態の変更はここを通す）。

仕様上の禁止事項をプログラムで強制する。画面は RuleError のメッセージをそのまま表示する。
"""
from __future__ import annotations

import re

from ..core import (DIAG_CATEGORIES, REQUEST_STATUS, bump_version, fingerprint, log, next_id, now_iso)
from .evidence import evidence_fp, is_vendor_confirmed, validate_evidence


class RuleError(Exception):
    """業務ルール違反。利用者に理由を表示する。"""


# ================= 資料 =================
def add_source(project: dict, ingest: dict, meta: dict, new_version_of: str | None = None) -> dict:
    """読込結果を資料として登録する。new_version_of を指定すると同じIDの新しい版になる。"""
    if new_version_of:
        olds = [s for s in project["sources"] if s["id"] == new_version_of]
        if not olds:
            raise RuleError("元の資料が見つかりません。")
        version = max(int(s.get("version", 1)) for s in olds) + 1
        for s in olds:
            s["status"] = "旧版"
        sid = new_version_of
    else:
        sid, version = next_id(project, "sources"), 1
    src = {
        "id": sid, "version": version,
        "name": meta.get("name") or meta.get("file_name") or "無題の資料",
        "file_name": meta.get("file_name", ""),
        "owner": meta.get("owner", "製品"),  # 製品 / 自社
        "product_id": meta.get("product_id") if meta.get("owner", "製品") == "製品" else None,
        "kind": meta.get("kind", "その他"),
        "issued_on": meta.get("issued_on", ""), "received_on": meta.get("received_on", ""),
        "plan": meta.get("plan", ""), "status": meta.get("status", "有効"),
        "file_type": ingest["file_type"], "extract_status": ingest["status"],
        "warnings": ingest["warnings"], "coverage": ingest["coverage"], "segments": ingest["segments"],
        "user_notes": "", "registered_at": now_iso(), "original_retained": False,
    }
    project["sources"].append(src)
    log(project, "資料登録", f"{sid} v{version}", detail=src["name"])
    return src


def set_segment_selected(source: dict, seg_id: str, selected: bool) -> None:
    seg = next((g for g in source["segments"] if g["seg_id"] == seg_id), None)
    if seg is None:
        raise RuleError("箇所が見つかりません。")
    if selected and seg.get("is_note") and not seg.get("note_reviewed"):
        raise RuleError("発表者ノートは、内容を確認したことをチェックしてから対象にしてください。")
    seg["selected"] = selected


# ================= 要件 =================
REQ_FIELDS = ["business", "workflow", "role", "rules", "exceptions", "inputs", "outputs", "priority",
              "reason", "basis", "open_issues", "original_text"]

_KEY_TERMS = ["以上", "未満", "以下", "超", "禁止", "不可", "例外", "除く", "以外", "必ず", "のみ", "ただし"]
_NUM = re.compile(r"[0-9０-９][0-9０-９,，.]*")


def missing_terms(original: str, fields: dict) -> list[str]:
    """元文にある数値・条件語が、分割後の項目から落ちていないかを調べる。"""
    joined = " ".join(str(fields.get(k, "")) for k in REQ_FIELDS if k != "original_text")
    norm = lambda s: s.replace(",", "").replace("，", "")
    missing = [n for n in set(_NUM.findall(original)) if norm(n) not in norm(joined)]
    missing += [t for t in _KEY_TERMS if t in original and t not in joined]
    return sorted(set(missing))


def add_requirement(project: dict, fields: dict, origin: str = "手動", by: str = "") -> dict:
    req = {"id": next_id(project, "requirements"), "version": 1, "status": "下書き", "origin": origin,
           "created_at": now_iso(), "history": [], "confirmed_by": "", "confirmed_at": ""}
    for k in REQ_FIELDS:
        req[k] = fields.get(k, "")
    req["priority"] = req["priority"] or "必須"
    req["term_warnings"] = missing_terms(req["original_text"], req) if req["original_text"] else []
    project["requirements"].append(req)
    log(project, "要件登録", req["id"], by, origin)
    return req


def update_requirement(project: dict, req: dict, fields: dict, by: str = "", reason: str = "") -> bool:
    changed = {k: v for k, v in fields.items() if k in REQ_FIELDS and req.get(k) != v}
    if not changed:
        return False
    if req["status"] == "確定":
        bump_version(req, by, reason or "確定後の変更")
        req["status"] = "下書き"  # 変更後は再確定が必要
    req.update(changed)
    req["term_warnings"] = missing_terms(req["original_text"], req) if req.get("original_text") else []
    log(project, "要件変更", f"{req['id']} v{req['version']}", by, reason)
    return True


def confirm_requirement(project: dict, req: dict, by: str) -> None:
    if not by.strip():
        raise RuleError("確定する人の名前を入力してください（自己申告）。")
    if not (req.get("rules") or req.get("workflow")):
        raise RuleError("作業内容またはルール・条件を入力してから確定してください。")
    req["status"], req["confirmed_by"], req["confirmed_at"] = "確定", by, now_iso()
    log(project, "要件確定", f"{req['id']} v{req['version']}", by)


def retire_requirement(project: dict, req: dict, by: str, reason: str) -> None:
    if not reason.strip():
        raise RuleError("廃止の理由を入力してください。")
    bump_version(req, by, "廃止：" + reason)
    req["status"] = "廃止"
    log(project, "要件廃止", req["id"], by, reason)


# ================= 診断 =================
def diagnosis_basis(project: dict, dg: dict) -> dict:
    """診断が前提にした情報の指紋。後で変わったら「再確認が必要」になる。"""
    from ..core import find

    from ..core import primary_product

    req = find(project, "requirements", dg["req_id"])
    prod = find(project, "products", dg.get("product_id")) if dg.get("product_id") else primary_product(project)
    basis = {
        "requirement": fingerprint([req and req.get("version"), req and req.get("status")]),
        "product_plan": fingerprint([prod and prod.get("plan"), prod and prod.get("edition")]),
    }
    for i, ev in enumerate(dg.get("evidence", [])):
        basis[f"evidence:{i}"] = evidence_fp(project, ev)
    return basis


def check_diagnosis(project: dict, dg: dict) -> dict:
    """根拠を検証し、診断区分とのつじつまを確認する。結果は dg['validation'] に保存。"""
    results, valid = [], []
    for ev in dg.get("evidence", []):
        v = validate_evidence(project, ev, dg.get("product_id"))
        results.append(v)
        if v["ok"]:
            valid.append(ev)
    problems = []
    cat = dg.get("category")
    if cat not in DIAG_CATEGORIES:
        problems.append("診断区分が不正です。")
    if cat in DIAG_CATEGORIES[:4] and not valid:
        problems.append("有効な根拠がありません。根拠なしでは「情報不足・ベンダー確認が必要」になります。")
    if cat == "対応不可との記載・確認済み発言あり":
        strong = [ev for ev in valid if ev.get("ref_type") == "source" or is_vendor_confirmed(project, ev)
                  or ev.get("ref_type") == "answer"]
        if not strong:
            problems.append("「対応不可」には、資料の記載か利用者確認済みのベンダー発言が必要です（記載がない＝不可ではありません）。")
    if cat in DIAG_CATEGORIES[:2] and dg.get("remaining_conditions"):
        problems.append("満たしていない条件が残っているのに「対応できる見込み」になっています。")
    only_unconfirmed = valid and all(ev.get("ref_type") == "utterance" and not is_vendor_confirmed(project, ev)
                                     for ev in valid)
    if only_unconfirmed and cat in DIAG_CATEGORIES[:3]:
        problems.append("根拠が未確認の発言だけです。話者と内容を確認するまで見込みとして確定できません。")
    dg["validation"] = {"evidence": results, "problems": problems, "checked_at": now_iso()}
    return dg["validation"]


def normalize_ai_diagnosis(project: dict, dg: dict) -> dict:
    """AI の診断案を検証し、根拠のない断定を自動で弱める（人の確認前の安全装置）。"""
    v = check_diagnosis(project, dg)
    valid = [ev for ev, r in zip(dg.get("evidence", []), v["evidence"]) if r["ok"]]
    dropped = len(dg.get("evidence", [])) - len(valid)
    notes = []
    if dropped:
        notes.append(f"検証できない根拠 {dropped} 件を除外しました。")
    dg["rejected_evidence"] = [ev for ev, r in zip(dg.get("evidence", []), v["evidence"]) if not r["ok"]]
    dg["evidence"] = valid
    cat = dg.get("category")
    if cat in DIAG_CATEGORIES[:4] and not valid:
        notes.append(f"根拠がないため「{cat}」を「情報不足・ベンダー確認が必要」に変更しました。")
        dg["category"] = "情報不足・ベンダー確認が必要"
    elif cat == "対応不可との記載・確認済み発言あり":
        strong = [ev for ev in valid if ev.get("ref_type") in ("source", "answer") or is_vendor_confirmed(project, ev)]
        if not strong:
            notes.append("確かな根拠がないため「対応不可」を「情報不足・ベンダー確認が必要」に変更しました。")
            dg["category"] = "情報不足・ベンダー確認が必要"
    if dg["category"] in DIAG_CATEGORIES[:2] and dg.get("remaining_conditions"):
        notes.append("満たしていない条件が残るため「情報不足・ベンダー確認が必要」に変更しました（部分対応を全体の適合としない）。")
        dg["category"] = "情報不足・ベンダー確認が必要"
    dg["auto_adjustments"] = notes
    check_diagnosis(project, dg)
    return dg


def add_diagnosis(project: dict, data: dict, origin: str = "AI生成") -> dict:
    from ..core import find

    req = find(project, "requirements", data["req_id"])
    if req is None:
        raise RuleError(f"要件 {data['req_id']} が存在しません。")
    # 同じ要件の以前の診断は「旧診断」として残す（最新へ自動流用しない）
    for old in project["diagnoses"]:
        if old["req_id"] == req["id"] and not old.get("superseded_by"):
            old["superseded_by"] = "pending"
    dg = {
        "id": next_id(project, "diagnoses"), "req_id": req["id"], "req_version": req["version"],
        "product_id": data.get("product_id"), "category": data.get("category", "情報不足・ベンダー確認が必要"),
        "reason": data.get("reason", ""), "met_conditions": data.get("met_conditions", []),
        "remaining_conditions": data.get("remaining_conditions", []), "evidence": data.get("evidence", []),
        "constraints": data.get("constraints", ""), "plan_conditions": data.get("plan_conditions", ""),
        "next_check": data.get("next_check", ""), "review_status": "未確認",
        "origin": origin, "reviewed_by": "", "reviewed_at": "", "review_comment": "",
        "created_at": now_iso(), "superseded_by": None,
    }
    if origin == "手動":
        check_diagnosis(project, dg)
    else:
        normalize_ai_diagnosis(project, dg)
    dg["basis"] = diagnosis_basis(project, dg)
    for old in project["diagnoses"]:
        if old.get("superseded_by") == "pending":
            old["superseded_by"] = dg["id"]
    project["diagnoses"].append(dg)
    log(project, "診断作成", dg["id"], detail=f"{req['id']} {origin}")
    return dg


def review_diagnosis(project: dict, dg: dict, by: str, status: str, comment: str = "",
                     category: str | None = None) -> None:
    if not by.strip():
        raise RuleError("確認した人の名前を入力してください（自己申告）。")
    if category and category != dg["category"]:
        dg.setdefault("history", []).append({"at": now_iso(), "by": by, "from": dg["category"], "to": category})
        dg["category"] = category
    v = check_diagnosis(project, dg)
    if status == "人が確認済み":
        if any(not r["ok"] for r in v["evidence"]):
            raise RuleError("検証エラーのある根拠が含まれています。根拠を修正・削除してから確認済みにしてください。")
        if v["problems"]:
            raise RuleError("診断区分と根拠が合っていません：" + " / ".join(v["problems"]))
    dg["review_status"], dg["reviewed_by"], dg["reviewed_at"], dg["review_comment"] = status, by, now_iso(), comment
    dg["basis"] = diagnosis_basis(project, dg)
    log(project, "診断確認", dg["id"], by, status)


def current_diagnosis(project: dict, req_id: str) -> dict | None:
    cands = [d for d in project["diagnoses"] if d["req_id"] == req_id and not d.get("superseded_by")]
    return cands[-1] if cands else None


# ================= 質問・回答 =================
def add_question(project: dict, data: dict, origin: str = "手動") -> dict:
    q = {"id": next_id(project, "questions"), "req_ids": data.get("req_ids", []),
         "diag_id": data.get("diag_id", ""), "background": data.get("background", ""),
         "question": data.get("question", ""), "points": data.get("points", ""),
         "evidence": data.get("evidence", []), "status": "下書き", "origin": origin,
         "answer_source": "", "answer_date": "", "answer_text": "", "answer_evidence": [],
         "answer_review": "", "answer_reviewed_by": "", "created_at": now_iso(), "sent_on": ""}
    if not q["question"].strip():
        raise RuleError("質問文を入力してください。")
    project["questions"].append(q)
    log(project, "質問作成", q["id"], detail=origin)
    return q


def written_confirmation_question(project: dict, ev: dict, req_ids: list | None = None) -> dict:
    """重要な口頭説明を、時刻と引用付きで書面確認する質問にする（AI不要の定型文）。"""
    from .evidence import evidence_label

    label = evidence_label(project, ev)
    return add_question(project, {
        "req_ids": req_ids or [],
        "background": f"営業説明ミーティングで次の説明がありました。\n{label}",
        "question": "上記のご説明内容について、書面（メールまたは回答書）で正式にご回答ください。",
        "points": "・対象となるプラン／オプション名\n・追加費用の有無\n・設定方法または手順\n・制限事項・前提条件",
        "evidence": [ev],
    }, origin="定型（書面確認）")


def record_answer(project: dict, q: dict, text: str, source: str, date: str, by: str,
                  evidence: list | None = None) -> None:
    if not text.strip():
        raise RuleError("回答本文を入力してください。")
    if source not in ("手動入力", "資料", "確認済み営業発言"):
        raise RuleError("回答元を選んでください。")
    if source == "確認済み営業発言":
        if not evidence or not all(is_vendor_confirmed(project, ev) for ev in evidence):
            raise RuleError("確認済み営業発言を回答元にする場合は、話者・内容が確認済みのベンダー発言を根拠に指定してください。")
    q.update({"answer_text": text, "answer_source": source, "answer_date": date,
              "answer_evidence": evidence or [], "status": "回答あり", "answer_recorded_by": by})
    log(project, "回答記録", q["id"], by, source)


def confirm_answer(project: dict, q: dict, by: str, review: str) -> None:
    if not by.strip():
        raise RuleError("確認した人の名前を入力してください。")
    if not q.get("answer_text"):
        raise RuleError("回答が記録されていません。")
    q["status"], q["answer_reviewed_by"], q["answer_review"] = "回答確認済み", by, review
    log(project, "回答確認", q["id"], by)


def mark_question_sent(project: dict, q: dict, by: str, date: str) -> None:
    if q["status"] not in ("確定",):
        raise RuleError("送付済みにできるのは「確定」した質問だけです（作成だけでは送付済みになりません）。")
    if not by.strip() or not date:
        raise RuleError("送付した人と日付を記録してください。")
    q["status"], q["sent_on"] = "送付済み", date
    log(project, "質問送付を記録", q["id"], by, date)


# ================= 対応方法 =================
def add_action(project: dict, data: dict, origin: str = "手動") -> dict:
    a = {"id": next_id(project, "actions"), "req_id": data.get("req_id", ""), "diag_id": data.get("diag_id", ""),
         "type": data.get("type", "調査依頼"), "reason": data.get("reason", ""),
         "unknowns": data.get("unknowns", ""), "status": "候補", "origin": origin,
         "decided_by": "", "decided_at": "", "decision_reason": "", "created_at": now_iso()}
    project["actions"].append(a)
    log(project, "対応候補作成", a["id"], detail=origin)
    return a


def decide_action(project: dict, a: dict, status: str, by: str, reason: str) -> None:
    if not by.strip() or not reason.strip():
        raise RuleError("判断した人と理由を入力してください。")
    a.update({"status": status, "decided_by": by, "decided_at": now_iso(), "decision_reason": reason})
    log(project, "対応方法の判断", a["id"], by, f"{status}：{reason}")


# ================= 依頼書 =================
REQUEST_FIELDS = ["title", "kind", "phase", "to", "background", "purpose", "req_ids", "diag_ids", "question_ids",
                  "test_ids", "run_ids", "spec_in_docs", "sales_explanation", "actual_behavior", "conditions",
                  "repro_steps", "needed_behavior", "gap", "impact", "scope", "out_of_scope", "priority",
                  "priority_reason", "desired_date", "desired_date_reason", "assumptions", "questions_to_vendor",
                  "acceptance_criteria", "test_candidates", "evidence"]


def add_request(project: dict, data: dict, origin: str = "手動") -> dict:
    r = {"id": next_id(project, "requests"), "version": 1, "status": "下書き", "origin": origin,
         "history": [], "created_at": now_iso(), "status_log": [],
         "vendor": {"answer": "", "settings_possible": "不明", "modification_needed": "不明",
                    "cost_amount": None, "cost_currency": "", "effort": None, "effort_unit": "",
                    "planned_date": "", "constraints": "", "vendor_done": False, "recorded_by": ""},
         "completion": {"human_confirmed": False, "with_remaining": False, "reason": "", "by": "", "at": ""}}
    for k in REQUEST_FIELDS:
        r[k] = data.get(k, [] if k.endswith("_ids") or k in ("evidence",) else "")
    if not r["title"].strip():
        raise RuleError("件名を入力してください。")
    if r["phase"] == "テストで発生した現象" and not r["run_ids"]:
        raise RuleError("「テストで発生した現象」には、関連する実施結果（実施ID）を指定してください。")
    project["requests"].append(r)
    log(project, "依頼書作成", r["id"], detail=origin)
    return r


def update_request(project: dict, r: dict, fields: dict, by: str = "") -> bool:
    changed = {k: v for k, v in fields.items() if k in REQUEST_FIELDS and r.get(k) != v}
    if not changed:
        return False
    if r["status"] != "下書き":
        bump_version(r, by, "確定後の変更")
    r.update(changed)
    log(project, "依頼書変更", f"{r['id']} v{r['version']}", by)
    return True


_ALLOWED_NEXT = {
    "下書き": {"確定", "見送り"},
    "確定": {"下書き", "送付済み", "見送り"},
    "送付済み": {"回答待ち", "対応検討中", "見送り"},
    "回答待ち": {"対応検討中", "対応中", "見送り", "完了"},
    "対応検討中": {"対応中", "見送り", "完了"},
    "対応中": {"テスト待ち", "見送り"},
    "テスト待ち": {"完了", "対応中", "見送り"},
    "完了": set(),
    "見送り": {"下書き"},
}


def change_request_status(project: dict, r: dict, new: str, by: str, reason: str = "",
                          with_remaining: bool = False) -> None:
    """依頼の状態変更。外部の出来事（送付・回答）は人が記録した場合だけ反映する。"""
    if new not in REQUEST_STATUS:
        raise RuleError("状態が不正です。")
    if not by.strip():
        raise RuleError("記録する人の名前を入力してください（自己申告）。")
    cur = r["status"]
    if new not in _ALLOWED_NEXT.get(cur, set()):
        raise RuleError(f"「{cur}」から「{new}」には変更できません。")
    if new == "見送り" and not reason.strip():
        raise RuleError("見送りの理由を入力してください（見送りでテスト結果は変わりません）。")
    if new == "完了":
        if r.get("kind") == "調査依頼":
            qs = [q for q in project["questions"] if q["id"] in r.get("question_ids", [])]
            answered = bool(r["vendor"].get("answer")) or any(q["status"] == "回答確認済み" for q in qs)
            if not answered:
                raise RuleError("調査依頼を完了にするには、相手の回答を記録して人が確認してください。")
        else:
            passed = _has_current_pass(project, r)
            if not passed and not with_remaining:
                raise RuleError("関連テストの最新の実施が「合格」になっていません。相手の対応完了だけでは完了にできません。"
                                "残件付きで完了する場合は、理由を入力して「残件付き完了」を選んでください。")
            if with_remaining and not reason.strip():
                raise RuleError("残件付き完了の理由を入力してください。")
        r["completion"] = {"human_confirmed": True, "with_remaining": with_remaining, "reason": reason,
                           "by": by, "at": now_iso()}
    r["status_log"].append({"at": now_iso(), "by": by, "from": cur, "to": new, "reason": reason})
    r["status"] = new
    log(project, "依頼状態変更", r["id"], by, f"{cur}→{new} {reason}")


def _has_current_pass(project: dict, r: dict) -> bool:
    from ..core import find

    tests = r.get("test_ids") or []
    if not tests:
        return False
    for tid in tests:
        t = find(project, "tests", tid)
        if not t:
            return False
        latest = latest_run(project, tid)
        if not latest or latest["result"] != "合格" or latest["test_version"] != t["version"]:
            return False
    return True


def record_vendor_response(project: dict, r: dict, data: dict, by: str) -> None:
    """相手の回答の記録。不明な費用・工数は None（0 にしない）。"""
    v = r["vendor"]
    for key in ("cost_amount", "effort"):
        val = data.get(key)
        if val in ("", None):
            v[key] = None
        else:
            try:
                v[key] = float(val)
            except (TypeError, ValueError):
                raise RuleError("費用・工数は数値で入力してください（不明なら空欄）。")
    if v["cost_amount"] is not None and not data.get("cost_currency"):
        raise RuleError("費用を入力した場合は通貨を選んでください。")
    if v["effort"] is not None and not data.get("effort_unit"):
        raise RuleError("工数を入力した場合は単位を選んでください。")
    for key in ("answer", "settings_possible", "modification_needed", "cost_currency", "effort_unit",
                "planned_date", "constraints", "vendor_done"):
        if key in data:
            v[key] = data[key]
    v["recorded_by"] = by
    log(project, "相手の回答を記録", r["id"], by)


# ================= テスト・実施 =================
TEST_FIELDS = ["req_ids", "evidence", "request_ids", "acceptance_ref", "purpose", "viewpoint", "role",
               "preconditions", "inputs", "steps", "expected", "expected_basis", "importance",
               "importance_reason", "open_issues", "expected_confirmed", "title"]


def add_test(project: dict, data: dict, origin: str = "手動") -> dict:
    from ..core import find

    t = {"id": next_id(project, "tests"), "version": 1, "status": "下書き", "origin": origin,
         "history": [], "created_at": now_iso(), "confirmed_by": "", "confirmed_at": "", "req_versions": {}}
    for k in TEST_FIELDS:
        t[k] = data.get(k, [] if k in ("req_ids", "evidence", "request_ids") else "")
    t["expected_confirmed"] = bool(data.get("expected_confirmed", False))
    for rid in t["req_ids"]:
        req = find(project, "requirements", rid)
        if req is None:
            raise RuleError(f"要件 {rid} が存在しません。")
        t["req_versions"][rid] = req["version"]
    t["request_versions"] = {}
    for crid in t["request_ids"]:
        cr = find(project, "requests", crid)
        if cr:
            t["request_versions"][crid] = cr["version"]
    project["tests"].append(t)
    log(project, "テスト作成", t["id"], detail=origin)
    return t


def update_test(project: dict, t: dict, fields: dict, by: str = "") -> bool:
    changed = {k: v for k, v in fields.items() if k in TEST_FIELDS and t.get(k) != v}
    if not changed:
        return False
    if t["status"] == "確定":
        bump_version(t, by, "確定後の変更")
        t["status"] = "下書き"
        t["expected_confirmed"] = False if "expected" in changed else t["expected_confirmed"]
    t.update(changed)
    log(project, "テスト変更", f"{t['id']} v{t['version']}", by)
    return True


def confirm_test(project: dict, t: dict, by: str) -> None:
    from ..core import find

    if not by.strip():
        raise RuleError("確定する人の名前を入力してください。")
    if not t.get("expected", "").strip():
        raise RuleError("期待結果を入力してから確定してください。")
    if not t.get("expected_confirmed"):
        raise RuleError("期待結果が未確定です。期待結果を人が確認したことをチェックしてください。")
    if "要確認" in (t.get("steps") or "") or "要確認" in (t.get("expected") or ""):
        raise RuleError("手順または期待結果に「要確認」が残っています。ベンダーに確認してから確定してください。")
    for rid in t.get("req_ids", []):
        req = find(project, "requirements", rid)
        if req:
            t["req_versions"][rid] = req["version"]
    for crid in t.get("request_ids", []):
        cr = find(project, "requests", crid)
        if cr:
            t.setdefault("request_versions", {})[crid] = cr["version"]
    t["status"], t["confirmed_by"], t["confirmed_at"] = "確定", by, now_iso()
    log(project, "テスト確定", f"{t['id']} v{t['version']}", by)


def runs_for(project: dict, test_id: str) -> list[dict]:
    return [r for r in project["runs"] if r["test_id"] == test_id]


def latest_run(project: dict, test_id: str) -> dict | None:
    runs = runs_for(project, test_id)
    return runs[-1] if runs else None


def record_run(project: dict, t: dict, data: dict) -> dict:
    """実施結果の記録。再テストは常に新しい履歴として追加し、過去の結果は書き換えない。"""
    status, result = data.get("status", "未実施"), data.get("result", "未判定")
    if not data.get("tester", "").strip():
        raise RuleError("実施者の名前を入力してください（自己申告）。")
    if result in ("合格", "不合格") and status != "完了":
        raise RuleError("合否は、実施状態が「完了」のときだけ記録できます。")
    if status == "実施不能" and result != "未判定":
        raise RuleError("実施不能は合否に数えません。結果は「未判定」にしてください。")
    if result == "合格":
        if t["status"] != "確定" or not t.get("expected_confirmed"):
            raise RuleError("期待結果が確定していないテストは「合格」にできません。先にテストを確定してください。")
        if not data.get("actual", "").strip():
            raise RuleError("実際の結果を入力してください。")
    if result == "不合格" and not data.get("actual", "").strip():
        raise RuleError("不合格の場合は、実際の結果（何が起きたか）を入力してください。")
    prev = latest_run(project, t["id"])
    run = {"id": next_id(project, "runs"), "test_id": t["id"], "test_version": t["version"],
           "tester": data["tester"], "executed_at": data.get("executed_at") or now_iso(),
           "product_version": data.get("product_version", ""), "plan": data.get("plan", ""),
           "environment": data.get("environment", ""), "actual": data.get("actual", ""),
           "status": status, "result": result, "evidence_memo": data.get("evidence_memo", ""),
           "defect": data.get("defect", ""), "open_points": data.get("open_points", ""),
           "is_retest": prev is not None, "previous_run_id": prev["id"] if prev else "",
           "recorded_at": now_iso()}
    project["runs"].append(run)
    log(project, "実施結果記録", run["id"], data["tester"], f"{t['id']} v{t['version']} {status}/{result}")
    return run


# ================= 導入判断 =================
def record_decision(project: dict, value: str, by: str, date: str, reason: str, conditions: str,
                    snapshot: dict) -> None:
    if value not in ("未判断", "導入可", "条件付き導入可", "導入延期"):
        raise RuleError("判断の値が不正です。")
    if value != "未判断" and (not by.strip() or not date or not reason.strip()):
        raise RuleError("判断者・日付・理由を入力してください（名前は自己申告で、正式な承認ではありません）。")
    if value == "条件付き導入可" and not conditions.strip():
        raise RuleError("条件付き導入可の場合は条件を入力してください。")
    d = project["decision"]
    if d.get("value") != "未判断":
        d.setdefault("history", []).append({k: d.get(k) for k in ("value", "by", "date", "reason", "conditions")})
    d.update({"value": value, "by": by, "date": date, "reason": reason, "conditions": conditions,
              "snapshot": snapshot, "recorded_at": now_iso()})
    log(project, "導入判断", value, by, reason)
