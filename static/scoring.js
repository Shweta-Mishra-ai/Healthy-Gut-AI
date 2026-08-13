// Shared quality-score → color mapping. Thresholds:
// 80-100 green | 60-79 yellow | 40-59 orange | 0-39 red
function scoreClass(score) {
    if (score === null || score === undefined || score === '' || Number.isNaN(Number(score))) return 'score-na';
    const s = Number(score);
    if (s >= 80) return 'score-green';
    if (s >= 60) return 'score-yellow';
    if (s >= 40) return 'score-orange';
    return 'score-red';
}

function scoreBadge(score) {
    // The dial is a small circle — show just the number (or — for n/a), with
    // "/100" as a title tooltip rather than crowding the ring itself.
    const raw = (score === null || score === undefined || score === '') ? '—' : score;
    const display = Gutfolio.escapeHTML(raw);
    const title = raw === '—' ? 'No score available' : `Quality score: ${display}/100`;
    return `<span class="score-badge ${scoreClass(score)}" title="${title}">${display}</span>`;
}

function qualityFlagsBlock(flags) {
    if (!flags || !flags.length) return '';
    // Flag text is assembled from model output (slugs, meta descriptions),
    // so it is escaped like any other untrusted string.
    const items = flags.map(f => `<li>${Gutfolio.escapeHTML(f)}</li>`).join('');
    return `<div class="quality-flags"><strong>Review before publishing:</strong><ul>${items}</ul></div>`;
}
