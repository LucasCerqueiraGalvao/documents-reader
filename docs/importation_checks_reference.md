# Documentação Técnica - Verificações de Importação

## 1. Objetivo

Este documento descreve, de forma executiva e técnica, **o que o pipeline verifica**:

1. Na **extração de campos (Stage 02)** para cada tipo de documento:
   - Invoice
   - Packing List
   - BL/HBL
2. Na **comparação entre documentos (Stage 03)**:
   - Checks por pares
   - Checks globais (group checks)
   - Regras de negócio (rule checks)

Escopo desta versão: código em `src/stage_02_field_extract/importation/` e `src/stage_03_compare_docs/compare_importation.py`.

---

## 2. Stage 02 - Campos verificados por documento

### 2.1 Invoice (`invoice.py`)

| Campo | Obrigatório | Regra de extração/validação |
|---|---|---|
| `invoice_number` | Sim | Regex `INVOICE NO`; fallback para padrão de referência (ex.: `DN-24139`) |
| `invoice_date` | Sim | Regex de data em inglês (ex.: `AUG. 28, 2025`) |
| `payment_terms` | Sim | Busca `ADVANCE PAYMENT` ou `PAYMENT TERMS` |
| `importer_name` | Sim | Heurística: linha imediatamente antes do CNPJ |
| `importer_cnpj` | Sim | Regex de CNPJ, normalizado para dígitos |
| `consignee_cnpj` | Sim | Alias de `importer_cnpj` |
| `shipper_name` | Sim | Heurística por regex (bloco com nome do exportador/shipper) |
| `currency` | Sim | Regex `CURRENCY: XXX` |
| `incoterm` | Sim | Busca de Incoterm (FCA, FOB, CIF etc.) |
| `country_of_origin` | Sim | Regex |
| `country_of_acquisition` | Sim | Regex |
| `country_of_provenance` | Sim | Regex |
| `net_weight_kg` | Sim | Regex + parser numérico robusto |
| `gross_weight_kg` | Sim | Regex + parser numérico robusto |
| `freight_and_expenses` | Não | Flag booleana por varredura de keywords |
| `line_items` | Não | Parser de linhas de item (`* MODEL QTY UNITS @...`) |

### 2.2 Packing List (`packing_list.py`)

| Campo | Obrigatório | Regra de extração/validação |
|---|---|---|
| `invoice_number` | Sim | Regex de referência documental (ex.: `DN-...`) |
| `importer_name` | Sim | Preferência: linha antes do CNPJ; com limpeza de ruído OCR |
| `shipper_name` | Não | Heurística por bloco `SHIPPER/EXPORTER` ou linha anterior a `ACCOUNT OF` |
| `importer_cnpj` | Sim | Regex de CNPJ + normalização |
| `packages_total` | Sim | Linha `TOTAL: <packs> CARTON(S)` |
| `net_weight_kg` | Sim | Prioriza valor do `TOTAL` |
| `gross_weight_kg` | Sim | Prioriza valor do `TOTAL` |
| `measurement_total_m3` | Sim | Valor de M3 na linha `TOTAL` |
| `items` | Sim | Parser tabular de itens (No, cartons, pesos, m3) |

Regras adicionais do Packing List:
- O parser aceita `CARTON` e `CARTONS`.
- Aceita faixa de numeração (`19 - 21`) e item único (`5`).
- Se soma dos itens divergir do `TOTAL` acima da tolerância, gera warning e mantém o `TOTAL` como fonte final.

### 2.3 BL/HBL (`bl.py`)

| Campo | Obrigatório | Regra de extração/validação |
|---|---|---|
| `shipper_name` | Sim | Bloco `SHIPPER` com limpeza de ruído e sufixos indevidos |
| `importer_name` | Sim | Bloco `CONSIGNEE`, priorizando linha do nome próxima ao CNPJ |
| `importer_cnpj` | Sim | Regex de CNPJ |
| `ncm` | Sim | Regex NCM/HS com 4, 6 ou 8 dígitos |
| `gross_weight_kg` | Sim | Regex robusta para OCR (`KG`, variantes OCR como `K6/KS`) + fallback por linha com `M3/CBM` |
| `freight_terms` | Não | Identifica `COLLECT` ou `PREPAID` no bloco FREIGHT |

Regras adicionais do BL:
- Para `ncm`, 4/6/8 dígitos são aceitos; warning apenas fora desses comprimentos.

---

## 3. Stage 03 - Comparações entre documentos

Arquivo de referência: `src/stage_03_compare_docs/compare_importation.py`.

### 3.1 Tipos de comparação por pares (pair checks)

#### A) Invoice vs Packing List
1. Invoice vs Packing reference number (`docref`)
2. Consignee name (`string`)
3. Consignee CNPJ (`cnpj`)
4. Gross weight (kg) (`number`)
5. Net weight (kg) (`number`)

#### B) Invoice vs BL
1. Consignee name (`string`)
2. Consignee CNPJ (`cnpj`)
3. Gross weight (kg) (`number`)

#### C) Packing List vs BL
1. Consignee name (`string`)
2. Consignee CNPJ (`cnpj`)
3. Gross weight (kg) (`number`)

#### D) DI/LI vs Base (quando houver DI/LI)
1. Invoice number (`docref`)
2. Consignee name (`string`)
3. Consignee CNPJ (`cnpj`)
4. Gross weight (kg) (`number`)

### 3.2 Regras de pareamento de documentos

- Invoice e Packing List são pareados por referência (com regra tolerante para sufixo `-P`).
- BL compara com Invoice(s) e Packing List(s) disponíveis.
- Se houver DI/LI, compara com os documentos base disponíveis.

### 3.3 Métodos de comparação usados

| Tipo | Regra aplicada |
|---|---|
| `number` | Conversão numérica robusta + tolerância (tipicamente abs `1.0` e rel `1%`) |
| `string` | Similaridade por tokens (Jaccard) + contenção textual |
| `cnpj` | Igualdade exata dos dígitos |
| `docref` | Normalização alfanumérica + tolerância para sufixo final `P` |

### 3.4 Group checks (cross-doc)

1. `shipper_exporter_equal_across_invoice_packing_bl`  
   - Confere se shipper/exporter está coerente entre Invoice, Packing e BL.  
   - Usa comparação textual "soft", com remoção de stopwords corporativas e incoterms.

2. `consignee_cnpj_equal_across_invoice_packing_bl`  
   - Confere igualdade exata de CNPJ nos três documentos.

### 3.5 Rule checks (regras de negócio)

`incoterm_vs_freight_mode`:
- Incoterms `FOB/FCA/EXW` tendem a `COLLECT`.
- Incoterms `CFR/CIF/CPT/CIP/DAP/DPU/DDP` tendem a `PREPAID`.

---

## 4. Significado dos status

| Status | Significado |
|---|---|
| `match` | Valor comparado coerente com a regra |
| `divergent` | Valor comparado em desacordo com a regra |
| `skipped` | Check não executado por falta de dado/condição |
| `missing` | Campo ausente em check de grupo |

---

## 5. Arquivos de saída para auditoria

- Stage 02 por documento: `data/output/.../stage_02_fields/importation/*_fields.json`
- Resumo Stage 02: `data/output/.../stage_02_fields/importation/_stage02_summary.json`
- Comparações Stage 03: `data/output/.../stage_03_compare/importation/_stage03_comparison.json`
- Relatório final Stage 04: `data/output/.../stage_04_report/importation/_stage04_report.html`

---

## 6. Versão

- Data de geração desta documentação: **2026-02-04**
- Documento preparado para acompanhamento técnico e apresentação gerencial.
