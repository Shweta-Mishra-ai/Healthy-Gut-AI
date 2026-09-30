const esc = Gutfolio.escapeHTML;

async function loadDashboard() {
    const summary = document.getElementById('dash-summary');
    const tbody = document.querySelector('#dash-table tbody');
    try {
        const res = await Gutfolio.apiFetch('/dashboard/stats?recent=30');
        if (!res.ok) {
            summary.innerHTML = '<p class="empty-state">Could not load stats. Check your access key and refresh.</p>';
            return;
        }
        const data = await res.json();

        summary.innerHTML = `
<div class="dash-card"><h3>${esc(data.total_requests)}</h3><p>Total requests</p></div>
<div class="dash-card"><h3>${esc(data.succeeded)}</h3><p>Succeeded</p></div>
<div class="dash-card"><h3>${esc(data.out_of_scope)}</h3><p>Out of scope</p></div>
<div class="dash-card"><h3>${esc(data.failed)}</h3><p>Failed</p></div>
<div class="dash-card"><h3>${scoreBadge(data.avg_quality_score ? Math.round(data.avg_quality_score) : data.avg_quality_score)}</h3><p>Average quality</p></div>
<div class="dash-card"><h3>${esc(data.avg_word_count)}</h3><p>Average words</p></div>
<div class="dash-card"><h3>${esc(data.cache_hit_rate_percent)}%</h3><p>Cache hit rate</p></div>`;

        if (!data.recent.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Nothing generated yet. Start on the Generator tab.</td></tr>';
            return;
        }
        tbody.innerHTML = data.recent.map(r => `
<tr>
<td><strong>${esc(r.topic)}</strong></td>
<td>${esc(r.provider ? Gutfolio.providerLabel(r.provider) : '—')}</td>
<td><span class="status-pill ${r.success ? 'pill-ok' : r.out_of_scope ? 'pill-draft' : 'pill-fail'}">${r.success ? 'OK' : r.out_of_scope ? 'Out of scope' : 'Failed'}</span></td>
<td>${r.success ? scoreBadge(r.quality_score) : '—'}</td>
<td>${r.success ? esc(r.word_count) : '—'}</td>
<td>${r.cached ? 'Yes' : 'No'}</td>
</tr>`).join('');
    } catch (err) {
        console.error('Dashboard load failed:', err);
        summary.innerHTML = `<p class="empty-state">Dashboard failed to load: ${esc(err.message)}</p>`;
    }
}

loadDashboard();
