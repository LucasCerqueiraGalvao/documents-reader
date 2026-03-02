# Passo 1 - Baseline Report

## Scope

This report records the baseline requested in Step 1:
- current repository snapshot
- smoke checks for `importation` and `exportation`
- Stage 02 LLM contract tests for both flows
- rollback criteria (file sets to revert in a rollback commit if needed)

## Repository Snapshot

- Branch: `main`
- HEAD: `3ab60b1`
- Working tree: dirty (local changes present)

Changed files at snapshot time:

```text
M README.md
M src/api.py
M src/pipeline.py
M src/stage_01_text_extract/extract_text_exportation.py
M src/stage_01_text_extract/extract_text_importation.py
M src/stage_02_field_extract/exportation/extract_fields_exportation.py
?? EXPORTATION_IMPLEMENTATION_PLAN.md
?? src/stage_02_field_extract/exportation/stage_02_llm.py
?? src/stage_02_field_extract/exportation/test_stage_02_llm.py
?? src/stage_03_compare_docs/compare_exportation.py
?? src/stage_04_report/generate_report_exportation.py
?? src/test_pipeline_exportation_smoke.py
```

## Commands Executed and Results

## 1) Stage 02 LLM contract - importation

Command:

```powershell
python -m unittest src/stage_02_field_extract/importation/test_stage_02_llm.py -v
```

Result:
- PASS (`Ran 1 test`, `OK`)

## 2) Stage 02 LLM contract - exportation

Command:

```powershell
python -m unittest src/stage_02_field_extract/exportation/test_stage_02_llm.py -v
```

Result:
- PASS (`Ran 1 test`, `OK`)

## 3) Smoke - importation

Command:

```powershell
@'
from pathlib import Path
import tempfile
import sys
import json
sys.path.insert(0, str(Path('src').resolve()))
from pipeline import PipelineConfig, run_pipeline

input_dir = Path('data/input/importation')
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / 'out'
    out.mkdir(parents=True, exist_ok=True)
    res = run_pipeline(PipelineConfig(input_dir=input_dir, output_dir=out, flow='importation', min_chars=10))
    print(json.dumps({
        'success': res.success,
        'flow': res.flow,
        'stages_completed': res.stages_completed,
        'errors': res.errors,
        'warnings_count': len(res.warnings),
        'output_stage4_html_exists': (out / 'stage_04_report' / 'importation' / '_stage04_report.html').exists(),
        'output_stage5_html_exists': (out / 'stage_05_debug_report' / 'importation' / '_stage05_debug_report.html').exists(),
    }, ensure_ascii=False))
'@ | python -
```

Result:
- PASS
- `success=true`
- Stages completed:
  - `stage_01_text_extract`
  - `stage_02_field_extract`
  - `stage_03_compare`
  - `stage_04_report`
  - `stage_05_debug_report`
- Stage 04 HTML exists: true
- Stage 05 HTML exists: true

## 4) Smoke - exportation

Command:

```powershell
python -m unittest src/test_pipeline_exportation_smoke.py -v
```

Result:
- PASS (`Ran 1 test`, `OK`)
- Generated outputs confirmed by test:
  - Stage 01 folder/files
  - Stage 02 folder/files
  - Stage 03 comparison JSON
  - Stage 04 JSON/MD/HTML

## Baseline Verdict

- Importation baseline: stable in this snapshot.
- Exportation backend baseline (Stages 01-04): stable in this snapshot.
- Stage 02 LLM contract validation: stable for both flows.

## Rollback Criteria

If a future step breaks behavior, rollback should be done by creating a dedicated rollback commit reverting the affected file set.

Rollback set A (flow orchestration/API regressions):
- `src/pipeline.py`
- `src/api.py`
- `src/stage_01_text_extract/extract_text_importation.py`

Rollback set B (exportation backend regressions):
- `src/stage_01_text_extract/extract_text_exportation.py`
- `src/stage_02_field_extract/exportation/extract_fields_exportation.py`
- `src/stage_02_field_extract/exportation/stage_02_llm.py`
- `src/stage_02_field_extract/exportation/test_stage_02_llm.py`
- `src/stage_03_compare_docs/compare_exportation.py`
- `src/stage_04_report/generate_report_exportation.py`
- `src/test_pipeline_exportation_smoke.py`

Rollback set C (docs-only regressions):
- `README.md`
- `EXPORTATION_IMPLEMENTATION_PLAN.md`
- `STEP_01_BASELINE_REPORT.md`

## Notes

- This baseline does not claim Electron UI exportation parity yet; it validates backend + contracts only.
- Next steps should keep one-step-at-a-time execution and rerun smoke/contract checks after each step.
