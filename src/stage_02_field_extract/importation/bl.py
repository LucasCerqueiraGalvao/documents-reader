# -*- coding: utf-8 -*-
"""
Stage 02 - Importation - BL/HBL field extraction (stdlib only)

Return signature:
    fields_dict, missing_required_fields, warnings
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from .common import parse_mixed_number
except ImportError:  # pragma: no cover
    from common import parse_mixed_number


# -----------------------------
# Helpers
# -----------------------------
def _clean_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _strip_boilerplate(s: str) -> str:
    """Remove parágrafos padrões que às vezes colam no nome via OCR."""
    if not s:
        return s
    u = s.upper()
    cut_markers = (
        "RECEIVED BY THE CARRIER",
        "RECEIVED BY",
        "IN APPARENT GOOD ORDER",
        "CONDITIONS UNLESS OTHERWISE",
        "CARRIAGE OF GOODS",
    )
    cut_idx = None
    for mk in cut_markers:
        i = u.find(mk)
        if i != -1:
            cut_idx = i if cut_idx is None else min(cut_idx, i)
    if cut_idx is not None:
        s = s[:cut_idx]
    return _clean_spaces(s)


def _join_split_words_caps(s: str) -> str:
    """Heurística para OCR que quebra palavra em caixa alta: "VEICU LOS" -> "VEICULOS"."""
    if not s:
        return s

    toks = s.split()
    out: list[str] = []
    i = 0
    block = {"LTDA", "LTD", "INC", "SA", "CO", "CO.", "S/A"}

    while i < len(toks):
        t1 = toks[i]
        if i + 1 < len(toks):
            t2 = toks[i + 1]
            if (
                t1.isalpha()
                and t2.isalpha()
                and t1.upper() == t1
                and t2.upper() == t2
                and 2 <= len(t1) <= 6
                and 1 <= len(t2) <= 3
                and t2.upper() not in block
            ):
                out.append(t1 + t2)
                i += 2
                continue
        out.append(t1)
        i += 1

    return " ".join(out)


def _clean_company_line(s: str) -> str:
    s = _strip_boilerplate(s)
    s = _join_split_words_caps(s)
    return _clean_spaces(s)


def _present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    if isinstance(v, list) and len(v) == 0:
        return False
    return True


def _mk_field(
    value: Any, required: bool, evidence: List[str], method: str
) -> Dict[str, Any]:
    return {
        "present": bool(_present(value)),
        "required": bool(required),
        "value": value if _present(value) else None,
        "evidence": evidence or [],
        "method": method,
    }


def _parse_number(v: str) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None

    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None

    return parse_mixed_number(s)


def _lines(text: str) -> List[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _find_label_index(lines: List[str], pattern: str) -> Optional[int]:
    for i, ln in enumerate(lines):
        if re.search(pattern, ln, flags=re.I):
            return i
    return None


def _find_inline_value(
    lines: List[str], pattern: str
) -> Tuple[Optional[str], List[str]]:
    for ln in lines:
        m = re.search(pattern, ln, flags=re.I)
        if not m:
            continue
        val = _clean_company_line(m.group(1))
        if val:
            return val, [ln]
    return None, []


def _clean_company_candidate(cand: str) -> Optional[str]:
    cand_clean = _clean_company_line(cand)
    if not cand_clean:
        return None

    parts = cand_clean.split()
    while parts and re.search(r"\d", parts[-1]) and len(parts[-1]) >= 6:
        parts.pop()

    name = _clean_spaces(" ".join(parts))
    return name if name and len(name) >= 3 else None


def _find_name_after_index(
    lines: List[str],
    start_index: int,
    stop_words: set[str],
    max_lookahead: int,
) -> Tuple[Optional[str], List[str]]:
    for j in range(start_index + 1, min(start_index + 1 + max_lookahead, len(lines))):
        cand = lines[j].strip()
        if not cand:
            continue
        if any(sw in cand.upper() for sw in stop_words):
            continue
        name = _clean_company_candidate(cand)
        if name:
            return name, [cand]
    return None, []


def _find_shipper(lines: List[str]) -> Tuple[Optional[str], List[str]]:
    """
    BL OCR geralmente vem como:
      "Shipper Booking No. B/L No."
      "SUZUKI MOTOR CORPORATION 258255821A"
      "300 TAKATSUKA-CHO ..."
    A ideia: achar "SHIPPER" e pegar a próxima linha "boa" como nome.
    """
    stop_words = {"CONSIGNEE", "NOTIFY", "BOOKING", "B/L", "B/L NO", "B/L NO."}

    idx = _find_label_index(lines, r"\bSHIPPER\b")
    if idx is not None:
        name, ev = _find_name_after_index(
            lines, idx, stop_words=stop_words, max_lookahead=7
        )
        if name:
            return name, ev

    # fallback: às vezes vem "SHIPPER:" na mesma linha
    return _find_inline_value(lines, r"\bSHIPPER\b\s*:?\s*(.+)$")


def _find_consignee_name_cnpj(
    lines: List[str],
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    Muito comum aparecer:
      Consignee
      GHANDI ...
      CNPJ: 03....
    Vamos capturar o nome (linha após Consignee) e o CNPJ.
    """
    evidence: List[str] = []

    name: str | None = None
    idx = _find_label_index(lines, r"\bCONSIGNEE\b")
    if idx is not None:
        stop_words = {"NOTIFY"}
        name, ev = _find_name_after_index(
            lines, idx, stop_words=stop_words, max_lookahead=5
        )
        if name:
            evidence.extend(ev)

    cnpj: str | None = None
    for ln in lines:
        m = re.search(r"\bCNPJ\s*:?\s*([0-9\.\-\/]+)", ln, flags=re.I)
        if not m:
            continue
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        if digits:
            cnpj = digits
            evidence.append(ln)
            break

    return name, cnpj, evidence


def _find_ncm(lines: List[str]) -> Tuple[Optional[str], List[str], List[str]]:
    """
    Aceitar 4, 6 ou 8 dígitos (HS/NCM), sem warning para 4 dígitos.
    Gera warning apenas se achar algo com tamanho "estranho".
    """
    warnings: List[str] = []
    for ln in lines:
        m = re.search(r"\bNCM\b\s*(?:NO\.?|Nº)?\s*(\d{4,8})", ln, flags=re.I)
        if m:
            code = m.group(1)
            # BL pode trazer HS (4 dígitos). Emitir warning para revisão.
            if len(code) == 4:
                warnings.append(
                    f"HS/NCM encontrado com 4 dígitos ({code}). Verificar se há NCM 8 dígitos."
                )
            elif len(code) not in (6, 8):
                warnings.append(
                    f"NCM/HS encontrado com {len(code)} dígitos ({code}). Verificar."
                )
            return code, [ln], warnings

    return None, [], warnings


def _find_gross_weight(lines: List[str]) -> Tuple[Optional[float], List[str]]:
    """
    Ex: "Gross Weight 'in kilo's" e logo depois "9,825.000 KG"
    """
    val, ev = _find_gross_weight_near_heading(lines)
    if val is not None:
        return val, ev
    return _find_best_kg_candidate(lines)


def _find_gross_weight_near_heading(
    lines: List[str],
) -> Tuple[Optional[float], List[str]]:
    idx = _find_label_index(lines, r"\bGROSS\s+WEIGHT\b")
    if idx is None:
        return None, []

    for j in range(idx, min(idx + 8, len(lines))):
        cand = lines[j]
        m = re.search(r"(\d[\d\.,]+)\s*KG", cand, flags=re.I)
        if not m:
            continue
        num = _parse_number(m.group(1))
        if num is not None:
            return float(num), [cand]

    return None, []


def _find_best_kg_candidate(lines: List[str]) -> Tuple[Optional[float], List[str]]:
    best_score: float | None = None
    best_value: float | None = None
    best_line: str | None = None

    for ln in lines:
        res = _best_kg_in_line(ln)
        if res is None:
            continue
        score, value = res
        if best_score is None or score > best_score:
            best_score = score
            best_value = value
            best_line = ln

    if best_line is None or best_value is None:
        return None, []

    return best_value, [best_line]


def _best_kg_in_line(line: str) -> Optional[tuple[float, float]]:
    matches = re.findall(r"\b(\d[\d\.,]+)\s*KG\b", line or "", flags=re.I)
    if not matches:
        return None

    values: list[float] = []
    for raw in matches:
        num = _parse_number(raw)
        if num is None:
            continue
        val = float(num)
        if 1.0 <= val <= 50_000_000.0:
            values.append(val)

    if not values:
        return None

    value = max(values)
    score = value
    if re.search(r"\b(GROSS|WEIGHT)\b", line or "", flags=re.I):
        score *= 1.1

    return score, value


def extract_bl_fields(text: str) -> Tuple[Dict[str, Any], List[str], List[str]]:
    ln = _lines(text)

    warnings: List[str] = []
    missing: List[str] = []

    shipper_name, shipper_ev = _find_shipper(ln)
    consignee_name, consignee_cnpj, consignee_ev = _find_consignee_name_cnpj(ln)
    ncm, ncm_ev, ncm_warn = _find_ncm(ln)
    gross_weight, gross_ev = _find_gross_weight(ln)

    warnings.extend(ncm_warn)

    # Required rules (Karina)
    # - shipper/exportador obrigatório
    # - consignee CNPJ obrigatório
    # - NCM obrigatório (pode ser 4/6/8)
    required = {
        "shipper_name": True,
        "importer_name": True,
        "importer_cnpj": True,
        "ncm": True,
        "gross_weight_kg": True,
    }

    fields: Dict[str, Any] = {}
    fields["shipper_name"] = _mk_field(
        shipper_name, required["shipper_name"], shipper_ev, "line_block"
    )
    fields["importer_name"] = _mk_field(
        consignee_name, required["importer_name"], consignee_ev[:1], "line_block"
    )
    fields["importer_cnpj"] = _mk_field(
        consignee_cnpj, required["importer_cnpj"], consignee_ev, "regex"
    )
    fields["ncm"] = _mk_field(ncm, required["ncm"], ncm_ev, "regex")
    fields["gross_weight_kg"] = _mk_field(
        gross_weight, required["gross_weight_kg"], gross_ev, "regex"
    )

    for k, meta in fields.items():
        if meta["required"] and not meta["present"]:
            missing.append(k)

    return fields, missing, warnings
