# Documentação Técnica — Documents Reader

---

## Índice

- [Documentação Técnica — Documents Reader](#documentação-técnica--documents-reader)
  - [Índice](#índice)
  - [1. O que é este projeto e qual problema ele resolve](#1-o-que-é-este-projeto-e-qual-problema-ele-resolve)
    - [O problema](#o-problema)
    - [A solução](#a-solução)
  - [2. Visão geral da arquitetura](#2-visão-geral-da-arquitetura)
  - [3. Como o sistema funciona — os quatro estágios](#3-como-o-sistema-funciona--os-quatro-estágios)
    - [Estágio 1 — Extração de texto dos PDFs](#estágio-1--extração-de-texto-dos-pdfs)
    - [Estágio 2 — Extração de campos estruturados](#estágio-2--extração-de-campos-estruturados)
    - [Estágio 3 — Comparação entre documentos](#estágio-3--comparação-entre-documentos)
    - [Estágio 4 — Geração do relatório final](#estágio-4--geração-do-relatório-final)
  - [4. Formas de usar o sistema](#4-formas-de-usar-o-sistema)
    - [Forma 1 — Linha de comando (terminal)](#forma-1--linha-de-comando-terminal)
    - [Forma 2 — Código Python](#forma-2--código-python)
    - [Forma 3 — API HTTP (para o aplicativo desktop Electron)](#forma-3--api-http-para-o-aplicativo-desktop-electron)
    - [Forma 4 — Aplicativo desktop Electron](#forma-4--aplicativo-desktop-electron)
  - [5. Estrutura de pastas](#5-estrutura-de-pastas)
  - [6. Dependências externas](#6-dependências-externas)
    - [Bibliotecas Python (`requirements.txt`)](#bibliotecas-python-requirementstxt)
    - [Software externo — Tesseract](#software-externo--tesseract)
    - [Instalação do ambiente Python](#instalação-do-ambiente-python)
  - [7. Como manter e evoluir o projeto](#7-como-manter-e-evoluir-o-projeto)
    - [Onde ficam as regras de negócio](#onde-ficam-as-regras-de-negócio)
      - [1. Regras de extração de campos (o que extrair e como)](#1-regras-de-extração-de-campos-o-que-extrair-e-como)
      - [2. Regras de comparação entre documentos (quais campos devem bater)](#2-regras-de-comparação-entre-documentos-quais-campos-devem-bater)
      - [3. Lista de campos obrigatórios por tipo de documento](#3-lista-de-campos-obrigatórios-por-tipo-de-documento)
    - [Como adicionar um novo tipo de documento](#como-adicionar-um-novo-tipo-de-documento)
    - [Como adicionar uma nova regra de comparação](#como-adicionar-uma-nova-regra-de-comparação)
    - [Como adicionar um novo campo a um documento existente](#como-adicionar-um-novo-campo-a-um-documento-existente)
  - [8. Pontos críticos que podem quebrar](#8-pontos-críticos-que-podem-quebrar)
    - [1. Qualidade do OCR](#1-qualidade-do-ocr)
    - [2. Variações de layout entre fornecedores](#2-variações-de-layout-entre-fornecedores)
    - [3. Codificação de texto (encoding)](#3-codificação-de-texto-encoding)
    - [4. Dependência do Tesseract](#4-dependência-do-tesseract)
    - [5. Mudança no formato de saída dos extractores](#5-mudança-no-formato-de-saída-dos-extractores)
    - [6. Dados de entrada fora do padrão esperado](#6-dados-de-entrada-fora-do-padrão-esperado)
  - [9. Decisões arquiteturais relevantes](#9-decisões-arquiteturais-relevantes)
    - [Por que cada estágio escreve arquivos em disco?](#por-que-cada-estágio-escreve-arquivos-em-disco)
    - [Por que as regras de negócio estão em código Python e não em arquivo de configuração?](#por-que-as-regras-de-negócio-estão-em-código-python-e-não-em-arquivo-de-configuração)
    - [Por que o sistema suporta execução por estágio individual?](#por-que-o-sistema-suporta-execução-por-estágio-individual)
  - [10. Fluxo de dados — exemplo prático completo](#10-fluxo-de-dados--exemplo-prático-completo)

---

## 1. O que é este projeto e qual problema ele resolve

### O problema

Operações de comércio exterior envolvem um conjunto de documentos emitidos por partes diferentes: o exportador cria a **Invoice** (nota fiscal comercial) e o **Packing List** (lista de volumes e pesos), enquanto o transportador emite o **Bill of Lading — BL** (conhecimento de embarque). Cada documento é gerado de forma independente e, por isso, é muito comum que haja **divergências** entre eles — valores, pesos, CNPJ do importador, referências de pedido — o que pode causar retenção de mercadoria, multas ou problemas na liberação alfandegária.

Hoje essa verificação é feita manualmente por analistas: abrir cada PDF, ler, comparar campo a campo. É lento, sujeito a erros e difícil de escalar.

### A solução

Este projeto é um **pipeline automatizado** (sequência de etapas de processamento) que:

1. **Lê PDFs** de documentos de importação/exportação.
2. **Extrai o texto** de cada página, usando leitura direta quando o PDF é digital ou OCR (*Optical Character Recognition* — reconhecimento ótico de caracteres) quando o PDF é uma imagem escaneada.
3. **Identifica e extrai campos estruturados** de cada documento (número da invoice, CNPJ do importador, peso bruto, incoterm, etc.).
4. **Compara os campos entre documentos**, detectando divergências e inconsistências.
5. **Gera um relatório** legível (HTML, Markdown ou JSON) com o resultado da análise.

O sistema foi projetado para ser usado de três formas: via linha de comando, via código Python, ou via uma interface gráfica desktop (aplicativo Electron).

---

## 2. Visão geral da arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FORMAS DE ENTRADA                           │
│                                                                     │
│   CLI (terminal)   │   Python (código)   │   App Desktop (Electron) │
└────────┬───────────┴──────────┬──────────┴───────────┬─────────────┘
         │                      │                       │ HTTP (REST)
         └──────────────────────▼───────────────────────┘
                          pipeline.py
                      (orquestrador central)
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                     ▼                 ▼
    stage_01              stage_02             stage_03          stage_04
  Extração texto       Extração campos      Comparação       Relatório final
  (PDF → texto)       (texto → JSON)       (JSON → diffs)   (diffs → HTML/MD)
```

**Conceito-chave: pipeline**
Um pipeline é uma sequência de etapas onde a saída de uma etapa vira a entrada da próxima. Aqui, cada estágio escreve seus resultados em arquivos JSON em disco, e o estágio seguinte lê esses arquivos. Isso significa que cada etapa pode ser executada separadamente, o que facilita depuração e reprocessamento.

**Conceito-chave: API HTTP (REST)**
Uma API (*Application Programming Interface*) HTTP é um "cardápio de serviços" que um programa oferece para outros programas. O servidor Python expõe endpoints (endereços) que o aplicativo Electron chama para pedir processamento, sem precisar entender como o Python funciona internamente.

---

## 3. Como o sistema funciona — os quatro estágios

### Estágio 1 — Extração de texto dos PDFs

**Arquivo:** `src/stage_01_text_extract/extract_text_importation.py`

**Objetivo:** transformar cada PDF em um arquivo de texto estruturado (JSON).

**Como funciona:**

Para cada página do PDF, o sistema tenta dois métodos em cascata:

1. **Extração direta** — usa a biblioteca PyMuPDF para ler o texto embutido no PDF (funciona para PDFs criados digitalmente). Se a página retornar pelo menos 80 caracteres, considera-se que a extração foi bem-sucedida.
2. **OCR** — se a extração direta retornar texto insuficiente (página provavelmente escaneada), a página é renderizada como imagem e processada pelo Tesseract OCR. Antes do OCR, a imagem passa por pré-processamento: conversão para escala de cinza, ajuste de contraste e binarização (transformar em preto-e-branco), para melhorar a acurácia.

O resultado de cada página inclui: o texto extraído, o método usado (`direct` ou `ocr`), e a contagem de caracteres.

**Saída:** um arquivo `<nome_do_pdf>_extracted.json` por documento, com a estrutura:

```json
{
  "file": "invoice.pdf",
  "pages": [
    {"page": 1, "method": "direct", "text_chars": 1250, "text": "..."},
    {"page": 2, "method": "ocr",    "text_chars": 980,  "text": "..."}
  ]
}
```

**Parâmetros configuráveis:**
| Parâmetro | Padrão | Significado |
|-----------|--------|-------------|
| `ocr_lang` | `eng+por` | Idiomas do OCR (inglês + português) |
| `ocr_dpi` | `300` | Resolução da imagem para OCR. Valores maiores = mais preciso, mais lento |
| `min_chars` | `80` | Mínimo de caracteres para aceitar extração direta |

---

### Estágio 2 — Extração de campos estruturados

**Arquivos:** `src/stage_02_field_extract/importation/`

**Objetivo:** a partir do texto bruto, identificar e extrair campos específicos de cada tipo de documento.

**Como funciona:**

O sistema primeiro **detecta o tipo de documento** pelo nome do arquivo e depois pelo conteúdo do texto, procurando palavras-chave como "PACKING LIST", "INVOICE", "BILL OF LADING". Os tipos suportados no fluxo de importação são:

| Tipo | Arquivo extrator | Campos principais extraídos |
|------|-----------------|----------------------------|
| `invoice` | `invoice.py` | Número, data, CNPJ do importador, nome do exportador, incoterm, peso líquido/bruto, moeda, condições de pagamento |
| `packing_list` | `packing_list.py` | Número, exportador, importador, CNPJ, incoterm, peso líquido/bruto total, quantidade de caixas, itens com modelo/quantidade |
| `bl` (Bill of Lading) | `bl.py` | Número do BL, shipper, consignee, CNPJ, porto de origem/destino, incoterm, peso bruto |

**Estratégias de extração:**

Cada campo é extraído por expressões regulares (_regex_) — padrões de texto que descrevem o formato esperado — ou por heurísticas (regras práticas baseadas no comportamento real dos documentos):

- **Regex:** `INVOICE NO[.:]?\s*([A-Z0-9\-\/]+)` encontra o número da invoice
- **Heurística:** para achar o nome da empresa importadora, o sistema busca a linha imediatamente antes do CNPJ, pois esse é o padrão típico em documentos de comércio exterior

Cada campo extraído é armazenado com metadados sobre como foi encontrado:

```json
{
  "invoice_number": {
    "present": true,
    "required": true,
    "value": "DN-24139",
    "evidence": ["INVOICE NO. DN-24139"],
    "method": "regex"
  }
}
```

**Saída:** um arquivo `<nome>_fields.json` por documento, mais um `_stage02_summary.json` com o resumo de todos os documentos.

---

### Estágio 3 — Comparação entre documentos

**Arquivo:** `src/stage_03_compare_docs/compare_importation.py`

**Objetivo:** cruzar os campos extraídos de todos os documentos e identificar divergências.

**Como funciona:**

O sistema carrega todos os `_fields.json` do estágio anterior e realiza comparações em grupos:

**Comparações diretas (Invoice ↔ Packing List ↔ BL):**

| Campo | Como é comparado |
|-------|-----------------|
| Número do documento | Comparação tolerante: `DN-24139` == `DN-24139-P` (aceita sufixo "-P") |
| Peso bruto / líquido | Tolerância numérica: diferença < 0,5 kg ou < 1% do valor |
| CNPJ do importador | Comparação apenas dos dígitos (ignora formatação `XX.XXX.XXX/0001-XX` vs `XXXXXXXXXXXXXXXX`) |
| Nome do exportador (shipper) | Similaridade de tokens com Jaccard ≥ 55% (robusto a ruído de OCR) |
| NCM / HS Code | Aceita prefixo: código de 4 dígitos bate com código de 8 se os primeiros 4 forem iguais |

**Regra de negócio especial — Incoterm × Frete:**

O sistema verifica se o incoterm declarado é compatível com a modalidade de frete:

```
FOB / FCA / EXW  →  frete tende a ser COLLECT (pago pelo importador)
CFR / CIF / CPT / CIP / DAP / DPU / DDP  →  frete tende a ser PREPAID (pago pelo exportador)
```

Se o incoterm for FOB mas o frete estiver marcado como PREPAID, o sistema gera um alerta de inconsistência.

**Saída:** um arquivo `_stage03_comparison.json` com todas as comparações, status (`match` / `divergent` / `skipped`) e evidências.

---

### Estágio 4 — Geração do relatório final

**Arquivo:** `src/stage_04_report/generate_report_importation.py`

**Objetivo:** consolidar os resultados dos três estágios anteriores em um relatório legível.

**Como funciona:**

O relatório lê os arquivos de saída dos estágios 1, 2 e 3 e produz três formatos simultaneamente:

- **JSON** (`_stage04_report.json`): dados estruturados, úteis para integração com outros sistemas.
- **Markdown** (`_stage04_report.md`): texto formatado, fácil de ler em qualquer editor.
- **HTML** (`_stage04_report.html`): página visual pronta para abrir no navegador ou incorporar no aplicativo desktop.

O relatório inclui:
- Qualidade da extração de texto por documento (quantas páginas usaram OCR, quais tiveram problemas)
- Status de cada campo em cada documento (presente/ausente, obrigatório/opcional)
- Resultado de cada comparação entre documentos
- Resumo executivo com quantidade de divergências e alertas

---

## 4. Formas de usar o sistema

### Forma 1 — Linha de comando (terminal)

```bash
# Ativar ambiente virtual
source .venv/bin/activate

# Rodar o pipeline completo
python src/pipeline.py \
  --input data/input/importation \
  --output data/output \
  --flow importation
```

O relatório HTML estará em `data/output/stage_04_report/importation/_stage04_report.html`.

### Forma 2 — Código Python

```python
from pathlib import Path
from src.pipeline import run_pipeline, PipelineConfig

config = PipelineConfig(
    input_dir=Path("data/input/importation"),
    output_dir=Path("data/output"),
    flow="importation",
    ocr_lang="eng+por",
    ocr_dpi=300
)

result = run_pipeline(config)

if result.success:
    print("Relatório gerado:", result.output_files["stage_04_html"])
else:
    print("Erros:", result.errors)
```

### Forma 3 — API HTTP (para o aplicativo desktop Electron)

**Iniciar o servidor:**
```bash
python src/api.py --host 127.0.0.1 --port 5000
```

**Chamadas disponíveis:**

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Verifica se o servidor está no ar |
| POST | `/api/v1/process` | Roda o pipeline completo |
| POST | `/api/v1/process/stage/1` | Roda apenas o estágio 1 |
| POST | `/api/v1/process/stage/2` | Roda apenas o estágio 2 |
| POST | `/api/v1/process/stage/3` | Roda apenas o estágio 3 |
| POST | `/api/v1/process/stage/4` | Roda apenas o estágio 4 |

**Exemplo de requisição para o pipeline completo:**
```json
POST /api/v1/process
{
  "input_dir": "/caminho/para/pdfs",
  "output_dir": "/caminho/para/saida",
  "flow": "importation",
  "ocr_lang": "eng+por",
  "ocr_dpi": 300
}
```

### Forma 4 — Aplicativo desktop Electron

O diretório `examples/electron_app/` contém um aplicativo desktop completo com interface gráfica. Ele se comunica com o servidor Python via HTTP.

```bash
cd examples/electron_app
npm install
npm start
```

O aplicativo pode ser distribuído como executável standalone (sem o usuário precisar instalar Python), usando PyInstaller para empacotar o Python junto.

---

## 5. Estrutura de pastas

```
documents_reader/
│
├── src/                          # Código-fonte principal
│   ├── pipeline.py               # Orquestrador: conecta todos os estágios
│   ├── api.py                    # Servidor HTTP (Flask) para o Electron
│   │
│   ├── stage_01_text_extract/    # Estágio 1: PDF → texto
│   │   ├── extract_text_importation.py
│   │   └── extract_text_exportation.py
│   │
│   ├── stage_02_field_extract/   # Estágio 2: texto → campos
│   │   ├── importation/
│   │   │   ├── extract_fields_importation.py  # Orquestrador do est. 2
│   │   │   ├── invoice.py         # Extrator de Invoice
│   │   │   ├── packing_list.py    # Extrator de Packing List
│   │   │   ├── bl.py              # Extrator de Bill of Lading
│   │   │   └── common.py          # Funções utilitárias compartilhadas
│   │   └── exportation/
│   │       └── extract_fields_exportation.py
│   │
│   ├── stage_03_compare_docs/    # Estágio 3: comparação cruzada
│   │   └── compare_importation.py
│   │
│   └── stage_04_report/          # Estágio 4: geração de relatório
│       └── generate_report_importation.py
│
├── data/
│   ├── input/
│   │   ├── importation/raw/      # ← Coloque os PDFs de importação aqui
│   │   └── exportation/raw/      # ← Coloque os PDFs de exportação aqui
│   └── output/                   # ← Saídas geradas automaticamente
│       ├── stage_01_text/
│       ├── stage_02_fields/
│       ├── stage_03_compare/
│       └── stage_04_report/
│
├── configs/
│   ├── importation_rules.yaml    # Referência: campos obrigatórios (stub)
│   └── exportation_rules.yaml
│
├── examples/
│   ├── electron_app/             # Aplicativo desktop completo
│   └── nodejs_client.js          # Exemplo de cliente Node.js
│
└── requirements.txt              # Dependências Python
```

---

## 6. Dependências externas

### Bibliotecas Python (`requirements.txt`)

| Biblioteca | Versão | Para que serve |
|-----------|--------|---------------|
| `pymupdf` | 1.26.5 | Leitura de PDFs e renderização de páginas como imagem |
| `pillow` | 11.3.0 | Manipulação de imagens (pré-processamento para OCR) |
| `pytesseract` | 0.3.13 | Interface Python para o motor de OCR Tesseract |
| `flask` | 3.0.0 | Framework para o servidor HTTP |
| `flask-cors` | 4.0.0 | Permite que o Electron (rodando em outra "origem") chame o servidor |
| `packaging` | 25.0 | Utilitário de comparação de versões |

> **O que é um framework?** É uma estrutura pronta que resolve problemas comuns, para que você não precise "reinventar a roda". O Flask, por exemplo, cuida de receber requisições HTTP, parsear JSON e enviar respostas — você só escreve a lógica de negócio.

### Software externo — Tesseract

O Tesseract é o motor de OCR. Ele precisa ser instalado **separadamente** no sistema operacional:

| Sistema | Comando de instalação |
|---------|----------------------|
| macOS | `brew install tesseract tesseract-lang` |
| Ubuntu/Debian | `apt-get install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng` |
| Windows | Download em [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) |

Após instalar, o sistema o encontra automaticamente via PATH. Se precisar especificar o caminho manualmente, defina a variável de ambiente `TESSERACT_EXE`.

### Instalação do ambiente Python

```bash
# Criar ambiente virtual (isola as dependências deste projeto)
python -m venv .venv

# Ativar (macOS/Linux)
source .venv/bin/activate

# Ativar (Windows)
.venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

> **O que é um ambiente virtual?** É uma cópia isolada do Python com suas próprias dependências. Evita conflitos entre versões de bibliotecas de projetos diferentes no mesmo computador.

---

## 7. Como manter e evoluir o projeto

### Onde ficam as regras de negócio

As regras de negócio estão distribuídas em três locais principais:

#### 1. Regras de extração de campos (o que extrair e como)

**Localização:** `src/stage_02_field_extract/importation/`

Cada tipo de documento tem seu próprio arquivo Python com as expressões regulares e heurísticas:

```
invoice.py       → campos da Invoice comercial
packing_list.py  → campos do Packing List
bl.py            → campos do Bill of Lading
common.py        → funções reutilizadas por todos os três
```

**Exemplo:** para alterar como o número da Invoice é extraído, edite `invoice.py`, especificamente a variável `RE_INVOICE_NO`:

```python
# Padrão atual — encontra "INVOICE NO. DN-24139"
RE_INVOICE_NO = re.compile(r"(?is)\bINVOICE\s*NO\.?\s*[:\-]?\s*([A-Z0-9\-\/]+)\b")
```

Se os documentos do seu fornecedor usarem `INV#` em vez de `INVOICE NO.`, adicione uma alternativa:
```python
RE_INVOICE_NO = re.compile(r"(?is)\b(?:INVOICE\s*NO\.?|INV#)\s*[:\-]?\s*([A-Z0-9\-\/]+)\b")
```

#### 2. Regras de comparação entre documentos (quais campos devem bater)

**Localização:** `src/stage_03_compare_docs/compare_importation.py`

Agrupe as buscas na função principal `run_stage_03_comparison()` e nas funções auxiliares de comparação (ex: `num_close`, `token_overlap_close`, `docref_close`). Cada comparação gera um item de resultado com status `match`, `divergent` ou `skipped`.

A regra de incoterm × frete, por exemplo, está implementada como uma função separada que retorna `match` ou `divergent`.

#### 3. Lista de campos obrigatórios por tipo de documento

**Localização:** `configs/importation_rules.yaml`

Este arquivo é atualmente um **stub de referência** (documentação das regras, ainda não lido em tempo de execução pelo código). A obrigatoriedade de cada campo está codificada diretamente nos extractores, no parâmetro `required=True` de cada `build_field()`/`_mk_field()`. Se quiser centralizar isso no YAML e fazê-lo ser lido dinamicamente, seria uma evolução necessária.

---

### Como adicionar um novo tipo de documento

**Exemplo:** adicionar suporte ao **Certificado de Origem** no fluxo de importação.

**Passo 1 — Criar o extrator**

Crie `src/stage_02_field_extract/importation/certificate_of_origin.py` seguindo o mesmo padrão dos outros:

```python
# certificate_of_origin.py
import re
from .common import build_field, find_first

RE_CERT_NO = re.compile(r"(?is)\bCERTIFICATE\s*NO\.?\s*[:\-]?\s*([A-Z0-9\-\/]+)\b")

def extract_certificate_of_origin_fields(text: str):
    warnings = []
    fields = {}

    cert_no, ev = find_first(RE_CERT_NO, text)
    fields["certificate_number"] = build_field(bool(cert_no), True, cert_no, [ev] if ev else [], "regex")

    # ... outros campos ...

    return fields, warnings  # retorna a mesma assinatura dos outros extractors
```

**Passo 2 — Registrar no orquestrador do estágio 2**

Em `extract_fields_importation.py`, adicione:

```python
# Nas importações no topo do arquivo
from .certificate_of_origin import extract_certificate_of_origin_fields

# Na função detect_kind(), adicione a regra de detecção
if "CERTIFICATE OF ORIGIN" in up or "CERT OF ORIGIN" in up:
    return "certificate_of_origin"

# Na lógica de despacho, adicione o novo tipo
elif doc_kind == "certificate_of_origin":
    res = extract_certificate_of_origin_fields(full_text)
```

**Passo 3 — Adicionar comparações no estágio 3** (se necessário)

Em `compare_importation.py`, adicione comparações entre o certificado de origem e os outros documentos, caso campos como "país de origem" devam bater com os da Invoice.

---

### Como adicionar uma nova regra de comparação

**Exemplo:** verificar se o porto de destino no BL é compatível com o endereço do importador.

Em `compare_importation.py`, adicione uma nova função de comparação e inclua seu resultado na lista de checks:

```python
def check_port_vs_consignee(bl_doc: dict, invoice_doc: dict) -> dict:
    """Verifica se o porto de destino bate com o estado do importador."""
    port, _ = get_field(bl_doc, "port_of_discharge")
    address, _ = get_field(invoice_doc, "importer_address")

    if not port or not address:
        return {"rule": "port_vs_consignee", "status": "skipped", "reason": "campo ausente"}

    # ... lógica de comparação ...
    match = port_in_state(port, address)
    return {
        "rule": "port_vs_consignee",
        "status": "match" if match else "divergent",
        "values": {"bl_port": port, "importer_address": address}
    }
```

---

### Como adicionar um novo campo a um documento existente

**Exemplo:** extrair o número de containers da Invoice.

Em `invoice.py`:

1. Adicione a expressão regular:
```python
RE_CONTAINERS = re.compile(r"(?is)\bCONTAINER[S]?\s*[:\-]?\s*(\d+)\b")
```

2. Adicione a extração na função `extract_invoice_fields`:
```python
containers, ev = find_first(RE_CONTAINERS, text)
fields["containers_count"] = build_field(
    bool(containers), False, containers, [ev] if ev else [], "regex"
)
```

> Use `required=False` para campos informativos. Use `required=True` apenas para campos que, se ausentes, devem gerar alerta no relatório.

---

## 8. Pontos críticos que podem quebrar

### 1. Qualidade do OCR

**Risco:** documentos escaneados com má qualidade de imagem (baixa resolução, manchas, inclinação) produzem texto com erros de OCR, o que faz com que as expressões regulares não encontrem os campos.

**Sintomas:** campos aparecem como `"present": false` no JSON do estágio 2, apesar de o documento conter a informação visualmente.

**Mitigação:**
- Aumentar `ocr_dpi` para 400 ou 600 para documentos problemáticos.
- Se um fornecedor específico gera documentos com ruído consistente, adicionar limpeza de texto específica em `common.py`.
- O estágio 4 mostra quantas páginas usaram OCR e quais tiveram qualidade baixa.

### 2. Variações de layout entre fornecedores

**Risco:** cada exportador tem um modelo de invoice diferente. Uma expressão regular que funciona para o fornecedor A pode não funcionar para o fornecedor B.

**Sintomas:** campos extraídos incorretamente ou ausentes para documentos de um novo fornecedor.

**Mitigação:**
- Os extractores já têm fallbacks (tentativas alternativas) para os campos mais comuns.
- Quando um novo fornecedor aparece, revise os arquivos `invoice.py`, `packing_list.py`, `bl.py` e adicione padrões alternativos.
- A evidência salva em cada campo (`"evidence": ["texto capturado"]`) ajuda a depurar: veja o que foi capturado para entender o que o regex encontrou.

### 3. Codificação de texto (encoding)

**Risco:** PDFs que contêm caracteres especiais (acentos, símbolos) podem gerar texto corrompido durante a extração direta.

**Sintomas:** você verá `Ã£` no lugar de `ã`, ou similar, no texto extraído.

**Mitigação:** já existe limpeza de texto no estágio 1 (`clean_text()`). Se aparecerem novos problemas, adicione as substituições necessárias ali.

### 4. Dependência do Tesseract

**Risco:** o Tesseract precisa estar instalado e no PATH do sistema. Em ambientes de produção (servidores, containers Docker), isso precisa ser configurado explicitamente.

**Mitigação:**
- A variável de ambiente `TESSERACT_EXE` permite especificar o caminho exato.
- O aplicativo Electron inclui um binário empacotado do Tesseract em `examples/electron_app/resources/tesseract/`.
- O sistema faz fallback graciosamente: se o Tesseract não estiver disponível, registra um aviso e pula o OCR (não quebra, mas deixa o campo vazio).

### 5. Mudança no formato de saída dos extractores

**Risco:** os extractores retornam tuplas `(fields, warnings)` ou `(fields, missing, warnings)`. Se alguém modificar um extrator e alterar a assinatura do retorno sem atualizar o orquestrador, o código quebra.

**Mitigação:** a função `unpack_extractor_result()` em `extract_fields_importation.py` foi criada exatamente para normalizar essas variações. Sempre retorne tuplas nesses dois formatos e use essa função no orquestrador.

### 6. Dados de entrada fora do padrão esperado

**Risco:** o pipeline espera encontrar os PDFs em `data/input/importation/raw/`. Se a pasta não existir ou estiver vazia, o estágio 1 não processa nada, e os estágios seguintes recebem entrada vazia.

**Mitigação:** o sistema já retorna erros descritivos nesses casos. Sempre verifique o campo `"warnings"` e `"errors"` no resultado do pipeline.

---

## 9. Decisões arquiteturais relevantes

### Por que cada estágio escreve arquivos em disco?

**Alternativa:** passar os dados diretamente entre funções na memória, sem escrever arquivos intermediários.

**Decisão tomada:** escrever arquivos JSON entre estágios.

**Por quê:** permite:
- Reprocessar apenas um estágio específico sem rodar o pipeline inteiro (útil quando se ajusta uma regra de extração).
- Depurar problemas: você pode abrir `_extracted.json` e `_fields.json` e inspecionar o que cada estágio produziu.
- Rastreabilidade: cada execução deixa um rastro auditável do que foi extraído.

**Implicação:** o diretório `data/output/` cresce com o tempo. Planeje uma rotina de limpeza periódica se o volume de documentos procesados for alto.

---

### Por que as regras de negócio estão em código Python e não em arquivo de configuração?

**Alternativa:** usar o `importation_rules.yaml` para definir todos os campos e regras.

**Decisão tomada:** as regras de extração ficam nos arquivos Python (`invoice.py`, etc.) e o YAML é apenas referência de documentação.

**Por quê:** expressões regulares com fallbacks e heurísticas complexas são difíceis de expressar em YAML de forma flexível. O código Python permite lógica condicional, encadeamento de tentativas e tratamento de casos especiais com muito mais clareza.

**Implicação:** para adicionar ou alterar uma regra, você precisa editar código Python — não basta editar o YAML.

---

### Por que o sistema suporta execução por estágio individual?

A API HTTP expõe endpoints para cada estágio individualmente (`/api/v1/process/stage/1`, etc.), além do pipeline completo.

**Por quê:** para o aplicativo Electron, isso permite implementar uma interface com **barra de progresso** exibindo cada estágio, e também permite que o usuário reprocesse apenas um estágio se ajustar uma configuração.

---

## 10. Fluxo de dados — exemplo prático completo

Suponha que você tem os arquivos:
- `data/input/importation/raw/invoice_DN24139.pdf`
- `data/input/importation/raw/packing_list_DN24139.pdf`
- `data/input/importation/raw/BL_MAEU123456.pdf`

Após rodar `python src/pipeline.py --input data/input/importation --output data/output --flow importation`:

**Após o estágio 1:**
```
data/output/stage_01_text/importation/
  invoice_DN24139_extracted.json     ← texto de cada página
  packing_list_DN24139_extracted.json
  BL_MAEU123456_extracted.json
```

**Após o estágio 2:**
```
data/output/stage_02_fields/importation/
  invoice_DN24139_fields.json        ← campos estruturados
  packing_list_DN24139_fields.json
  BL_MAEU123456_fields.json
  _stage02_summary.json              ← resumo de todos os docs
```

Exemplo de conteúdo de `invoice_DN24139_fields.json`:
```json
{
  "source": {"doc_kind": "invoice", "original_file": "invoice_DN24139.pdf"},
  "fields": {
    "invoice_number": {"present": true, "required": true, "value": "DN-24139", "method": "regex"},
    "importer_cnpj":  {"present": true, "required": true, "value": "12.345.678/0001-90", "method": "regex"},
    "gross_weight":   {"present": true, "required": true, "value": 388.0, "method": "regex"},
    "incoterm":       {"present": true, "required": true, "value": "FOB", "method": "regex"}
  },
  "missing_required_fields": []
}
```

**Após o estágio 3:**
```
data/output/stage_03_compare/importation/
  _stage03_comparison.json           ← todas as comparações cruzadas
```

Exemplo de trecho do resultado de comparação:
```json
{
  "comparisons": [
    {
      "rule": "invoice_vs_packing_gross_weight",
      "status": "match",
      "values": {"invoice": 388.0, "packing_list": 388.0}
    },
    {
      "rule": "incoterm_vs_freight_mode",
      "status": "divergent",
      "detail": "Incoterm FOB sugere COLLECT, mas BL indica PREPAID"
    }
  ]
}
```

**Após o estágio 4:**
```
data/output/stage_04_report/importation/
  _stage04_report.json
  _stage04_report.md
  _stage04_report.html               ← ← ← este é o relatório final para o usuário
```

O relatório HTML apresenta:
- Uma tabela com o status de cada campo em cada documento
- Uma seção de divergências destacadas em vermelho
- Uma seção de alertas em amarelo
- Metadados sobre a qualidade da extração (quantas páginas precisaram de OCR)
