const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('docReader', {
  selectFiles: () => ipcRenderer.invoke('dialog:selectFiles'),
  runPipeline: (payload) => ipcRenderer.invoke('pipeline:run', payload),
  openReport: (reportPath) => ipcRenderer.invoke('report:open', reportPath),
  getProjectRoot: () => ipcRenderer.invoke('projectRoot:get'),
  selectProjectRoot: () => ipcRenderer.invoke('projectRoot:select'),
  codexAuthGetStatus: (payload) => ipcRenderer.invoke('codexAuth:getStatus', payload),
  codexAuthStart: (payload) => ipcRenderer.invoke('codexAuth:start', payload),
  codexAuthRefresh: () => ipcRenderer.invoke('codexAuth:refresh'),
  codexAuthLogout: () => ipcRenderer.invoke('codexAuth:logout'),
  onPipelineLog: (handler) => {
    const listener = (_event, msg) => handler(msg);
    ipcRenderer.on('pipeline:log', listener);
    return () => ipcRenderer.removeListener('pipeline:log', listener);
  },
  onCodexAuthChanged: (handler) => {
    const listener = (_event, msg) => handler(msg);
    ipcRenderer.on('codexAuth:changed', listener);
    return () => ipcRenderer.removeListener('codexAuth:changed', listener);
  },
  onCodexAuthLog: (handler) => {
    const listener = (_event, msg) => handler(msg);
    ipcRenderer.on('codexAuth:log', listener);
    return () => ipcRenderer.removeListener('codexAuth:log', listener);
  },
});
