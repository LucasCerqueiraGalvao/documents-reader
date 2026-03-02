from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from stage_02_field_extract.exportation.stage_02_llm import (  # noqa: E402
    FIELD_META_KEYS,
    TOP_LEVEL_KEYS,
    build_fields_template,
    run_stage02_llm_for_exportation,
)


class Stage02ExportLLMContractTest(unittest.TestCase):
    def _mock_llm(self, prompt: str, _cwd: Path) -> str:
        self.assertIn("TEMPLATE_STAGE02_JSON", prompt)
        self.assertIn("STAGE01_JSON", prompt)

        fields = build_fields_template("commercial_invoice")
        for field_name, meta in fields.items():
            if meta["required"]:
                meta["present"] = True
                meta["value"] = f"mock_{field_name}"
                meta["evidence"] = [f"evidence_{field_name}"]
                meta["method"] = "llm_manual"

        payload = {
            "source": {
                "stage01_file": "COMMERCIAL_INVOICE_extracted.json",
                "original_file": "COMMERCIAL INVOICE.pdf",
                "doc_kind": "commercial_invoice",
                "doc_kind_hint": "commercial_invoice",
            },
            "generated_at": "2026-01-01T00:00:00",
            "fields": fields,
            "missing_required_fields": [],
            "warnings": [],
        }
        return json.dumps(payload)

    def test_stage02_export_llm_output_keeps_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            in_dir = root / "stage_01"
            out_dir = root / "stage_02"
            in_dir.mkdir(parents=True, exist_ok=True)
            out_dir.mkdir(parents=True, exist_ok=True)

            stage01_input = {
                "file": "COMMERCIAL INVOICE.pdf",
                "doc_kind_hint": "commercial_invoice",
                "pages": [
                    {
                        "page": 1,
                        "text": "COMMERCIAL INVOICE\nINVOICE NR I-0007/25\nCNPJ 03.562.381/0006-03",
                    }
                ],
            }
            (in_dir / "COMMERCIAL_INVOICE_extracted.json").write_text(
                json.dumps(stage01_input, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            result = run_stage02_llm_for_exportation(
                in_dir=in_dir,
                out_dir=out_dir,
                verbose=False,
                llm_client=self._mock_llm,
            )
            self.assertEqual(result["processed_count"], 1)

            out_file = out_dir / "COMMERCIAL_INVOICE_fields.json"
            self.assertTrue(out_file.exists(), "Stage 02 export output file not created")

            out_obj = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(set(out_obj.keys()), set(TOP_LEVEL_KEYS))
            self.assertEqual(out_obj["source"]["doc_kind"], "commercial_invoice")
            self.assertEqual(out_obj["source"]["stage01_file"], "COMMERCIAL_INVOICE_extracted.json")

            expected_fields = build_fields_template("commercial_invoice")
            self.assertEqual(set(out_obj["fields"].keys()), set(expected_fields.keys()))
            for field_name, field_obj in out_obj["fields"].items():
                self.assertEqual(set(field_obj.keys()), set(FIELD_META_KEYS), field_name)

            self.assertEqual(out_obj["missing_required_fields"], [])
            self.assertEqual(out_obj["warnings"], [])
            self.assertTrue((out_dir / "_stage02_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
