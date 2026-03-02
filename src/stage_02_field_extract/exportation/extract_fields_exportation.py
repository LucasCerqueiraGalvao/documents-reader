# -*- coding: utf-8 -*-
"""
Stage 02 - EXPORTATION - Extract fields from Stage 01 text.

Input : stage_01_text/exportation/*_extracted.json
Output: stage_02_fields/exportation/*_fields.json + _stage02_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .stage_02_llm import run_stage02_llm_for_exportation
except ImportError:  # pragma: no cover
    from stage_02_llm import run_stage02_llm_for_exportation


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def normalize_for_search(s: str) -> str:
    return normalize_spaces(s).lower()


def parse_number_mixed(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("US$", "").replace("$", "")
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        parts = s.split(",")
        if len(parts) > 2:
            s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            s = s.replace(",", ".")
    elif "." in s and s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return float(s)
    except ValueError:
        return None


def parse_cnpj(raw: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(raw or ""))
    return digits if len(digits) == 14 else None


def find_first(text: str, pattern: str, flags: int = re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text or "", flags)
    if not m:
        return None
    return (m.group(1) if m.lastindex else m.group(0)).strip()


def find_all(text: str, pattern: str, flags: int = re.IGNORECASE) -> List[str]:
    out: List[str] = []
    for m in re.finditer(pattern, text or "", flags):
        v = (m.group(1) if m.lastindex else m.group(0)).strip()
        if v:
            out.append(v)
    return out


def evidence_lines(text: str, token: str, limit: int = 2) -> List[str]:
    lines = []
    needle = str(token or "").strip().lower()
    if not needle:
        return lines
    for line in (text or "").splitlines():
        if needle in line.lower():
            lines.append(normalize_spaces(line))
            if len(lines) >= limit:
                break
    return lines


def make_field(required: bool, value: Any, evidence: Optional[List[str]] = None, method: str = "regex") -> Dict[str, Any]:
    present = value is not None and value != "" and value != []
    return {
        "present": bool(present),
        "required": bool(required),
        "value": value if present else None,
        "evidence": evidence or [],
        "method": method,
    }


def join_pages(stage01: Dict[str, Any]) -> str:
    parts: List[str] = []
    for pg in stage01.get("pages") or []:
        txt = (pg.get("text") or "").strip()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts).strip()


DOC_KIND_HINT_ALIASES = {
    "commercial_invoice": "commercial_invoice",
    "invoice": "commercial_invoice",
    "packing_list": "packing_list",
    "packing list": "packing_list",
    "pl": "packing_list",
    "draft_bl": "draft_bl",
    "bl": "draft_bl",
    "bill_of_lading": "draft_bl",
    "certificate_of_origin": "certificate_of_origin",
    "co": "certificate_of_origin",
    "container_data": "container_data",
}


def normalize_doc_kind_hint(v: Any) -> Optional[str]:
    if v is None:
        return None
    return DOC_KIND_HINT_ALIASES.get(str(v).strip().lower())


def infer_doc_kind(filename: str, full_text: str) -> str:
    fn = (filename or "").lower()
    t = normalize_for_search(full_text)

    if ("certificate of origin" in t) or ("certificado de origem" in t):
        return "certificate_of_origin"
    if ("bill of lading" in t) or ("b/l number" in t) or ("carrier" in t and "freight" in t):
        return "draft_bl"
    if ("packing list" in fn) or ("packing" in fn) or ("packing list" in t):
        return "packing_list"
    if ("commercial invoice" in fn) or ("invoice" in fn) or ("invoice" in t):
        return "commercial_invoice"
    if ("dados cntr" in fn) or ("booking" in t and "container" in t):
        return "container_data"
    return "unknown"


def _parse_container_rows(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for ln in (text or "").splitlines():
        line = normalize_spaces(ln)
        m = re.match(r"^([A-Z]{4}\d{7})\s+([A-Z0-9]{6,})\s+([\d\.,]+)(?:\s+([\d\.,]+))?.*$", line)
        if not m:
            continue
        rows.append(
            {
                "container_number": m.group(1),
                "seal": m.group(2),
                "value_1": parse_number_mixed(m.group(3)),
                "value_2": parse_number_mixed(m.group(4)) if m.group(4) else None,
                "raw_line": line,
            }
        )
    return rows


def ex_commercial_invoice(text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    fields: Dict[str, Dict[str, Any]] = {}

    invoice_number = find_first(text, r"\b(?:INVOICE(?:\s*NR\.?)?|FATURA)\b[:\s\-]*([A-Z0-9\-\/\.]+)")
    invoice_date = find_first(text, r"\b(\d{2}/\d{2}/\d{4})\b")
    country_of_origin = find_first(text, r"\bPA[IÍ]S\s+DE\s+ORIGEN\b[:\s\-]*([A-Z ]{3,})")
    transport_mode = find_first(text, r"\bVIA\s+DE\s+TRANSPORTE\b[:\s\-]*([A-Z ]{3,})")
    port_loading = find_first(text, r"\bPORT(?:O|)\s+OF\s+LOADING\b[:\s\-]*([A-Z ]{3,})")
    port_destination = find_first(text, r"\bPORT(?:O|)\s+OF\s+(?:DESTINATION|DISCHARGE)\b[:\s\-]*([A-Z ]{3,})")
    gross_weight = parse_number_mixed(find_first(text, r"\bPESO\s+BRUTO\b[^\d]{0,20}([\d\.,]+)"))
    net_weight = parse_number_mixed(find_first(text, r"\bPESO\s+NETO\b[^\d]{0,20}([\d\.,]+)"))
    incoterm = find_first(text, r"\bINCOTERM(?:S)?\b[^\w]{0,10}([A-Z]{3})")
    currency = find_first(text, r"\b(?:CURRENCY|MONEDA)\b[:\s\-]*([A-Z]{3})")
    ncm = find_first(text, r"\bN\.?C\.?M\.?\b[:\s\-]*([0-9\.]{4,})")
    container_count_raw = find_first(text, r"\bCNTR\b[^\d]{0,10}(\d+)")
    exporter_cnpj = parse_cnpj(find_first(text, r"\bCNPJ\b[:\s\-]*([0-9\.\-\/]+)"))
    exporter_name = find_first(text, r"\bEXPORTER\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    importer_name = find_first(text, r"\bCONSIGNEE\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    payment_terms = find_first(text, r"\b(PAYMENT\s+TERMS[^\n\r]*)")

    fields["invoice_number"] = make_field(True, invoice_number, evidence_lines(text, invoice_number))
    fields["invoice_date"] = make_field(True, invoice_date, evidence_lines(text, invoice_date))
    fields["country_of_origin"] = make_field(True, country_of_origin, evidence_lines(text, country_of_origin))
    fields["transport_mode"] = make_field(True, transport_mode, evidence_lines(text, transport_mode))
    fields["port_of_loading"] = make_field(True, port_loading, evidence_lines(text, port_loading))
    fields["port_of_destination"] = make_field(True, port_destination, evidence_lines(text, port_destination))
    fields["gross_weight_kg"] = make_field(True, gross_weight, evidence_lines(text, "PESO BRUTO"))
    fields["net_weight_kg"] = make_field(True, net_weight, evidence_lines(text, "PESO NETO"))
    fields["incoterm"] = make_field(True, incoterm, evidence_lines(text, "INCOTERM"))
    fields["currency"] = make_field(True, currency, evidence_lines(text, currency))
    fields["ncm"] = make_field(True, ncm, evidence_lines(text, "NCM"))
    fields["container_count"] = make_field(True, int(container_count_raw) if container_count_raw else None, evidence_lines(text, "CNTR"))
    fields["exporter_cnpj"] = make_field(True, exporter_cnpj, evidence_lines(text, "CNPJ"))
    fields["exporter_name"] = make_field(True, exporter_name, evidence_lines(text, "EXPORTER"))
    fields["importer_name"] = make_field(True, importer_name, evidence_lines(text, "CONSIGNEE"))
    fields["payment_terms"] = make_field(False, payment_terms, evidence_lines(text, "PAYMENT TERMS"))
    return fields, warnings


def ex_packing_list(text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    fields: Dict[str, Dict[str, Any]] = {}

    packing_number = find_first(text, r"\bPACKING(?:\s+LIST)?(?:\s*NR\.?)?\b[:\s\-]*([A-Z0-9\-\/\.]+)")
    packing_date = find_first(text, r"\b(\d{2}/\d{2}/\d{4})\b")
    gross_weight = parse_number_mixed(find_first(text, r"\bPESO\s+BRUTO\b[^\d]{0,20}([\d\.,]+)"))
    net_weight = parse_number_mixed(find_first(text, r"\bPESO\s+NETO\b[^\d]{0,20}([\d\.,]+)"))
    ncm = find_first(text, r"\bN\.?C\.?M\.?\b[:\s\-]*([0-9\.]{4,})")
    incoterm = find_first(text, r"\bINCOTERM(?:S)?\b[^\w]{0,10}([A-Z]{3})")
    container_count_raw = find_first(text, r"\bCNTR\b[^\d]{0,10}(\d+)")
    containers = _parse_container_rows(text)

    fields["packing_list_number"] = make_field(True, packing_number, evidence_lines(text, packing_number))
    fields["packing_date"] = make_field(True, packing_date, evidence_lines(text, packing_date))
    fields["gross_weight_kg"] = make_field(True, gross_weight, evidence_lines(text, "PESO BRUTO"))
    fields["net_weight_kg"] = make_field(True, net_weight, evidence_lines(text, "PESO NETO"))
    fields["ncm"] = make_field(True, ncm, evidence_lines(text, "NCM"))
    fields["incoterm"] = make_field(True, incoterm, evidence_lines(text, "INCOTERM"))
    fields["container_count"] = make_field(True, int(container_count_raw) if container_count_raw else None, evidence_lines(text, "CNTR"))
    fields["containers"] = make_field(True, containers if containers else None, [c["raw_line"] for c in containers[:4]], method="line_parse")
    return fields, warnings


def _incoterm_expected_freight_mode(incoterm: Optional[str]) -> Optional[str]:
    if not incoterm:
        return None
    it = incoterm.upper().strip()
    if it in {"CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"}:
        return "PREPAID"
    if it in {"EXW", "FCA", "FOB", "FAS"}:
        return "COLLECT"
    return None


def ex_draft_bl(text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    fields: Dict[str, Dict[str, Any]] = {}

    freight_mode = find_first(text, r"\bFREIGHT\b[^\n\r]{0,25}\b(COLLECT|PREPAID)\b")
    incoterm = find_first(text, r"\bINCOTERM(?:S)?\b[^\w]{0,10}([A-Z]{3})")
    ncm = find_first(text, r"\bNCM(?:/NALADI)?\b[:\s\-]*([0-9\.]{4,})")
    due = find_first(text, r"\bDUE\b[:\s\-]*([A-Z0-9\.\-\/]+)")
    ruc = find_first(text, r"\bRUC\b[:\s\-]*([A-Z0-9]+)")
    booking = find_first(text, r"\b(SSZ\d{4,})\b")
    wooden_packing = find_first(text, r"\bWOODEN\s+PACKAGE\b[:\s\-]*([A-Z \/\-]+)")
    total_cartons_raw = find_first(text, r"\b([\d\.,]+)\s+CARTONS\b")
    net_total = parse_number_mixed(find_first(text, r"\bNET\s+WEIGHT\b[^\d]{0,20}([\d\.,]+)"))
    gross_total = parse_number_mixed(find_first(text, r"\bGROSS\s+WEIGHT\b[^\d]{0,20}([\d\.,]+)"))
    cubic_meters = parse_number_mixed(find_first(text, r"\b([\d\.,]+)\s*(?:M3|CBM|M³)\b"))
    exporter_cnpj = parse_cnpj(find_first(text, r"\bCNPJ\b[:\s\-]*([0-9\.\-\/]+)"))
    exporter_name = find_first(text, r"\bSHIPPER\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    importer_name = find_first(text, r"\bCONSIGNEE\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    notify_party = find_first(text, r"\bNOTIFY\s+PARTY\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    phones = sorted(set(find_all(text, r"(\+\d{1,3}\s*\d{2,4}\s*\d{3,5}[-\s]?\d{3,5})")))
    containers = _parse_container_rows(text)

    expected_mode = _incoterm_expected_freight_mode(incoterm)
    if freight_mode and expected_mode and freight_mode.upper() != expected_mode:
        warnings.append(
            f"possible_incoterm_freight_mismatch: incoterm={incoterm} expected={expected_mode} freight_mode={freight_mode}"
        )

    fields["freight_mode"] = make_field(True, freight_mode, evidence_lines(text, "FREIGHT"))
    fields["incoterm"] = make_field(True, incoterm, evidence_lines(text, "INCOTERM"))
    fields["ncm"] = make_field(True, ncm, evidence_lines(text, "NCM"))
    fields["due"] = make_field(True, due, evidence_lines(text, "DUE"))
    fields["ruc"] = make_field(True, ruc, evidence_lines(text, "RUC"))
    fields["booking_number"] = make_field(False, booking, evidence_lines(text, booking))
    fields["wooden_packing"] = make_field(True, wooden_packing, evidence_lines(text, "WOODEN"))
    fields["containers"] = make_field(True, containers if containers else None, [c["raw_line"] for c in containers[:4]], method="line_parse")
    fields["total_cartons"] = make_field(True, int(parse_number_mixed(total_cartons_raw)) if total_cartons_raw else None, evidence_lines(text, "CARTONS"))
    fields["net_weight_kg_total"] = make_field(True, net_total, evidence_lines(text, "NET WEIGHT"))
    fields["gross_weight_kg_total"] = make_field(True, gross_total, evidence_lines(text, "GROSS WEIGHT"))
    fields["cubic_meters_total"] = make_field(True, cubic_meters, evidence_lines(text, "CBM"))
    fields["exporter_cnpj"] = make_field(True, exporter_cnpj, evidence_lines(text, "CNPJ"))
    fields["exporter_name"] = make_field(True, exporter_name, evidence_lines(text, "SHIPPER"))
    fields["phones_found"] = make_field(False, phones if phones else None, phones[:4], method="regex_findall")
    fields["importer_name"] = make_field(True, importer_name, evidence_lines(text, "CONSIGNEE"))
    fields["notify_party_name"] = make_field(True, notify_party, evidence_lines(text, "NOTIFY"))
    return fields, warnings


def ex_certificate_of_origin(text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    fields: Dict[str, Dict[str, Any]] = {}

    invoice_number = find_first(text, r"\b(I-\d{4}\/\d{2})\b")
    certificate_date = find_first(text, r"\b(\d{2}/\d{2}/\d{4})\b")
    transport_mode = find_first(text, r"\b(BY\s+SEA|MARITIME|MARITIMO)\b")
    exporter_name = find_first(text, r"\bEXPORTER\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    importer_name = find_first(text, r"\bCONSIGNEE\b[:\s\-]*([A-Z0-9 &\.\-]{4,})")
    kgs = [parse_number_mixed(v) for v in find_all(text, r"([\d\.,]+)\s*KGS\b")]
    kgs = [v for v in kgs if v is not None]
    net_weight = min(kgs) if len(kgs) >= 2 else None
    gross_weight = max(kgs) if len(kgs) >= 2 else None
    total_m2 = parse_number_mixed(find_first(text, r"([\d\.,]+)\s*(?:M2|M²)\b"))

    fields["invoice_number"] = make_field(True, invoice_number, evidence_lines(text, invoice_number))
    fields["certificate_date"] = make_field(True, certificate_date, evidence_lines(text, certificate_date))
    fields["transport_mode"] = make_field(True, transport_mode, evidence_lines(text, "SEA"))
    fields["exporter_name"] = make_field(True, exporter_name, evidence_lines(text, "EXPORTER"))
    fields["importer_name"] = make_field(True, importer_name, evidence_lines(text, "CONSIGNEE"))
    fields["net_weight_kg"] = make_field(True, net_weight, evidence_lines(text, "KGS"))
    fields["gross_weight_kg"] = make_field(True, gross_weight, evidence_lines(text, "KGS"))
    fields["total_m2"] = make_field(True, total_m2, evidence_lines(text, "M2"))
    return fields, warnings


def ex_container_data(text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    fields: Dict[str, Dict[str, Any]] = {}

    invoice_number = find_first(text, r"\bFATURA\b[:\s\-]*([A-Z0-9\-\/]+)")
    booking_number = find_first(text, r"\bBOOKING\b[:\s\-]*(SSZ\d+)")
    containers = _parse_container_rows(text)

    fields["invoice_number"] = make_field(True, invoice_number, evidence_lines(text, "FATURA"))
    fields["booking_number"] = make_field(True, booking_number, evidence_lines(text, "BOOKING"))
    fields["containers"] = make_field(True, containers if containers else None, [c["raw_line"] for c in containers[:4]], method="line_parse")
    return fields, warnings


def extract_by_kind(doc_kind: str, full_text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    if doc_kind == "commercial_invoice":
        return ex_commercial_invoice(full_text)
    if doc_kind == "packing_list":
        return ex_packing_list(full_text)
    if doc_kind == "draft_bl":
        return ex_draft_bl(full_text)
    if doc_kind == "certificate_of_origin":
        return ex_certificate_of_origin(full_text)
    if doc_kind == "container_data":
        return ex_container_data(full_text)
    return {}, [f"unsupported_doc_kind:{doc_kind}"]


def build_output(
    stage01_filename: str,
    original_pdf: str,
    doc_kind: str,
    doc_kind_hint: str,
    fields: Dict[str, Dict[str, Any]],
    warnings: List[str],
) -> Dict[str, Any]:
    missing = [k for k, v in (fields or {}).items() if v.get("required") and not v.get("present")]
    return {
        "source": {
            "stage01_file": stage01_filename,
            "original_file": original_pdf,
            "doc_kind": doc_kind,
            "doc_kind_hint": doc_kind_hint,
        },
        "generated_at": now_iso(),
        "fields": fields,
        "missing_required_fields": missing,
        "warnings": warnings or [],
    }


def _read_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def resolve_stage2_engine(engine: Optional[str] = None) -> str:
    raw = (engine or os.getenv("DOCREADER_STAGE2_ENGINE", "regex")).strip().lower()
    aliases = {
        "regex": "regex",
        "legacy": "regex",
        "llm": "llm",
        "codex": "llm",
    }
    if raw not in aliases:
        allowed = ", ".join(sorted(aliases.keys()))
        raise ValueError(f"Invalid Stage 02 engine '{raw}'. Allowed values: {allowed}")
    return aliases[raw]


def read_codex_runtime_context() -> Dict[str, Any]:
    context_file = os.getenv("DOCREADER_CODEX_AUTH_CONTEXT_FILE", "").strip()
    has_access_token = bool(os.getenv("DOCREADER_CODEX_ACCESS_TOKEN"))

    info: Dict[str, Any] = {
        "context_file": context_file,
        "has_access_token": has_access_token,
        "connected": False,
        "provider": "",
    }
    if not context_file:
        return info

    p = Path(context_file)
    if not p.exists():
        info["context_file_missing"] = True
        return info
    try:
        payload = read_json(p)
    except Exception:
        info["context_file_invalid"] = True
        return info

    info["connected"] = bool(payload.get("connected"))
    info["provider"] = str(payload.get("provider") or "")
    identity = payload.get("identity")
    if isinstance(identity, dict):
        info["identity"] = {
            "sub": str(identity.get("sub") or ""),
            "email": str(identity.get("email") or ""),
        }
    return info


def _run_stage_02_extraction_regex(
    in_dir: Path,
    out_dir: Path,
    verbose: bool = True,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(in_dir.glob("*_extracted.json"))
    if not files:
        return {
            "processed_count": 0,
            "warnings": [f"No *_extracted.json files found in: {in_dir}"],
            "documents": [],
        }

    docs: List[Dict[str, Any]] = []
    all_warnings: List[str] = []

    for p in files:
        stage01 = read_json(p)
        original_pdf = stage01.get("file") or p.name.replace("_extracted.json", ".pdf")
        full_text = join_pages(stage01)
        doc_kind_hint = normalize_doc_kind_hint(stage01.get("doc_kind_hint")) or ""
        doc_kind = doc_kind_hint or infer_doc_kind(original_pdf, full_text)

        fields, warns = extract_by_kind(doc_kind, full_text)
        out_obj = build_output(
            stage01_filename=p.name,
            original_pdf=original_pdf,
            doc_kind=doc_kind,
            doc_kind_hint=doc_kind_hint,
            fields=fields,
            warnings=warns,
        )

        out_name = p.name.replace("_extracted.json", "_fields.json")
        write_json(out_dir / out_name, out_obj)

        doc_summary = {
            "doc_kind": doc_kind,
            "doc_kind_hint": doc_kind_hint,
            "original_file": original_pdf,
            "stage01_file": p.name,
            "stage02_file": out_name,
            "missing_required_fields": out_obj["missing_required_fields"],
            "warnings": out_obj["warnings"],
        }
        docs.append(doc_summary)
        all_warnings.extend(out_obj["warnings"])

        if verbose:
            print(
                f"OK -> {out_name} | kind={doc_kind} | "
                f"missing={len(out_obj['missing_required_fields'])} | warnings={len(out_obj['warnings'])}"
            )

    codex_runtime = read_codex_runtime_context()
    summary = {
        "generated_at": now_iso(),
        "flow": "exportation",
        "input_folder": str(in_dir),
        "output_folder": str(out_dir),
        "codex_auth_context": codex_runtime,
        "documents": docs,
    }
    write_json(out_dir / "_stage02_summary.json", summary)

    if verbose:
        print("Completed.")

    return {
        "processed_count": len(docs),
        "warnings": all_warnings,
        "codex_auth_context": codex_runtime,
        "documents": docs,
    }


def run_stage_02_extraction(
    in_dir: Path,
    out_dir: Path,
    verbose: bool = True,
    engine: Optional[str] = None,
) -> Dict[str, Any]:
    selected_engine = resolve_stage2_engine(engine)
    if verbose:
        print(f"Stage 02 engine selected: {selected_engine}")

    if selected_engine == "llm":
        fallback_regex = _read_env_bool("DOCREADER_STAGE2_LLM_FALLBACK_REGEX", False)
        try:
            return run_stage02_llm_for_exportation(
                in_dir=in_dir,
                out_dir=out_dir,
                verbose=verbose,
                model=os.getenv("DOCREADER_STAGE2_LLM_MODEL", "").strip() or None,
                timeout_sec=int(os.getenv("DOCREADER_STAGE2_LLM_TIMEOUT_SEC", "240")),
            )
        except Exception as exc:
            if verbose:
                print(f"[Stage02-LLM-EXPORT] ERROR: {exc}")
                print("[Stage02-LLM-EXPORT] TRACEBACK START")
                print(traceback.format_exc())
                print("[Stage02-LLM-EXPORT] TRACEBACK END")
            if not fallback_regex:
                raise RuntimeError(
                    f"Stage 02 LLM extraction failed: {exc}. "
                    "Set DOCREADER_STAGE2_LLM_FALLBACK_REGEX=1 to fallback to regex."
                ) from exc
            if verbose:
                print(f"Stage 02 LLM failed: {exc}. Falling back to regex extractor.")
            return _run_stage_02_extraction_regex(in_dir=in_dir, out_dir=out_dir, verbose=verbose)

    return _run_stage_02_extraction_regex(in_dir=in_dir, out_dir=out_dir, verbose=verbose)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", help="Stage 01 folder (with *_extracted.json)")
    ap.add_argument("--out", dest="out_dir", help="Stage 02 output folder")
    ap.add_argument("--input", dest="in_dir_alt", help="Alias of --in")
    ap.add_argument("--output", dest="out_dir_alt", help="Alias of --out")
    ap.add_argument(
        "--engine",
        dest="engine",
        choices=["regex", "llm"],
        default=None,
        help="Stage 02 engine (default: env DOCREADER_STAGE2_ENGINE or regex).",
    )
    args = ap.parse_args()

    in_dir = args.in_dir or args.in_dir_alt
    out_dir = args.out_dir or args.out_dir_alt
    if not in_dir or not out_dir:
        raise SystemExit("Both --in/--input and --out/--output are required.")

    run_stage_02_extraction(
        in_dir=Path(in_dir),
        out_dir=Path(out_dir),
        verbose=True,
        engine=args.engine,
    )


if __name__ == "__main__":
    main()
