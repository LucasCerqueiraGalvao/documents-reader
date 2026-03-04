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


def _clean_token(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = normalize_spaces(str(value))
    if not s:
        return None
    s = s.strip(" \t\r\n:-")
    if not s:
        return None
    if re.fullmatch(r"[.\-_/\\:]+", s):
        return None
    if s.upper() in {"N/A", "NA", "NONE", "NULL", "NIL"}:
        return None
    return s


def _is_present_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return _clean_token(value) is not None
    if isinstance(value, list):
        return len(value) > 0
    return True


def _split_lines(text: str) -> List[str]:
    out: List[str] = []
    for ln in (text or "").splitlines():
        c = normalize_spaces(ln)
        if c:
            out.append(c)
    return out


def _line_match_any(line: str, patterns: List[str]) -> bool:
    return any(re.search(p, line or "", re.IGNORECASE) for p in patterns)


def _extract_first_date(text: str) -> Optional[str]:
    return find_first(text, r"\b(\d{2}/\d{2}/\d{4})\b")


def _next_value_after_label(
    lines: List[str],
    label_patterns: List[str],
    value_pattern: Optional[str] = None,
    max_lookahead: int = 8,
    reject_patterns: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    for i, line in enumerate(lines):
        for pat in label_patterns:
            m = re.search(pat, line, re.IGNORECASE)
            if not m:
                continue

            inline = _clean_token(line[m.end():].strip(" :-"))
            if inline:
                if reject_patterns and _line_match_any(inline, reject_patterns):
                    inline = None
                elif value_pattern and not re.search(value_pattern, inline, re.IGNORECASE):
                    inline = None
            if inline:
                return inline, line

            for j in range(i + 1, min(len(lines), i + 1 + max_lookahead)):
                cand = _clean_token(lines[j])
                if not cand:
                    continue
                if reject_patterns and _line_match_any(cand, reject_patterns):
                    continue
                if value_pattern and not re.search(value_pattern, cand, re.IGNORECASE):
                    continue
                return cand, f"{line} | {cand}"
    return None, None


def _extract_doc_ref(text: str, lines: List[str], label_patterns: List[str]) -> Optional[str]:
    ref, _ = _next_value_after_label(
        lines,
        label_patterns=label_patterns,
        value_pattern=r"[A-Z0-9][A-Z0-9\-\/\.]*\d[A-Z0-9\-\/\.]*",
        reject_patterns=[r"\d{2}/\d{2}/\d{4}"],
        max_lookahead=10,
    )
    if ref and re.search(r"\d", ref):
        return ref
    return find_first(text, r"\b(I-\d{3,6}/\d{2})\b")


def _extract_incoterm(text: str, lines: List[str]) -> Optional[str]:
    token_pattern = r"\b(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b"
    for i, line in enumerate(lines):
        if not re.search(r"\bINCOTERM", line, re.IGNORECASE):
            continue
        m = re.search(token_pattern, line, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        for j in range(i + 1, min(i + 5, len(lines))):
            m2 = re.search(token_pattern, lines[j], re.IGNORECASE)
            if m2:
                return m2.group(1).upper()
    m3 = re.search(token_pattern, text or "", re.IGNORECASE)
    return m3.group(1).upper() if m3 else None


def _extract_currency(text: str, lines: List[str]) -> Optional[str]:
    cur, _ = _next_value_after_label(
        lines,
        label_patterns=[r"\bMONEDA\b", r"\bCURRENCY\b"],
        value_pattern=r"(US\$|USD|BRL|R\$|EUR|GBP|JPY|CNY|[A-Z]{3})",
        max_lookahead=4,
    )
    if cur:
        c = cur.upper().replace(" ", "")
        return "US$" if c in {"USD", "US$"} else c
    m = re.search(r"\b(US\$|USD|BRL|R\$|EUR|GBP|JPY|CNY)\b", text or "", re.IGNORECASE)
    if not m:
        return None
    c2 = m.group(1).upper()
    return "US$" if c2 == "USD" else c2


def _find_number_after_label(lines: List[str], label_patterns: List[str], max_lookahead: int = 10) -> Optional[float]:
    for i, line in enumerate(lines):
        if not _line_match_any(line, label_patterns):
            continue
        inline = re.search(r"([0-9][0-9\.,]*)\s*(?:KGS?|KG|M3|CBM)\b", line, re.IGNORECASE)
        if inline:
            v = parse_number_mixed(inline.group(1))
            if v is not None:
                return v
        for j in range(i + 1, min(i + 1 + max_lookahead, len(lines))):
            cand = _clean_token(lines[j])
            if not cand or "/" in cand:
                continue
            m = re.search(r"^([0-9][0-9\.,]*)$", cand)
            if not m:
                continue
            v = parse_number_mixed(m.group(1))
            if v is not None:
                return v
    return None


def _extract_cnpj(text: str) -> Optional[str]:
    first = find_first(text, r"\bC\.?\s*N\.?\s*P\.?\s*J\.?\b[:\s\-]*([0-9\.\-\/ ]+)")
    cnpj = parse_cnpj(first)
    if cnpj:
        return cnpj
    fallback = find_first(text, r"(\d{2}[.\s]?\d{3}[.\s]?\d{3}[\/\s]?\d{4}[-\s]?\d{2})")
    return parse_cnpj(fallback)


def _normalize_company_line(line: str) -> str:
    s = normalize_spaces(line or "").strip(" -:")
    s = re.sub(r"^(?:CONSIGNEE|SHIPPER|EXPORTER|IMPORTER|NOTIFY(?:\s+PARTY)?)\b[:\s\-]*", "", s, flags=re.IGNORECASE)
    return s.strip(" -:")


def _looks_company_line(line: str) -> bool:
    s = _normalize_company_line(line)
    if not s or len(s) < 4:
        return False
    if s.startswith("/"):
        return False
    if "@" in s or "http://" in s.lower() or "https://" in s.lower():
        return False
    if _line_match_any(
        s,
        [
            r"\b(BILL OF|CERTIFICATE|CERTIFICAT|ORIGINE|ORIGEN|PROCEDENCIA|PROVENANCE|INVOICE|PACKING|PESO|WEIGHT|COUNTRY|CITY|PORT|CONTAINER|CARTONS|PALLETS|RUC|NCM|DUE|FREIGHT|PREPAID|COLLECT|PAGE|PHONE|FAX|E-MAIL|WEB|TERMS|OBS|INSC|ESTRADA|DESTINO|DESTINATION|EXPORTADOR|EXPORTATEUR|IMPORTADOR)\b",
        ],
    ):
        return False
    if re.search(r"\b\d{2}/\d{2}/\d{2,4}\b", s):
        return False
    if re.search(r"\b(ROAD|RUA|AVENUE|AV\.|STREET|KM|BOULEVARD|BLVD)\b", s, re.IGNORECASE):
        return False
    words = re.findall(r"[A-Za-z]{2,}", s)
    return len(words) >= 2


def _find_company_before_cnpj(lines: List[str]) -> Optional[str]:
    for i, line in enumerate(lines):
        if not re.search(r"\bC\.?\s*N\.?\s*P\.?\s*J\.?\b|\bCNPJ\b", line, re.IGNORECASE):
            continue
        cands: List[str] = []
        for j in range(i - 1, max(-1, i - 8), -1):
            cand = _normalize_company_line(lines[j])
            if _looks_company_line(cand):
                cands.append(cand)
        for cand in cands:
            if re.search(r"\b(LTDA|LTD|INC|CORP|COMPANY|IND\.?|INDUSTRIA|COMERCIO|SHIPPING)\b", cand, re.IGNORECASE):
                return cand
        if cands:
            return cands[0]
    return None


def _find_consignee_name(lines: List[str]) -> Optional[str]:
    name, _ = _next_value_after_label(
        lines,
        label_patterns=[r"^CONSIGNEE\b", r"\bCONSIGNEE\b"],
        max_lookahead=10,
        reject_patterns=[r"\b(not negotiable|consigned to order|phone|road|jamaica|kingston/jamaica)\b"],
    )
    return _normalize_company_line(name) if name else None


def _parse_int_digits(raw: Any) -> Optional[int]:
    digits = re.sub(r"\D+", "", str(raw or ""))
    return int(digits) if digits else None


def _front_text_for_bl(text: str) -> str:
    m = re.search(r"\bCONDITIONS OF CARRIAGE\b", text or "", re.IGNORECASE)
    return (text or "")[: m.start()] if m else (text or "")


def make_field(required: bool, value: Any, evidence: Optional[List[str]] = None, method: str = "regex") -> Dict[str, Any]:
    present = _is_present_value(value)
    return {
        "present": bool(present),
        "required": bool(required),
        "value": _clean_token(value) if isinstance(value, str) and present else (value if present else None),
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
    seen: Set[str] = set()
    lines = _split_lines(text)

    for i, line in enumerate(lines):
        m_inline = re.match(r"^(?:\d+\s+)?([A-Z]{4}\d{7})\s+([A-Z0-9]{6,10})(?:\s+(.*))?$", line)
        if m_inline:
            cn = m_inline.group(1).upper()
            if cn in seen:
                continue
            seal = m_inline.group(2).upper()
            tail = m_inline.group(3) or ""
            nums = [parse_number_mixed(x) for x in re.findall(r"\d[\d\.,]*", tail)]
            nums = [n for n in nums if n is not None]
            rows.append(
                {
                    "container_number": cn,
                    "seal": seal,
                    "value_1": nums[0] if len(nums) >= 1 else None,
                    "value_2": nums[1] if len(nums) >= 2 else None,
                    "raw_line": line,
                }
            )
            seen.add(cn)
            continue

        m_cn = re.fullmatch(r"([A-Z]{4}\d{7})", line)
        if not m_cn:
            continue

        cn = m_cn.group(1).upper()
        if cn in seen:
            continue

        seal: Optional[str] = None
        nums: List[float] = []
        raw_parts: List[str] = [line]
        for j in range(i + 1, min(i + 8, len(lines))):
            cand = lines[j]
            if re.fullmatch(r"[A-Z]{4}\d{7}", cand):
                break
            raw_parts.append(cand)
            if seal is None and re.fullmatch(r"[A-Z0-9]{6,10}", cand) and not re.fullmatch(r"\d+", cand):
                seal = cand.upper()
                continue
            for hit in re.findall(r"\d[\d\.,]*", cand):
                n = parse_number_mixed(hit)
                if n is not None:
                    nums.append(n)
            if seal and len(nums) >= 2:
                break

        rows.append(
            {
                "container_number": cn,
                "seal": seal,
                "value_1": nums[0] if len(nums) >= 1 else None,
                "value_2": nums[1] if len(nums) >= 2 else None,
                "raw_line": " | ".join(raw_parts[:5]),
            }
        )
        seen.add(cn)

    return rows


def ex_commercial_invoice(text: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    fields: Dict[str, Dict[str, Any]] = {}

    lines = _split_lines(text)

    invoice_number = _extract_doc_ref(text, lines, [r"\bINVOICE\s*(?:NR\.?|NO\.?|N[Oº°\.]?)\b", r"\bFATURA\b"])
    invoice_date = _extract_first_date(text)
    country_of_origin, _ = _next_value_after_label(
        lines,
        [r"\bPA\S*\s+DE\s+ORIGEN\b", r"\bCOUNTRY\s+OF\s+ORIGIN\b"],
        max_lookahead=6,
        reject_patterns=[r"\bPARA\b", r"\bFECHA\b"],
    )

    transport_mode = None
    port_loading = None
    port_destination = None
    mode_labels = [r"\bVIA\s+DE\s+TRANSPORTE\b", r"\bMEANS\s+OF\s+TRANSPORT\b"]
    load_labels = [r"\bPUERTO\s+DE\s+EMBARQUE\b", r"\bPORT\s+OF\s+LOADING\b"]
    dest_labels = [r"\bPUERTO\s+DE\s+DESTINO\b", r"\bPORT\s+OF\s+(?:DESTINATION|DISCHARGE)\b"]

    idx_mode = next((i for i, ln in enumerate(lines) if _line_match_any(ln, mode_labels)), -1)
    idx_load = next((i for i, ln in enumerate(lines) if i > idx_mode and _line_match_any(ln, load_labels)), -1)
    idx_dest = next((i for i, ln in enumerate(lines) if i > idx_load and _line_match_any(ln, dest_labels)), -1)
    if idx_mode >= 0 and idx_load >= 0 and idx_dest >= 0:
        vals: List[str] = []
        for j in range(idx_dest + 1, min(idx_dest + 12, len(lines))):
            cand = _clean_token(lines[j])
            if not cand:
                continue
            if _line_match_any(cand, mode_labels + load_labels + dest_labels + [r"\bPESO\b", r"\bWEIGHT\b"]):
                continue
            vals.append(cand)
            if len(vals) >= 3:
                break
        if len(vals) >= 3:
            transport_mode, port_loading, port_destination = vals[0], vals[1], vals[2]
    if not transport_mode:
        transport_mode, _ = _next_value_after_label(lines, mode_labels, max_lookahead=8)
    if not port_loading:
        port_loading, _ = _next_value_after_label(lines, load_labels, max_lookahead=10)
    if not port_destination:
        port_destination, _ = _next_value_after_label(lines, dest_labels, max_lookahead=10)

    gross_weight = None
    net_weight = None
    peso_bruto_labels = [r"\bPESO\s+BRUTO\b", r"\bGROSS\s+WEIGHT\b"]
    peso_neto_labels = [r"\bPESO\s+NETO\b", r"\bNET\s+WEIGHT\b"]
    idx_g = next((i for i, ln in enumerate(lines) if _line_match_any(ln, peso_bruto_labels)), -1)
    idx_n = next((i for i, ln in enumerate(lines) if _line_match_any(ln, peso_neto_labels)), -1)
    start = max(idx_g, idx_n)
    if start >= 0:
        vals_num: List[float] = []
        for j in range(start + 1, min(start + 30, len(lines))):
            cand = lines[j]
            if not re.fullmatch(r"[0-9\.,]+", cand):
                continue
            n = parse_number_mixed(cand)
            if n is None:
                continue
            vals_num.append(n)
            if len(vals_num) >= 2:
                break
        if len(vals_num) >= 2:
            gross_weight, net_weight = vals_num[0], vals_num[1]
    if gross_weight is None:
        gross_weight = _find_number_after_label(lines, peso_bruto_labels, max_lookahead=16)
    if net_weight is None:
        net_weight = _find_number_after_label(lines, peso_neto_labels, max_lookahead=16)

    incoterm = _extract_incoterm(text, lines)
    currency = _extract_currency(text, lines)
    ncm = find_first(text, r"\bN\.?C\.?M\.?\b[:\s\-]*([0-9\.]{4,})")
    container_count_raw = find_first(text, r"\bCNTR\b[^\d]{0,10}(\d+)")
    exporter_cnpj = _extract_cnpj(text)
    exporter_name = _find_company_before_cnpj(lines)
    importer_name = _find_consignee_name(lines)
    payment_terms = find_first(text, r"\b(COBRANZA[^\n\r]{3,120})") or find_first(text, r"\b(PAYMENT\s+TERMS[^\n\r]*)")

    fields["invoice_number"] = make_field(True, invoice_number, evidence_lines(text, invoice_number))
    fields["invoice_date"] = make_field(True, invoice_date, evidence_lines(text, invoice_date))
    fields["country_of_origin"] = make_field(True, country_of_origin, evidence_lines(text, country_of_origin))
    fields["transport_mode"] = make_field(True, transport_mode, evidence_lines(text, transport_mode))
    fields["port_of_loading"] = make_field(True, port_loading, evidence_lines(text, port_loading))
    fields["port_of_destination"] = make_field(True, port_destination, evidence_lines(text, port_destination))
    fields["gross_weight_kg"] = make_field(True, gross_weight, evidence_lines(text, "PESO BRUTO"))
    fields["net_weight_kg"] = make_field(True, net_weight, evidence_lines(text, "PESO NETO"))
    fields["incoterm"] = make_field(True, incoterm, evidence_lines(text, "INCOTERM"))
    fields["currency"] = make_field(True, currency, evidence_lines(text, "MONEDA"))
    fields["ncm"] = make_field(True, ncm, evidence_lines(text, "NCM"))
    fields["container_count"] = make_field(True, _parse_int_digits(container_count_raw), evidence_lines(text, "CNTR"))
    fields["exporter_cnpj"] = make_field(True, exporter_cnpj, evidence_lines(text, "CNPJ"))
    fields["exporter_name"] = make_field(True, exporter_name, evidence_lines(text, exporter_name or "INCOPISOS"))
    fields["importer_name"] = make_field(True, importer_name, evidence_lines(text, importer_name or "CONSIGNEE"))
    fields["payment_terms"] = make_field(False, payment_terms, evidence_lines(text, "COBRANZA"))
    return fields, warnings

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

    lines = _split_lines(text)
    packing_number = _extract_doc_ref(text, lines, [r"\bPACKING\s*(?:NR\.?|NO\.?|N[Oº°\.]?)\b", r"\bPACKING\s+LIST\b"])
    packing_date = _extract_first_date(text)

    gross_weight = None
    net_weight = None
    peso_bruto_labels = [r"\bPESO\s+BRUTO\b", r"\bGROSS\s+WEIGHT\b"]
    peso_neto_labels = [r"\bPESO\s+NETO\b", r"\bNET\s+WEIGHT\b"]
    idx_g = next((i for i, ln in enumerate(lines) if _line_match_any(ln, peso_bruto_labels)), -1)
    idx_n = next((i for i, ln in enumerate(lines) if _line_match_any(ln, peso_neto_labels)), -1)
    start = max(idx_g, idx_n)
    if start >= 0:
        vals_num: List[float] = []
        for j in range(start + 1, min(start + 30, len(lines))):
            cand = lines[j]
            if not re.fullmatch(r"[0-9\.,]+", cand):
                continue
            n = parse_number_mixed(cand)
            if n is None:
                continue
            vals_num.append(n)
            if len(vals_num) >= 2:
                break
        if len(vals_num) >= 2:
            gross_weight, net_weight = vals_num[0], vals_num[1]
    if gross_weight is None:
        gross_weight = _find_number_after_label(lines, peso_bruto_labels, max_lookahead=16)
    if net_weight is None:
        net_weight = _find_number_after_label(lines, peso_neto_labels, max_lookahead=16)

    ncm = find_first(text, r"\bN\.?C\.?M\.?\b[:\s\-]*([0-9\.]{4,})")
    incoterm = _extract_incoterm(text, lines)
    container_count_raw = find_first(text, r"\bCNTR\b[^\d]{0,10}(\d+)")
    containers = _parse_container_rows(text)

    fields["packing_list_number"] = make_field(True, packing_number, evidence_lines(text, packing_number))
    fields["packing_date"] = make_field(True, packing_date, evidence_lines(text, packing_date))
    fields["gross_weight_kg"] = make_field(True, gross_weight, evidence_lines(text, "PESO BRUTO"))
    fields["net_weight_kg"] = make_field(True, net_weight, evidence_lines(text, "PESO NETO"))
    fields["ncm"] = make_field(True, ncm, evidence_lines(text, "NCM"))
    fields["incoterm"] = make_field(True, incoterm, evidence_lines(text, "INCOTERM"))
    fields["container_count"] = make_field(True, _parse_int_digits(container_count_raw), evidence_lines(text, "CNTR"))
    fields["containers"] = make_field(True, containers if containers else None, [c["raw_line"] for c in containers[:4]], method="line_parse")
    return fields, warnings

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

    front_text = _front_text_for_bl(text)
    lines = _split_lines(front_text)

    freight_mode = find_first(front_text, r"\bFREIGHT\b[^\n\r]{0,25}\b(COLLECT|PREPAID)\b")
    incoterm = _extract_incoterm(front_text, lines)
    ncm = find_first(front_text, r"\bNCM(?:/NALADI)?\b[:\s\-]*([0-9\.]{4,})")
    due_raw = find_first(front_text, r"\bDUE\b[:\s\-]*([A-Z0-9\.\-\/]+)")
    due = _clean_token(due_raw)
    due_required = True
    if due_raw and not due:
        warnings.append('DUE appears empty (example: "DUE: .") and was treated as missing.')
        due_required = False
    ruc = find_first(front_text, r"\bRUC\b[:\s\-]*([A-Z0-9]+)")
    booking = find_first(front_text, r"\b([A-Z]{3}\d{7,})\b")
    wooden_packing = find_first(front_text, r"\bWOODEN\s+PACKAGE\b[:\s\-]*([A-Z \/\-]+)")
    total_cartons_raw = find_first(front_text, r"\b([\d\.,]+)\s+CARTONS\b")
    net_total = _find_number_after_label(lines, [r"\bNET\s+WEIGHT\b"], max_lookahead=6)
    gross_total = _find_number_after_label(lines, [r"\bGROSS\s+WEIGHT\b"], max_lookahead=6)
    cubic_meters = parse_number_mixed(find_first(front_text, r"\b([\d\.,]+)\s*(?:M3|CBM|MÂ³|M³|M\W?3)\b"))
    exporter_cnpj = _extract_cnpj(front_text)
    exporter_name = _find_company_before_cnpj(lines)
    importer_name = None
    cnpj_idx = next(
        (i for i, ln in enumerate(lines) if re.search(r"\bC\.?\s*N\.?\s*P\.?\s*J\.?\b|\bCNPJ\b", ln, re.IGNORECASE)),
        -1,
    )
    if cnpj_idx >= 0:
        for j in range(cnpj_idx + 1, min(cnpj_idx + 24, len(lines))):
            cand = _normalize_company_line(lines[j])
            if not _looks_company_line(cand):
                continue
            if exporter_name and normalize_for_search(cand) == normalize_for_search(exporter_name):
                continue
            importer_name = cand
            break
    if not importer_name:
        importer_name = _find_consignee_name(lines)

    notify_party = None
    for i in range(0, len(lines) - 1):
        if "@" not in lines[i + 1]:
            continue
        options = [lines[i - 1]] if i - 1 >= 0 else []
        options.append(lines[i])
        for opt in options:
            cand = _normalize_company_line(opt)
            if not _looks_company_line(cand):
                continue
            if exporter_name and normalize_for_search(cand) == normalize_for_search(exporter_name):
                continue
            if importer_name and normalize_for_search(cand) == normalize_for_search(importer_name):
                continue
            notify_party = cand
            break
        if notify_party:
            break
    if not notify_party:
        notify_party, _ = _next_value_after_label(
            lines,
            [r"\bNOTIFY\s+PARTY\b", r"\bALSO\s+NOTIFY\b", r"^NOTIFY\b"],
            max_lookahead=12,
            reject_patterns=[r"\bPHONE\b", r"\bPORT\b", r"\bVESSEL\b"],
        )

    phones_raw = find_all(front_text, r"(\+?\d[\d\s().\-]{7,}\d)")
    phones: List[str] = []
    for p in phones_raw:
        d = re.sub(r"\D+", "", p)
        if 8 <= len(d) <= 16:
            phones.append(normalize_spaces(p))
    phones = sorted(set(phones))
    containers = _parse_container_rows(front_text)

    expected_mode = _incoterm_expected_freight_mode(incoterm)
    if freight_mode and expected_mode and freight_mode.upper() != expected_mode:
        warnings.append(
            f"possible_incoterm_freight_mismatch: incoterm={incoterm} expected={expected_mode} freight_mode={freight_mode}"
        )

    fields["freight_mode"] = make_field(True, freight_mode, evidence_lines(front_text, "FREIGHT"))
    fields["incoterm"] = make_field(True, incoterm, evidence_lines(front_text, "INCOTERM"))
    fields["ncm"] = make_field(True, ncm, evidence_lines(front_text, "NCM"))
    fields["due"] = make_field(due_required, due, evidence_lines(front_text, "DUE"))
    fields["ruc"] = make_field(True, ruc, evidence_lines(front_text, "RUC"))
    fields["booking_number"] = make_field(False, booking, evidence_lines(front_text, booking or "SSZ"))
    fields["wooden_packing"] = make_field(True, wooden_packing, evidence_lines(front_text, "WOODEN"))
    fields["containers"] = make_field(True, containers if containers else None, [c["raw_line"] for c in containers[:4]], method="line_parse")
    fields["total_cartons"] = make_field(True, _parse_int_digits(total_cartons_raw), evidence_lines(front_text, "CARTONS"))
    fields["net_weight_kg_total"] = make_field(True, net_total, evidence_lines(front_text, "NET WEIGHT"))
    fields["gross_weight_kg_total"] = make_field(True, gross_total, evidence_lines(front_text, "GROSS WEIGHT"))
    fields["cubic_meters_total"] = make_field(True, cubic_meters, evidence_lines(front_text, "M3"))
    fields["exporter_cnpj"] = make_field(True, exporter_cnpj, evidence_lines(front_text, "CNPJ"))
    fields["exporter_name"] = make_field(True, exporter_name, evidence_lines(front_text, exporter_name or "SHIPPER"))
    fields["phones_found"] = make_field(False, phones if phones else None, phones[:4], method="regex_findall")
    fields["importer_name"] = make_field(True, importer_name, evidence_lines(front_text, importer_name or "CONSIGNEE"))
    fields["notify_party_name"] = make_field(True, notify_party, evidence_lines(front_text, notify_party or "NOTIFY"))
    return fields, warnings

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

    lines = _split_lines(text)
    invoice_number = _extract_doc_ref(
        text,
        lines,
        [r"\bINVOICE\s+N", r"\bFACTURA\s+N", r"\bFATURA\s+N"],
    )
    certificate_date = _extract_first_date(text)
    transport_mode = find_first(text, r"\b(BY\s+SEA|MARITIME|MARITIMO)\b")
    if not transport_mode:
        transport_mode, _ = _next_value_after_label(lines, [r"\bMEANS\s+OF\s+TRANSPORT\b"], max_lookahead=8)

    company_candidates: List[str] = []
    seen_candidates: Set[str] = set()
    for ln in lines[:160]:
        cand = _normalize_company_line(ln)
        if not _looks_company_line(cand):
            continue
        key = normalize_for_search(cand)
        if not key or key in seen_candidates:
            continue
        seen_candidates.add(key)
        company_candidates.append(cand)

    exporter_name = None
    for cand in company_candidates:
        if re.search(r"\b(LTDA|LTD|INC|CORP|COMPANY|INDUSTRIA|COMERCIO)\b", cand, re.IGNORECASE):
            exporter_name = cand
            break
    if not exporter_name and company_candidates:
        exporter_name = company_candidates[0]

    importer_name, _ = _next_value_after_label(
        lines,
        [r"\bCONSIGNEE\b"],
        value_pattern=r"[A-Za-z&]{3,}",
        max_lookahead=8,
        reject_patterns=[r"\d{2}/\d{2}/\d{4}", r"\bconsignataire|consignatario|consignat[áa]rio\b"],
    )
    importer_name = _normalize_company_line(importer_name) if importer_name else None
    if importer_name and exporter_name and normalize_for_search(importer_name) == normalize_for_search(exporter_name):
        importer_name = None
    if not importer_name:
        for cand in company_candidates:
            if exporter_name and normalize_for_search(cand) == normalize_for_search(exporter_name):
                continue
            importer_name = cand
            break

    kgs = [parse_number_mixed(v) for v in find_all(text, r"([\d\.,]+)\s*KGS\b")]
    kgs = [v for v in kgs if v is not None]
    net_weight = min(kgs) if len(kgs) >= 2 else None
    gross_weight = max(kgs) if len(kgs) >= 2 else None
    total_m2 = parse_number_mixed(find_first(text, r"([\d\.,]+)\s*(?:M2|MÂ²|M²|M\W?2)"))

    fields["invoice_number"] = make_field(True, invoice_number, evidence_lines(text, invoice_number))
    fields["certificate_date"] = make_field(True, certificate_date, evidence_lines(text, certificate_date))
    fields["transport_mode"] = make_field(True, transport_mode, evidence_lines(text, transport_mode or "SEA"))
    fields["exporter_name"] = make_field(True, exporter_name, evidence_lines(text, exporter_name or "EXPORTER"))
    fields["importer_name"] = make_field(True, importer_name, evidence_lines(text, importer_name or "CONSIGNEE"))
    fields["net_weight_kg"] = make_field(True, net_weight, evidence_lines(text, "KGS"))
    fields["gross_weight_kg"] = make_field(True, gross_weight, evidence_lines(text, "KGS"))
    fields["total_m2"] = make_field(True, total_m2, evidence_lines(text, "M2"))
    return fields, warnings

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

    lines = _split_lines(text)
    invoice_number = _extract_doc_ref(text, lines, [r"\bFATURA\b", r"\bINVOICE\b"])
    booking_number, _ = _next_value_after_label(lines, [r"\bBOOKING\b"], value_pattern=r"[A-Z]{3}\d{4,}", max_lookahead=4)
    if not booking_number:
        booking_number = find_first(text, r"\b([A-Z]{3}\d{4,})\b")
    containers = _parse_container_rows(text)

    fields["invoice_number"] = make_field(True, invoice_number, evidence_lines(text, "FATURA"))
    fields["booking_number"] = make_field(True, booking_number, evidence_lines(text, "BOOKING"))
    fields["containers"] = make_field(True, containers if containers else None, [c["raw_line"] for c in containers[:4]], method="line_parse")
    return fields, warnings

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
