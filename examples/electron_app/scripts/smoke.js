#!/usr/bin/env node

/**
 * Headless smoke test for the pipeline runner.
 *
 * It does NOT launch Electron.
 * It verifies:
 * - `.venv/bin/python` exists in repo root
 * - sample PDFs exist in `data/input/<flow>/raw`
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

async function copyFile(src, dst) {
  await ensureDir(path.dirname(dst));
  await fsp.copyFile(src, dst);
}

function runId() {
  return new Date().toISOString().replaceAll(':', '-').replaceAll('.', '-');
}

function normalizeFlow(value) {
  return String(value || '').trim().toLowerCase() === 'exportation' ? 'exportation' : 'importation';
}

function getImportationSamples() {
  return ['BL.pdf', 'INVOICE.pdf', 'PACKING LIST.pdf'];
}

async function getExportationSamples(rawDir) {
  const entries = await fsp.readdir(rawDir, { withFileTypes: true });
  const pdfs = entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((name) => name.toLowerCase().endsWith('.pdf'))
    .sort();

  if (pdfs.length < 3) {
    throw new Error(`Expected at least 3 sample PDFs in ${rawDir}, found ${pdfs.length}.`);
  }
  return pdfs;
}

async function main() {
  const flow = normalizeFlow(process.argv[2] || 'importation');
  const root = repoRoot();
  const python = detectVenvPython(root);
  if (!python) {
    console.error('ERROR: venv python not found at .venv. Create venv and install requirements.');
    process.exit(2);
  }

  const sampleRaw = path.join(root, 'data', 'input', flow, 'raw');
  if (!fs.existsSync(sampleRaw)) {
    console.error(`ERROR: sample raw folder not found: ${sampleRaw}`);
    process.exit(3);
  }
  const sampleFiles =
    flow === 'importation' ? getImportationSamples() : await getExportationSamples(sampleRaw);
  for (const f of sampleFiles) {
    const p = path.join(sampleRaw, f);
    if (!fs.existsSync(p)) {
      console.error(`ERROR: missing sample input: ${p}`);
      process.exit(4);
    }
  }

  const runBase = path.join(root, '.electron_runs_smoke', runId());
  const inputBase = path.join(runBase, 'input');
  const outputBase = path.join(runBase, 'output');
  const rawDir = path.join(inputBase, flow, 'raw');

  await ensureDir(rawDir);
  await ensureDir(outputBase);

  // Copy samples
  for (const name of sampleFiles) {
    await copyFile(path.join(sampleRaw, name), path.join(rawDir, name));
  }

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
