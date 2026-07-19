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
    if (status === 422 && data.out_of_scope) {
        return data.error;
    }
    if (status === 422) {
        const details = (data.details || []).map(d => d.msg).join('; ');
        return 'Please fix your input: ' + (details || data.error || 'invalid data.');
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
    const words = data.metrics?.wordCount ?? 0;
    const quality = data.quality?.score;

    let qualityHtml = '';
    if (quality !== undefined) {
        const flags = data.quality.flags || [];
        const flagsList = flags.length > 0
            ? `<ul style="text-align: left; font-size: 0.85em; color: #b91c1c; margin-top: 0.5rem; padding-left: 1.2rem; line-height: 1.4;">` + flags.map(f => `<li>${f}</li>`).join('') + `</ul>`
            : `<p style="color: #10B981; font-size: 0.85em; margin-top: 0.5rem; font-weight: 600;">✓ Passed all quality checks</p>`;

        qualityHtml = `
            <div class="metric-card" style="grid-column: span 3; text-align: center;">
                <h3 style="color: ${quality >= 80 ? '#10B981' : quality >= 50 ? '#F59E0B' : '#EF4444'};">${quality}/100</h3>
                <p>Programmatic Quality Score</p>
                ${flagsList}
            </div>
        `;
    }

    return `
        <div class="metrics-grid">
            <div class="metric-card"><h3>${words}</h3><p>Word Count</p></div>
            <div class="metric-card"><h3>${density}%</h3><p>Keyword Density</p></div>
            <div class="metric-card"><h3>${readability}</h3><p>Readability Score</p></div>
            ${qualityHtml}
        </div>`;
}

function renderSingleResult(data) {
    const resultsPanel = document.getElementById('results');
    const providerBadge = data.cached ? 'Cached' : (data.provider_used || 'mock');
    state.lastSingleMarkdown = data.optimized_article_markdown || '';
    resultsPanel.innerHTML = `
        <div class="results-header">
            <h2>Generated Output <small style="opacity:.6;font-size:0.7em;">(${providerBadge})</small></h2>
            <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" onclick="window.print()">Print / PDF</button>
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="export-docx-btn">Download DOCX</button>
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="export-pdf-btn">Download PDF</button>
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="copy-article-btn">📋 Copy</button>
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
    document.getElementById('copy-article-btn').onclick = (e) => copyToClipboard(state.lastSingleMarkdown, e.target);
}

async function copyToClipboard(text, buttonEl) {
    const original = buttonEl.textContent;
    try {
        await navigator.clipboard.writeText(text || '');
        buttonEl.textContent = '✅ Copied!';
    } catch (err) {
        buttonEl.textContent = '❌ Copy failed';
        showError('Clipboard copy failed — your browser may be blocking clipboard access. Try selecting the text manually.');
    }
    setTimeout(() => { buttonEl.textContent = original; }, 1800);
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
    state.lastBatchMarkdowns = data.results.map(r => r.optimized_article_markdown || '');
    const items = data.results.map((r, i) => {
        const req = state.lastRequests[i] || {};
        const label = req.topic || 'Item ' + (i + 1);
        if (r.error) {
            const scopeNote = r.out_of_scope ? ' <em>(out of scope for this tool)</em>' : '';
            return `<div class="article-content"><p style="color:#e66">❌ <strong>${label}</strong>: ${r.error}${scopeNote}</p></div>`;
        }
        const words = r.metrics?.wordCount ?? '';
        return `
            <details class="glass" style="margin-bottom:1rem;padding:1rem;">
                <summary><strong>${label}</strong> (${r.provider_used || 'mock'}, ${words} words)</summary>
                ${metricsBlock(r)}
                <div class="article-content">${safeHTML(r.optimized_article_markdown)}</div>
                <div style="display:flex; gap:0.5rem; margin-top:0.75rem; flex-wrap:wrap;">
                    <button class="btn-primary" style="width:auto;padding:.4rem .8rem;margin-top:0;font-size:.85rem;" onclick='downloadOneFromBatch(${i}, "docx")'>Download DOCX</button>
                    <button class="btn-primary" style="width:auto;padding:.4rem .8rem;margin-top:0;font-size:.85rem;" onclick='downloadOneFromBatch(${i}, "pdf")'>Download PDF</button>
                    <button class="btn-primary" style="width:auto;padding:.4rem .8rem;margin-top:0;font-size:.85rem;" onclick='copyToClipboard(state.lastBatchMarkdowns[${i}], event.target)'>📋 Copy</button>
                </div>
            </details>`;
    }).join('');

    resultsPanel.innerHTML = `
        <div class="results-header">
            <h2>Batch Results — ${data.succeeded}/${data.total} succeeded</h2>
            <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="download-zip-btn">⬇ Download All (ZIP)</button>
                <button class="btn-primary" style="width:auto;padding:.5rem 1rem;margin-top:0;" id="copy-all-btn">📋 Copy All</button>
            </div>
        </div>
        ${items}
    `;
    resultsPanel.classList.remove('hidden');
    resultsPanel.scrollIntoView({ behavior: 'smooth' });

    document.getElementById('download-zip-btn').onclick = downloadBatchZip;
    document.getElementById('copy-all-btn').onclick = (e) => {
        const combined = data.results
            .map((r, i) => {
                const label = state.lastRequests[i]?.topic || `Article ${i + 1}`;
                if (r.error) return `## ${label}\n\n_Failed: ${r.error}_`;
                return `## ${label}\n\n${r.optimized_article_markdown || ''}`;
            })
            .join('\n\n---\n\n');
        copyToClipboard(combined, e.target);
    };
}

async function downloadOneFromBatch(index, kind) {
    const payload = state.lastRequests[index];
    if (!payload) return;
    try {
        const res = await fetch(`/export/${kind}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) { showError(`Export to ${kind} failed for "${payload.topic}".`); return; }
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

async function downloadBatchZip() {
    const btn = document.getElementById('download-zip-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Preparing ZIP...';
    try {
        const res = await fetch('/export/batch/zip', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: state.lastRequests })
        });
        if (!res.ok) { showError('Batch ZIP export failed.'); return; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'healthy-gut-ai-batch.zip';
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        showError(`Batch ZIP export failed: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}
