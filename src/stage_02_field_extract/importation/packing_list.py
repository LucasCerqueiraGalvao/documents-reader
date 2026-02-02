# -*- coding: utf-8 -*-
"""
Stage 02 - Importation - Packing List field extraction (stdlib only)

Fixes:
- aceita "CARTON" (singular) e "CARTONS" (plural)
- aceita "No." como 1 número ("5") ou range ("19 - 21")
- captura a linha final "* MODEL: DF300APXX" + "5 1 CARTON ..." + pesos "323 388"
- soma e compara com TOTAL; só gera warning se realmente divergir

Return signature:
    fields_dict, missing_required_fields, warnings
"""

from __future__ import annotations

import re

try:
    from .common import (
        build_field,
        find_first,
        find_cnpj,
        find_company_line_before_cnpj,
        parse_mixed_number,
    )
except ImportError:  # pragma: no cover
    from common import (
        build_field,
        find_first,
        find_cnpj,
        find_company_line_before_cnpj,
        parse_mixed_number,
    )

RE_ANY_DOC_NO = re.compile(r"(?is)\b([A-Z]{1,4}-\d{3,8}(?:-P)?)\b")  # DN-24139-P
RE_TOTAL_UNITS_CARTONS = re.compile(r"(?is)\b(\d+)\s+UNITS?\s*/\s*(\d+)\s+CARTONS?\b")
RE_MODEL = re.compile(r"(?im)^\s*\*\s*MODEL:\s*([A-Z0-9]+)\b")

# linha de pesos logo abaixo (normalmente: "597 792")
RE_WEIGHTS_LINE = re.compile(r"(?im)^\s*([0-9\.,]+)\s+([0-9\.,]+)\s*$")

# linha TOTAL do documento (ex.: "TOTAL : 33 CARTONS 7,980 9,825 53.772")
RE_TOTAL_SUMMARY = re.compile(
    r"(?is)\bTOTAL\b\s*:?\s*(\d+)\s*CARTONS?\s+([0-9\.,]+)\s+([0-9\.,]+)\s+([0-9\.,]+)"
)

RE_SHIPPER_HINT = re.compile(r"(?is)\b(SUZUKI[^\n]{0,80})\b")


def _clean_company_name(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"\bVEICU\s+LOS\b", "VEICULOS", s, flags=re.I)
    # remover datas comuns no final (ex: AUG. 28,2025)
    s = re.sub(
        r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\.?\s+\d{1,2},\s*\d{4}\b",
        "",
        s,
        flags=re.I,
    ).strip()
    # cortar em ruídos que às vezes grudam no bloco do nome
    upper = s.upper()
    for kw in [
        " RECEIVED BY",
        " RECEIVED",
        " PARTY TO CONTACT",
        " TEL",
        " PHONE",
        " PH:",
    ]:
        idx = upper.find(kw)
        if idx > 0:
            s = s[:idx].strip()
            upper = s.upper()
    s = re.sub(r"\s+", " ", s).strip(" ,;-\t")
    return s


def _find_total_summary(
    text: str,
) -> tuple[int | None, float | None, float | None, float | None, str | None]:
    m = RE_TOTAL_SUMMARY.search(text or "")
    if not m:
        return None, None, None, None, None
    cartons = int(m.group(1))
    net = parse_mixed_number(m.group(2))
    gross = parse_mixed_number(m.group(3))
    m3 = parse_mixed_number(m.group(4))
    return cartons, net, gross, m3, m.group(0)


def _model_from_line(line: str) -> str | None:
    m_model = re.search(r"\*\s*MODEL\s*:\s*([A-Z0-9\-]+)", line or "", flags=re.I)
    if not m_model:
        return None
    return m_model.group(1).strip() or None


def _next_nonempty_line(lines: list[str], start_idx: int) -> int | None:
    j = start_idx
    while j < len(lines) and not (lines[j] or "").strip():
        j += 1
    return j if j < len(lines) else None


def _try_parse_item_with_weights(
    lines: list[str],
    idx: int,
    current_model: str,
) -> tuple[dict | None, int]:
    parsed = _try_parse_item_row(lines[idx])
    if parsed is None:
        return None, idx + 1

    weights_idx = _next_nonempty_line(lines, idx + 1)
    net_total = None
    gross_total = None
    ev_total = None

    next_idx = idx + 1
    if weights_idx is not None:
        m_tot = RE_WEIGHTS_LINE.match((lines[weights_idx] or "").strip())
        if m_tot:
            net_total = parse_mixed_number(m_tot.group(1))
            gross_total = parse_mixed_number(m_tot.group(2))
            ev_total = m_tot.group(0)
            next_idx = weights_idx + 1

    item = {
        "model": current_model,
        "carton_range": parsed["carton_range"],
        "cartons": parsed["cartons"],
        "net_weight_per_pkg_kg": parsed["net_weight_per_pkg_kg"],
        "gross_weight_per_pkg_kg": parsed["gross_weight_per_pkg_kg"],
        "measurement_per_pkg_m3": parsed["measurement_per_pkg_m3"],
        "measurement_total_m3": parsed["measurement_total_m3"],
        "net_weight_total_kg": net_total,
        "gross_weight_total_kg": gross_total,
        "evidence_row": (lines[idx] or "").strip(),
        "evidence_totals": ev_total,
    }
    return item, next_idx


def _extract_items(text: str) -> list[dict]:
    lines = (text or "").splitlines()

    current_model: str | None = None
    items: list[dict] = []

    i = 0
    while i < len(lines):
        ln = lines[i]

        model = _model_from_line(ln)
        if model:
            current_model = model
            i += 1
            continue

        if not current_model:
            i += 1
            continue

        item, next_i = _try_parse_item_with_weights(lines, i, current_model)
        if item is not None:
            items.append(item)
            i = next_i
            continue

        i += 1

    return items


def _try_parse_item_row(line: str) -> dict | None:
    """Parse uma linha de item do PL sem regex pesada.

    Formatos típicos:
      - "19 - 21 3 CARTONS @199 @264 1.754325 5.263"
      - "5 1 CARTON @199 @264 1.754325 5.263"

    Retorna dict normalizado ou None.
    """
    s = re.sub(r"\s+", " ", (line or "").strip())
    if not s:
        return None

    toks = s.split(" ")
    if len(toks) < 7:
        return None

    carton_idx = None
    for i, t in enumerate(toks):
        tu = t.upper()
        if tu == "CARTON" or tu == "CARTONS":
            carton_idx = i
            break
    if carton_idx is None or carton_idx < 2:
        return None

    # packs é o token imediatamente antes de CARTON(S)
    try:
        cartons = int(toks[carton_idx - 1])
    except ValueError:
        return None

    # o restante antes de packs é o "No." (pode ser range)
    carton_range = " ".join(toks[: carton_idx - 1]).strip()
    if not carton_range:
        return None
    carton_range = re.sub(r"\s+", "", carton_range)

    # após CARTON(S): @nw @gw m3_each m3_total
    tail = toks[carton_idx + 1 :]
    if len(tail) < 4:
        return None

    def strip_at(x: str) -> str:
        return x[1:] if x.startswith("@") else x

    net_pkg = parse_mixed_number(strip_at(tail[0]))
    gross_pkg = parse_mixed_number(strip_at(tail[1]))
    m3_each = parse_mixed_number(tail[2])
    m3_total = parse_mixed_number(tail[3])

    return {
        "carton_range": carton_range,
        "cartons": cartons,
        "net_weight_per_pkg_kg": net_pkg,
        "gross_weight_per_pkg_kg": gross_pkg,
        "measurement_per_pkg_m3": m3_each,
        "measurement_total_m3": m3_total,
    }


def _finalize_weight_totals(
    *,
    items: list[dict],
    total_net: float | None,
    total_gross: float | None,
) -> tuple[float | None, float | None, list[str]]:
    warnings: list[str] = []

    net_sum = 0.0
    gross_sum = 0.0
    has_item_totals = False
    for it in items:
        net_it = it.get("net_weight_total_kg")
        gross_it = it.get("gross_weight_total_kg")
        if net_it is not None and gross_it is not None:
            net_sum += float(net_it)
            gross_sum += float(gross_it)
            has_item_totals = True

    net_final: float | None = None
    if total_net is not None:
        net_final = float(total_net)
    elif has_item_totals:
        net_final = float(net_sum)

    gross_final: float | None = None
    if total_gross is not None:
        gross_final = float(total_gross)
    elif has_item_totals:
        gross_final = float(gross_sum)

    tol = 0.5
    if (
        total_net is not None
        and has_item_totals
        and abs(net_sum - float(total_net)) > tol
    ):
        warnings.append(
            f"Soma Net Weight da tabela ({net_sum:.2f}) difere do TOTAL ({float(total_net):.2f}). Usando TOTAL."
        )
    if (
        total_gross is not None
        and has_item_totals
        and abs(gross_sum - float(total_gross)) > tol
    ):
        warnings.append(
            f"Soma Gross Weight da tabela ({gross_sum:.2f}) difere do TOTAL ({float(total_gross):.2f}). Usando TOTAL."
        )

    return net_final, gross_final, warnings


def _build_party_fields(text: str) -> dict:
    fields: dict = {}

    docno, ev = find_first(RE_ANY_DOC_NO, text)
    fields["packing_list_number"] = build_field(
        bool(docno), True, docno, [ev] if ev else [], "regex"
    )

    m = RE_SHIPPER_HINT.search(text or "")
    shipper = m.group(1).strip() if m else None
    fields["shipper_name"] = build_field(
        bool(shipper), True, shipper, [m.group(0)] if m else [], "heuristic_regex"
    )

    consignee_name, ev_name = find_company_line_before_cnpj(text)
    if consignee_name:
        consignee_name = _clean_company_name(consignee_name)
    fields["consignee_name"] = build_field(
        bool(consignee_name),
        True,
        consignee_name,
        [ev_name] if ev_name else [],
        "heuristic_line_before_cnpj",
    )

    cnpj, ev = find_cnpj(text)
    fields["consignee_cnpj"] = build_field(
        bool(cnpj), True, cnpj, [ev] if ev else [], "regex"
    )

    return fields


def _extract_counts_and_totals(
    text: str,
) -> tuple[
    int | None,
    str | None,
    int | None,
    str | None,
    float | None,
    float | None,
    float | None,
    str | None,
]:
    tu: int | None = None
    tc: int | None = None
    tu_ev: str | None = None
    tc_ev: str | None = None

    m2 = RE_TOTAL_UNITS_CARTONS.search(text or "")
    if m2:
        tu = int(m2.group(1))
        tc = int(m2.group(2))
        tu_ev = m2.group(0)
        tc_ev = m2.group(0)

    sum_cartons, sum_net, sum_gross, sum_m3, sum_ev = _find_total_summary(text)
    if tc is None and sum_cartons is not None:
        tc = sum_cartons
        tc_ev = sum_ev

    return tu, tu_ev, tc, tc_ev, sum_net, sum_gross, sum_m3, sum_ev


def extract_packing_list_fields(text: str):
    warnings: list[str] = []

    fields: dict = _build_party_fields(text)

    tu, tu_ev, tc, tc_ev, sum_net, sum_gross, sum_m3, sum_ev = (
        _extract_counts_and_totals(text)
    )

    fields["total_units"] = build_field(
        tu is not None, True, tu, [tu_ev] if tu_ev else [], "regex"
    )
    fields["total_cartons"] = build_field(
        tc is not None, True, tc, [tc_ev] if tc_ev else [], "regex"
    )

    items = _extract_items(text)

    fields["items"] = build_field(
        bool(items),
        False,
        items if items else None,
        [it["evidence_row"] for it in items[:5]],
        "regex_items",
    )

    fields["measurement_total_m3"] = build_field(
        sum_m3 is not None,
        False,
        float(sum_m3) if sum_m3 is not None else None,
        [sum_ev] if sum_ev else [],
        "regex_total",
    )

    net_final, gross_final, total_warnings = _finalize_weight_totals(
        items=items,
        total_net=sum_net,
        total_gross=sum_gross,
    )
    warnings.extend(total_warnings)

    fields["net_weight_kg_total_calc"] = build_field(
        net_final is not None,
        False,
        net_final,
        [sum_ev] if sum_ev else [],
        "total_line_or_sum",
    )
    fields["gross_weight_kg_total_calc"] = build_field(
        gross_final is not None,
        False,
        gross_final,
        [sum_ev] if sum_ev else [],
        "total_line_or_sum",
    )

    missing = [
        key
        for key, meta in (fields or {}).items()
        if isinstance(meta, dict) and meta.get("required") and not meta.get("present")
    ]

    return fields, missing, warnings
