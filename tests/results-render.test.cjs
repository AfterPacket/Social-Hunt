// Offline renderer regressions: node --test tests/results-render.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');

function renderer() {
  const container = { dataset: {}, innerHTML: '', querySelectorAll: () => [] };
  const context = vm.createContext({
    URL, location: { protocol: 'https:' }, console,
    document: { getElementById: (id) => id === 'results' ? container : null },
    escapeHtml: (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'),
    badge: (s) => s,
  });
  vm.runInContext(source.slice(source.indexOf('function renderResults('), source.indexOf('function initGoogleDorksView(')), context);
  return { container, render: context.renderResults };
}

const job = {
  job_id: 'test', state: 'running',
  results: Array.from({ length: 650 }, (_, i) => ({ provider: `site-${i}`, status: 'unknown', url: 'https://example.org/user' })),
};

test('all 650 live results are rendered, not capped at 300 or paginated at 50', () => {
  const { container, render } = renderer();
  render(job, 'results');
  assert.equal((container.innerHTML.match(/<tr>/g) || []).length, 651);
  assert.match(container.innerHTML, /site-649/);
});

test('filter survives live refresh and completion, resets for a different job', () => {
  const { container, render } = renderer();
  render(job, 'results', { filter: 'site-649' });
  render({ ...job, state: 'done' }, 'results');
  assert.match(container.innerHTML, /site-649/);
  assert.doesNotMatch(container.innerHTML, /<td>site-0<\/td>/);
  render({ ...job, job_id: 'new' }, 'results');
  assert.match(container.innerHTML, /<td>site-0<\/td>/);
});

test('avatar URLs are resolved, escaped, lazy-loaded; unsafe schemes are rejected', () => {
  const { container, render } = renderer();
  const one = (avatar_url) => ({ ...job, results: [{ ...job.results[0], profile: { avatar_url } }] });
  render(one('/avatar.png?a=1&amp;b=2'), 'results');
  assert.match(container.innerHTML, /src="https:\/\/example.org\/avatar.png\?a=1&amp;b=2"/);
  assert.match(container.innerHTML, /loading="lazy" referrerpolicy="no-referrer"/);
  render(one('javascript:alert(1)'), 'results');
  assert.doesNotMatch(container.innerHTML, /<img/);
  assert.match(container.innerHTML, /No image/);
});

test('live polling has no 300-result limit', () => {
  assert.doesNotMatch(source, /RESULTS_RENDER_LIMIT/);
});
