# -*- coding: utf-8 -*-
"""
Stage 01 - EXPORTATION - Text extraction wrapper.

For parity between flows, this module reuses the same extraction core used by
importation (direct text + OCR fallback), while exposing an exportation entrypoint.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

try:
    from .extract_text_importation import run_stage_01_extraction as _run_stage_01_extraction
except ImportError:  # pragma: no cover
    from extract_text_importation import run_stage_01_extraction as _run_stage_01_extraction


def run_stage_01_extraction(
    in_dir: Path,
    out_dir: Path,
    ocr_lang: str = "eng+por",
    ocr_dpi: int = 300,
    min_chars: int = 80,
    verbose: bool = True,
) -> Dict[str, Any]:
    return _run_stage_01_extraction(
        in_dir=in_dir,
        out_dir=out_dir,
        ocr_lang=ocr_lang,
        ocr_dpi=ocr_dpi,
        min_chars=min_chars,
        verbose=verbose,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 01 - Exportation - Extract text from PDFs (direct + OCR fallback)."
    )
    parser.add_argument("--in", dest="in_dir", help="Input folder with PDFs")
    parser.add_argument("--out", dest="out_dir", help="Output folder for txt/json")
    parser.add_argument("--input", dest="in_dir_alt", help="Alias of --in")
    parser.add_argument("--output", dest="out_dir_alt", help="Alias of --out")
    parser.add_argument("--lang", default="eng+por", help="OCR language(s)")
    parser.add_argument("--dpi", type=int, default=300, help="OCR DPI")
    parser.add_argument("--min-chars", type=int, default=80, help="Minimum chars for direct text")

    args = parser.parse_args()
    in_dir = args.in_dir or args.in_dir_alt
    out_dir = args.out_dir or args.out_dir_alt
    if not in_dir or not out_dir:
        raise SystemExit("Both --in/--input and --out/--output are required.")

    run_stage_01_extraction(
        in_dir=Path(in_dir),
        out_dir=Path(out_dir),
        ocr_lang=args.lang,
        ocr_dpi=args.dpi,
        min_chars=args.min_chars,
        verbose=True,
    )


if __name__ == "__main__":
    main()
