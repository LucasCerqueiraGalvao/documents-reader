const path = require('node:path');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

function platformFolder() {
  switch (process.platform) {
    case 'darwin':
      return 'mac';
    case 'win32':
      return 'win';
    default:
      return 'linux';
  }
}

async function ensureDir(p) {
  await fsp.mkdir(p, { recursive: true });
}

function detectPython(repoRoot) {
  const candidates = [
    path.join(repoRoot, '.venv', 'bin', 'python'),
    path.join(repoRoot, '.venv', 'bin', 'python3'),
    path.join(repoRoot, '.venv', 'Scripts', 'python.exe'),
    'python',
  ];

  for (const candidate of candidates) {
    if (candidate !== 'python' && !fs.existsSync(candidate)) continue;
    const probe = spawnSync(candidate, ['--version'], {
      cwd: repoRoot,
      encoding: 'utf8',
      windowsHide: true,
    });
    if (!probe.error && probe.status === 0) {
      return candidate;
    }
  }
  return null;
}

function generateSyntheticImportationPdfs(python, repoRoot, destRaw) {
  const script = `
import os
from pathlib import Path
import fitz

dest = Path(os.environ["DOCREADER_SMOKE_RAW"])
dest.mkdir(parents=True, exist_ok=True)

docs = {
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

for filename, text in docs.items():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(dest / filename))
    doc.close()
`;

  const res = spawnSync(python, ['-c', script], {
    cwd: repoRoot,
    encoding: 'utf8',
    windowsHide: true,
    env: {
      ...process.env,
      DOCREADER_SMOKE_RAW: destRaw,
    },
  });

  if (res.error || res.status !== 0) {
    const errText = String(res.stderr || res.stdout || res.error || '').trim();
    throw new Error(`Failed to generate synthetic smoke PDFs: ${errText || `exit ${res.status}`}`);
  }
}

async function main() {
  const appRoot = path.resolve(__dirname, '..');
  const repoRoot = path.resolve(appRoot, '..', '..');

  const folder = platformFolder();
  const exe = process.platform === 'win32' ? 'docreader-runner.exe' : 'docreader-runner';
  const runner = path.join(appRoot, 'resources', 'python', folder, exe);

  if (!fs.existsSync(runner)) {
    console.error(`ERROR: bundled runner not found: ${runner}`);
    console.error('Run: npm run build:python');
    process.exit(1);
  }

  const python = detectPython(repoRoot);
  if (!python) {
    console.error('ERROR: Python not found. Create .venv and install requirements.');
    process.exit(1);
  }

  const tmpBase = await fsp.mkdtemp(path.join(os.tmpdir(), 'docreader-smoke-runner-'));
  const inputBase = path.join(tmpBase, 'input');
  const outputBase = path.join(tmpBase, 'output');

  const destRaw = path.join(inputBase, 'importation', 'raw');

  await ensureDir(destRaw);
  await ensureDir(outputBase);
  generateSyntheticImportationPdfs(python, repoRoot, destRaw);

  const res = spawnSync(
    runner,
    ['--input', inputBase, '--output', outputBase, '--flow', 'importation', '--json'],
    { stdio: 'inherit' }
  );

  if (res.error) throw res.error;
  if (res.status !== 0) {
    console.error(`ERROR: runner exited with code ${res.status}`);
    process.exit(res.status);
  }

  const report = path.join(
    outputBase,
    'stage_04_report',
    'importation',
    '_stage04_report.html'
  );

  if (!fs.existsSync(report)) {
    console.error(`ERROR: Stage 4 HTML not found: ${report}`);
    process.exit(1);
  }

  console.log(`\nOK: runner produced Stage 4 report: ${report}`);
}

main().catch((e) => {
  console.error(`ERROR: ${e?.stack || e}`);
  process.exit(1);
});
