# Documents Reader

Document processing pipeline for import/export trade documents with OCR, field extraction, comparison/validation, and report generation.

## Architecture

All stages are callable Python functions and can be used via:
- Python (programmatic)
- CLI
- HTTP API (Flask) for Node.js / Electron

Pipeline stages:
1. Stage 01 - Text extraction (PyMuPDF + OCR fallback)
2. Stage 02 - Field extraction (`regex` or `llm`)
3. Stage 03 - Cross-document compare/validation
4. Stage 04 - Report generation (JSON/Markdown/HTML)

Optional:
5. Stage 05 - Detailed debug report

## Project Structure

```text
data/
  input/importation/raw/
  input/exportation/raw/
  output/
src/
  stage_01_text_extract/
  stage_02_field_extract/
  stage_03_compare_docs/
  stage_04_report/
  stage_05_debug_report/
  pipeline.py
  api.py
examples/
  electron_app/
  nodejs_client.js
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

Tesseract OCR is optional but recommended for scanned PDFs.

## Run by Flow

### CLI - importation

```bash
python src/pipeline.py \
  --input data/input/importation \
  --output data/output \
  --flow importation \
  --json
```

### CLI - exportation

```bash
python src/pipeline.py \
  --input data/input/exportation \
  --output data/output \
  --flow exportation \
  --json
```

`--input` supports these layouts:
- `<input>/<flow>/raw`
- `<input>/raw`
- `<input>` directly containing PDFs

### Electron UI - importation

```bash
cd examples/electron_app
npm install
npm start
```

In UI:
1. Set `Modo = Importation`
2. Select PDFs
3. Set document types (`BL`, `HBL`, `INVOICE`, `PACKING LIST`, `DI`, `LI`)
4. Select Stage 02 engine (`Regex` or `LLM (Codex)`)
5. Click `Run`

### Electron UI - exportation

Use the same app, changing only mode and document types:
1. Set `Modo = Exportation`
2. Select PDFs
3. Set document types (`COMMERCIAL INVOICE`, `PACKING LIST`, `DRAFT BL`, `CERTIFICATE OF ORIGIN`, `CONTAINER DATA`)
4. Select Stage 02 engine (`Regex` or `LLM (Codex)`)
5. Click `Run`

### Smoke scripts

```bash
npm --prefix examples/electron_app run smoke
npm --prefix examples/electron_app run smoke:exportation
```

## Programmatic

```python
from pathlib import Path
from pipeline import PipelineConfig, run_pipeline

config = PipelineConfig(
    input_dir=Path("data/input/exportation"),
    output_dir=Path("data/output"),
    flow="exportation",
    ocr_lang="eng+por",
    ocr_dpi=300,
)

result = run_pipeline(config)
print(result.success, result.output_files.get("stage_04_html"))
```

## API

Start server:

```bash
python src/api.py --host 127.0.0.1 --port 5000
```

Full pipeline endpoint:

```http
POST /api/v1/process
Content-Type: application/json

{
  "input_dir": "/path/to/input",
  "output_dir": "/path/to/output",
  "flow": "importation | exportation",
  "ocr_lang": "eng+por",
  "ocr_dpi": 300,
  "min_chars": 80
}
```

Single-stage endpoints:

```http
POST /api/v1/process/stage/1
POST /api/v1/process/stage/2
POST /api/v1/process/stage/3
POST /api/v1/process/stage/4
```

For single-stage calls, include `flow` in JSON body when using exportation (`importation` is default).

Health:

```http
GET /health
```

## Stage 02 LLM Environment Variables

Core selection:
- `DOCREADER_STAGE2_ENGINE`
  - `regex` (default)
  - `llm`

LLM execution:
- `DOCREADER_CODEX_CLI_PATH`
  - Codex CLI command/path (default: `codex`)
- `DOCREADER_STAGE2_LLM_MODEL`
  - Optional model override passed to `codex exec -m`
- `DOCREADER_STAGE2_LLM_TIMEOUT_SEC`
  - Timeout in seconds (default: `240`)
- `DOCREADER_STAGE2_LLM_DETAILED_LOG`
  - `1` to emit detailed Stage 02 LLM logs (`[Stage02-LLM]` / `[Stage02-LLM-EXPORT]`)

Fallback policy:
- `DOCREADER_STAGE2_LLM_FALLBACK_REGEX`
  - `0` (recommended): fail-fast if LLM fails
  - `1`: fallback to regex extractor

Auth context (typically injected by Electron main process):
- `DOCREADER_CODEX_AUTH_CONTEXT_FILE`
- `DOCREADER_CODEX_ACCESS_TOKEN`
- `DOCREADER_CODEX_TOKEN_TYPE`
- `DOCREADER_CODEX_EXPIRES_AT`
- `DOCREADER_CODEX_SUB`

## Stage CLI Scripts

Importation:
- `src/stage_01_text_extract/extract_text_importation.py`
- `src/stage_02_field_extract/importation/extract_fields_importation.py`
- `src/stage_03_compare_docs/compare_importation.py`
- `src/stage_04_report/generate_report_importation.py`

Exportation:
- `src/stage_01_text_extract/extract_text_exportation.py`
- `src/stage_02_field_extract/exportation/extract_fields_exportation.py`
- `src/stage_03_compare_docs/compare_exportation.py`
- `src/stage_04_report/generate_report_exportation.py`

## Output Files

Both flows generate the same output naming convention:
- Stage 01: `*_extracted.txt`, `*_extracted.json`
- Stage 02: `*_fields.json`, `_stage02_summary.json`
- Stage 03: `_stage03_comparison.json`
- Stage 04: `_stage04_report.json`, `_stage04_report.html`, `_stage04_report.md`

Both flows:
- Stage 05: `_stage05_debug_report.json`, `_stage05_debug_report.html`, `_stage05_debug_report.md`

## Troubleshooting

### Pipeline appears stuck in Stage 02 LLM

1. Check UI logs for progress markers:
   - `[Stage02-LLM]`
   - `[Stage02-LLM-EXPORT]`
2. Open the run debug log path shown by Electron (`RUN LOG: ...pipeline_debug.log`)
3. Re-run with detailed logs:
   - `DOCREADER_STAGE2_LLM_DETAILED_LOG=1`

### "Codex auth obrigatoria para Stage 02 LLM"

Cause:
- Stage 02 engine is `llm`, but Codex auth is not connected.

Fix:
1. Connect Codex in UI
2. Re-run pipeline
3. If running CLI/API directly, provide valid Codex session/token context

### "Codex CLI indisponivel" or command not found

Cause:
- `codex` is not installed or not reachable from process PATH.

Fix:
1. Verify command:
   - `codex --version`
2. If needed, set:
   - `DOCREADER_CODEX_CLI_PATH=<full path to codex>`

### Stage 02 LLM timeout

Symptom:
- Error contains `timeout` or `Codex CLI timeout after ...s`.

Fix:
1. Increase timeout:
   - `DOCREADER_STAGE2_LLM_TIMEOUT_SEC=360`
2. Re-run and inspect run log for slow documents/prompts

### Exportation document classified with wrong kind in raw CLI runs

Symptom:
- Stage 02 output kind does not match expected document type.

Cause:
- CLI run without `_doc_type_hints.json` relies on filename/content heuristics.

Fix:
1. Prefer Electron/UI flow (it writes `_doc_type_hints.json`)
2. Use clear filenames aligned with expected doc type
3. Validate `*_fields.json` before Stage 03 analysis

### Stage 04 report not generated

1. Ensure Stage 01 and Stage 02 produced expected outputs
2. Check `_stage03_comparison.json` exists
3. Re-run pipeline with `--json` and inspect `errors` and `warnings`

## Document Types

Importation:
- Invoice
- Packing List
- BL / HBL
- DI
- LI

Exportation:
- Commercial Invoice
- Packing List
- Draft BL
- Certificate of Origin
- Container Data

## License

MIT
