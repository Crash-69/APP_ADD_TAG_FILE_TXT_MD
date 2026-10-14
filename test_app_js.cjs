const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function createApp() {
  const elements = new Map();
  function element() {
    return {
      value: '', files: [], checked: false, hidden: false, disabled: false,
      options: [], children: [], listeners: {}, dataset: {},
      classList: {add() {}, remove() {}},
      addEventListener(name, callback) { this.listeners[name] = callback; },
      replaceChildren(...children) { this.children = children; },
      append(...children) { this.children.push(...children); },
      add(option) { this.options.push(option); },
    };
  }
  function get(id) {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  }
  get('use-index').checked = true;
  const requests = [];
  const context = vm.createContext({
    document: {
      getElementById: get,
      querySelector: () => ({content: 'test-token'}),
      createElement: element,
      createTextNode: text => text,
    },
    window: {}, FormData, Option: function(text, value) { return {text, value}; },
    fetch: async (url, options) => {
      if (url === '/api/health') {
        return {json: async () => ({ready: true, base_directory: 'output'})};
      }
      if (url === '/api/ollama/models') {
        return {ok: true, json: async () => ({available: true, models: ['test-model']})};
      }
      requests.push(options.body);
      const filenames = options.body.has('markdown')
        ? ['B.txt'] : ['a.txt', 'B.txt'];
      return {ok: true, json: async () => ({
        filenames, count: filenames.length, missing_indexes: [], include_extension: false,
      })};
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'app.js'), 'utf8'), context);
  return {get, requests, run: code => vm.runInContext(code, context)};
}

test('folder selection with default settings shows files without an index', async () => {
  const app = createApp();
  await app.run('initialize()');
  app.get('source-files').files = [
    {name: 'B.txt', webkitRelativePath: 'folder/B.txt'},
    {name: 'a.txt', webkitRelativePath: 'folder/a.txt'},
    {name: 'nested.txt', webkitRelativePath: 'folder/nested/nested.txt'},
  ];
  app.get('source-files').listeners.change();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.get('ai-file-selection').hidden, false);
  assert.equal(app.get('ai-file-list').children.length, 2);
  assert.equal(app.get('generate').disabled, false);
  assert.equal(app.requests.at(-1).has('markdown'), false);
  assert.deepEqual(JSON.parse(app.requests.at(-1).get('source_filenames')), ['B.txt', 'a.txt']);
  app.get('ai-enabled').checked = true;
  app.get('ai-file-list').children[0].children[0].checked = false;
  app.get('ai-file-list').children[0].children[0].listeners.change();
  assert.equal(app.get('ai-selection-count').textContent, '1/2 selezionati');
  assert.equal(app.get('generate').disabled, false);
});

test('directory path works without an index and a loaded index still filters files', async () => {
  const app = createApp();
  await app.run('initialize()');
  app.get('source-directory').value = 'source';
  await app.run('refreshPreview()');
  assert.equal(app.get('ai-file-list').children.length, 2);
  assert.equal(app.get('generate').disabled, false);
  app.get('markdown').files = [new Blob(['- B.txt'])];
  await app.run('refreshPreview()');
  assert.equal(app.requests.at(-1).has('markdown'), true);
  assert.equal(app.get('ai-file-list').children.length, 1);
  app.get('use-index').checked = false;
  app.get('use-index').listeners.change();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(app.requests.at(-1).has('markdown'), false);
  assert.equal(app.get('ai-file-list').children.length, 2);
  app.get('source-directory').value = '';
  await app.run('refreshPreview()');
  assert.equal(app.get('ai-file-selection').hidden, true);
  assert.equal(app.get('generate').disabled, true);
});
