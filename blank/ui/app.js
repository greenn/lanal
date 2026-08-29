const tabs = [...document.querySelectorAll('.tab')];
const tabContents = [...document.querySelectorAll('.tab-content')];
const segmentedGroups = [...document.querySelectorAll('.segmented')];
const historyRows = [...document.querySelectorAll('.request-row')];
const domainHeadings = [...document.querySelectorAll('.domain-heading')];
const historySearch = document.getElementById('historySearch');
const urlInput = document.getElementById('urlInput');
const runButton = document.getElementById('runButton');
const noteInput = document.getElementById('noteInput');
const noteState = document.getElementById('noteState');
const copyCommand = document.getElementById('copyCommand');
const commandText = document.getElementById('commandText');
const statusBig = document.getElementById('statusBig');
const statusText = document.getElementById('statusText');
const metricStatus = document.getElementById('metricStatus');
const finalUrl = document.getElementById('finalUrl');
const runState = document.getElementById('runState');
const verboseToggle = document.getElementById('verboseToggle');
const browserToggle = document.getElementById('browserToggle');
const infoSelect = document.getElementById('infoSelect');

const notes = new Map();
let currentRequestKey = 'https://novelcrow.com/|08:45:12';

function activateTab(name) {
  tabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.tab === name));
  tabContents.forEach((panel) => panel.classList.toggle('active', panel.id === name));
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => activateTab(tab.dataset.tab));
});

segmentedGroups.forEach((group) => {
  group.addEventListener('click', (event) => {
    const button = event.target.closest('.segment');
    if (!button) return;
    group.querySelectorAll('.segment').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    updateCommand();
  });
});

[verboseToggle, browserToggle, infoSelect].forEach((control) => {
  control.addEventListener('change', updateCommand);
});

urlInput.addEventListener('input', updateCommand);

function activeValue(groupName) {
  return document.querySelector(`.segmented[data-group="${groupName}"] .segment.active`)?.dataset.value;
}

function quoteUrl(url) {
  return /\s/.test(url) ? `"${url.replaceAll('"', '\\"')}"` : url;
}

function updateCommand() {
  const args = ['curl'];
  const method = activeValue('method');
  const ip = activeValue('ip');
  const http = activeValue('http');

  if (method === 'HEAD') args.push('-I');
  if (method === 'GET') args.push('-i');
  if (verboseToggle.checked) args.push('-v');
  if (ip === 'IPv4') args.push('-4');
  if (ip === 'IPv6') args.push('-6');
  if (http === 'HTTP/1.1') args.push('--http1.1');
  if (http === 'HTTP/2') args.push('--http2');
  if (browserToggle.checked) args.push('-A', '"Mozilla/5.0"', '--compressed');
  if (infoSelect.value === 'Redirects') args.push('-L');
  if (infoSelect.value === 'Raw') args.push('--raw');

  args.push(quoteUrl(urlInput.value.trim() || 'https://example.com/'));
  commandText.textContent = args.join(' ');
}

domainHeadings.forEach((heading) => {
  heading.addEventListener('click', () => {
    heading.closest('.domain-group').classList.toggle('collapsed');
  });
});

historySearch.addEventListener('input', () => {
  const query = historySearch.value.trim().toLowerCase();
  document.querySelectorAll('.domain-group').forEach((group) => {
    const domainMatches = group.dataset.domain.includes(query);
    const requestMatches = [...group.querySelectorAll('.request-row')].some((row) =>
      `${row.dataset.method} ${row.dataset.path} ${row.dataset.status}`.toLowerCase().includes(query)
    );
    group.hidden = Boolean(query) && !domainMatches && !requestMatches;
  });
});

function saveCurrentNote() {
  notes.set(currentRequestKey, noteInput.value);
}

function restoreCurrentNote() {
  const note = notes.get(currentRequestKey) || '';
  noteInput.value = note;
  noteState.textContent = note.trim() ? 'Saved locally in this prototype' : 'No notes yet';
}

noteInput.addEventListener('input', () => {
  saveCurrentNote();
  noteState.textContent = noteInput.value.trim() ? 'Saved locally in this prototype' : 'No notes yet';
});

function setStatus(code) {
  const isOk = Number(code) >= 200 && Number(code) < 400;
  const label = code === '403' ? 'Forbidden' : code === '200' ? 'OK' : `HTTP ${code}`;
  statusBig.textContent = code;
  statusBig.classList.toggle('ok', isOk);
  statusText.textContent = label;
  metricStatus.textContent = label;
}

historyRows.forEach((row) => {
  row.addEventListener('click', () => {
    saveCurrentNote();
    historyRows.forEach((item) => item.classList.remove('active'));
    row.classList.add('active');

    urlInput.value = row.dataset.url;
    finalUrl.textContent = row.dataset.url;
    currentRequestKey = `${row.dataset.url}|${row.querySelector('.time')?.textContent || ''}`;
    restoreCurrentNote();
    setStatus(row.dataset.status);

    const method = row.dataset.method;
    const methodGroup = document.querySelector('.segmented[data-group="method"]');
    methodGroup.querySelectorAll('.segment').forEach((item) => {
      item.classList.toggle('active', item.dataset.value === (method === 'HEAD' ? 'HEAD' : 'GET'));
    });
    updateCommand();
    activateTab('overview');
  });
});

runButton.addEventListener('click', async () => {
  runButton.disabled = true;
  const previousText = runButton.innerHTML;
  runButton.textContent = 'Running…';
  runState.textContent = 'Running';

  await new Promise((resolve) => setTimeout(resolve, 650));

  finalUrl.textContent = urlInput.value.trim() || '—';
  runState.textContent = 'Completed';
  runButton.innerHTML = previousText;
  runButton.disabled = false;
});

copyCommand.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(commandText.textContent);
    const oldText = copyCommand.textContent;
    copyCommand.textContent = 'Copied';
    setTimeout(() => (copyCommand.textContent = oldText), 1200);
  } catch {
    copyCommand.textContent = 'Select and copy manually';
  }
});

updateCommand();
restoreCurrentNote();
