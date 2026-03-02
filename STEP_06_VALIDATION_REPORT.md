# Passo 6 - Testes e Validacao de Regressao

## Escopo executado

Este passo cobriu:
- ajuste/adicao de testes automatizados (backend + Electron)
- execucao da matriz da secao 9 do plano
- validacao de outputs Stage 04 para ambos os flows

## Ajustes implementados para viabilizar os testes

### Electron smoke por flow

- `examples/electron_app/scripts/smoke.js`
  - agora aceita flow via argumento (`importation` ou `exportation`)
  - detecta Python funcional por probe (`--version`) antes de escolher binario
  - copia samples conforme o flow e valida Stage 04 em `output/stage_04_report/<flow>/...`

- `examples/electron_app/package.json`
  - novo script: `smoke:exportation`

### Teste de logica de UI (modo + tipos + payload)

- novo arquivo: `examples/electron_app/scripts/test-renderer-flow.js`
  - executa `renderer.js` em harness fake-DOM
  - valida troca de modo (`importation`/`exportation`)
  - valida legenda/tipos por modo
  - valida payload enviado ao `runPipeline`:
    - `flow` correto
    - `files[].docType` coerente com modo selecionado

- `examples/electron_app/package.json`
  - novo script: `test:renderer-flow`

## Matriz executada (secao 9)

### Backend (Python)

1. `python -m unittest src/stage_02_field_extract/importation/test_stage_02_llm.py -v`
   - PASS (`Ran 1 test`, `OK`)

2. `python -m unittest src/stage_02_field_extract/exportation/test_stage_02_llm.py -v`
   - PASS (`Ran 1 test`, `OK`)

3. `python -m unittest src/test_pipeline_exportation_smoke.py -v`
   - PASS (`Ran 1 test`, `OK`)

4. `python src/pipeline.py --input data/input/importation --output .tmp_step6/importation_cli --flow importation --json`
   - PASS (`success: true`)
   - stages: 01, 02, 03, 04, 05

5. `python src/pipeline.py --input data/input/exportation --output .tmp_step6/exportation_cli --flow exportation --json`
   - PASS (`success: true`)
   - stages: 01, 02, 03, 04

### Electron (Node)

1. `npm --prefix examples/electron_app run smoke`
   - PASS (importation)

2. `npm --prefix examples/electron_app run smoke:exportation`
   - PASS (exportation)

3. `npm --prefix examples/electron_app run test:renderer-flow`
   - PASS

## Validacao Stage 04/05 (artefatos)

Checagens de existencia:

- `.tmp_step6/importation_cli/stage_04_report/importation/_stage04_report.html` => `True`
- `.tmp_step6/importation_cli/stage_05_debug_report/importation/_stage05_debug_report.html` => `True`
- `.tmp_step6/exportation_cli/stage_04_report/exportation/_stage04_report.html` => `True`

## Checklist manual minimo (status neste ambiente)

1. UI `importation` + Stage 02 `regex`
   - Coberto indiretamente por `npm run smoke` + `test:renderer-flow` (sem abrir janela)

2. UI `importation` + Stage 02 `llm`
   - Nao executado manualmente (sem sessao interativa de UI + auth Codex neste ambiente headless)

3. UI `exportation` + Stage 02 `regex`
   - Coberto indiretamente por `npm run smoke:exportation` + `test:renderer-flow`

4. UI `exportation` + Stage 02 `llm`
   - Nao executado manualmente (mesma limitacao acima)

## Observacoes tecnicas

- Na execucao CLI direta de exportation (sem `_doc_type_hints.json` vindo da UI), houve classificacao de `COMMERCIAL INVOICE I-000725` como `draft_bl` no Stage 02 regex.
- O pipeline ainda concluiu com `success=true` e gerou Stage 04, mas isso indica risco de classificacao automatica por conteudo/nome em runs sem hints.
