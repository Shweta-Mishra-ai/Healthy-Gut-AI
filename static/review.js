const esc = Gutfolio.escapeHTML;
let currentStatus = 'draft';
// Items of the currently shown tab, by id — the regenerate action needs the
// original request (geo, language, type, tone) that each summary carries.
const queueItems = new Map();

const RISK_LABEL = { blocked: 'Blocked', review: 'Review', clear: 'Clear' };

function riskPill(risk) {
    if (!risk) return '';
    const cls = risk === 'blocked' ? 'pill-fail' : risk === 'review' ? 'pill-draft' : 'pill-ok';
    return `<span class="status-pill ${cls}">${esc(RISK_LABEL[risk] || risk)}</span>`;
}

function duplicationPill(status) {
    if (!status || status === 'clear') return '';
    const label = status === 'duplicate' ? 'Duplicate' : 'Competing keyword';
    return `<span class="status-pill pill-draft">${esc(label)}</span>`;
}

async function loadCounts() {
    try {
        const res = await Gutfolio.apiFetch('/review/counts');
        if (!res.ok) return;
        const c = await res.json();
        document.getElementById('counts-summary').textContent =
            `${c.total} total · ${c.draft} pending · ${c.approved} approved · ${c.rejected} rejected`;
    } catch (err) {
        console.error(err);
    }
}

async function loadQueue(status) {
    currentStatus = status;
    document.querySelectorAll('.tabs .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.status === status));
    const listEl = document.getElementById('queue-list');
    listEl.innerHTML = '<p class="muted">Loading...</p>';

    try {
        const res = await Gutfolio.apiFetch(`/review/queue?status=${encodeURIComponent(status)}`);
        if (!res.ok) {
            listEl.innerHTML = '<p class="empty-state">Could not load the queue. Check your access key and refresh.</p>';
            return;
        }
        const data = await res.json();
        queueItems.clear();
        data.items.forEach(item => queueItems.set(item.id, item));

        if (!data.items.length) {
            listEl.innerHTML = `<p class="empty-state">Nothing ${esc(status)} right now.</p>`;
            return;
        }

        listEl.innerHTML = data.items.map(item => `
<article class="review-card">
<div class="review-card-head">
<h3>${esc(item.topic)}</h3>
<div class="button-row">
${riskPill(item.compliance_risk)}
${duplicationPill(item.duplication_status)}
<span class="status-pill pill-${item.status === 'approved' ? 'ok' : item.status === 'rejected' ? 'fail' : 'draft'}">${esc(item.status)}</span>
</div>
</div>
<div class="review-meta">
<span>Keyword <strong>${esc(item.primary_keyword)}</strong></span>
<span>Provider <strong>${esc(item.provider_used ? Gutfolio.providerLabel(item.provider_used) : '—')}</strong></span>
<span>Quality ${scoreBadge(item.quality_score)}</span>
<span>Words <strong>${esc(item.word_count ?? '—')}</strong></span>
</div>
${qualityFlagsBlock(item.quality_flags)}
${item.reviewer_badge ? `<div class="badge-verified">${esc(item.reviewer_badge)}</div>` : ''}
${item.reviewer_note ? `<p class="muted small mt-2xs">Note: ${esc(item.reviewer_note)}</p>` : ''}
<div class="review-actions">
<button type="button" class="btn-secondary" data-view="${esc(item.id)}">Read full draft</button>
${status === 'draft' ? `
<button type="button" class="btn-secondary" data-edit="${esc(item.id)}">Edit draft</button>
<button type="button" class="btn-action approve" data-action="approve" data-id="${esc(item.id)}">Approve and sign</button>
<button type="button" class="btn-action reject" data-action="reject" data-id="${esc(item.id)}">Reject</button>` : ''}
${status === 'approved' ? `
<button type="button" class="btn-secondary" data-publish="${esc(item.id)}" data-dry="true">Dry run to WordPress</button>
<button type="button" class="btn-primary btn-inline" data-publish="${esc(item.id)}" data-dry="false">${item.wp_post_id ? 'Update WordPress post' : 'Publish to WordPress'}</button>` : ''}
${status === 'rejected' && item.request ? `
<button type="button" class="btn-secondary" data-regenerate="${esc(item.id)}">Regenerate with this feedback</button>` : ''}
${/^https?:\/\//i.test(item.wp_post_url || '') ? `<a class="muted small" href="${esc(item.wp_post_url)}" target="_blank" rel="noopener noreferrer">Open WordPress post</a>` : ''}
</div>
<div id="wp-result-${esc(item.id)}" class="hidden mt-sm text-sm"></div>
<div id="article-body-${esc(item.id)}" class="hidden article-content mt-md"></div>
<div id="editor-${esc(item.id)}" class="hidden review-editor mt-md"></div>
</article>`).join('');
    } catch (err) {
        listEl.innerHTML = `<p class="empty-state">Failed to load the queue: ${esc(err.message)}</p>`;
    }
}

async function viewArticle(id) {
    const el = document.getElementById(`article-body-${id}`);
    if (!el.classList.contains('hidden')) { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    el.innerHTML = '<p class="muted">Loading draft...</p>';
    const res = await Gutfolio.apiFetch(`/review/${encodeURIComponent(id)}`);
    if (!res.ok) {
        el.innerHTML = '<p class="muted">Could not load this draft.</p>';
        return;
    }
    const data = await res.json();
    const compliance = data.article?.compliance;
    const blockers = (compliance?.findings || []).filter(f => f.severity === 'blocker');
    const warning = blockers.length
        ? `<div class="panel-note note-warn"><span>${esc(blockers.length)} compliance blocker(s) must be fixed before this can publish: ${esc(blockers.map(b => b.code.replace(/_/g, ' ')).join(', '))}.</span></div>`
        : '';
    el.innerHTML = warning + Gutfolio.renderMarkdown(data.article?.optimized_article_markdown);
}

/* ---------- regenerate after rejection ---------- */

async function regenerate(id, button) {
    const item = queueItems.get(id);
    if (!item || !item.request) return;
    button.disabled = true;
    button.textContent = 'Generating...';
    try {
        const res = await Gutfolio.apiFetch('/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(item.request),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            Gutfolio.toast(`Could not regenerate: ${data.error || 'unknown error'}`, 'error');
            return;
        }
        const fb = data.reviewer_feedback;
        const how = fb && !fb.applied
            ? ' The offline template cannot use the feedback — configure a provider for that.'
            : fb ? ' The reviewer note was given to the writer.' : '';
        Gutfolio.toast(`New draft created.${how}`, fb && !fb.applied ? 'warning' : 'success');
        await loadCounts();
        await loadQueue('draft');
    } catch (err) {
        Gutfolio.toast(`Regenerate failed: ${err.message}`, 'error');
    } finally {
        button.disabled = false;
        button.textContent = 'Regenerate with this feedback';
    }
}

/* ---------- reviewer edits ---------- */

async function openEditor(id) {
    const el = document.getElementById(`editor-${id}`);
    if (!el.classList.contains('hidden')) { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    el.innerHTML = '<p class="muted">Loading draft...</p>';
    const res = await Gutfolio.apiFetch(`/review/${encodeURIComponent(id)}`);
    if (!res.ok) {
        el.innerHTML = '<p class="muted">Could not load this draft.</p>';
        return;
    }
    const data = await res.json();
    const article = data.article || {};
    el.innerHTML = `
<label for="meta-${esc(id)}">Meta description</label>
<input type="text" id="meta-${esc(id)}" maxlength="320" value="${esc(article.meta_description || '')}">
<label for="md-${esc(id)}" class="mt-sm">Article (Markdown)</label>
<textarea id="md-${esc(id)}" rows="22" spellcheck="true">${esc(article.optimized_article_markdown || '')}</textarea>
<label for="editor-name-${esc(id)}" class="mt-sm">Your name (optional)</label>
<input type="text" id="editor-name-${esc(id)}" maxlength="100">
<p class="muted small mt-xs">Saving re-scores the article — quality, claim risk, SEO pack and duplicate check. The medical disclaimer is added back if it was removed.</p>
<div class="button-row mt-xs">
<button type="button" class="btn-primary btn-inline" data-save-edit="${esc(id)}">Save changes</button>
<button type="button" class="btn-secondary" data-cancel-edit="${esc(id)}">Cancel</button>
</div>`;
}

async function saveEdit(id, button) {
    const body = {
        article_markdown: document.getElementById(`md-${id}`).value,
        meta_description: document.getElementById(`meta-${id}`).value,
        editor_name: document.getElementById(`editor-name-${id}`).value,
    };
    button.disabled = true;
    try {
        const res = await Gutfolio.apiFetch(`/review/${encodeURIComponent(id)}/edit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const details = (data.details || []).map(d => d.msg).join('; ');
            Gutfolio.toast(`Could not save: ${details || data.error || 'unknown error'}`, 'error');
            return;
        }
        const blockers = data.article?.compliance?.counts?.blocker || 0;
        Gutfolio.toast(
            `Saved. Quality ${data.article?.quality?.score ?? '—'}${blockers ? ` — ${blockers} compliance blocker(s) remain` : ''}.`,
            blockers ? 'warning' : 'success',
        );
        await loadCounts();
        await loadQueue(currentStatus);
    } catch (err) {
        Gutfolio.toast(`Save failed: ${err.message}`, 'error');
    } finally {
        button.disabled = false;
    }
}

async function reviewAction(id, action) {
    const note = prompt(`Optional note for this ${action}:`) || '';
    let reviewer_name = '';
    let reviewer_credential = '';
    if (action === 'approve') {
        reviewer_name = prompt('Reviewer name (for example: Dr. Ananya Roy):') || '';
        if (reviewer_name) {
            reviewer_credential = prompt('Credential (for example: MD, Gastroenterologist):') || '';
        }
    }
    try {
        const res = await Gutfolio.apiFetch(`/review/${encodeURIComponent(id)}/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note, reviewer_name, reviewer_credential }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            Gutfolio.toast(`Could not ${action}: ${err.error || 'unknown error'}`, 'error');
            return;
        }
        Gutfolio.toast(`Article ${action === 'approve' ? 'approved' : 'rejected'}.`, 'success');
        await loadCounts();
        await loadQueue(currentStatus);
    } catch (err) {
        Gutfolio.toast(`Review action failed: ${err.message}`, 'error');
    }
}

async function publishToWordPress(id, dryRun, overrideCompliance = false) {
    const resultEl = document.getElementById(`wp-result-${id}`);
    resultEl.classList.remove('hidden');
    resultEl.innerHTML = '<p class="muted">Contacting WordPress...</p>';

    try {
        const params = new URLSearchParams({
            status: 'draft',
            dry_run: String(dryRun),
            override_compliance: String(overrideCompliance),
        });
        const res = await Gutfolio.apiFetch(`/publish/wordpress/${encodeURIComponent(id)}?${params}`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));

        if (res.status === 409 && data.compliance_blockers) {
            const list = data.compliance_blockers.map(b => `<li>${esc(b.message)}</li>`).join('');
            resultEl.innerHTML = `
<div class="panel-note note-warn"><span>${esc(data.error)}</span></div>
<ul class="plain-list">${list}</ul>
<div class="button-row mt-xs">
<button type="button" class="btn-secondary" data-override="${esc(id)}" data-dry="${String(dryRun)}">Publish anyway</button>
</div>`;
            return;
        }
        if (!res.ok) {
            resultEl.innerHTML = `<div class="panel-note note-warn"><span>${esc(data.error || 'Publish failed.')}</span></div>`;
            return;
        }
        if (dryRun) {
            const verb = data.updates_existing ? 'update the existing post' : 'create the draft';
            resultEl.innerHTML = `<p>Dry run succeeded — would ${verb} <strong>${esc(data.would_send?.title || '')}</strong>.</p>`;
            Gutfolio.toast('WordPress dry run verified.', 'success');
        } else {
            const done = data.updated_existing ? 'Updated the existing WordPress post.' : 'Published as a WordPress draft.';
            resultEl.innerHTML = `<p>${done} <a href="${esc(/^https?:\/\//i.test(data.post_url || '') ? data.post_url : '#')}" target="_blank" rel="noopener noreferrer">Open the post</a></p>`;
            Gutfolio.toast(data.updated_existing ? 'WordPress post updated.' : 'Published to WordPress.', 'success');
            await loadQueue(currentStatus);
        }
    } catch (err) {
        resultEl.innerHTML = `<div class="panel-note note-warn"><span>Connection error: ${esc(err.message)}</span></div>`;
    }
}

document.querySelectorAll('.tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => loadQueue(btn.dataset.status));
});

document.getElementById('queue-list').addEventListener('click', e => {
    const view = e.target.closest('[data-view]');
    if (view) return viewArticle(view.dataset.view);
    const regen = e.target.closest('[data-regenerate]');
    if (regen) return regenerate(regen.dataset.regenerate, regen);
    const edit = e.target.closest('[data-edit]');
    if (edit) return openEditor(edit.dataset.edit);
    const save = e.target.closest('[data-save-edit]');
    if (save) return saveEdit(save.dataset.saveEdit, save);
    const cancel = e.target.closest('[data-cancel-edit]');
    if (cancel) return document.getElementById(`editor-${cancel.dataset.cancelEdit}`).classList.add('hidden');
    const action = e.target.closest('[data-action]');
    if (action) return reviewAction(action.dataset.id, action.dataset.action);
    const publish = e.target.closest('[data-publish]');
    if (publish) return publishToWordPress(publish.dataset.publish, publish.dataset.dry === 'true');
    const override = e.target.closest('[data-override]');
    if (override) return publishToWordPress(override.dataset.override, override.dataset.dry === 'true', true);
});

loadCounts();
loadQueue('draft');
