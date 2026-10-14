const get = id => document.getElementById(id);
const token = document.querySelector('meta[name="app-token"]').content;
let previewCount = 0;
let previewBusy = false;
let requestRevision = 0;
let unresolvedIndexes = [];
let resolvedFilenames = [];
let tagsByFilename = {};
let ollamaAvailable = false;
let aiRunBusy = false;
let selectedAiFilenames = null;

function icons() { if (window.lucide) lucide.createIcons(); }
function showError(message) {
  get('error').textContent = message;
  get('error').hidden = !message;
  get('warning').hidden = true;
  get('success').hidden = true;
}
function showWarning(message) {
  get('warning').textContent = message;
  get('warning').hidden = !message;
  get('error').hidden = true;
}
function updateButton() {
  get('generate').disabled = previewBusy || aiRunBusy || !previewCount || !get('output-directory').value.trim() || (get('ai-enabled').checked && (!get('model-select').value || !getSelectedAiFilenames().length));
}
function getSourceTextFiles() {
  return Array.from(get('source-files').files).filter(file =>
    file.name.toLowerCase().endsWith('.txt') &&
    (!file.webkitRelativePath || file.webkitRelativePath.split('/').length === 2));
}
function getSelectedAiFilenames() {
  if (selectedAiFilenames === null) return [...resolvedFilenames];
  return resolvedFilenames.filter(filename => selectedAiFilenames.has(filename));
}
function updateAISelection() {
  const candidates = resolvedFilenames;
  const selected = getSelectedAiFilenames();
  get('ai-file-selection').hidden = !candidates.length;
  get('ai-selection-count').textContent = `${selected.length}/${candidates.length} selezionati`;
  get('ai-select-all').checked = candidates.length > 0 && selected.length === candidates.length;
  get('ai-select-all').indeterminate = selected.length > 0 && selected.length < candidates.length;
  const list = get('ai-file-list');
  list.replaceChildren();
  for (const filename of candidates) {
    const label = document.createElement('label');
    label.className = 'ai-file-option';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selected.includes(filename);
    checkbox.dataset.filename = filename;
    checkbox.addEventListener('change', () => {
      selectedAiFilenames = new Set(getSelectedAiFilenames());
      if (checkbox.checked) selectedAiFilenames.add(filename);
      else selectedAiFilenames.delete(filename);
      updateAISelection();
      updateButton();
    });
    const name = document.createElement('span');
    name.textContent = filename;
    label.append(checkbox, name);
    list.append(label);
  }
}
function renderPreview(filenames, includeExtension, tags = {}) {
  const preview = get('preview');
  preview.replaceChildren();
  if (!filenames.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-preview';
    empty.textContent = 'Nessun riferimento a file .txt trovato.';
    preview.append(empty);
    return;
  }
  const list = document.createElement('ul');
  for (const filename of filenames.slice(0, 10)) {
    const item = document.createElement('li');
    const link = document.createElement('code');
    link.textContent = `[[${includeExtension ? filename : filename.replace(/\.txt$/i, '')}]]`;
    item.append(link);
    if (tags[filename]?.length) {
      const tagList = document.createElement('span');
      tagList.className = 'tag-list';
      tagList.textContent = 'Tags: ';
      for (const tag of tags[filename]) {
        const tagCode = document.createElement('code');
        tagCode.textContent = tag;
        tagList.append(tagCode, document.createTextNode(' '));
      }
      item.append(tagList);
    }
    list.append(item);
  }
  preview.append(list);
}
async function post(path, form) {
  const response = await fetch(path, {method: 'POST', headers: {'X-App-Token': token}, body: form});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Richiesta non riuscita.');
  return data;
}
function makeForm() {
  const form = new FormData();
  if (get('use-index').checked && get('markdown').files[0]) {
    form.append('markdown', get('markdown').files[0]);
  }
  form.append('source_directory', get('source-directory').value.trim());
  const sourceNames = getSourceTextFiles().map(file => file.name);
  form.append('source_filenames', JSON.stringify(sourceNames));
  form.append('include_extension', String(get('include-extension').checked));
  return form;
}
function setProgress(done, total, currentName = '') {
  const percentage = total ? Math.round(done / total * 100) : 0;
  get('analysis-progress').max = 100;
  get('analysis-progress').value = percentage;
  get('progress-value').textContent = `${percentage}%`;
  get('progress-label').textContent = currentName ? `${done + 1}/${total} · ${currentName}` : `${done}/${total} file analizzati`;
}
async function loadOllamaModels() {
  const status = get('ollama-status');
  const select = get('model-select');
  try {
    const response = await fetch('/api/ollama/models', {cache: 'no-store'});
    const data = await response.json();
    if (!response.ok || !data.available) throw new Error(data.error || 'Ollama non raggiungibile.');
    ollamaAvailable = true;
    select.replaceChildren();
    for (const model of data.models) select.add(new Option(model, model));
    const preferred = data.models.find(model => model === 'gemma3:4b')
      || data.models.find(model => model === 'nemotron-3-nano:4b')
      || data.models.find(model => /^(llama3|mistral)(:|$)/i.test(model))
      || data.models[0];
    if (preferred) select.value = preferred;
    select.disabled = !get('ai-enabled').checked || !data.models.length;
    status.textContent = data.models.length ? `Ollama connesso · ${data.models.length} modelli` : 'Ollama attivo · nessun modello installato';
    status.className = data.models.length ? 'ready' : 'offline';
  } catch (error) {
    ollamaAvailable = false;
    select.replaceChildren(new Option('Ollama non disponibile', ''));
    select.disabled = true;
    status.textContent = 'Ollama non raggiungibile';
    status.className = 'offline';
  }
  updateButton();
}
async function analyzeSelectedFiles(jobId, filesToAnalyze) {
  const model = get('model-select').value;
  const sourceDirectory = get('source-directory').value.trim();
  const selectedTextFiles = getSourceTextFiles();
  const selectedByName = new Map(selectedTextFiles.map(file => [file.name, file]));
  const failedFiles = [];
  tagsByFilename = {};
  get('progress-wrap').hidden = false;
  setProgress(0, filesToAnalyze.length);
  for (let index = 0; index < filesToAnalyze.length; index += 1) {
    const filename = filesToAnalyze[index];
    setProgress(index, filesToAnalyze.length, filename);
    try {
      const form = new FormData();
      form.append('filename', filename);
      form.append('model', model);
      form.append('job_id', jobId);
      if (sourceDirectory) {
        form.append('source_directory', sourceDirectory);
      } else {
        const browserFile = selectedByName.get(filename);
        if (!browserFile) throw new Error(`File ${filename} non disponibile. Seleziona la cartella sorgente o inserisci il percorso.`);
        form.append('file_text', await browserFile.text());
      }
      const result = await post('/api/analyze', form);
      tagsByFilename[filename] = result.tags;
    } catch (error) {
      failedFiles.push(`${filename}: ${error.message}`);
      if (/ollama|modello|timeout|timed out/i.test(error.message)) throw error;
    }
    setProgress(index + 1, filesToAnalyze.length);
    renderPreview(resolvedFilenames, get('include-extension').checked, tagsByFilename);
    get('preview-count').textContent = `${previewCount} collegamenti · analisi ${index + 1}/${filesToAnalyze.length}`;
  }
  return failedFiles;
}
async function generateIndex(jobId, aiFilenames) {
  const form = makeForm();
  form.append('output_directory', get('output-directory').value.trim());
  form.append('overwrite', String(get('overwrite').checked));
  form.append('tags_by_filename', JSON.stringify(tagsByFilename));
  form.append('job_id', jobId);
  form.append('ai_filenames', JSON.stringify(aiFilenames));
  return post('/api/generate', form);
}
async function refreshPreview() {
  const useIndex = get('use-index').checked;
  const file = useIndex ? get('markdown').files[0] : null;
  const hasSource = Boolean(file || get('source-directory').value.trim() || get('source-files').files.length);
  const revision = ++requestRevision;
  previewBusy = false;
  previewCount = 0;
  unresolvedIndexes = [];
  resolvedFilenames = [];
  tagsByFilename = {};
  get('preview-count').textContent = hasSource ? 'Lettura delle sorgenti...' : 'Seleziona un indice o una cartella per visualizzare i collegamenti';
  get('output-info').textContent = 'Nessun file pronto';
  get('success').hidden = true;
  get('warning').hidden = true;
  get('error').hidden = true;
  get('preview').replaceChildren();
  updateAISelection();
  if (!hasSource) {
    const empty = document.createElement('p');
    empty.className = 'empty-preview';
    empty.textContent = 'L\'anteprima dei primi 10 collegamenti apparirà qui.';
    get('preview').append(empty);
    updateButton();
    return;
  }
  if (file) {
    get('markdown-name').textContent = file.name;
    get('markdown-size').textContent = `${(file.size / 1024).toFixed(1)} KB`;
    get('markdown-zone').classList.add('selected');
  }
  if (file && file.size > 20 * 1024 * 1024) {
    showError('Il file supera il limite di 20 MB.');
    get('preview-count').textContent = 'File troppo grande';
    updateButton();
    return;
  }
  previewBusy = true;
  updateButton();
  try {
    const data = await post('/api/preview', makeForm());
    if (revision !== requestRevision) return;
    previewCount = data.count;
    unresolvedIndexes = data.missing_indexes;
    resolvedFilenames = data.filenames;
    if (selectedAiFilenames !== null) {
      selectedAiFilenames = new Set([...selectedAiFilenames].filter(filename => resolvedFilenames.includes(filename)));
    }
    updateAISelection();
    renderPreview(resolvedFilenames, data.include_extension);
    get('preview-count').textContent = `${data.count} collegamenti${data.count > 10 ? ' / primi 10 mostrati' : ''}${unresolvedIndexes.length ? ` / ${unresolvedIndexes.length} senza corrispondenza` : ''}`;
    get('output-info').textContent = data.count ? 'Anteprima pronta' : 'Nessun collegamento trovato';
    if (unresolvedIndexes.length && data.count) showWarning(`Nessun file per gli indici ${unresolvedIndexes.join(', ')}: verranno esclusi dall'indice generato.`);
    else if (unresolvedIndexes.length) showError(`Nessun file trovato per gli indici ${unresolvedIndexes.join(', ')}. Seleziona la cartella con i file .txt.`);
    else if (!data.count) showError('Nessun riferimento a file .txt trovato nell\'indice sorgente.');
  } catch (error) {
    if (revision === requestRevision) showError(error.message);
  } finally {
    if (revision === requestRevision) {
      previewBusy = false;
      updateButton();
    }
  }
}
get('markdown').addEventListener('change', () => { selectedAiFilenames = null; refreshPreview(); });
get('use-index').addEventListener('change', () => {
  const useIndex = get('use-index').checked;
  get('markdown-zone').hidden = !useIndex;
  get('markdown').disabled = !useIndex;
  selectedAiFilenames = null;
  refreshPreview();
});
get('source-directory').addEventListener('change', () => {
  selectedAiFilenames = null;
  if (get('source-directory').value.trim()) {
    get('source-files').value = '';
    get('source-files-name').textContent = 'Seleziona cartella .txt';
  }
  refreshPreview();
});
get('source-files').addEventListener('change', () => {
  selectedAiFilenames = null;
  if (get('source-files').files.length) get('source-directory').value = '';
  const count = getSourceTextFiles().length;
  get('source-files-name').textContent = count ? `${count} file .txt selezionati` : 'Seleziona cartella .txt';
  refreshPreview();
});
get('include-extension').addEventListener('change', refreshPreview);
get('ai-enabled').addEventListener('change', () => {
  get('model-select').disabled = !get('ai-enabled').checked || !ollamaAvailable || !get('model-select').options.length;
  get('progress-wrap').hidden = true;
  tagsByFilename = {};
  if (resolvedFilenames.length) renderPreview(resolvedFilenames, get('include-extension').checked);
  get('success').hidden = true;
  updateButton();
});
get('ai-select-all').addEventListener('change', () => {
  selectedAiFilenames = get('ai-select-all').checked ? null : new Set();
  updateAISelection();
  updateButton();
});
get('model-select').addEventListener('change', () => { get('success').hidden = true; updateButton(); });
get('output-directory').addEventListener('input', updateButton);
get('overwrite').addEventListener('change', () => { get('success').hidden = true; get('error').hidden = true; });
get('conversion-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (get('generate').disabled) return;
  const useAi = get('ai-enabled').checked;
  const aiFilenames = useAi ? getSelectedAiFilenames() : [];
  const jobId = useAi ? crypto.randomUUID().replaceAll('-', '') : '';
  aiRunBusy = useAi;
  get('generate').disabled = true;
  get('generate').querySelector('span').textContent = useAi ? 'Analisi sequenziale in corso...' : 'Generazione in corso...';
  get('error').hidden = true;
  get('warning').hidden = true;
  get('success').hidden = true;
  try {
    const failedFiles = useAi ? await analyzeSelectedFiles(jobId, aiFilenames) : [];
    get('generate').querySelector('span').textContent = 'Salvataggio indice...';
    const data = await generateIndex(jobId, aiFilenames);
    const skipped = data.missing_indexes.length ? `; esclusi indici ${data.missing_indexes.join(', ')}` : '';
    const noteCount = data.created_notes.length;
    const resultType = noteCount ? `indice e ${noteCount} note AI` : 'indice';
    get('success').textContent = `Creati ${resultType} in ${data.output_directory} (${data.count} collegamenti${skipped}).`;
    if (failedFiles.length) {
      showWarning(`${get('success').textContent} Analisi non riuscita per ${failedFiles.length} file: ${failedFiles.map(item => item.split(':')[0]).join(', ')}.`);
    } else {
      get('success').hidden = false;
    }
    get('output-info').textContent = `${data.count} collegamenti salvati`;
  } catch (error) {
    showError(error.message);
  } finally {
    aiRunBusy = false;
    get('generate').querySelector('span').textContent = 'Genera indice Obsidian';
    updateButton();
  }
});
const zone = get('markdown-zone');
for (const eventName of ['dragenter', 'dragover']) zone.addEventListener(eventName, event => {
  event.preventDefault();
  zone.classList.add('dragging');
});
for (const eventName of ['dragleave', 'drop']) zone.addEventListener(eventName, event => {
  event.preventDefault();
  zone.classList.remove('dragging');
});
zone.addEventListener('drop', event => {
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  get('markdown').files = transfer.files;
  selectedAiFilenames = null;
  refreshPreview();
});
async function initialize() {
  icons();
  try {
    const response = await fetch('/api/health');
    const data = await response.json();
    get('health').textContent = data.ready ? 'Applicazione pronta' : 'Servizio non disponibile';
    get('output-directory').value = data.base_directory || '';
  } catch {
    get('health').textContent = 'Server locale non raggiungibile';
  }
  await loadOllamaModels();
  updateButton();
}
initialize();