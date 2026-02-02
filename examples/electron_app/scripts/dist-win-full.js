#!/usr/bin/env node

const { spawnSync } = require('node:child_process');

function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (res.error) throw res.error;
  if (res.status !== 0) {
    throw new Error(`Command failed (${res.status}): ${cmd} ${args.join(' ')}`);
  }
}

function runNpm(args) {
  // On Windows, executing `npm.cmd` directly can fail with EINVAL depending on how Node is installed.
  // When invoked from `npm run`, npm provides `npm_execpath` which points to npm-cli.js.
  const npmExecPath = process.env.npm_execpath;
  if (npmExecPath) {
    return run(process.execPath, [npmExecPath, ...args]);
  }

  // Fallback: rely on PATH and (on Windows) shell resolution.
  return run('npm', args, { shell: process.platform === 'win32' });
}

function main() {
  if (process.platform !== 'win32') {
    console.error('ERROR: dist:win:full must be run on Windows (win32).');
    console.error('Reason: PyInstaller cannot cross-compile Windows executables from macOS/Linux.');
    process.exit(2);
  }

  // Build embedded Python runner
  runNpm(['run', 'build:python']);

  // Fetch/pack Tesseract into resources/tesseract/win
  runNpm(['run', 'fetch:tesseract']);

  // Validate both artifacts before producing the installer
  runNpm(['run', 'smoke:python']);
  runNpm(['run', 'smoke:tesseract']);

  // Build NSIS installer
  runNpm(['run', 'dist:win']);
}

main();
