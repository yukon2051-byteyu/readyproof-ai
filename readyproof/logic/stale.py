"""古い根拠・旧版に基づく結果の検出（再確認対象の抽出）。

旧版を保管しただけでは再確認にしない。各結果が「採用した根拠・前提」の指紋を持ち、
その指紋が今と違う場合だけ再確認対象にする。
"""
from __future__ import annotations

from ..core import find, fingerprint
from .rules import diagnosis_basis, latest_run

_BASIS_LABEL = {"requirement": "要件の版・状態", "product_plan": "製品のプラン・版"}


def diagnosis_stale_reasons(project: dict, dg: dict) -> list[str]:
    if dg.get("superseded_by"):
        return []
    old = dg.get("basis") or {}
    new = diagnosis_basis(project, dg)
    reasons = []
    for k, v in new.items():
        if old.get(k) != v:
            if k.startswith("evidence:"):
                i = int(k.split(":")[1])
                ev = dg["evidence"][i]
                ref = ev.get("seg_id") or ev.get("utt_id") or ev.get("question_id")
                reasons.append(f"根拠 {ref} の内容・確認状態・版が変わりました")
            else:
                reasons.append(f"{_BASIS_LABEL.get(k, k)}が変わりました")
    req = find(project, "requirements", dg["req_id"])
    if req and req["version"] != dg["req_version"]:
        reasons.append(f"要件が第{dg['req_version']}版→第{req['version']}版に更新されました")
    return sorted(set(reasons))


def test_stale_reasons(project: dict, t: dict) -> list[str]:
    reasons = []
    for rid, ver in (t.get("req_versions") or {}).items():
        req = find(project, "requirements", rid)
        if req and req["version"] != ver:
            reasons.append(f"要件 {rid} が第{ver}版→第{req['version']}版に更新されました")
    for crid in t.get("request_ids", []):
        cr = find(project, "requests", crid)
        if cr and t.get("request_versions", {}).get(crid) not in (None, cr["version"]):
            reasons.append(f"依頼書 {crid} が更新されました（受入条件を確認）")
    return reasons


def run_stale_reasons(project: dict, run: dict) -> list[str]:
    t = find(project, "tests", run["test_id"])
    if not t:
        return ["テストが存在しません"]
    reasons = []
    if run["test_version"] != t["version"]:
        reasons.append(f"テストが第{run['test_version']}版→第{t['version']}版に変わりました（旧版の結果は流用不可）")
    reasons += test_stale_reasons(project, t)
    return reasons


def decision_snapshot(project: dict, metrics: dict) -> dict:
    """導入判断時点の状態。判断後の更新を検出するために保存する。"""
    return {"metrics": {k: v for k, v in metrics.items() if isinstance(v, (int, float, str))},
            "fp": fingerprint([project["diagnoses"], project["runs"], project["requests"],
                               project["questions"], project["requirements"]])}


def decision_changed_since(project: dict) -> bool:
    d = project.get("decision") or {}
    snap = d.get("snapshot")
    if not snap or d.get("value") == "未判断":
        return False
    return snap.get("fp") != fingerprint([project["diagnoses"], project["runs"], project["requests"],
                                          project["questions"], project["requirements"]])


def all_stale(project: dict) -> list[dict]:
    """再確認が必要な項目の一覧。"""
    items = []
    for dg in project["diagnoses"]:
        rs = diagnosis_stale_reasons(project, dg)
        if rs:
            items.append({"type": "診断", "id": dg["id"], "req_id": dg["req_id"], "reasons": rs})
    for t in project["tests"]:
        if t["status"] == "廃止":
            continue
        rs = test_stale_reasons(project, t)
        if rs:
            items.append({"type": "テスト", "id": t["id"], "req_id": ",".join(t.get("req_ids", [])), "reasons": rs})
        lr = latest_run(project, t["id"])
        if lr:
            rr = run_stale_reasons(project, lr)
            if rr:
                items.append({"type": "実施結果", "id": lr["id"], "req_id": ",".join(t.get("req_ids", [])),
                              "reasons": rr})
    return items
