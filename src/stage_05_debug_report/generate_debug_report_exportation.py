# -*- coding: utf-8 -*-
"""
Stage 05 - EXPORTATION - Detailed debug report from Stage 02 + Stage 03

Inputs:
- Stage 02: data/output/stage_02_fields/exportation/*_fields.json
- Stage 03: data/output/stage_03_compare/exportation/_stage03_comparison.json

Outputs:
- data/output/stage_05_debug_report/exportation/_stage05_debug_report.json
- data/output/stage_05_debug_report/exportation/_stage05_debug_report.md
- data/output/stage_05_debug_report/exportation/_stage05_debug_report.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def tr(x: Any) -> str:
    if x is None:
        return ""
    return html.escape(str(x))


def to_text(v: Any, max_chars: int = 1800) -> str:
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False)
    elif v is None:
        s = ""
    else:
        s = str(v)
    if len(s) > max_chars:
        return s[: max_chars - 3] + "..."
    return s


def doc_kind_label(kind: Any) -> str:
    labels = {
        "commercial_invoice": "COMMERCIAL INVOICE",
        "packing_list": "PACKING LIST",
        "draft_bl": "DRAFT BL",
        "certificate_of_origin": "CERTIFICATE OF ORIGIN",
        "container_data": "CONTAINER DATA",
    }
    k = str(kind or "").strip().lower()
    return labels.get(k, str(kind or "").upper())


def split_pair_companies(pair_text: Any) -> Tuple[str, str]:
    """
    Parse pair text into two labels in format similar to Stage 04.
    Examples:
      "<rule> | INVOICE <> BL" -> ("INVOICE", "BL")
      "INVOICE <> BL" -> ("INVOICE", "BL")
    """
    s = str(pair_text or "").strip()
    if not s:
        return ("", "")

    rhs = s.split("|", 1)[1].strip() if "|" in s else s
    if "<>" in rhs:
        left, right = rhs.split("<>", 1)
        return (left.strip(), right.strip())

    m = re.match(r"(.+?)\s+(?:vs|x)\s+(.+)", rhs, flags=re.IGNORECASE)
    if m:
        return (m.group(1).strip(), m.group(2).strip())

    return (rhs, "")


def load_stage02_docs(stage02_dir: Path) -> List[dict]:
    docs: List[dict] = []
    if not stage02_dir.exists():
        return docs
    for p in sorted(stage02_dir.glob("*_fields.json")):
        if p.name == "_stage02_summary.json":
            continue
        try:
            docs.append(read_json(p))
        except Exception:
            continue
    return docs


def normalize_stage03(stage03_obj: dict) -> Dict[str, Any]:
    pairs = stage03_obj.get("comparisons") or stage03_obj.get("pairs") or stage03_obj.get("pair_checks") or []
    groups = stage03_obj.get("group_checks") or stage03_obj.get("groups") or []
    rules = stage03_obj.get("rule_checks") or stage03_obj.get("rules") or []

    norm_pairs: List[dict] = []
    for item in pairs:
        c = dict(item)
        if not c.get("field"):
            c["field"] = c.get("check") or c.get("key") or c.get("campo") or ""
        norm_pairs.append(c)

    summary = stage03_obj.get("summary") or {}
    if "pair_checks" in summary:
        pair_summary = summary.get("pair_checks") or {}
        group_summary = summary.get("group_checks") or {}
        rule_summary = summary.get("rule_checks") or {}
        total = int(pair_summary.get("total", 0) or 0) + int(group_summary.get("total", 0) or 0) + int(rule_summary.get("total", 0) or 0)
        matches = int(pair_summary.get("matches", 0) or 0)
        matches += max(0, int(group_summary.get("total", 0) or 0) - int(group_summary.get("divergences", 0) or 0) - int(group_summary.get("missing", 0) or 0))
        matches += max(0, int(rule_summary.get("total", 0) or 0) - int(rule_summary.get("divergences", 0) or 0) - int(rule_summary.get("skipped", 0) or 0))
        divergences = int(pair_summary.get("divergences", 0) or 0) + int(group_summary.get("divergences", 0) or 0) + int(rule_summary.get("divergences", 0) or 0)
        skipped = int(pair_summary.get("skipped", 0) or 0) + int(group_summary.get("missing", 0) or 0) + int(rule_summary.get("skipped", 0) or 0)
    else:
        total = len(norm_pairs) + len(groups) + len(rules)
        all_items = list(norm_pairs) + list(groups) + list(rules)
        divergences = sum(1 for c in all_items if str(c.get("status") or "").lower() in {"divergent", "fail", "error"})
        skipped = sum(1 for c in all_items if str(c.get("status") or "").lower() in {"skipped", "missing"})
        matches = max(0, total - divergences - skipped)

    return {
        "pairs": norm_pairs,
        "groups": [dict(x) for x in groups],
        "rules": [dict(x) for x in rules],
        "summary": {
            "total": total,
            "matches": matches,
            "divergences": divergences,
            "skipped": skipped,
        },
    }


def build_stage02_debug(stage02_docs: List[dict]) -> Dict[str, Any]:
    docs_out: List[dict] = []
    total_fields = 0
    present_fields = 0
    missing_required_total = 0
    warnings_total = 0

    for d in stage02_docs:
        src = d.get("source") or {}
        fields = d.get("fields") or {}
        missing = list(d.get("missing_required_fields") or [])
        warnings = list(d.get("warnings") or [])

        rows: List[dict] = []
        req_total = 0
        req_present = 0
        for k in sorted(fields.keys()):
            meta = fields.get(k) or {}
            required = bool(meta.get("required"))
            present = bool(meta.get("present"))
            if required:
                req_total += 1
                if present:
                    req_present += 1
            rows.append(
                {
                    "field": k,
                    "required": required,
                    "present": present,
                    "method": str(meta.get("method") or ""),
                    "value": meta.get("value"),
                    "evidence": list(meta.get("evidence") or []),
                }
            )

        docs_out.append(
            {
                "source": {
                    "doc_kind": src.get("doc_kind"),
                    "original_file": src.get("original_file"),
                    "stage01_file": src.get("stage01_file"),
                },
                "summary": {
                    "fields_total": len(rows),
                    "fields_present": sum(1 for r in rows if r["present"]),
                    "required_total": req_total,
                    "required_present": req_present,
                    "missing_required_count": len(missing),
                    "warnings_count": len(warnings),
                },
                "missing_required_fields": missing,
                "warnings": warnings,
                "fields": rows,
            }
        )

        total_fields += len(rows)
        present_fields += sum(1 for r in rows if r["present"])
        missing_required_total += len(missing)
        warnings_total += len(warnings)

    return {
        "summary": {
            "documents_total": len(docs_out),
            "fields_total": total_fields,
            "fields_present": present_fields,
            "missing_required_total": missing_required_total,
            "warnings_total": warnings_total,
        },
        "documents": docs_out,
    }


def build_stage03_debug(stage03_norm: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "summary": stage03_norm.get("summary") or {},
        "pair_checks": stage03_norm.get("pairs") or [],
        "group_checks": stage03_norm.get("groups") or [],
        "rule_checks": stage03_norm.get("rules") or [],
    }


def build_markdown(report: dict) -> str:
    lines: List[str] = []
    s2 = report.get("stage02") or {}
    s3 = report.get("stage03") or {}

    lines.append("# Stage 05 Debug Report - Exportation")
    lines.append("")
    lines.append(f"- Generated at: **{report.get('generated_at','')}**")
    lines.append("")

    s2s = s2.get("summary") or {}
    lines.append("## Stage 02 Summary")
    lines.append(
        f"- Documents: **{s2s.get('documents_total',0)}** | Fields present: **{s2s.get('fields_present',0)} / {s2s.get('fields_total',0)}** | Missing required: **{s2s.get('missing_required_total',0)}** | Warnings: **{s2s.get('warnings_total',0)}**"
    )
    lines.append("")

    for doc in s2.get("documents") or []:
        src = doc.get("source") or {}
        summ = doc.get("summary") or {}
        lines.append(
            f"### Stage 02 Document: {doc_kind_label(src.get('doc_kind'))} - {src.get('original_file') or src.get('stage01_file') or ''}"
        )
        lines.append(
            f"- Required: **{summ.get('required_present',0)} / {summ.get('required_total',0)}** | Missing required: **{summ.get('missing_required_count',0)}** | Warnings: **{summ.get('warnings_count',0)}**"
        )
        lines.append("")
        lines.append("| Field | Required | Present | Method | Value | Evidence |")
        lines.append("|---|---|---|---|---|---|")
        for f in doc.get("fields") or []:
            evidence = " // ".join(str(x) for x in (f.get("evidence") or []))
            lines.append(
                f"| {f.get('field','')} | {f.get('required',False)} | {f.get('present',False)} | {f.get('method','')} | {to_text(f.get('value'), 280)} | {to_text(evidence, 320)} |"
            )
        lines.append("")

    s3s = s3.get("summary") or {}
    lines.append("## Stage 03 Summary")
    lines.append(
        f"- Total: **{s3s.get('total',0)}** | Matches: **{s3s.get('matches',0)}** | Divergences: **{s3s.get('divergences',0)}** | Skipped: **{s3s.get('skipped',0)}**"
    )
    lines.append("")

    lines.append("## Stage 03 Pair Checks")
    lines.append("| Empresa A | Empresa B | Field | Status | A | B | Reason |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in s3.get("pair_checks") or []:
        company_a, company_b = split_pair_companies(c.get("pair"))
        lines.append(
            f"| {to_text(company_a,120)} | {to_text(company_b,120)} | {to_text(c.get('field') or c.get('check'),120)} | {to_text(c.get('status'),80)} | {to_text(c.get('a_value'),180)} | {to_text(c.get('b_value'),180)} | {to_text(c.get('reason'),160)} |"
        )
    lines.append("")

    lines.append("## Stage 03 Group Checks")
    lines.append("| Group Check | Status | Reason | Items |")
    lines.append("|---|---|---|---|")
    for g in s3.get("group_checks") or []:
        items_txt = "; ".join(
            f"{it.get('doc') or it.get('doc_kind')}: {to_text(it.get('value'),80)}"
            for it in (g.get("items") or [])
        )
        lines.append(
            f"| {to_text(g.get('group_check'),160)} | {to_text(g.get('status'),80)} | {to_text(g.get('reason'),160)} | {to_text(items_txt,320)} |"
        )
    lines.append("")

    lines.append("## Stage 03 Rule Checks")
    lines.append("| Rule Check | Empresa A | Empresa B | Status | Invoice Incoterm | BL Freight | Reason |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in s3.get("rule_checks") or []:
        company_a, company_b = split_pair_companies(r.get("pair"))
        lines.append(
            f"| {to_text(r.get('rule_check'),160)} | {to_text(company_a,120)} | {to_text(company_b,120)} | {to_text(r.get('status'),80)} | {to_text(r.get('invoice_incoterm'),100)} | {to_text(r.get('bl_freight_mode'),100)} | {to_text(r.get('reason'),140)} |"
        )
    lines.append("")
    return "\n".join(lines)


def build_html(report: dict) -> str:
    s2 = report.get("stage02") or {}
    s3 = report.get("stage03") or {}
    s2s = s2.get("summary") or {}
    s3s = s3.get("summary") or {}

    def render_stage02_doc(doc: dict) -> str:
        src = doc.get("source") or {}
        summ = doc.get("summary") or {}
        rows: List[str] = []
        for f in doc.get("fields") or []:
            evidence = "\n".join(str(x) for x in (f.get("evidence") or []))
            rows.append(
                f"""
                <tr>
                  <td><code>{tr(f.get('field',''))}</code></td>
                  <td>{tr(f.get('required'))}</td>
                  <td>{tr(f.get('present'))}</td>
                  <td>{tr(f.get('method',''))}</td>
                  <td><pre class="mono">{tr(to_text(f.get('value')))}</pre></td>
                  <td><pre class="mono">{tr(to_text(evidence))}</pre></td>
                </tr>
                """
            )

        missing = ", ".join(doc.get("missing_required_fields") or []) or "-"
        warnings = "; ".join(doc.get("warnings") or []) or "-"
        return f"""
        <div class="section">
          <h3>{tr(doc_kind_label(src.get("doc_kind")))} - {tr(src.get("original_file") or src.get("stage01_file") or "")}</h3>
          <div class="muted">
            Required: {tr(summ.get("required_present",0))}/{tr(summ.get("required_total",0))}
            | Missing required: {tr(summ.get("missing_required_count",0))}
            | Warnings: {tr(summ.get("warnings_count",0))}
          </div>
          <div class="muted">Missing fields: {tr(missing)}</div>
          <div class="muted">Warnings: {tr(warnings)}</div>
          <table class="tbl">
            <thead>
              <tr>
                <th>Field</th><th>Required</th><th>Present</th><th>Method</th><th>Value</th><th>Evidence</th>
              </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """

    pair_rows: List[str] = []
    for c in s3.get("pair_checks") or []:
        company_a, company_b = split_pair_companies(c.get("pair"))
        pair_rows.append(
            f"""
            <tr>
              <td>{tr(to_text(company_a,140))}</td>
              <td>{tr(to_text(company_b,140))}</td>
              <td><code>{tr(to_text(c.get("field") or c.get("check"),120))}</code></td>
              <td>{tr(c.get("status",""))}</td>
              <td>{tr(to_text(c.get("a_value"),220))}</td>
              <td>{tr(to_text(c.get("b_value"),220))}</td>
              <td>{tr(to_text(c.get("reason"),220))}</td>
            </tr>
            """
        )

    group_rows: List[str] = []
    for g in s3.get("group_checks") or []:
        items_txt = "; ".join(
            f"{it.get('doc') or it.get('doc_kind')}: {to_text(it.get('value'),80)}"
            for it in (g.get("items") or [])
        )
        group_rows.append(
            f"""
            <tr>
              <td>{tr(to_text(g.get("group_check"),220))}</td>
              <td>{tr(to_text(g.get("status"),80))}</td>
              <td>{tr(to_text(g.get("reason"),220))}</td>
              <td>{tr(to_text(items_txt,500))}</td>
            </tr>
            """
        )

    rule_rows: List[str] = []
    for r in s3.get("rule_checks") or []:
        company_a, company_b = split_pair_companies(r.get("pair"))
        rule_rows.append(
            f"""
            <tr>
              <td>{tr(to_text(r.get("rule_check"),220))}</td>
              <td>{tr(to_text(company_a,140))}</td>
              <td>{tr(to_text(company_b,140))}</td>
              <td>{tr(to_text(r.get("status"),80))}</td>
              <td>{tr(to_text(r.get("invoice_incoterm"),120))}</td>
              <td>{tr(to_text(r.get("bl_freight_mode"),120))}</td>
              <td>{tr(to_text(r.get("reason"),220))}</td>
            </tr>
            """
        )

    docs_html = "".join(render_stage02_doc(doc) for doc in (s2.get("documents") or []))

    return f"""
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Stage 05 Debug Report - Exportation</title>
  <style>
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      background: #fff; color: #111; margin: 20px;
    }}
    .container {{ max-width: 1320px; margin: 0 auto; }}
    h1 {{ margin: 0 0 6px 0; }}
    h2 {{ margin-top: 28px; }}
    h3 {{ margin: 0 0 8px 0; }}
    .muted {{ color: #666; font-size: 12px; white-space: pre-wrap; }}
    .grid {{
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px; margin-top: 10px;
    }}
    .card {{
      border: 1px solid #eee; border-radius: 12px; padding: 12px; background: #fff;
    }}
    .card .k {{ color: #666; font-size: 12px; }}
    .card .v {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
    .section {{
      border: 1px solid #eee; border-radius: 14px; padding: 14px; margin-top: 14px; background: #fff;
    }}
    .tbl {{
      width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: fixed;
    }}
    .tbl th, .tbl td {{
      border-bottom: 1px solid #eee; padding: 8px; vertical-align: top; font-size: 12px; word-break: break-word;
    }}
    .tbl th {{ text-align: left; background: #fafafa; }}
    .mono {{
      margin: 0; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
    }}
    code {{
      background: #f6f6f6; padding: 2px 6px; border-radius: 6px; font-size: 11px;
      display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Stage 05 Debug Report - Exportation</h1>
    <div class="muted">Generated at {tr(report.get("generated_at",""))}</div>

    <h2>Overview</h2>
    <div class="grid">
      <div class="card"><div class="k">Stage 02 documents</div><div class="v">{tr(s2s.get("documents_total",0))}</div></div>
      <div class="card"><div class="k">Stage 02 fields present</div><div class="v">{tr(s2s.get("fields_present",0))} / {tr(s2s.get("fields_total",0))}</div></div>
      <div class="card"><div class="k">Missing required</div><div class="v">{tr(s2s.get("missing_required_total",0))}</div></div>
      <div class="card"><div class="k">Stage 03 divergences</div><div class="v">{tr(s3s.get("divergences",0))}</div></div>
    </div>

    <h2>Stage 02 Full Details</h2>
    {docs_html or "<div class='section'><div class='muted'>No Stage 02 documents found.</div></div>"}

    <h2>Stage 03 Pair Checks</h2>
    <div class="section">
      <div class="muted">Total: {tr(s3s.get("total",0))} | Matches: {tr(s3s.get("matches",0))} | Divergences: {tr(s3s.get("divergences",0))} | Skipped: {tr(s3s.get("skipped",0))}</div>
      <table class="tbl">
        <thead>
          <tr><th>Empresa A</th><th>Empresa B</th><th>Field</th><th>Status</th><th>A</th><th>B</th><th>Reason</th></tr>
        </thead>
        <tbody>{''.join(pair_rows) if pair_rows else "<tr><td colspan='7' class='muted'>No pair checks.</td></tr>"}</tbody>
      </table>
    </div>

    <h2>Stage 03 Group Checks</h2>
    <div class="section">
      <table class="tbl">
        <thead>
          <tr><th>Group Check</th><th>Status</th><th>Reason</th><th>Items</th></tr>
        </thead>
        <tbody>{''.join(group_rows) if group_rows else "<tr><td colspan='4' class='muted'>No group checks.</td></tr>"}</tbody>
      </table>
    </div>

    <h2>Stage 03 Rule Checks</h2>
    <div class="section">
      <table class="tbl">
        <thead>
          <tr><th>Rule Check</th><th>Empresa A</th><th>Empresa B</th><th>Status</th><th>Invoice Incoterm</th><th>BL Freight</th><th>Reason</th></tr>
        </thead>
        <tbody>{''.join(rule_rows) if rule_rows else "<tr><td colspan='7' class='muted'>No rule checks.</td></tr>"}</tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


def run_stage_05_debug_report(
    stage02_dir: Path,
    stage03_file: Path,
    out_dir: Path,
    verbose: bool = True,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    stage02_docs = load_stage02_docs(stage02_dir)
    stage03_obj = read_json(stage03_file)
    stage03_norm = normalize_stage03(stage03_obj)

    report = {
        "generated_at": now_iso(),
        "flow": "exportation",
        "inputs": {
            "stage02_dir": str(stage02_dir),
            "stage03_file": str(stage03_file),
        },
        "stage02": build_stage02_debug(stage02_docs),
        "stage03": build_stage03_debug(stage03_norm),
        "raw": {
            "stage02_documents": stage02_docs,
            "stage03": stage03_obj,
        },
    }

    out_json = out_dir / "_stage05_debug_report.json"
    out_md = out_dir / "_stage05_debug_report.md"
    out_html = out_dir / "_stage05_debug_report.html"

    write_json(out_json, report)
    write_text(out_md, build_markdown(report))
    write_text(out_html, build_html(report))

    if verbose:
        print("Stage 05 completed.")
        print(f"JSON : {out_json}")
        print(f"MD   : {out_md}")
        print(f"HTML : {out_html}")

    return {
        "processed": True,
        "warnings": [],
        "output_json": str(out_json),
        "output_md": str(out_md),
        "output_html": str(out_html),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage02", required=True, help="Stage 02 folder (exportation)")
    ap.add_argument("--stage03", required=True, help="Stage 03 comparison json")
    ap.add_argument("--out", required=True, help="Output folder for Stage 05 debug report")
    args = ap.parse_args()

    run_stage_05_debug_report(
        stage02_dir=Path(args.stage02),
        stage03_file=Path(args.stage03),
        out_dir=Path(args.out),
        verbose=True,
    )


if __name__ == "__main__":
    main()

