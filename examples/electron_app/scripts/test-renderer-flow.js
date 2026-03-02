#!/usr/bin/env node

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeClassList {
  constructor() {
    this._set = new Set();
  }

  add(name) {
    this._set.add(String(name));
  }

  remove(name) {
    this._set.delete(String(name));
  }

  toggle(name, force) {
    const key = String(name);
    if (typeof force === 'boolean') {
      if (force) this._set.add(key);
      else this._set.delete(key);
      return this._set.has(key);
    }
    if (this._set.has(key)) {
      this._set.delete(key);
      return false;
    }
    this._set.add(key);
    return true;
  }

  contains(name) {
    return this._set.has(String(name));
  }
}

class FakeElement {
  constructor(documentRef, tagName, id = null) {
    this._document = documentRef;
    this.tagName = String(tagName || 'div').toUpperCase();
    this.id = id;
    this.children = [];
    this.parentNode = null;
    this.textContent = '';
    this.className = '';
    this.classList = new FakeClassList();
    this.style = {};
    this.dataset = {};
    this.listeners = new Map();
    this.disabled = false;
    this.value = '';
    this.checked = false;
    this.type = '';
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this._innerHTML = '';
  }

  set innerHTML(value) {
    this._innerHTML = String(value || '');
    if (!this._innerHTML) this.children = [];
  }

  get innerHTML() {
    return this._innerHTML;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  querySelector(selector) {
    if (selector === 'option[value="llm"]') {
      return this.children.find(
        (child) => child.tagName === 'OPTION' && String(child.value || '').toLowerCase() === 'llm'
      ) || null;
    }
    return null;
  }

  addEventListener(type, handler) {
    const key = String(type);
    if (!this.listeners.has(key)) this.listeners.set(key, []);
    this.listeners.get(key).push(handler);
  }

  dispatchEvent(event) {
    const evt = event || {};
    const type = String(evt.type || '');
    if (!type) return;
    if (!evt.target) evt.target = this;
    if (typeof evt.preventDefault !== 'function') evt.preventDefault = () => {};
    const handlers = this.listeners.get(type) || [];
    for (const handler of handlers) {
      handler(evt);
    }
  }

  click() {
    if (this.disabled) return;
    this.dispatchEvent({ type: 'click', target: this });
  }
}

class FakeDocument {
  constructor(initialIds) {
    this._nodesById = new Map();
    this._allNodes = [];
    for (const id of initialIds) {
      const el = new FakeElement(this, 'div', id);
      this._nodesById.set(id, el);
      this._allNodes.push(el);
    }
  }

  createElement(tagName) {
    const el = new FakeElement(this, tagName);
    this._allNodes.push(el);
    return el;
  }

  getElementById(id) {
    const key = String(id);
    if (!this._nodesById.has(key)) {
      const el = new FakeElement(this, 'div', key);
      this._nodesById.set(key, el);
      this._allNodes.push(el);
    }
    return this._nodesById.get(key);
  }

  querySelectorAll(selector) {
    const m = String(selector || '').match(/^input\[data-group="(.*)"\]$/);
    if (!m) return [];
    const group = m[1].replace(/\\([\\":])/g, '$1');
    return this._allNodes.filter(
      (node) => node.tagName === 'INPUT' && node.dataset && node.dataset.group === group
    );
  }
}

function buildSelectWithOptions(documentRef, id, values) {
  const select = documentRef.getElementById(id);
  select.tagName = 'SELECT';
  select.children = [];
  for (const value of values) {
    const option = documentRef.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
  select.value = values[0] || '';
  return select;
}

function createLocalStorage() {
  const data = new Map();
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      data.set(key, String(value));
    },
    removeItem(key) {
      data.delete(key);
    },
    clear() {
      data.clear();
    },
  };
}

async function wait(ms = 0) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  const rendererPath = path.resolve(__dirname, '..', 'src', 'renderer', 'renderer.js');
  const source = fs.readFileSync(rendererPath, 'utf8');

  const requiredIds = [
    'status',
    'reportPath',
    'log',
    'progressPct',
    'progressLabel',
    'progressFill',
    'projectRoot',
    'codexAuthStatus',
    'flowMode',
    'stage2Engine',
    'btnPick',
    'btnRun',
    'btnCodexConnect',
    'btnCodexLogout',
    'btnOpenReport',
    'btnOpenDetailedReport',
    'dropzone',
    'fileList',
    'docTypeLegend',
  ];
  const documentRef = new FakeDocument(requiredIds);
  buildSelectWithOptions(documentRef, 'flowMode', ['importation', 'exportation']);
  buildSelectWithOptions(documentRef, 'stage2Engine', ['regex', 'llm']);

  let selectedFiles = [];
  let lastRunPayload = null;
  const pipelineLogListeners = [];
  const codexAuthChangedListeners = [];
  const codexAuthLogListeners = [];

  const docReader = {
    async getProjectRoot() {
      return { projectRoot: 'C:/tmp/project', isPackaged: false };
    },
    async codexAuthGetStatus() {
      return {
        connected: true,
        configured: true,
        missingConfig: [],
        identity: { email: 'qa@example.com' },
        expiresAt: null,
        provider: 'codex-cli',
      };
    },
    async codexAuthStart() {
      return { ok: true, status: { connected: true, configured: true, provider: 'codex-cli' } };
    },
    async codexAuthLogout() {
      return { ok: true, status: { connected: false, configured: true, provider: 'codex-cli' } };
    },
    async selectFiles() {
      return selectedFiles.slice();
    },
    async runPipeline(payload) {
      lastRunPayload = payload;
      return {
        ok: true,
        reportPath: 'C:/tmp/_stage04_report.html',
        debugReportPath: null,
        runLogPath: 'C:/tmp/pipeline_debug.log',
        requestedStage2Engine: payload.stage2Engine,
        effectiveStage2Engine: payload.stage2Engine,
        codexAuth: { connected: true },
      };
    },
    async openReport() {
      return { ok: true };
    },
    onPipelineLog(cb) {
      pipelineLogListeners.push(cb);
    },
    onCodexAuthChanged(cb) {
      codexAuthChangedListeners.push(cb);
    },
    onCodexAuthLog(cb) {
      codexAuthLogListeners.push(cb);
    },
  };

  const context = {
    console,
    setTimeout,
    clearTimeout,
    document: documentRef,
    localStorage: createLocalStorage(),
    CSS: { escape: (value) => String(value).replace(/[\\"]/g, '\\$&') },
    docReader,
  };
  context.globalThis = context;

  vm.createContext(context);
  vm.runInContext(source, context, { filename: rendererPath });

  // Let async setup calls settle.
  await wait(10);

  // Case 1: exportation mode should produce exportation payload + doc types.
  const flowMode = documentRef.getElementById('flowMode');
  flowMode.value = 'exportation';
  flowMode.dispatchEvent({ type: 'change', target: flowMode });
  await wait(10);

  const legendAfterExport = documentRef.getElementById('docTypeLegend').textContent;
  assert.match(legendAfterExport, /COMMERCIAL INVOICE/);
  assert.match(legendAfterExport, /CONTAINER DATA/);

  selectedFiles = [
    'C:/docs/COMMERCIAL INVOICE I-000725.pdf',
    'C:/docs/PACKING LIST I-000725.pdf',
    'C:/docs/DRAFT BL I-0007-25.pdf',
  ];
  documentRef.getElementById('btnPick').click();
  await wait(10);

  lastRunPayload = null;
  documentRef.getElementById('btnRun').click();
  await wait(10);

  assert.ok(lastRunPayload, 'runPipeline should be called for exportation run');
  assert.equal(lastRunPayload.flow, 'exportation');
  assert.equal(
    JSON.stringify(lastRunPayload.files.map((f) => f.docType)),
    JSON.stringify(['COMMERCIAL INVOICE', 'PACKING LIST', 'DRAFT BL'])
  );

  // Case 2: importation mode should switch payload flow and types.
  flowMode.value = 'importation';
  flowMode.dispatchEvent({ type: 'change', target: flowMode });
  await wait(10);

  const legendAfterImport = documentRef.getElementById('docTypeLegend').textContent;
  assert.match(legendAfterImport, /BL/);
  assert.match(legendAfterImport, /INVOICE/);

  selectedFiles = [
    'C:/docs/BL 77.pdf',
    'C:/docs/INVOICE 77.pdf',
    'C:/docs/PACKING LIST 77.pdf',
  ];
  documentRef.getElementById('btnPick').click();
  await wait(10);

  lastRunPayload = null;
  documentRef.getElementById('btnRun').click();
  await wait(10);

  assert.ok(lastRunPayload, 'runPipeline should be called for importation run');
  assert.equal(lastRunPayload.flow, 'importation');
  const importTypes = new Set(lastRunPayload.files.map((f) => f.docType));
  assert.ok(importTypes.has('BL'), 'importation payload should include BL');
  assert.ok(importTypes.has('INVOICE'), 'importation payload should include INVOICE');
  assert.ok(importTypes.has('PACKING LIST'), 'importation payload should include PACKING LIST');

  console.log('OK: renderer flow logic test passed');
}

main().catch((error) => {
  console.error('ERROR:', error && error.stack ? error.stack : error);
  process.exit(1);
});
