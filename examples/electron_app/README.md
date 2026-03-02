# Documents Reader - Electron App

Desktop UI (Electron) on top of the Python pipeline.

## Prerequisites

- Node.js + npm
- Python environment in repository root (`.venv`) with dependencies installed
- Optional: Tesseract for scanned PDFs

## Run (development)

```bash
cd examples/electron_app
npm install
npm start
```

In development mode, Electron runs `src/pipeline.py` from the repository.

## Flow operation in UI

The app supports two modes in the `Modo` selector:

- `Importation`
- `Exportation`

Per run:
1. Select mode
2. Add PDFs
3. Confirm document type for each file
4. Select Stage 02 engine (`Regex` or `LLM (Codex)`)
5. Click `Run`

Mode-specific document types:

- Importation:
  - `BL`, `HBL`, `INVOICE`, `PACKING LIST`, `DI`, `LI`
- Exportation:
  - `COMMERCIAL INVOICE`, `PACKING LIST`, `DRAFT BL`, `CERTIFICATE OF ORIGIN`, `CONTAINER DATA`

## Smoke tests (without opening UI)

```bash
cd examples/electron_app
npm run smoke
npm run smoke:exportation
```

Additional logic test for renderer flow/type/payload behavior:

```bash
cd examples/electron_app
npm run test:renderer-flow
```

## Build overview

The packaged app can run with embedded pipeline binary (`docreader-runner`) and optional embedded Tesseract.

Useful scripts:

```bash
cd examples/electron_app
npm run build:python
npm run smoke:python
npm run fetch:tesseract
npm run smoke:tesseract
```

Packaging:

```bash
npm run dist:win
npm run dist:mac
npm run dist:linux
```

## Stage 02 LLM in Electron

When `LLM (Codex)` is selected:

- Codex auth must be connected
- Preflight checks Codex CLI availability
- No automatic fallback to regex by default (`DOCREADER_STAGE2_LLM_FALLBACK_REGEX=0`)

Useful environment variables:

- `DOCREADER_STAGE2_ENGINE`
- `DOCREADER_STAGE2_LLM_TIMEOUT_SEC`
- `DOCREADER_STAGE2_LLM_MODEL`
- `DOCREADER_STAGE2_LLM_DETAILED_LOG`
- `DOCREADER_STAGE2_LLM_FALLBACK_REGEX`
- `DOCREADER_CODEX_CLI_PATH`

## Troubleshooting

### LLM blocked: auth required

Symptom:
- Run fails with message that Codex auth is required.

Fix:
1. Click `Conectar Codex`
2. Retry run

### Codex CLI unavailable

Symptom:
- Preflight error about Codex CLI unavailable.

Fix:
1. Check `codex --version`
2. Configure `DOCREADER_CODEX_CLI_PATH` if needed

### LLM timeout

Symptom:
- Error contains timeout information.

Fix:
1. Increase `DOCREADER_STAGE2_LLM_TIMEOUT_SEC`
2. Retry and inspect run log path shown in UI

### Stage 04 report not opened

Fix:
1. Check run log path shown in log pane
2. Confirm report exists at `.../output/stage_04_report/<flow>/_stage04_report.html`
