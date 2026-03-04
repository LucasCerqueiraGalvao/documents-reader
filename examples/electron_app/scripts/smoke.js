#!/usr/bin/env node

/**
 * Headless smoke test for the pipeline runner.
 *
 * It does NOT launch Electron.
 * It verifies:
 * - `.venv/bin/python` exists in repo root
 * - synthetic PDFs are generated for the selected flow
 * - pipeline runs successfully and generates Stage 4 HTML
 */

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

function repoRoot() {
  // examples/electron_app/scripts -> repo root
  return path.resolve(__dirname, '..', '..', '..');
}

function detectVenvPython(root) {
  const candidates = [
    path.join(root, '.venv', 'bin', 'python'),
    path.join(root, '.venv', 'bin', 'python3'),
    path.join(root, '.venv', 'Scripts', 'python.exe'),
    'python',
  ];
  for (const candidate of candidates) {
    if (candidate !== 'python' && !fs.existsSync(candidate)) continue;
    const probe = spawnSync(candidate, ['--version'], {
      cwd: root,
      encoding: 'utf8',
      windowsHide: true,
    });
    if (!probe.error && probe.status === 0) return candidate;
  }
  return null;
}

async function ensureDir(p) {
  await fsp.mkdir(p, { recursive: true });
}

function runId() {
  return new Date().toISOString().replaceAll(':', '-').replaceAll('.', '-');
}

function normalizeFlow(value) {
  return String(value || '').trim().toLowerCase() === 'exportation' ? 'exportation' : 'importation';
}

function generateSyntheticPdfs(python, root, flow, rawDir) {
  const script = `
import os
from pathlib import Path
import fitz

flow = os.environ["DOCREADER_SMOKE_FLOW"].strip().lower()
dest = Path(os.environ["DOCREADER_SMOKE_RAW"])
dest.mkdir(parents=True, exist_ok=True)

docs_importation = {
    "BL.pdf": "\\n".join([
        "BILL OF LADING",
        "MASTER BL: TESTMBL001",
        "HOUSE BL: TESTHBL001",
        "SHIPPER: TEST SHIPPER LTD",
        "CONSIGNEE: TEST CONSIGNEE LTD",
        "PORT OF LOADING: SANTOS",
        "PORT OF DISCHARGE: NAVEGANTES",
        "VESSEL: TEST VESSEL",
        "VOYAGE: 001A",
        "CONTAINER: TEMU1680211",
        "SEAL: M1024218",
    ]),
    "INVOICE.pdf": "\\n".join([
        "COMMERCIAL INVOICE",
        "INVOICE NO: INV-TEST-001",
        "CNPJ: 03.562.381/0006-03",
        "INCOTERM: CFR",
        "NCM: 8703.21.00",
        "QTY: 12",
        "NET WEIGHT: 7980,000",
        "GROSS WEIGHT: 9825,000",
        "TOTAL: 12345,67",
    ]),
    "PACKING LIST.pdf": "\\n".join([
        "PACKING LIST",
        "INVOICE NO: INV-TEST-001",
        "QTY: 12",
        "PACKAGES: 12",
        "NET WEIGHT: 7980,000",
        "GROSS WEIGHT: 9825,000",
        "VOLUME: 53,772",
    ]),
}

docs_exportation = {
    "COMMERCIAL INVOICE TEST.pdf": "\\n".join([
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
    ]),
    "PACKING LIST TEST.pdf": "\\n".join([
        "PACKING LIST NR I-0007/25",
        "15/02/2026",
        "PESO BRUTO 9825,000",
        "PESO NETO 7980,000",
        "NCM 8703.21.00",
        "INCOTERMS CFR",
        "CNTR 1",
        "TEMU1680211 M1024218 76,98",
    ]),
    "DRAFT BL TEST.pdf": "\\n".join([
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
    ]),
}

docs = docs_exportation if flow == "exportation" else docs_importation
for filename, text in docs.items():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(dest / filename))
    doc.close()
`;

  const res = spawnSync(python, ['-c', script], {
    cwd: root,
    encoding: 'utf8',
    windowsHide: true,
    env: {
      ...process.env,
      DOCREADER_SMOKE_FLOW: flow,
      DOCREADER_SMOKE_RAW: rawDir,
    },
  });

  if (res.error || res.status !== 0) {
    const errText = String(res.stderr || res.stdout || res.error || '').trim();
    throw new Error(`Failed to generate synthetic smoke PDFs: ${errText || `exit ${res.status}`}`);
  }
}

async function main() {
  const flow = normalizeFlow(process.argv[2] || 'importation');
  const root = repoRoot();
  const python = detectVenvPython(root);
  if (!python) {
    console.error('ERROR: venv python not found at .venv. Create venv and install requirements.');
    process.exit(2);
  }

  const runBase = path.join(root, '.electron_runs_smoke', runId());
  const inputBase = path.join(runBase, 'input');
  const outputBase = path.join(runBase, 'output');
  const rawDir = path.join(inputBase, flow, 'raw');

  await ensureDir(rawDir);
  await ensureDir(outputBase);
  generateSyntheticPdfs(python, root, flow, rawDir);

  const args = [
    path.join(root, 'src', 'pipeline.py'),
    '--input',
    inputBase,
    '--output',
    outputBase,
    '--flow',
    flow,
    '--json',
  ];

  console.log(`Flow: ${flow}`);
  console.log('Running:', python, args.join(' '));

  const child = spawn(python, args, { cwd: root, env: { ...process.env } });

  let stdout = '';
  let stderr = '';

  child.stdout.on('data', (c) => {
    const t = c.toString();
    stdout += t;
    process.stdout.write(t);
  });
  child.stderr.on('data', (c) => {
    const t = c.toString();
    stderr += t;
    process.stderr.write(t);
  });

  const code = await new Promise((resolve) => child.on('close', resolve));

  const reportPath = path.join(
    outputBase,
    'stage_04_report',
    flow,
    '_stage04_report.html'
  );
  const debugReportPath = path.join(
    outputBase,
    'stage_05_debug_report',
    flow,
    '_stage05_debug_report.html'
  );

  if (code !== 0) {
    console.error(`ERROR: pipeline exited with code ${code}`);
    process.exit(10);
  }

  if (!fs.existsSync(reportPath)) {
    console.error('ERROR: Stage 4 HTML not found:', reportPath);
    console.error('STDERR:', stderr || '(empty)');
    console.error('STDOUT tail:', stdout.slice(-1500));
    process.exit(11);
  }

  if (!fs.existsSync(debugReportPath)) {
    console.error('ERROR: Stage 5 HTML not found:', debugReportPath);
    console.error('STDERR:', stderr || '(empty)');
    console.error('STDOUT tail:', stdout.slice(-1500));
    process.exit(12);
  }

  console.log('\nOK: Stage 4 HTML generated at:', reportPath);
  console.log('OK: Stage 5 HTML generated at:', debugReportPath);
}

main().catch((e) => {
  console.error('FATAL:', e);
  process.exit(1);
});
