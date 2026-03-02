"""
Pipeline orchestrator for document processing.
Provides both programmatic API and CLI interfaces.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


Stage01Runner = Callable[..., Dict[str, Any]]
Stage02Runner = Callable[..., Dict[str, Any]]
Stage03Runner = Callable[..., Dict[str, Any]]
Stage04Runner = Callable[..., Dict[str, Any]]
Stage05Runner = Callable[..., Dict[str, Any]]

SUPPORTED_FLOWS = {"importation", "exportation"}


@dataclass
class PipelineConfig:
    input_dir: Path
    output_dir: Path
    flow: str = "importation"
    ocr_lang: str = "eng+por"
    ocr_dpi: int = 300
    min_chars: int = 80


@dataclass
class PipelineResult:
    success: bool
    flow: str
    stages_completed: List[str]
    output_files: Dict[str, str]
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]
    completed_at: str


@dataclass(frozen=True)
class FlowRegistry:
    stage_01: Stage01Runner
    stage_02: Stage02Runner
    stage_03: Stage03Runner
    stage_04: Stage04Runner
    stage_05: Optional[Stage05Runner] = None


def normalize_flow(flow: str) -> str:
    value = str(flow or "").strip().lower()
    if value not in SUPPORTED_FLOWS:
        allowed = ", ".join(sorted(SUPPORTED_FLOWS))
        raise ValueError(f"Invalid flow '{flow}'. Allowed values: {allowed}")
    return value


def get_flow_registry(flow: str) -> FlowRegistry:
    selected_flow = normalize_flow(flow)

    if selected_flow == "importation":
        from stage_01_text_extract.extract_text_importation import run_stage_01_extraction
        from stage_02_field_extract.importation.extract_fields_importation import (
            run_stage_02_extraction,
        )
        from stage_03_compare_docs.compare_importation import run_stage_03_comparison
        from stage_04_report.generate_report_importation import run_stage_04_report
        from stage_05_debug_report.generate_debug_report_importation import (
            run_stage_05_debug_report,
        )

        return FlowRegistry(
            stage_01=run_stage_01_extraction,
            stage_02=run_stage_02_extraction,
            stage_03=run_stage_03_comparison,
            stage_04=run_stage_04_report,
            stage_05=run_stage_05_debug_report,
        )

    from stage_01_text_extract.extract_text_exportation import run_stage_01_extraction
    from stage_02_field_extract.exportation.extract_fields_exportation import (
        run_stage_02_extraction,
    )
    from stage_03_compare_docs.compare_exportation import run_stage_03_comparison
    from stage_04_report.generate_report_exportation import run_stage_04_report
    from stage_05_debug_report.generate_debug_report_exportation import (
        run_stage_05_debug_report,
    )

    return FlowRegistry(
        stage_01=run_stage_01_extraction,
        stage_02=run_stage_02_extraction,
        stage_03=run_stage_03_comparison,
        stage_04=run_stage_04_report,
        stage_05=run_stage_05_debug_report,
    )


def resolve_stage01_input_dir(input_dir: Path, flow: str) -> Path:
    """
    Accept common input layouts:
    - <input>/<flow>/raw
    - <input>/raw
    - <input> (already the raw folder with PDFs)
    """
    candidates = [
        input_dir / flow / "raw",
        input_dir / "raw",
        input_dir,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir() and any(candidate.glob("*.pdf")):
            return candidate

    expected = " OR ".join(str(p) for p in candidates[:2])
    raise FileNotFoundError(
        f"Could not locate raw PDF folder for flow='{flow}'. "
        f"Checked: {expected} (or direct PDFs in {input_dir})."
    )


def _require_params(params: Dict[str, Any], required: List[str]) -> None:
    for key in required:
        if key not in params:
            raise ValueError(f"Missing required parameter: {key}")


def run_single_stage_from_dict(stage_num: int, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a single stage with flow-aware routing.
    Used by the HTTP API /api/v1/process/stage/<n>.
    """
    flow = normalize_flow(params.get("flow", "importation"))
    registry = get_flow_registry(flow)

    if int(stage_num) == 1:
        _require_params(params, ["in_dir", "out_dir"])
        return registry.stage_01(
            in_dir=Path(params["in_dir"]),
            out_dir=Path(params["out_dir"]),
            ocr_lang=params.get("ocr_lang", "eng+por"),
            ocr_dpi=params.get("ocr_dpi", 300),
            min_chars=params.get("min_chars", 80),
            verbose=False,
        )

    if int(stage_num) == 2:
        _require_params(params, ["in_dir", "out_dir"])
        return registry.stage_02(
            in_dir=Path(params["in_dir"]),
            out_dir=Path(params["out_dir"]),
            verbose=False,
            engine=params.get("engine"),
        )

    if int(stage_num) == 3:
        _require_params(params, ["in_dir", "out_dir"])
        return registry.stage_03(
            in_dir=Path(params["in_dir"]),
            out_dir=Path(params["out_dir"]),
            verbose=False,
        )

    if int(stage_num) == 4:
        _require_params(params, ["stage01_dir", "stage02_dir", "stage03_file", "out_dir"])
        return registry.stage_04(
            stage01_dir=Path(params["stage01_dir"]),
            stage02_dir=Path(params["stage02_dir"]),
            stage03_file=Path(params["stage03_file"]),
            out_dir=Path(params["out_dir"]),
            verbose=False,
        )

    if int(stage_num) == 5:
        if registry.stage_05 is None:
            raise ValueError(f"Stage 05 is not available for flow '{flow}'.")
        _require_params(params, ["stage02_dir", "stage03_file", "out_dir"])
        return registry.stage_05(
            stage02_dir=Path(params["stage02_dir"]),
            stage03_file=Path(params["stage03_file"]),
            out_dir=Path(params["out_dir"]),
            verbose=False,
        )

    raise ValueError(f"Invalid stage number: {stage_num}")


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """
    Execute full document processing pipeline.
    """
    flow = normalize_flow(config.flow)
    registry = get_flow_registry(flow)

    errors: List[str] = []
    warnings: List[str] = []
    stages_completed: List[str] = []
    output_files: Dict[str, str] = {}

    try:
        stage01_in = resolve_stage01_input_dir(config.input_dir, flow)

        stage01_out = config.output_dir / "stage_01_text" / flow
        result_01 = registry.stage_01(
            in_dir=stage01_in,
            out_dir=stage01_out,
            ocr_lang=config.ocr_lang,
            ocr_dpi=config.ocr_dpi,
            min_chars=config.min_chars,
        )
        stages_completed.append("stage_01_text_extract")
        output_files["stage_01"] = str(stage01_out)
        warnings.extend(result_01.get("warnings", []))

        stage02_out = config.output_dir / "stage_02_fields" / flow
        result_02 = registry.stage_02(in_dir=stage01_out, out_dir=stage02_out)
        stages_completed.append("stage_02_field_extract")
        output_files["stage_02"] = str(stage02_out)
        warnings.extend(result_02.get("warnings", []))

        stage03_out = config.output_dir / "stage_03_compare" / flow
        result_03 = registry.stage_03(in_dir=stage02_out, out_dir=stage03_out)
        stages_completed.append("stage_03_compare")
        output_files["stage_03"] = str(stage03_out / "_stage03_comparison.json")
        warnings.extend(result_03.get("warnings", []))

        stage04_out = config.output_dir / "stage_04_report" / flow
        registry.stage_04(
            stage01_dir=stage01_out,
            stage02_dir=stage02_out,
            stage03_file=stage03_out / "_stage03_comparison.json",
            out_dir=stage04_out,
        )
        stages_completed.append("stage_04_report")
        output_files["stage_04_json"] = str(stage04_out / "_stage04_report.json")
        output_files["stage_04_html"] = str(stage04_out / "_stage04_report.html")
        output_files["stage_04_md"] = str(stage04_out / "_stage04_report.md")

        if registry.stage_05 is not None:
            try:
                stage05_out = config.output_dir / "stage_05_debug_report" / flow
                result_05 = registry.stage_05(
                    stage02_dir=stage02_out,
                    stage03_file=stage03_out / "_stage03_comparison.json",
                    out_dir=stage05_out,
                )
                stages_completed.append("stage_05_debug_report")
                output_files["stage_05_json"] = str(stage05_out / "_stage05_debug_report.json")
                output_files["stage_05_html"] = str(stage05_out / "_stage05_debug_report.html")
                output_files["stage_05_md"] = str(stage05_out / "_stage05_debug_report.md")
                warnings.extend(result_05.get("warnings", []))
            except Exception as stage05_error:
                warnings.append(f"stage_05_debug_report_failed: {stage05_error}")

        return PipelineResult(
            success=True,
            flow=flow,
            stages_completed=stages_completed,
            output_files=output_files,
            errors=errors,
            warnings=warnings,
            metadata={
                "documents_processed": result_01.get("processed_count", 0),
                "ocr_lang": config.ocr_lang,
                "ocr_dpi": config.ocr_dpi,
                "stage01_input_dir": str(stage01_in),
            },
            completed_at=datetime.now().isoformat(),
        )
    except Exception as exc:
        errors.append(str(exc))
        return PipelineResult(
            success=False,
            flow=flow,
            stages_completed=stages_completed,
            output_files=output_files,
            errors=errors,
            warnings=warnings,
            metadata={},
            completed_at=datetime.now().isoformat(),
        )


def run_pipeline_from_dict(params: Dict[str, Any]) -> Dict[str, Any]:
    config = PipelineConfig(
        input_dir=Path(params["input_dir"]),
        output_dir=Path(params["output_dir"]),
        flow=normalize_flow(params.get("flow", "importation")),
        ocr_lang=params.get("ocr_lang", "eng+por"),
        ocr_dpi=params.get("ocr_dpi", 300),
        min_chars=params.get("min_chars", 80),
    )
    result = run_pipeline(config)
    return asdict(result)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Document Processing Pipeline")
    parser.add_argument("--input", required=True, help="Input directory with raw PDFs")
    parser.add_argument("--output", required=True, help="Output directory for all stages")
    parser.add_argument("--flow", default="importation", choices=["importation", "exportation"])
    parser.add_argument("--ocr-lang", default="eng+por", help="OCR language(s)")
    parser.add_argument("--ocr-dpi", type=int, default=300, help="OCR DPI")
    parser.add_argument("--min-chars", type=int, default=80, help="Minimum chars for direct text")
    parser.add_argument("--json", action="store_true", help="Output JSON result")

    args = parser.parse_args()
    config = PipelineConfig(
        input_dir=Path(args.input),
        output_dir=Path(args.output),
        flow=args.flow,
        ocr_lang=args.ocr_lang,
        ocr_dpi=args.ocr_dpi,
        min_chars=args.min_chars,
    )
    result = run_pipeline(config)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        if result.success:
            print("OK Pipeline completed successfully")
            print(f"  Flow: {result.flow}")
            print(f"  Stages: {', '.join(result.stages_completed)}")
            print(f"  Report: {result.output_files.get('stage_04_html', 'N/A')}")
            if result.warnings:
                print(f"  Warnings: {len(result.warnings)}")
        else:
            print("ERROR Pipeline failed")
            for err in result.errors:
                print(f"  Error: {err}")
