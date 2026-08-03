const state = { mode: 'single', lastRequests: [], theme: localStorage.getItem('theme') || 'light' };

// Initialize Theme
document.documentElement.setAttribute('data-theme', state.theme);
const themeBtn = document.getElementById('theme-toggle-btn');
if (themeBtn) {
    themeBtn.textContent = state.theme === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {
        state.theme = state.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', state.theme);
        localStorage.setItem('theme', state.theme);
        themeBtn.textContent = state.theme === 'dark' ? '☀️' : '🌙';
        showToast(`Switched to ${state.theme} mode`, 'info');
    });
}

// Toast Notification System
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><div>${message}</div>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Mode Toggle Button Listeners
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
    if (el) {
        el.textContent = msg;
        el.classList.remove('hidden');
    }
    showToast(msg, 'error');
}

function clearError() {
    const el = document.getElementById('form-error');
    if (el) {
        el.textContent = '';
        el.classList.add('hidden');
    }
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

    const loading = document.getElementById('loading');
    const resultsPanel = document.getElementById('results');
    const btn = document.getElementById('generate-btn');
    const article_type = document.getElementById('article_type').value;
    const language = document.getElementById('language').value;
    const tone = document.getElementById('tone').value;

    btn.disabled = true;
    loading.classList.remove('hidden');
    resultsPanel.classList.add('hidden');

    try {
        if (state.mode === 'single') {
            const payload = {
                topic: document.getElementById('topic').value,
                primary_keyword: document.getElementById('primary_keyword').value,
                geo_target: document.getElementById('geo_target').value,
                article_type, language, tone
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
                showToast('Article generated successfully!', 'success');
            }
        } else {
            const rawItems = parseBatchInput(document.getElementById('batch_topics').value)
                .map(it => ({ ...it, article_type, language, tone }));
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
                showToast(`Batch processing completed (${data.succeeded}/${data.total} succeeded)`, 'success');
            }
        }
    } catch (err) {
        console.error(err);
        showError('Failed to connect to backend server. Please verify your connection.');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
});

function formatError(status, data) {
    if (status === 429) {
        return `Too many requests — please wait ${data.retry_after_seconds || 'a moment'} seconds.`;
    }
    if (status === 422 && data.out_of_scope) {
        return data.error;
    }
    if (status === 422) {
        const details = (data.details || []).map(d => d.msg).join('; ');
        return 'Validation failed: ' + (details || data.error || 'invalid input.');
    }
    if (status === 502) {
        return 'The AI provider had trouble generating content. Served fallback result.';
    }
    return data.error || 'An unexpected server error occurred.';
}

function safeHTML(markdown) {
    if (!markdown) return '<p style="color:var(--text-muted);">No article content generated.</p>';
    let raw = '';
    if (window.marked && typeof window.marked.parse === 'function') {
        raw = window.marked.parse(markdown);
    } else {
        raw = markdown
            .replace(/^# (.*$)/gim, '<h1>$1</h1>')
            .replace(/^## (.*$)/gim, '<h2>$1</h2>')
            .replace(/^### (.*$)/gim, '<h3>$1</h3>')
            .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/gim, '<em>$1</em>')
            .replace(/\n\n/gim, '<br><br>');
    }
    return window.DOMPurify ? DOMPurify.sanitize(raw) : raw;
}

function internalLinksBlock(suggestions) {
    if (!suggestions || !suggestions.length) {
        return `<div class="seo-meta"><p style="opacity:.7;font-size:0.88rem;">🔗 <strong>Suggested Internal Links:</strong> Approve related articles in the Review Queue to automatically construct your SEO internal cluster.</p></div>`;
    }
    const items = suggestions.map(s => `
        <li style="margin-bottom:0.4rem;">
            <strong>${s.topic}</strong> <span style="opacity:.65;">(relevance ${s.relevance_score})</span>
            <br><small style="opacity:.6;">/${s.url_slug || ''}</small>
        </li>
    `).join('');
    return `
        <div class="seo-meta">
            <p><strong>🔗 Suggested Internal Links (from approved cluster):</strong></p>
            <ul style="padding-left:1.2rem; margin-top:0.4rem;">${items}</ul>
        </div>
    `;
}

function metricsBlock(data) {
    const density = data.metrics?.keywordDensity?.keywordDensityPercent ?? 0;
    const readability = data.metrics?.readability?.fleschReadingEase ?? 0;
    const words = data.metrics?.wordCount ?? 0;
    return `
        <div class="metrics-grid">
            <div class="metric-card"><h3>${words}</h3><p>Word Count</p></div>
            <div class="metric-card"><h3>${density}%</h3><p>Keyword Density</p></div>
            <div class="metric-card"><h3>${readability}</h3><p>Readability Score</p></div>
        </div>`;
}

function renderSingleResult(data) {
    const resultsPanel = document.getElementById('results');
    const providerBadge = data.cached ? 'Cached' : (data.provider_used || 'mock');
    state.lastSingleMarkdown = data.optimized_article_markdown || '';
    resultsPanel.innerHTML = `
        <div class="results-header" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem;">
            <div>
                <h2>Generated Article <span class="status-pill pill-ok">${providerBadge}</span></h2>
                <p style="font-size:0.85rem; color:var(--text-muted);">Registered in Review Queue (ID: ${data.review_id || 'draft'})</p>
            </div>
            <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                <button class="btn-secondary" onclick="window.print()">🖨 Print / PDF</button>
                <button class="btn-secondary" id="export-docx-btn">📄 DOCX</button>
                <button class="btn-secondary" id="export-pdf-btn">📕 PDF</button>
                <button class="btn-secondary" id="export-md-btn">📝 .MD</button>
                <button class="btn-secondary" id="export-json-btn">📦 JSON</button>
                <button class="btn-primary" style="width:auto; padding:0.5rem 1rem;" id="copy-article-btn">📋 Copy Article</button>
            </div>
        </div>
        ${metricsBlock(data)}
        <div class="article-content">${safeHTML(data.optimized_article_markdown)}</div>
        <div class="seo-meta">
            <p><strong>Meta Description A/B Variants:</strong></p>
            <ul class="meta-variants-list">
                ${(data.meta_description_variants || [data.meta_description || '']).map((v, i) => `
                    <li>
                        <span>${v}</span>
                        <small style="opacity:.65;">(${v.length} chars)</small>
                        <button class="btn-small-copy" onclick='copyToClipboard(${JSON.stringify(v)}, this)'>📋 Copy</button>
                    </li>
                `).join('')}
            </ul>
            <p><strong>URL Slug:</strong> <code>/${data.url_slug || ''}</code></p>
            <p><strong>Soft CTA:</strong> ${data.cta_soft || 'None'}</p>
            <p><strong>Direct CTA:</strong> ${data.cta_direct || 'None'}</p>
        </div>
        ${internalLinksBlock(data.internal_link_suggestions)}
    `;
    resultsPanel.classList.remove('hidden');
    resultsPanel.scrollIntoView({ behavior: 'smooth' });

    document.getElementById('export-docx-btn').onclick = () => downloadExport('docx');
    document.getElementById('export-pdf-btn').onclick = () => downloadExport('pdf');
    document.getElementById('export-md-btn').onclick = () => downloadExport('markdown', 'md');
    document.getElementById('export-json-btn').onclick = () => downloadExport('json');
    document.getElementById('copy-article-btn').onclick = (e) => copyToClipboard(state.lastSingleMarkdown, e.target);
}

async function copyToClipboard(text, buttonEl) {
    const original = buttonEl ? buttonEl.textContent : '';
    try {
        await navigator.clipboard.writeText(text || '');
        if (buttonEl) buttonEl.textContent = '✅ Copied!';
        showToast('Copied to clipboard!', 'success');
    } catch (err) {
        if (buttonEl) buttonEl.textContent = '❌ Failed';
        showToast('Clipboard copy failed. Please select text manually.', 'error');
    }
    if (buttonEl) setTimeout(() => { buttonEl.textContent = original; }, 1800);
}

async function downloadExport(kind, ext) {
    ext = ext || kind;
    const payload = state.lastRequests[0];
    if (!payload) return;
    try {
        const res = await fetch(`/export/${kind}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) { showError(`Export to ${ext} failed.`); return; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(payload.topic || 'article').toLowerCase().replace(/\s+/g, '-')}.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
        showToast(`Downloaded ${ext.toUpperCase()} file`, 'success');
    } catch (err) {
        showError(`Export to ${ext} failed: ${err.message}`);
    }
}

function renderBatchResults(data) {
    const resultsPanel = document.getElementById('results');
    state.lastBatchMarkdowns = data.results.map(r => r.optimized_article_markdown || '');
    const items = data.results.map((r, i) => {
        const req = state.lastRequests[i] || {};
        const label = req.topic || 'Item ' + (i + 1);
        if (r.error) {
            const scopeNote = r.out_of_scope ? ' <em>(out of scope)</em>' : '';
            return `<div class="article-content" style="border-color:rgba(239,68,68,0.3);"><p style="color:var(--danger);">❌ <strong>${label}</strong>: ${r.error}${scopeNote}</p></div>`;
        }
        const words = r.metrics?.wordCount ?? '';
        return `
            <details class="glass" style="margin-bottom:1rem; padding:1.25rem;">
                <summary style="cursor:pointer; font-weight:600; font-size:1.05rem;">
                    <strong>${label}</strong> <span class="status-pill pill-ok">${r.provider_used || 'mock'}</span> <span style="font-size:0.85rem; opacity:.7;">(${words} words)</span>
                </summary>
                <div style="margin-top:1rem;">
                    ${metricsBlock(r)}
                    <div class="article-content">${safeHTML(r.optimized_article_markdown)}</div>
                    <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                        <button class="btn-secondary" onclick='downloadOneFromBatch(${i}, "docx")'>📄 DOCX</button>
                        <button class="btn-secondary" onclick='downloadOneFromBatch(${i}, "pdf")'>📕 PDF</button>
                        <button class="btn-secondary" onclick='copyToClipboard(state.lastBatchMarkdowns[${i}], event.target)'>📋 Copy</button>
                    </div>
                </div>
            </details>`;
    }).join('');

    resultsPanel.innerHTML = `
        <div class="results-header" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; margin-bottom:1.5rem;">
            <h2>Batch Results (${data.succeeded}/${data.total} Succeeded)</h2>
            <div style="display:flex; gap:0.5rem;">
                <button class="btn-primary" style="width:auto;" id="download-zip-btn">⬇ Download ZIP Bundle</button>
                <button class="btn-secondary" id="copy-all-btn">📋 Copy All</button>
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
        if (!res.ok) { showError(`Export failed for "${payload.topic}".`); return; }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(payload.topic || 'article').toLowerCase().replace(/\s+/g, '-')}.${kind}`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        showError(`Export failed: ${err.message}`);
    }
}

async function downloadBatchZip() {
    const btn = document.getElementById('download-zip-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Compressing...';
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
        showToast('Downloaded ZIP bundle', 'success');
    } catch (err) {
        showError(`Batch ZIP export failed: ${err.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

document.getElementById('preview-outline-btn').addEventListener('click', async () => {
    const topic = document.getElementById('topic').value.trim();
    const keyword = document.getElementById('primary_keyword').value.trim();
    const geo = document.getElementById('geo_target').value.trim();
    const article_type = document.getElementById('article_type').value;

    if (!topic) {
        showError('Please enter a topic to preview its outline.');
        return;
    }

    const previewEl = document.getElementById('outline-preview');
    previewEl.classList.remove('hidden');
    previewEl.innerHTML = '<p style="color:var(--text-muted);">Consulting medical knowledge base...</p>';

    try {
        const params = new URLSearchParams({ topic, keyword, geo, article_type });
        const res = await fetch(`/outline?${params.toString()}`);
        const data = await res.json();

        if (!data.in_scope) {
            previewEl.innerHTML = `<div class="seo-meta" style="border-color:var(--warning);"><p>⚠️ ${data.scope_note}</p></div>`;
            return;
        }

        const sections = data.planned_sections.map(s => `<li><strong>${s.heading}</strong> <span style="color:var(--text-muted); font-size:0.85rem;">(~${s.target_words} words)</span></li>`).join('');
        const sources = data.grounding_sources.map(s => `<li>${s.title} <span style="color:var(--text-muted); font-size:0.85rem;">(Relevance ${s.relevance_score})</span></li>`).join('');

        previewEl.innerHTML = `
            <div class="glass" style="padding:1.25rem; margin-top:0.75rem;">
                <h4 style="color:var(--primary); margin-bottom:0.5rem;">Article Outline Plan (${data.target_word_count} words target)</h4>
                <p><strong>Sections:</strong></p>
                <ul style="padding-left:1.2rem; margin-bottom:0.75rem;">${sections}</ul>
                <p><strong>Verified Grounding Context:</strong></p>
                <ul style="padding-left:1.2rem;">${sources || '<li>Internal Gut-Health Guidelines</li>'}</ul>
            </div>
        `;
        showToast('Outline preview loaded', 'info');
    } catch (err) {
        previewEl.innerHTML = `<p style="color:var(--danger);">Outline preview failed: ${err.message}</p>`;
    }
});
