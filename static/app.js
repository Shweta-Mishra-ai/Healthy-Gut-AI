/* Generator page controller. */

const esc = Gutfolio.escapeHTML;

const state = {
    mode: 'single',
    lastRequests: [],
    lastSingleMarkdown: '',
    batchMarkdowns: [],
    lastPack: null,
};

/* ---------- mode switching ---------- */

const MODE_FIELDS = {
    single: ['single-fields'],
    batch: ['batch-fields'],
    audit: ['audit-fields'],
};

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.mode = btn.dataset.mode;

        Object.entries(MODE_FIELDS).forEach(([mode, ids]) => {
            ids.forEach(id => document.getElementById(id).classList.toggle('hidden', mode !== state.mode));
        });
        // Article type and tone steer generation; an audit only scores text
        // that already exists, so showing them there implies a control the
        // action does not have.
        document.getElementById('tone-col').classList.toggle('hidden', state.mode === 'audit');
        document.getElementById('article_type').closest('.col').classList.toggle('hidden', false);
        document.getElementById('preview-outline-btn').classList.toggle('hidden', state.mode !== 'single');
        // An outline preview belongs to the single-article request that
        // produced it; leaving it on screen after a mode switch reads as if
        // it describes whatever is now in the form.
        const outline = document.getElementById('outline-preview');
        outline.classList.add('hidden');
        outline.innerHTML = '';
        clearError();
        document.getElementById('generate-btn').textContent =
            state.mode === 'audit' ? 'Run audit' : state.mode === 'batch' ? 'Generate batch' : 'Generate content';
    });
});

/* ---------- errors ---------- */

function showError(msg) {
    const el = document.getElementById('form-error');
    el.textContent = msg;
    el.classList.remove('hidden');
    Gutfolio.toast(msg, 'error');
}

function clearError() {
    const el = document.getElementById('form-error');
    el.textContent = '';
    el.classList.add('hidden');
}

function formatError(status, data) {
    if (status === 429) return `Too many requests — try again in ${data.retry_after_seconds || 'a few'} seconds.`;
    if (status === 422 && data.out_of_scope) return data.error;
    if (status === 422) {
        const details = (data.details || []).map(d => d.msg).join('; ');
        return 'Check the form: ' + (details || data.error || 'one of the fields is invalid.');
    }
    if (status === 401) return 'This deployment requires an access key. Add it from the header.';
    if (status === 502) return 'Every content provider failed for this request. Nothing was saved — try again in a moment.';
    if (status === 503) return data.error || 'A required component is unavailable on the server.';
    return data.error || 'The server returned an unexpected error.';
}

function parseBatchInput(raw) {
    return raw.split('\n').map(l => l.trim()).filter(Boolean).map(line => {
        const [topic, keyword, geo] = line.split('|').map(p => (p || '').trim());
        return { topic, primary_keyword: keyword, geo_target: geo };
    });
}

/* ---------- shared blocks ---------- */

function metricsBlock(data) {
    const density = data.metrics?.keywordDensity?.keywordDensityPercent ?? 0;
    const readabilityScore = data.metrics?.readability?.fleschReadingEase;
    const readability = (readabilityScore === null || readabilityScore === undefined) ? 'n/a' : readabilityScore;
    const words = data.metrics?.wordCount ?? 0;
    const risk = data.compliance?.risk_level;
    return `
<div class="metrics-grid">
<div class="metric-card"><h3>${scoreBadge(data.quality?.score)}</h3><p>Quality score</p></div>
<div class="metric-card"><h3>${esc(words)}</h3><p>Words</p></div>
<div class="metric-card"><h3>${esc(density)}%</h3><p>Keyword density</p></div>
<div class="metric-card"><h3>${esc(readability)}</h3><p>Readability</p></div>
<div class="metric-card"><h3>${riskPill(risk)}</h3><p>Claim risk</p></div>
</div>${qualityFlagsBlock(data.quality?.flags)}`;
}

const RISK_LABELS = { blocked: 'Blocked', review: 'Review', clear: 'Clear' };

function riskPill(risk) {
    if (!risk) return '<span class="status-pill pill-draft">n/a</span>';
    const cls = risk === 'blocked' ? 'pill-fail' : risk === 'review' ? 'pill-draft' : 'pill-ok';
    return `<span class="status-pill ${cls}">${esc(RISK_LABELS[risk] || risk)}</span>`;
}

function complianceBlock(compliance) {
    if (!compliance) return '<p class="muted">No compliance scan available for this article.</p>';
    const { counts = {}, findings = [], risk_level: risk } = compliance;
    const summary = risk === 'clear'
        ? 'No claim-risk patterns found. The article still needs a human reviewer, but nothing here blocks publishing.'
        : risk === 'blocked'
            ? 'Fix every blocker below before this goes live. Blockers are the claims that get health pages demoted or ad accounts suspended.'
            : 'Nothing blocking, but an editor should confirm the items below.';

    const list = findings.length ? findings.map(f => `
<li class="finding finding-${esc(f.severity)}">
<div class="finding-head">
<span class="finding-severity">${esc(f.severity)}</span>
<span class="finding-code">${esc(f.code.replace(/_/g, ' '))}</span>
</div>
<p class="finding-message">${esc(f.message)}</p>
${f.evidence ? `<blockquote class="finding-evidence">${esc(f.evidence)}</blockquote>` : ''}
</li>`).join('') : '<li class="finding finding-clear"><p class="finding-message">Nothing flagged.</p></li>';

    return `
<div class="panel-note">${riskPill(risk)} <span>${esc(summary)}</span></div>
<p class="muted small">${esc(counts.blocker || 0)} blockers · ${esc(counts.warning || 0)} warnings · ${esc(counts.notice || 0)} notices · ${esc(compliance.checked_rules || 0)} rules checked</p>
<ul class="findings-list">${list}</ul>`;
}

function seoBlock(data) {
    const seo = data.seo || {};
    const social = seo.social || {};
    const tags = social.tags || {};
    const variants = data.meta_description_variants || (data.meta_description ? [data.meta_description] : []);
    const jsonLd = JSON.stringify(data.schema_json_ld || seo.structured_data || {}, null, 2);

    const titles = (social.title_tag_variants || []).map(t => `
<li><span>${esc(t)}</span><small>${esc(t.length)} chars</small>
<button type="button" class="btn-small-copy" data-copy="${esc(t)}">Copy</button></li>`).join('');

    const metas = variants.map(v => `
<li><span>${esc(v)}</span><small>${esc(v.length)} chars</small>
<button type="button" class="btn-small-copy" data-copy="${esc(v)}">Copy</button></li>`).join('');

    const tagRows = Object.entries(tags).map(([k, v]) => `
<tr><td><code>${esc(k)}</code></td><td>${esc(v)}</td></tr>`).join('');

    const toc = (seo.table_of_contents || []).map(t =>
        `<li class="toc-l${esc(t.level)}">${esc(t.text)}</li>`).join('');

    return `
<h4>Title tag candidates</h4>
<ul class="meta-variants-list">${titles || '<li><span class="muted">None generated.</span></li>'}</ul>

<h4>Meta description variants</h4>
<ul class="meta-variants-list">${metas || '<li><span class="muted">None generated.</span></li>'}</ul>

<h4>URL slug</h4>
<p><code>/${esc(data.url_slug || '')}</code></p>

<h4>Calls to action</h4>
<p><strong>Soft:</strong> ${esc(data.cta_soft || 'None')}</p>
<p><strong>Direct:</strong> ${esc(data.cta_direct || 'None')}</p>

<h4>Structured data</h4>
<p class="muted small">Article, FAQ and breadcrumb markup built from the finished article — paste into a <code>&lt;script type="application/ld+json"&gt;</code> tag in the page head.</p>
<div class="code-actions"><button type="button" class="btn-secondary" data-copy-target="json-ld-block">Copy JSON-LD</button></div>
<pre class="code-block" id="json-ld-block"><code>${esc(jsonLd)}</code></pre>

<h4>Social tags</h4>
<div class="table-scroll"><table class="kv-table"><tbody>${tagRows}</tbody></table></div>

<h4>On-page outline</h4>
<ul class="toc-list">${toc || '<li class="muted">No headings detected.</li>'}</ul>`;
}

function sourcesBlock(data) {
    const rag = data.rag_sources || [];
    const links = data.internal_link_suggestions || [];
    const dup = data.duplication;

    const ragItems = rag.length ? rag.map(s => `
<li><strong>${esc(s.title)}</strong> <span class="muted">relevance ${esc(s.relevance_score)}</span></li>`).join('')
        : '<li class="muted">No knowledge-base chunk matched this topic.</li>';

    const linkItems = links.length ? links.map(s => `
<li><strong>${esc(s.topic)}</strong> <span class="muted">relevance ${esc(s.relevance_score)}</span><br>
<small class="muted">/${esc(s.url_slug || '')}</small></li>`).join('')
        : '<li class="muted">Approve related articles in the review queue and they will appear here as internal-link targets.</li>';

    let dupBlock = '';
    if (dup) {
        const cls = dup.status === 'duplicate' ? 'pill-fail' : dup.status === 'cannibalisation_risk' ? 'pill-draft' : 'pill-ok';
        const label = dup.status === 'duplicate' ? 'Duplicate' : dup.status === 'cannibalisation_risk' ? 'Competing' : 'Unique';
        const rows = [...(dup.near_duplicates || []), ...(dup.related || [])].map(d => `
<li><strong>${esc(d.topic)}</strong> <span class="muted">${esc(Math.round(d.similarity * 100))}% similar · ${esc(d.status)}</span></li>`).join('');
        dupBlock = `
<h4>Library overlap</h4>
<div class="panel-note"><span class="status-pill ${cls}">${esc(label)}</span> <span>${esc(dup.summary || '')}</span></div>
<p class="muted small">Compared against ${esc(dup.corpus_size || 0)} stored article(s).</p>
${rows ? `<ul class="plain-list">${rows}</ul>` : ''}`;
    }

    return `
<h4>Grounding sources used</h4>
<ul class="plain-list">${ragItems}</ul>
<h4>Suggested internal links</h4>
<ul class="plain-list">${linkItems}</ul>
${dupBlock}`;
}

function providerNote(data) {
    if (!data.provider_note) return '';
    return `<div class="panel-note note-warn"><span>${esc(data.provider_note)}</span></div>`;
}

function languageNote(data) {
    const check = data.language_check;
    if (!check || check.ok) return '';
    return `<div class="panel-note note-warn"><span>Language check: ${esc(check.reason)}</span></div>`;
}

/* ---------- single result ---------- */

function resultShell(data, headerHTML) {
    return `
${headerHTML}
${providerNote(data)}
${languageNote(data)}
${metricsBlock(data)}
<div class="result-tabs">
<div role="tablist" aria-label="Result sections" class="tab-strip">
<button role="tab" id="tab-article" aria-controls="panel-article" aria-selected="true" class="tab-btn">Article</button>
<button role="tab" id="tab-seo" aria-controls="panel-seo" aria-selected="false" tabindex="-1" class="tab-btn">Search pack</button>
<button role="tab" id="tab-compliance" aria-controls="panel-compliance" aria-selected="false" tabindex="-1" class="tab-btn">Compliance</button>
<button role="tab" id="tab-sources" aria-controls="panel-sources" aria-selected="false" tabindex="-1" class="tab-btn">Sources</button>
</div>
<div role="tabpanel" id="panel-article" aria-labelledby="tab-article" class="tab-panel">
<div class="article-content">${Gutfolio.renderMarkdown(data.optimized_article_markdown)}</div>
</div>
<div role="tabpanel" id="panel-seo" aria-labelledby="tab-seo" class="tab-panel hidden">${seoBlock(data)}</div>
<div role="tabpanel" id="panel-compliance" aria-labelledby="tab-compliance" class="tab-panel hidden">${complianceBlock(data.compliance)}</div>
<div role="tabpanel" id="panel-sources" aria-labelledby="tab-sources" class="tab-panel hidden">${sourcesBlock(data)}</div>
</div>`;
}

function renderSingleResult(data) {
    const panel = document.getElementById('results');
    state.lastSingleMarkdown = data.optimized_article_markdown || '';
    const providerBadge = data.cached ? 'Cached' : Gutfolio.providerLabel(data.provider_used);

    const header = `
<div class="results-header">
<div>
<h2>Generated article <span class="status-pill pill-ok">${esc(providerBadge)}</span></h2>
<p class="muted small">In the review queue as <code>${esc(data.review_id || 'draft')}</code> — approve it there before publishing.</p>
</div>
<div class="button-row">
<button type="button" class="btn-secondary" data-export="docx">DOCX</button>
<button type="button" class="btn-secondary" data-export="pdf">PDF</button>
<button type="button" class="btn-secondary" data-export="markdown" data-ext="md">Markdown</button>
<button type="button" class="btn-secondary" data-export="json">JSON</button>
<button type="button" class="btn-primary btn-inline" id="copy-article-btn">Copy article</button>
</div>
</div>`;

    panel.innerHTML = resultShell(data, header);
    panel.classList.remove('hidden');
    Gutfolio.initTabs(panel);
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    panel.querySelectorAll('[data-export]').forEach(btn => {
        btn.addEventListener('click', () => downloadExport(btn.dataset.export, btn.dataset.ext));
    });
    document.getElementById('copy-article-btn')
        .addEventListener('click', e => Gutfolio.copy(state.lastSingleMarkdown, e.currentTarget));
}

/* ---------- audit result ---------- */

function renderAuditResult(data) {
    const panel = document.getElementById('results');
    const header = `
<div class="results-header">
<div>
<h2>Audit report <span class="status-pill pill-draft">no content generated</span></h2>
<p class="muted small">${esc(data.topic || 'Pasted article')}</p>
</div>
</div>`;
    panel.innerHTML = `
${header}
${languageNote(data)}
${metricsBlock(data)}
<div class="result-tabs">
<div role="tablist" aria-label="Audit sections" class="tab-strip">
<button role="tab" id="tab-compliance" aria-controls="panel-compliance" aria-selected="true" class="tab-btn">Compliance</button>
<button role="tab" id="tab-seo" aria-controls="panel-seo" aria-selected="false" tabindex="-1" class="tab-btn">Search pack</button>
<button role="tab" id="tab-sources" aria-controls="panel-sources" aria-selected="false" tabindex="-1" class="tab-btn">Library overlap</button>
</div>
<div role="tabpanel" id="panel-compliance" aria-labelledby="tab-compliance" class="tab-panel">${complianceBlock(data.compliance)}</div>
<div role="tabpanel" id="panel-seo" aria-labelledby="tab-seo" class="tab-panel hidden">${seoBlock({ ...data, schema_json_ld: data.seo?.structured_data })}</div>
<div role="tabpanel" id="panel-sources" aria-labelledby="tab-sources" class="tab-panel hidden">${sourcesBlock(data)}</div>
</div>`;
    panel.classList.remove('hidden');
    Gutfolio.initTabs(panel);
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ---------- batch ---------- */

function batchRowMarkup(index, topic, status, detail) {
    const cls = status === 'done' ? 'pill-ok' : status === 'failed' ? 'pill-fail' : 'pill-draft';
    const label = status === 'done' ? 'Done' : status === 'failed' ? 'Failed' : 'Queued';
    return `
<div class="batch-row" id="batch-row-${index}">
<span class="status-pill ${cls}">${label}</span>
<span class="batch-topic">${esc(topic)}</span>
<span class="muted small batch-detail">${esc(detail || '')}</span>
</div>`;
}

function renderBatchSkeleton(requests) {
    const el = document.getElementById('batch-progress');
    el.innerHTML = `
<div class="batch-head"><strong>Batch progress</strong><span class="muted small" id="batch-count">0 / ${requests.length}</span></div>
${requests.map((r, i) => batchRowMarkup(i, r.topic || `Item ${i + 1}`, 'queued', 'waiting')).join('')}`;
    el.classList.remove('hidden');
}

function updateBatchRow(index, topic, result) {
    const row = document.getElementById(`batch-row-${index}`);
    if (!row) return;
    const failed = Boolean(result.error);
    const detail = failed
        ? result.error
        : `${result.metrics?.wordCount ?? 0} words · quality ${result.quality?.score ?? '—'} · ${result.compliance?.risk_level ?? 'n/a'}`;
    row.outerHTML = batchRowMarkup(index, topic, failed ? 'failed' : 'done', detail);
}

function renderBatchResults(results, requests) {
    const panel = document.getElementById('results');
    state.batchMarkdowns = results.map(r => (r && r.optimized_article_markdown) || '');
    const succeeded = results.filter(r => r && !r.error).length;

    const items = results.map((r, i) => {
        const label = requests[i]?.topic || `Item ${i + 1}`;
        if (!r || r.error) {
            const scopeNote = r && r.out_of_scope ? ' (outside this tool’s scope)' : '';
            return `<div class="batch-failure"><strong>${esc(label)}</strong>: ${esc((r && r.error) || 'no result')}${esc(scopeNote)}</div>`;
        }
        return `
<details class="batch-item">
<summary>
<strong>${esc(label)}</strong>
<span class="status-pill pill-ok">${esc(Gutfolio.providerLabel(r.provider_used))}</span>
<span class="muted small">${esc(r.metrics?.wordCount ?? 0)} words</span>
${riskPill(r.compliance?.risk_level)}
</summary>
<div class="batch-body">
${metricsBlock(r)}
<div class="article-content">${Gutfolio.renderMarkdown(r.optimized_article_markdown)}</div>
<div class="button-row">
<button type="button" class="btn-secondary" data-batch-export="docx" data-index="${i}">DOCX</button>
<button type="button" class="btn-secondary" data-batch-export="pdf" data-index="${i}">PDF</button>
<button type="button" class="btn-secondary" data-batch-copy="${i}">Copy</button>
</div>
</div>
</details>`;
    }).join('');

    panel.innerHTML = `
<div class="results-header">
<h2>Batch results <span class="muted small">${esc(succeeded)} of ${esc(results.length)} succeeded</span></h2>
<div class="button-row">
<button type="button" class="btn-primary btn-inline" id="download-zip-btn">Download ZIP bundle</button>
<button type="button" class="btn-secondary" id="copy-all-btn">Copy all</button>
</div>
</div>
${items}`;
    panel.classList.remove('hidden');
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    panel.querySelectorAll('[data-batch-export]').forEach(btn => {
        btn.addEventListener('click', () => downloadOneFromBatch(Number(btn.dataset.index), btn.dataset.batchExport));
    });
    panel.querySelectorAll('[data-batch-copy]').forEach(btn => {
        btn.addEventListener('click', e => Gutfolio.copy(state.batchMarkdowns[Number(btn.dataset.batchCopy)], e.currentTarget));
    });
    document.getElementById('download-zip-btn').addEventListener('click', downloadBatchZip);
    document.getElementById('copy-all-btn').addEventListener('click', e => {
        const combined = results.map((r, i) => {
            const label = requests[i]?.topic || `Article ${i + 1}`;
            if (!r || r.error) return `## ${label}\n\n_Failed: ${(r && r.error) || 'no result'}_`;
            return `## ${label}\n\n${r.optimized_article_markdown || ''}`;
        }).join('\n\n---\n\n');
        Gutfolio.copy(combined, e.currentTarget);
    });
}

/* Reads the NDJSON stream line by line. Each finished article is painted as
   it lands rather than after the whole batch, which is what keeps a ten-item
   run from dying behind a proxy timeout with nothing to show for it. */
async function runStreamingBatch(requests) {
    renderBatchSkeleton(requests);
    const results = new Array(requests.length).fill(null);

    const res = await Gutfolio.apiFetch('/generate/batch/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: requests }),
    });

    if (!res.ok) {
        let data = {};
        try { data = await res.json(); } catch { /* non-JSON error body */ }
        showError(formatError(res.status, data));
        return null;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let completed = 0;

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
            if (!line.trim()) continue;
            let event;
            try { event = JSON.parse(line); } catch { continue; }
            if (event.type === 'item') {
                results[event.index] = event.result;
                updateBatchRow(event.index, event.topic, event.result);
                completed = event.completed;
                const counter = document.getElementById('batch-count');
                if (counter) counter.textContent = `${completed} / ${event.total}`;
            }
        }
    }
    return results;
}

/* ---------- submit ---------- */

document.getElementById('generate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    clearError();

    const loading = document.getElementById('loading');
    const resultsPanel = document.getElementById('results');
    const progress = document.getElementById('batch-progress');
    const btn = document.getElementById('generate-btn');
    const article_type = document.getElementById('article_type').value;
    const language = document.getElementById('language').value;
    const tone = document.getElementById('tone').value;

    btn.disabled = true;
    resultsPanel.classList.add('hidden');
    progress.classList.add('hidden');
    if (state.mode !== 'batch') loading.classList.remove('hidden');

    try {
        if (state.mode === 'single') {
            const payload = {
                topic: document.getElementById('topic').value,
                primary_keyword: document.getElementById('primary_keyword').value,
                geo_target: document.getElementById('geo_target').value,
                article_type, language, tone,
            };
            if (!payload.topic.trim() || !payload.primary_keyword.trim() || !payload.geo_target.trim()) {
                showError('Topic, primary keyword and geo target are all required.');
                return;
            }
            state.lastRequests = [payload];
            const res = await Gutfolio.apiFetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) showError(formatError(res.status, data));
            else {
                renderSingleResult(data);
                Gutfolio.toast('Article generated and queued for review.', 'success');
            }
        } else if (state.mode === 'audit') {
            const markdown = document.getElementById('audit_markdown').value;
            if (markdown.trim().length < 50) {
                showError('Paste at least a few sentences of article text to audit.');
                return;
            }
            const res = await Gutfolio.apiFetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    article_markdown: markdown,
                    topic: document.getElementById('audit_topic').value,
                    primary_keyword: document.getElementById('audit_keyword').value,
                    article_type, language,
                }),
            });
            const data = await res.json();
            if (!res.ok) showError(formatError(res.status, data));
            else {
                renderAuditResult(data);
                Gutfolio.toast('Audit complete.', 'success');
            }
        } else {
            const rawItems = parseBatchInput(document.getElementById('batch_topics').value)
                .map(it => ({ ...it, article_type, language, tone }));
            const incomplete = rawItems.filter(it => !it.topic || !it.primary_keyword || !it.geo_target);
            if (rawItems.length === 0) {
                showError('Add at least one line in the form: topic | keyword | geo.');
                return;
            }
            if (incomplete.length) {
                showError(`${incomplete.length} line(s) are missing a keyword or geo target — each line needs all three parts.`);
                return;
            }
            state.lastRequests = rawItems;
            const results = await runStreamingBatch(rawItems);
            if (results) {
                renderBatchResults(results, rawItems);
                const ok = results.filter(r => r && !r.error).length;
                Gutfolio.toast(`Batch finished — ${ok} of ${results.length} succeeded.`, ok === results.length ? 'success' : 'warning');
            }
        }
    } catch (err) {
        console.error(err);
        showError('Could not reach the server. Check your connection and try again.');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
});

/* ---------- exports ---------- */

async function downloadBlob(url, body, filename, label) {
    const res = await Gutfolio.apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        let data = {};
        try { data = await res.json(); } catch { /* binary or empty error body */ }
        showError(data.error || `${label} export failed.`);
        return;
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
    Gutfolio.toast(`${label} downloaded.`, 'success');
}

function safeFilename(topic, ext) {
    return `${(topic || 'article').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'article'}.${ext}`;
}

async function downloadExport(kind, ext) {
    const payload = state.lastRequests[0];
    if (!payload) return;
    await downloadBlob(`/export/${kind}`, payload, safeFilename(payload.topic, ext || kind), (ext || kind).toUpperCase());
}

async function downloadOneFromBatch(index, kind) {
    const payload = state.lastRequests[index];
    if (!payload) return;
    await downloadBlob(`/export/${kind}`, payload, safeFilename(payload.topic, kind), kind.toUpperCase());
}

async function downloadBatchZip() {
    const btn = document.getElementById('download-zip-btn');
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Bundling...';
    try {
        await downloadBlob('/export/batch/zip', { items: state.lastRequests }, 'gutfolio-batch.zip', 'ZIP bundle');
    } finally {
        btn.disabled = false;
        btn.textContent = original;
    }
}

/* ---------- outline preview ---------- */

document.getElementById('preview-outline-btn').addEventListener('click', async () => {
    const topic = document.getElementById('topic').value.trim();
    const keyword = document.getElementById('primary_keyword').value.trim();
    const geo = document.getElementById('geo_target').value.trim();
    const article_type = document.getElementById('article_type').value;

    if (!topic) {
        showError('Enter a topic first — the outline is built from it.');
        return;
    }

    const previewEl = document.getElementById('outline-preview');
    previewEl.classList.remove('hidden');
    previewEl.innerHTML = '<p class="muted">Checking scope and retrieving grounding sources...</p>';

    try {
        const params = new URLSearchParams({ topic, keyword, geo, article_type });
        const res = await Gutfolio.apiFetch(`/outline?${params.toString()}`);
        const data = await res.json();

        if (!res.ok) {
            previewEl.innerHTML = `<div class="panel-note note-warn"><span>${esc(formatError(res.status, data))}</span></div>`;
            return;
        }
        if (!data.in_scope) {
            previewEl.innerHTML = `<div class="panel-note note-warn"><span>${esc(data.scope_note)}</span></div>`;
            return;
        }

        const sections = data.planned_sections.map(s =>
            `<li><strong>${esc(s.heading)}</strong> <span class="muted small">~${esc(s.target_words)} words</span></li>`).join('');
        const sources = data.grounding_sources.map(s =>
            `<li>${esc(s.title)} <span class="muted small">relevance ${esc(s.relevance_score)}</span></li>`).join('');

        previewEl.innerHTML = `
<div class="outline-card">
<h4>Planned structure — ${esc(data.target_word_count)} words</h4>
<ul class="plain-list">${sections}</ul>
<h4>Grounding sources</h4>
<ul class="plain-list">${sources || '<li class="muted">General gut-health guidance</li>'}</ul>
</div>`;
    } catch (err) {
        previewEl.innerHTML = `<div class="panel-note note-warn"><span>Outline preview failed: ${esc(err.message)}</span></div>`;
    }
});

/* Copy buttons are rendered inside generated HTML, so they are handled by
   delegation instead of inline handlers — no user or model content is ever
   interpolated into executable attribute code. */
document.addEventListener('click', e => {
    const copyBtn = e.target.closest('[data-copy]');
    if (copyBtn) {
        Gutfolio.copy(copyBtn.dataset.copy, copyBtn);
        return;
    }
    // Multi-line payloads (the JSON-LD block) live in the DOM rather than in
    // an attribute — attribute values normalise whitespace, which would
    // reformat the markup on its way to the clipboard.
    const targetBtn = e.target.closest('[data-copy-target]');
    if (targetBtn) {
        const el = document.getElementById(targetBtn.dataset.copyTarget);
        if (el) Gutfolio.copy(el.textContent, targetBtn);
    }
});
