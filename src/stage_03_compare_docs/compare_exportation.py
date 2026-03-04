# -*- coding: utf-8 -*-
"""
Stage 03 - EXPORTATION - Compare extracted fields between documents.

Input : stage_02_fields/exportation/*_fields.json
Output: stage_03_compare/exportation/_stage03_comparison.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def is_blank(v: Any) -> bool:
    return v is None or v == "" or v == []


def norm_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().upper()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", "", s)
    return s.strip()


def digits_only(v: Any) -> str:
    return re.sub(r"\D+", "", str(v or ""))


def to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "." in s and s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s)
    except ValueError:
        return None


def num_close(a: float, b: float, abs_tol: float = 1.0, rel_tol: float = 0.01) -> bool:
    diff = abs(a - b)
    if diff <= abs_tol:
        return True
    return diff / max(abs(a), abs(b), 1.0) <= rel_tol


def token_overlap_close(a: Any, b: Any, min_jaccard: float = 0.55) -> bool:
    na = norm_str(a)
    nb = norm_str(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta = set(na.split())
    tb = set(nb.split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return (inter / union) >= min_jaccard


def cnpj_close(a: Any, b: Any) -> bool:
    da = digits_only(a)
    db = digits_only(b)
    return bool(da and db and da == db)


def docref_close(a: Any, b: Any) -> bool:
    da = re.sub(r"[^A-Z0-9]", "", norm_str(a))
    db = re.sub(r"[^A-Z0-9]", "", norm_str(b))
    if not da or not db:
        return False
    if da == db:
        return True
    return da.rstrip("P") == db.rstrip("P")


def code_prefix_close(a: Any, b: Any) -> bool:
    da = digits_only(a)
    db = digits_only(b)
    if not da or not db:
        return False
    if da == db:
        return True
    short, long_ = (da, db) if len(da) <= len(db) else (db, da)
    return len(short) in (4, 6) and long_.startswith(short)


def get_field(doc: Dict[str, Any], key: str) -> Tuple[Any, List[str]]:
    fields = doc.get("fields") or {}
    meta = fields.get(key) or {}
    if not isinstance(meta, dict):
        return None, []
    return meta.get("value"), list(meta.get("evidence") or [])


def get_field_any(doc: Dict[str, Any], keys: List[str]) -> Tuple[Any, List[str], Optional[str]]:
    for k in keys:
        value, evidence = get_field(doc, k)
        if not is_blank(value):
            return value, evidence, k
    return None, [], None


def get_container_numbers(doc: Dict[str, Any], key_candidates: List[str]) -> List[str]:
    value, _, _ = get_field_any(doc, key_candidates)
    out: List[str] = []

    def _collect_from_any(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, dict):
            cn = str(item.get("container_number") or "").strip().upper()
            if cn:
                out.append(cn)
                return
            for v in item.values():
                _collect_from_any(v)
            return
        if isinstance(item, list):
            for it in item:
                _collect_from_any(it)
            return
        if isinstance(item, str):
            for m in re.finditer(r"\b([A-Z]{4}\d{7})\b", item.upper()):
                out.append(m.group(1))
            return

    _collect_from_any(value)
    return sorted(set(out))


def doc_label(doc: Dict[str, Any]) -> str:
    src = doc.get("source") or {}
    return (
        src.get("original_file")
        or src.get("stage01_file")
        or src.get("doc_kind")
        or "doc"
    )


def get_doc_kind(doc: Dict[str, Any]) -> str:
    return str((doc.get("source") or {}).get("doc_kind") or "unknown")


@dataclass
class CheckSpec:
    name: str
    kind: str  # number|string|cnpj|docref|code_prefix
    a_keys: List[str]
    b_keys: List[str]
    abs_tol: float = 1.0
    rel_tol: float = 0.01


INVOICE_VS_PACKING = [
    CheckSpec("Invoice/Packing reference", "docref", ["invoice_number"], ["packing_list_number"]),
    CheckSpec("Gross weight (kg)", "number", ["gross_weight_kg"], ["gross_weight_kg"]),
    CheckSpec("Net weight (kg)", "number", ["net_weight_kg"], ["net_weight_kg"]),
    CheckSpec("NCM", "code_prefix", ["ncm"], ["ncm"]),
    CheckSpec("Incoterm", "string", ["incoterm"], ["incoterm"]),
    CheckSpec("Container count", "number", ["container_count"], ["container_count"], abs_tol=0.0, rel_tol=0.0),
]

INVOICE_VS_DRAFT_BL = [
    CheckSpec("Incoterm", "string", ["incoterm"], ["incoterm"]),
    CheckSpec("NCM", "code_prefix", ["ncm"], ["ncm"]),
    CheckSpec("Exporter CNPJ", "cnpj", ["exporter_cnpj"], ["exporter_cnpj"]),
    CheckSpec("Exporter name", "string", ["exporter_name"], ["exporter_name"]),
    CheckSpec("Importer name", "string", ["importer_name"], ["importer_name"]),
    CheckSpec("Gross weight (kg)", "number", ["gross_weight_kg"], ["gross_weight_kg_total"]),
    CheckSpec("Net weight (kg)", "number", ["net_weight_kg"], ["net_weight_kg_total"]),
]

PACKING_VS_DRAFT_BL = [
    CheckSpec("NCM", "code_prefix", ["ncm"], ["ncm"]),
    CheckSpec("Incoterm", "string", ["incoterm"], ["incoterm"]),
    CheckSpec("Gross weight (kg)", "number", ["gross_weight_kg"], ["gross_weight_kg_total"]),
    CheckSpec("Net weight (kg)", "number", ["net_weight_kg"], ["net_weight_kg_total"]),
]

COO_VS_INVOICE = [
    CheckSpec("Invoice reference", "docref", ["invoice_number"], ["invoice_number"]),
    CheckSpec("Exporter name", "string", ["exporter_name"], ["exporter_name"]),
    CheckSpec("Importer name", "string", ["importer_name"], ["importer_name"]),
    CheckSpec("Gross weight (kg)", "number", ["gross_weight_kg"], ["gross_weight_kg"]),
    CheckSpec("Net weight (kg)", "number", ["net_weight_kg"], ["net_weight_kg"]),
]


def compare_pair(doc_a: dict, doc_b: dict, specs: List[CheckSpec], label: str) -> List[dict]:
    out: List[dict] = []
    for spec in specs:
        va, eva, a_used = get_field_any(doc_a, spec.a_keys)
        vb, evb, b_used = get_field_any(doc_b, spec.b_keys)

        if is_blank(va) and is_blank(vb):
            out.append(
                {
                    "pair": label,
                    "check": spec.name,
                    "status": "skipped",
                    "reason": "missing_on_both",
                    "a_key_used": a_used,
                    "b_key_used": b_used,
                    "a_value": None,
                    "b_value": None,
                }
            )
            continue
        if is_blank(va):
            out.append(
                {
                    "pair": label,
                    "check": spec.name,
                    "status": "skipped",
                    "reason": "missing_on_a",
                    "a_key_used": a_used,
                    "b_key_used": b_used,
                    "a_value": None,
                    "b_value": vb,
                }
            )
            continue
        if is_blank(vb):
            out.append(
                {
                    "pair": label,
                    "check": spec.name,
                    "status": "skipped",
                    "reason": "missing_on_b",
                    "a_key_used": a_used,
                    "b_key_used": b_used,
                    "a_value": va,
                    "b_value": None,
                }
            )
            continue

        status = "divergent"
        a_value_out: Any = va
        b_value_out: Any = vb

        if spec.kind == "number":
            fa = to_float(va)
            fb = to_float(vb)
            if fa is None or fb is None:
                status = "skipped"
                reason = "not_numeric"
                out.append(
                    {
                        "pair": label,
                        "check": spec.name,
                        "status": status,
                        "reason": reason,
                        "a_key_used": a_used,
                        "b_key_used": b_used,
                        "a_value": va,
                        "b_value": vb,
                    }
                )
                continue
            status = "match" if num_close(fa, fb, abs_tol=spec.abs_tol, rel_tol=spec.rel_tol) else "divergent"
            a_value_out = fa
            b_value_out = fb
        elif spec.kind == "string":
            status = "match" if token_overlap_close(va, vb) else "divergent"
        elif spec.kind == "cnpj":
            status = "match" if cnpj_close(va, vb) else "divergent"
        elif spec.kind == "docref":
            status = "match" if docref_close(va, vb) else "divergent"
        elif spec.kind == "code_prefix":
            status = "match" if code_prefix_close(va, vb) else "divergent"

        out.append(
            {
                "pair": label,
                "check": spec.name,
                "status": status,
                "a_key_used": a_used,
                "b_key_used": b_used,
                "a_value": a_value_out,
                "b_value": b_value_out,
                "evidence": {"a": eva[:2], "b": evb[:2]},
            }
        )
    return out


def pair_by_reference(invoices: List[dict], packings: List[dict]) -> List[Tuple[dict, dict]]:
    pairs: List[Tuple[dict, dict]] = []
    for inv in invoices:
        inv_num, _, _ = get_field_any(inv, ["invoice_number"])
        for pl in packings:
            pl_num, _, _ = get_field_any(pl, ["packing_list_number", "invoice_number"])
            if not is_blank(inv_num) and not is_blank(pl_num) and docref_close(inv_num, pl_num):
                pairs.append((inv, pl))
    if pairs:
        return pairs
    for inv in invoices:
        for pl in packings:
            pairs.append((inv, pl))
    return pairs


def _group_check_equal(
    name: str,
    docs: List[dict],
    aliases_by_kind: Dict[str, List[str]],
    mode: str = "string",
) -> dict:
    items: List[dict] = []
    missing: List[str] = []
    values: List[Any] = []

    for d in docs:
        kind = get_doc_kind(d)
        keys = aliases_by_kind.get(kind, [])
        value, evidence, used = get_field_any(d, keys) if keys else (None, [], None)
        label = doc_label(d)
        if is_blank(value):
            missing.append(label)
        items.append(
            {
                "doc": label,
                "doc_kind": kind,
                "key_used": used,
                "value": value,
                "evidence": evidence[:2],
            }
        )
        values.append(value)

    present = [v for v in values if not is_blank(v)]
    if missing:
        return {
            "group_check": name,
            "status": "missing",
            "reason": f"missing_in: {', '.join(missing)}",
            "items": items,
        }
    if not present:
        return {
            "group_check": name,
            "status": "missing",
            "reason": "no_values_found",
            "items": items,
        }

    base = present[0]
    if mode == "cnpj":
        ok = all(cnpj_close(v, base) for v in present)
    else:
        ok = all(token_overlap_close(v, base) for v in present)
    return {
        "group_check": name,
        "status": "match" if ok else "divergent",
        "reason": "all_equal" if ok else "values_differ",
        "items": items,
    }


def rule_check_incoterm_vs_freight_mode(invoices: List[dict], bls: List[dict]) -> List[dict]:
    out: List[dict] = []
    mapping = {
        "EXW": "COLLECT",
        "FCA": "COLLECT",
        "FOB": "COLLECT",
        "FAS": "COLLECT",
        "CFR": "PREPAID",
        "CIF": "PREPAID",
        "CPT": "PREPAID",
        "CIP": "PREPAID",
        "DAP": "PREPAID",
        "DPU": "PREPAID",
        "DDP": "PREPAID",
    }
    for inv in invoices:
        for bl in bls:
            incoterm, ie, ik = get_field_any(inv, ["incoterm"])
            freight, fe, fk = get_field_any(bl, ["freight_mode"])
            label = f"{doc_label(inv)} <> {doc_label(bl)}"

            if is_blank(incoterm) or is_blank(freight):
                out.append(
                    {
                        "rule_check": "incoterm_vs_freight_mode",
                        "pair": label,
                        "status": "skipped",
                        "reason": "missing_incoterm_or_freight_mode",
                        "invoice_incoterm": incoterm,
                        "bl_freight_mode": freight,
                        "keys_used": {"invoice": ik, "bl": fk},
                        "evidence": {"invoice": ie[:2], "bl": fe[:2]},
                    }
                )
                continue

            expected = mapping.get(str(incoterm).strip().upper())
            actual = str(freight).strip().upper()
            if expected is None:
                out.append(
                    {
                        "rule_check": "incoterm_vs_freight_mode",
                        "pair": label,
                        "status": "skipped",
                        "reason": "incoterm_not_in_mapping",
                        "invoice_incoterm": incoterm,
                        "expected_mode": None,
                        "bl_freight_mode": actual,
                        "keys_used": {"invoice": ik, "bl": fk},
                        "evidence": {"invoice": ie[:2], "bl": fe[:2]},
                    }
                )
                continue

            out.append(
                {
                    "rule_check": "incoterm_vs_freight_mode",
                    "pair": label,
                    "status": "match" if actual == expected else "divergent",
                    "invoice_incoterm": incoterm,
                    "expected_mode": expected,
                    "bl_freight_mode": actual,
                    "keys_used": {"invoice": ik, "bl": fk},
                    "evidence": {"invoice": ie[:2], "bl": fe[:2]},
                }
            )
    return out


def run_stage_03_comparison(in_dir: Path, out_dir: Path, verbose: bool = True) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted([p for p in in_dir.glob("*_fields.json") if p.name != "_stage02_summary.json"])
    if not files:
        return {
            "processed_count": 0,
            "warnings": [f"No *_fields.json files found in: {in_dir}"],
            "output_file": "",
        }

    docs = [read_json(p) for p in files]
    by_kind: Dict[str, List[dict]] = {}
    for d in docs:
        kind = get_doc_kind(d)
        by_kind.setdefault(kind, []).append(d)

    invoices = by_kind.get("commercial_invoice", [])
    packings = by_kind.get("packing_list", [])
    bls = by_kind.get("draft_bl", [])
    coos = by_kind.get("certificate_of_origin", [])
    cntr_data = by_kind.get("container_data", [])

    comparisons: List[dict] = []
    group_checks: List[dict] = []
    rule_checks: List[dict] = []
    documents_meta: List[dict] = []

    for d in docs:
        src = d.get("source") or {}
        documents_meta.append(
            {
                "doc_kind": src.get("doc_kind"),
                "doc_kind_hint": src.get("doc_kind_hint"),
                "original_file": src.get("original_file"),
                "stage02_file": src.get("stage01_file"),
                "missing_required_fields": d.get("missing_required_fields", []),
                "warnings": d.get("warnings", []),
            }
        )

    for inv, pl in pair_by_reference(invoices, packings):
        label = f"invoice_vs_packing | {doc_label(inv)} <> {doc_label(pl)}"
        comparisons.extend(compare_pair(inv, pl, INVOICE_VS_PACKING, label))

    for bl in bls:
        for inv in invoices:
            label = f"invoice_vs_draft_bl | {doc_label(inv)} <> {doc_label(bl)}"
            comparisons.extend(compare_pair(inv, bl, INVOICE_VS_DRAFT_BL, label))
        for pl in packings:
            label = f"packing_vs_draft_bl | {doc_label(pl)} <> {doc_label(bl)}"
            comparisons.extend(compare_pair(pl, bl, PACKING_VS_DRAFT_BL, label))

    for coo in coos:
        for inv in invoices:
            label = f"coo_vs_invoice | {doc_label(coo)} <> {doc_label(inv)}"
            comparisons.extend(compare_pair(coo, inv, COO_VS_INVOICE, label))

    for cdoc in cntr_data:
        for bl in bls:
            label = f"container_data_vs_draft_bl | {doc_label(cdoc)} <> {doc_label(bl)}"
            booking_checks = compare_pair(
                cdoc,
                bl,
                [CheckSpec("Booking number", "docref", ["booking_number"], ["booking_number"])],
                label,
            )
            comparisons.extend(booking_checks)

            a = get_container_numbers(cdoc, ["containers"])
            b = get_container_numbers(bl, ["containers"])
            if not a and not b:
                status = "skipped"
                reason = "missing_on_both"
            elif not a:
                status = "skipped"
                reason = "missing_on_a"
            elif not b:
                status = "skipped"
                reason = "missing_on_b"
            else:
                status = "match" if set(a) == set(b) else "divergent"
                reason = "set_equal" if status == "match" else "set_differ"
            comparisons.append(
                {
                    "pair": label,
                    "check": "Container numbers",
                    "status": status,
                    "reason": reason,
                    "a_key_used": "containers",
                    "b_key_used": "containers",
                    "a_value": a,
                    "b_value": b,
                }
            )

    core_docs = []
    core_docs.extend(invoices[:1] if invoices else [])
    core_docs.extend(bls[:1] if bls else [])
    core_docs.extend(coos[:1] if coos else [])
    if core_docs:
        group_checks.append(
            _group_check_equal(
                name="exporter_name_equal_across_invoice_bl_coo",
                docs=core_docs,
                aliases_by_kind={
                    "commercial_invoice": ["exporter_name"],
                    "draft_bl": ["exporter_name"],
                    "certificate_of_origin": ["exporter_name"],
                },
                mode="string",
            )
        )
        group_checks.append(
            _group_check_equal(
                name="importer_name_equal_across_invoice_bl_coo",
                docs=core_docs,
                aliases_by_kind={
                    "commercial_invoice": ["importer_name"],
                    "draft_bl": ["importer_name"],
                    "certificate_of_origin": ["importer_name"],
                },
                mode="string",
            )
        )

    cnpj_docs = []
    cnpj_docs.extend(invoices[:1] if invoices else [])
    cnpj_docs.extend(bls[:1] if bls else [])
    if cnpj_docs:
        group_checks.append(
            _group_check_equal(
                name="exporter_cnpj_equal_across_invoice_bl",
                docs=cnpj_docs,
                aliases_by_kind={
                    "commercial_invoice": ["exporter_cnpj"],
                    "draft_bl": ["exporter_cnpj"],
                },
                mode="cnpj",
            )
        )

    rule_checks.extend(rule_check_incoterm_vs_freight_mode(invoices, bls))

    pair_total = len(comparisons)
    pair_matches = sum(1 for c in comparisons if c["status"] == "match")
    pair_divs = sum(1 for c in comparisons if c["status"] == "divergent")
    pair_skipped = sum(1 for c in comparisons if c["status"] == "skipped")

    group_total = len(group_checks)
    group_divs = sum(1 for g in group_checks if g["status"] == "divergent")
    group_missing = sum(1 for g in group_checks if g["status"] == "missing")

    rule_total = len(rule_checks)
    rule_divs = sum(1 for r in rule_checks if r.get("status") == "divergent")
    rule_skipped = sum(1 for r in rule_checks if r.get("status") == "skipped")

    out_obj = {
        "generated_at": now_iso(),
        "flow": "exportation",
        "input_folder": str(in_dir),
        "documents": documents_meta,
        "summary": {
            "pair_checks": {
                "total": pair_total,
                "matches": pair_matches,
                "divergences": pair_divs,
                "skipped": pair_skipped,
            },
            "group_checks": {
                "total": group_total,
                "divergences": group_divs,
                "missing": group_missing,
            },
            "rule_checks": {
                "total": rule_total,
                "divergences": rule_divs,
                "skipped": rule_skipped,
            },
        },
        "comparisons": comparisons,
        "group_checks": group_checks,
        "rule_checks": rule_checks,
    }

    out_path = out_dir / "_stage03_comparison.json"
    write_json(out_path, out_obj)

    if verbose:
        print("Completed.")
        print(f"Output: {out_path}")

    return {
        "processed_count": len(files),
        "warnings": [],
        "output_file": str(out_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Stage 02 exportation folder (*_fields.json)")
    ap.add_argument("--output", required=True, help="Stage 03 output folder")
    args = ap.parse_args()

    run_stage_03_comparison(
        in_dir=Path(args.input),
        out_dir=Path(args.output),
        verbose=True,
    )


if __name__ == "__main__":
    main()
