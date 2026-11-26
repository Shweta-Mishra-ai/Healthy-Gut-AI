// Unit tests for static/ui.js — the escaping and markdown renderer every
// page relies on to keep model output and reviewer notes from becoming markup.
// Run: node --test tests_js/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function loadUi() {
    const storage = new Map();
    const context = vm.createContext({
        document: { addEventListener() {}, getElementById() { return null; } },
        localStorage: {
            getItem: k => (storage.has(k) ? storage.get(k) : null),
            setItem: (k, v) => storage.set(k, String(v)),
            removeItem: k => storage.delete(k),
        },
        setTimeout, console,
    });
    const source = readFileSync(new URL('../static/ui.js', import.meta.url), 'utf8');
    return vm.runInContext(`${source}\nGutfolio;`, context);
}

const ui = loadUi();

test('escapeHTML escapes every HTML-significant character', () => {
    assert.equal(ui.escapeHTML(`<a href="x">'&'</a>`), '&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;');
    assert.equal(ui.escapeHTML(null), '');
});

test('renderMarkdown never emits raw HTML from the source', () => {
    const html = ui.renderMarkdown('Hello <img src=x onerror="alert(1)"> and <script>x()</script>');
    assert.ok(!html.includes('<img'));
    assert.ok(!html.includes('<script'));
    assert.ok(html.includes('&lt;img'));
});

test('renderMarkdown drops unsafe link schemes and keeps safe ones', () => {
    const html = ui.renderMarkdown('[a](javascript:alert(1)) [b](https://nih.gov) [c](data:text/html,x)');
    assert.ok(!/href="javascript:/i.test(html));
    assert.ok(!/href="data:/i.test(html));
    assert.ok(html.includes('href="https://nih.gov"'));
});

test('renderMarkdown renders lists, headings and tables', () => {
    const html = ui.renderMarkdown('## Title\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |');
    assert.match(html, /<h2[^>]*>Title<\/h2>/);
    assert.match(html, /<li>one<\/li>/);
    assert.match(html, /<table/);
});

test('API key round-trips through storage', () => {
    ui.setApiKey('k-123');
    assert.equal(ui.getApiKey(), 'k-123');
    ui.setApiKey('');
    assert.equal(ui.getApiKey(), '');
});
