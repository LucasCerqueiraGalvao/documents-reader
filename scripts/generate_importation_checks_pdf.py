from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DocTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0A5EA8"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0B3F6F"),
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubSection",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#16324F"),
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodySmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.6,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="Meta",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475569"),
        )
    )
    return styles


def _styled_table(rows, col_widths):
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A5EA8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFFFFF")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8.2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def build_pdf(output_file: Path) -> None:
    styles = _make_styles()

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.4 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title="Documentacao de Verificacoes - Importacao",
        author="Documents Reader",
        subject="Regras Stage 02 e Stage 03",
    )

    story = []
    story.append(Paragraph("Documentacao de Verificacoes - Importacao", styles["DocTitle"]))
    story.append(
        Paragraph(
            f"Projeto: Documents Reader | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles["Meta"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Este material resume tudo que o pipeline valida no Stage 02 (extracao de campos) e no Stage 03 (comparacoes e regras de negocio).",
            styles["BodySmall"],
        )
    )

    story.append(Paragraph("1. Stage 02 - Campos verificados por tipo de documento", styles["Section"]))

    story.append(Paragraph("1.1 Invoice", styles["SubSection"]))
    invoice_rows = [
        ["Campo", "Obrigatorio", "Regra"],
        ["invoice_number", "Sim", "Regex INVOICE NO + fallback DN-xxxxx"],
        ["invoice_date", "Sim", "Regex de data em ingles"],
        ["payment_terms", "Sim", "Busca ADVANCE PAYMENT/PAYMENT TERMS"],
        ["importer_name", "Sim", "Linha antes do CNPJ"],
        ["importer_cnpj", "Sim", "Regex de CNPJ"],
        ["consignee_cnpj", "Sim", "Alias de importer_cnpj"],
        ["shipper_name", "Sim", "Heuristica textual"],
        ["currency", "Sim", "Regex CURRENCY"],
        ["incoterm", "Sim", "Busca de Incoterm"],
        ["country_of_origin", "Sim", "Regex"],
        ["country_of_acquisition", "Sim", "Regex"],
        ["country_of_provenance", "Sim", "Regex"],
        ["net_weight_kg", "Sim", "Regex + parser numerico"],
        ["gross_weight_kg", "Sim", "Regex + parser numerico"],
        ["freight_and_expenses", "Nao", "Varredura por keywords"],
        ["line_items", "Nao", "Parser de itens"],
    ]
    story.append(_styled_table(invoice_rows, [4.2 * cm, 2.2 * cm, 8.6 * cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("1.2 Packing List", styles["SubSection"]))
    packing_rows = [
        ["Campo", "Obrigatorio", "Regra"],
        ["invoice_number", "Sim", "Regex de referencia documental"],
        ["importer_name", "Sim", "Linha antes do CNPJ + limpeza OCR"],
        ["shipper_name", "Nao", "Heuristica SHIPPER/EXPORTER ou ACCOUNT OF"],
        ["importer_cnpj", "Sim", "Regex + normalizacao"],
        ["packages_total", "Sim", "Linha TOTAL CARTON(S)"],
        ["net_weight_kg", "Sim", "Valor do TOTAL"],
        ["gross_weight_kg", "Sim", "Valor do TOTAL"],
        ["measurement_total_m3", "Sim", "M3 da linha TOTAL"],
        ["items", "Sim", "Parser tabular de itens"],
    ]
    story.append(_styled_table(packing_rows, [4.2 * cm, 2.2 * cm, 8.6 * cm]))
    story.append(
        Paragraph(
            "Observacoes: aceita CARTON/CARTONS, item unico ou faixa, e usa TOTAL como fonte final quando houver divergencia na soma dos itens.",
            styles["Meta"],
        )
    )

    story.append(Spacer(1, 8))
    story.append(Paragraph("1.3 BL/HBL", styles["SubSection"]))
    bl_rows = [
        ["Campo", "Obrigatorio", "Regra"],
        ["shipper_name", "Sim", "Bloco SHIPPER com limpeza de ruido"],
        ["importer_name", "Sim", "Bloco CONSIGNEE proximo ao CNPJ"],
        ["importer_cnpj", "Sim", "Regex de CNPJ"],
        ["ncm", "Sim", "Regex com 4, 6 ou 8 digitos"],
        ["gross_weight_kg", "Sim", "Regex OCR robusta + fallback M3/CBM"],
        ["freight_terms", "Nao", "Detecta COLLECT ou PREPAID"],
    ]
    story.append(_styled_table(bl_rows, [4.2 * cm, 2.2 * cm, 8.6 * cm]))

    story.append(Paragraph("2. Stage 03 - Comparacoes", styles["Section"]))
    pair_items = [
        "Invoice vs Packing List: referencia, nome consignatario, CNPJ, peso bruto e peso liquido.",
        "Invoice vs BL: nome consignatario, CNPJ e peso bruto.",
        "Packing List vs BL: nome consignatario, CNPJ e peso bruto.",
        "DI/LI vs base (quando houver): numero da invoice, nome, CNPJ e peso bruto.",
    ]
    story.append(
        ListFlowable(
            [ListItem(Paragraph(i, styles["BodySmall"])) for i in pair_items],
            bulletType="1",
            start="1",
            leftPadding=14,
        )
    )

    story.append(Spacer(1, 6))
    method_rows = [
        ["Tipo", "Regra"],
        ["number", "Comparacao numerica com tolerancia (tipicamente abs 1.0 e rel 1%)."],
        ["string", "Similaridade por tokens + contencao textual."],
        ["cnpj", "Igualdade exata dos digitos."],
        ["docref", "Normalizacao + tolerancia ao sufixo P."],
    ]
    story.append(_styled_table(method_rows, [3.0 * cm, 12.0 * cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Group checks e Rule check", styles["SubSection"]))
    checks_rows = [
        ["Check", "Descricao"],
        [
            "shipper_exporter_equal_across_invoice_packing_bl",
            "Valida coerencia de shipper/exporter entre Invoice, Packing e BL com regra textual flexivel.",
        ],
        [
            "consignee_cnpj_equal_across_invoice_packing_bl",
            "Valida igualdade de CNPJ nos tres documentos.",
        ],
        [
            "incoterm_vs_freight_mode",
            "Valida Incoterm vs modo de frete (FOB/FCA/EXW->COLLECT; CFR/CIF/CPT/CIP/DAP/DPU/DDP->PREPAID).",
        ],
    ]
    story.append(_styled_table(checks_rows, [6.4 * cm, 8.6 * cm]))

    story.append(Paragraph("3. Status e auditoria", styles["Section"]))
    status_rows = [
        ["Status", "Significado"],
        ["match", "Conforme a regra."],
        ["divergent", "Diferenca relevante."],
        ["skipped", "Nao comparado por falta de dado/condicao."],
        ["missing", "Campo ausente, principalmente em check de grupo."],
    ]
    story.append(_styled_table(status_rows, [3.0 * cm, 12.0 * cm]))

    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "Arquivos de saida para auditoria: stage_02_fields/*_fields.json, stage_02_fields/_stage02_summary.json, stage_03_compare/_stage03_comparison.json e stage_04_report/_stage04_report.html.",
            styles["Meta"],
        )
    )

    doc.build(story)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output_file = root / "docs" / "importation_checks_reference.pdf"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(output_file)
    print(output_file)


if __name__ == "__main__":
    main()
