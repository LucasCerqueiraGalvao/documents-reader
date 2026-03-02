from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import fitz


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pipeline import PipelineConfig, run_pipeline  # noqa: E402


def _write_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


class ExportationPipelineSmokeTest(unittest.TestCase):
    def test_exportation_pipeline_generates_all_stage_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_root = root / "data" / "input" / "exportation"
            raw_dir = input_root / "raw"
            output_root = root / "data" / "output"
            raw_dir.mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)

            _write_pdf(
                raw_dir / "COMMERCIAL INVOICE TEST.pdf",
                "\n".join(
                    [
                        "COMMERCIAL INVOICE",
                        "INVOICE NR I-0007/25",
                        "15/02/2026",
                        "PAIS DE ORIGEN BRASIL",
                        "VIA DE TRANSPORTE MARITIMO",
                        "PORT OF LOADING SANTOS",
                        "PORT OF DESTINATION KINGSTON",
                        "PESO BRUTO 9825,000",
                        "PESO NETO 7980,000",
                        "INCOTERMS CFR",
                        "CURRENCY USD",
                        "NCM 8703.21.00",
                        "CNTR 1",
                        "CNPJ 03.562.381/0006-03",
                        "EXPORTER HOME THINGS LTDA",
                        "CONSIGNEE CLIENTE TESTE SA",
                    ]
                ),
            )
            _write_pdf(
                raw_dir / "PACKING LIST TEST.pdf",
                "\n".join(
                    [
                        "PACKING LIST NR I-0007/25",
                        "15/02/2026",
                        "PESO BRUTO 9825,000",
                        "PESO NETO 7980,000",
                        "NCM 8703.21.00",
                        "INCOTERMS CFR",
                        "CNTR 1",
                        "TEMU1680211 M1024218 76,98",
                    ]
                ),
            )
            _write_pdf(
                raw_dir / "DRAFT BL TEST.pdf",
                "\n".join(
                    [
                        "BILL OF LADING",
                        "FREIGHT PREPAID",
                        "INCOTERM CFR",
                        "NCM 8703.21.00",
                        "DUE 26BR0000001",
                        "RUC BR123456789",
                        "SSZ1234567",
                        "WOODEN PACKAGE: NO",
                        "12 CARTONS",
                        "Net Weight: 7980,000 kg",
                        "Gross Weight: 9825,000 kg",
                        "53,772 CBM",
                        "CNPJ 03.562.381/0006-03",
                        "SHIPPER HOME THINGS LTDA",
                        "CONSIGNEE CLIENTE TESTE SA",
                        "NOTIFY PARTY CLIENTE TESTE SA",
                        "TEMU1680211 M1024218 2100,000 30480",
                    ]
                ),
            )

            result = run_pipeline(
                PipelineConfig(
                    input_dir=input_root,
                    output_dir=output_root,
                    flow="exportation",
                    ocr_lang="eng+por",
                    ocr_dpi=300,
                    min_chars=10,
                )
            )
            self.assertTrue(result.success, msg=f"pipeline failed: {result.errors}")

            stage01_dir = output_root / "stage_01_text" / "exportation"
            stage02_dir = output_root / "stage_02_fields" / "exportation"
            stage03_file = output_root / "stage_03_compare" / "exportation" / "_stage03_comparison.json"
            stage04_dir = output_root / "stage_04_report" / "exportation"
            stage05_dir = output_root / "stage_05_debug_report" / "exportation"

            self.assertTrue(stage01_dir.exists())
            self.assertTrue(stage02_dir.exists())
            self.assertTrue(stage03_file.exists())
            self.assertTrue((stage04_dir / "_stage04_report.json").exists())
            self.assertTrue((stage04_dir / "_stage04_report.md").exists())
            self.assertTrue((stage04_dir / "_stage04_report.html").exists())
            self.assertTrue((stage05_dir / "_stage05_debug_report.json").exists())
            self.assertTrue((stage05_dir / "_stage05_debug_report.md").exists())
            self.assertTrue((stage05_dir / "_stage05_debug_report.html").exists())

            self.assertGreaterEqual(len(list(stage01_dir.glob("*_extracted.json"))), 3)
            self.assertGreaterEqual(len(list(stage01_dir.glob("*_extracted.txt"))), 3)
            self.assertGreaterEqual(len(list(stage02_dir.glob("*_fields.json"))), 3)
            self.assertTrue((stage02_dir / "_stage02_summary.json").exists())

            stage03_obj = json.loads(stage03_file.read_text(encoding="utf-8"))
            self.assertIn("summary", stage03_obj)
            self.assertIn("comparisons", stage03_obj)

            stage04_obj = json.loads((stage04_dir / "_stage04_report.json").read_text(encoding="utf-8"))
            self.assertEqual(stage04_obj.get("flow"), "exportation")
            self.assertIn("overall", stage04_obj)
            self.assertIn("stage03", stage04_obj)

            stage05_obj = json.loads((stage05_dir / "_stage05_debug_report.json").read_text(encoding="utf-8"))
            self.assertEqual(stage05_obj.get("flow"), "exportation")
            self.assertIn("stage02", stage05_obj)
            self.assertIn("stage03", stage05_obj)


if __name__ == "__main__":
    unittest.main()
