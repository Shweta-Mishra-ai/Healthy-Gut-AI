const state = { mode: 'single', lastRequests: [] };

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.mode = btn.dataset.mode;
        document.getElementById('single-fields').classList.toggle('hidden', state.mode !== 'single');
        document.getElementById('batch-fields').classList.toggle('hidden', state.mode !== 'batch');
    });
});

function showError(msg) {
    const el = document.getElementById('form-error');
    el.textContent = msg;
    el.classList.remove('hidden');
}
function clearError() {
    const el = document.getElementById('form-error');
    el.textContent = '';
    el.classList.add('hidden');
}

function parseBatchInput(raw) {
    return raw.split('\n').map(l => l.trim()).filter(Boolean).map(line => {
        const [topic, keyword, geo] = line.split('|').map(p => (p || '').trim());
        return { topic, primary_keyword: keyword, geo_target: geo };
    });
}

document.getElementById('generate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    clearError();

    const formPanel = document.querySelector('.generator-panel');
    const loading = document.getElementById('loading');
    const resultsPanel = document.getElementById('results');
    const btn = document.getElementById('generate-btn');
    const article_type = document.getElementById('article_type').value;
    const language = document.getElementById('language').value;

    btn.disabled = true;
    loading.classList.remove('hidden');
    resultsPanel.classList.add('hidden');

    try {
        if (state.mode === 'single') {
            const payload = {
                topic: document.getElementById('topic').value,
                primary_keyword: document.getElementById('primary_keyword').value,
                geo_target: document.getElementById('geo_target').value,
                article_type, language
            };
            state.lastRequests = [payload];
            const res = await fetch('/generate', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) {
                showError(formatError(res.status, data));
            } else {
                renderSingleResult(data);
            }
        } else {
            const rawItems = parseBatchInput(document.getElementById('batch_topics').value)
                .map(it => ({ ...it, article_type, language }));
            if (rawItems.length === 0) {
                showError('Add at least one topic line (topic | keyword | geo).');
                return;
            }
            state.lastRequests = rawItems;
            const res = await fetch('/generate/batch', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items: rawItems })
            });
            const data = await res.json();
            if (!res.ok) {
                showError(formatError(res.status, data));
            } else {
                renderBatchResults(data);
            }
        }
    } catch (err) {
        console.error(err);
        showError('Failed to connect to backend. Check your connection and try again.');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
});

function formatError(status, data) {
    if (status === 429) {
        return `Too many requests — please wait ${data.retry_after_seconds || 'a moment'} seconds and try again.`;
    }
    if (status === 422) {
        const details = (data.details || []).map(d => d.msg).join('; ');
        return 'Please fix your input: ' + (details || 'invalid data.');
    }
    if (status === 502) {
        return 'The AI provider had trouble generating this article. Please try again.';
    }
    return data.error || 'Something went wrong on the server.';
}

function safeHTML(markdown) {
    const raw = marked.parse(markdown || 'No article content generated.');
    return window.DOMPurify ? DOMPurify.sanitize(raw) : raw;
}

function metricsBlock(data) {
    const density = data.metrics?.keywordDensity?.keywordDensityPercent ?? 0;
    const readability = data.metrics?.readability?.fleschReadingEase ?? 0;
    return `
        <div class="metrics-grid">
            <div class="metric-card"><h3>${density}%</h3><p>Keyword Density</p></div>
            <div class="metric-card"><h3>${readability}</h3><p>Readability Score</p></div>
        </div>`;
}

function renderSingleResult(data) {
    const resultsPanel = document.getElementById('results');
    const providerBadge = data.cached ? 'Cached' : (data.provider_used || 'mock');
    resultsPanel.innerHTML = `
        <div class="results-header">
            <h2>Generated Output <small style="opacity:.6;font-size:0.7em;">(${providerBadge})</small></h2>
            <div style="display:flex; gap:0.5rem;">
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" onclick="window.print()">Print / PDF</button>
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="export-docx-btn">Download DOCX</button>
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="export-pdf-btn">Download PDF</button>
            </div>
        </div>
        ${metricsBlock(data)}
        <div class="article-content">${safeHTML(data.optimized_article_markdown)}</div>
        <div class="seo-meta">
            <p><strong>Meta Description:</strong> ${data.meta_description || ''}</p>
            <p><strong>URL Slug:</strong> /${data.url_slug || ''}</p>
            <p><strong>Soft CTA:</strong> ${data.cta_soft || ''}</p>
            <p><strong>Direct CTA:</strong> ${data.cta_direct || ''}</p>
        </div>
    `;
    resultsPanel.classList.remove('hidden');
    resultsPanel.scrollIntoView({ behavior: 'smooth' });

    document.getElementById('export-docx-btn').onclick = () => downloadExport('docx');
    document.getElementById('export-pdf-btn').onclick = () => downloadExport('pdf');
}

async function downloadExport(kind) {
    const payload = state.lastRequests[0];
    if (!payload) return;
    try {
        const res = await fetch(`/export/${kind}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) { showError(`Export to ${kind} failed.`); return; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(payload.topic || 'article').toLowerCase().replace(/\s+/g, '-')}.${kind}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        showError(`Export to ${kind} failed: ${err.message}`);
    }
}

function renderBatchResults(data) {
    const resultsPanel = document.getElementById('results');
    const items = data.results.map((r, i) => {
        if (r.error) {
            return `<div class="article-content"><p style="color:#e66">❌ ${state.lastRequests[i]?.topic || 'Item ' + (i+1)}: ${r.error}</p></div>`;
        }
        return `
            <details class="glass" style="margin-bottom:1rem;padding:1rem;">
                <summary><strong>${state.lastRequests[i]?.topic || 'Article ' + (i+1)}</strong> (${r.provider_used || 'mock'})</summary>
                ${metricsBlock(r)}
                <div class="article-content">${safeHTML(r.optimized_article_markdown)}</div>
            </details>`;
    }).join('');

    resultsPanel.innerHTML = `
        <div class="results-header"><h2>Batch Results — ${data.succeeded}/${data.total} succeeded</h2></div>
        ${items}
    `;
    resultsPanel.classList.remove('hidden');
    resultsPanel.scrollIntoView({ behavior: 'smooth' });
}
