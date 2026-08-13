/* Shared UI primitives for every page: theme, toasts, escaping, and the
   single fetch wrapper that every request goes through.

   The escaping helpers are not optional politeness. Article bodies, meta
   descriptions, CTAs and slugs are model output, and reviewer notes are
   typed by a person — all of it used to be dropped into innerHTML raw, so a
   generated slug containing a tag executed as markup in the reviewer's
   browser. Everything interpolated into HTML now goes through escapeHTML,
   and article markdown goes through marked + DOMPurify. */

const Gutfolio = (() => {
    const API_KEY_STORAGE = 'gutfolio.apiKey';

    /* ---------- escaping ---------- */

    const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

    function escapeHTML(value) {
        if (value === null || value === undefined) return '';
        return String(value).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
    }

    /* ---------- API key ---------- */

    function getApiKey() {
        try { return localStorage.getItem(API_KEY_STORAGE) || ''; } catch { return ''; }
    }

    function setApiKey(key) {
        try {
            if (key) localStorage.setItem(API_KEY_STORAGE, key);
            else localStorage.removeItem(API_KEY_STORAGE);
        } catch { /* private browsing — the key just won't persist */ }
    }

    /* Every request in the app goes through here, so a deployment with
       API_KEY set works from the browser instead of failing with an
       unexplained 401 on every action. */
    async function apiFetch(url, options = {}) {
        const opts = { ...options, headers: { ...(options.headers || {}) } };
        const key = getApiKey();
        if (key) opts.headers['X-API-Key'] = key;
        const res = await fetch(url, opts);
        if (res.status === 401) {
            toast('This deployment requires an access key. Add it under Access key in the header.', 'error');
        }
        return res;
    }

    /* ---------- toasts ---------- */

    function toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.setAttribute('role', type === 'error' ? 'alert' : 'status');
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px)';
            setTimeout(() => el.remove(), 300);
        }, 4200);
    }

    /* ---------- markdown ----------

       Rendered locally rather than through a CDN copy of marked +
       DOMPurify. Those two scripts were the app's only runtime dependency on
       a third-party host, and when the CDN was unreachable — offline, a
       corporate proxy, a blocked region — the article panel fell back to a
       renderer that couldn't draw lists or the comparison table, so the most
       useful part of the article silently disappeared.

       Safety here comes from construction, not from sanitising afterwards:
       the source is escaped first, and only a fixed set of tags is emitted.
       No attacker-controlled string can become markup, so there is nothing
       left for a sanitiser to strip. */

    const SAFE_URL = /^(https?:\/\/|\/|#|mailto:)/i;

    function renderInline(text) {
        let out = escapeHTML(text);
        out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
        out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, url) =>
            SAFE_URL.test(url)
                ? `<a href="${escapeHTML(url)}" rel="noopener noreferrer">${label}</a>`
                : label);
        out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        out = out.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
        out = out.replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>');
        return out;
    }

    const TABLE_DIVIDER = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$/;

    function renderMarkdown(markdown) {
        if (!markdown || !markdown.trim()) return '<p class="muted">No article content generated.</p>';
        const lines = markdown.replace(/\r\n/g, '\n').split('\n');
        const html = [];
        let i = 0;

        const tableRow = line => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());

        while (i < lines.length) {
            const line = lines[i];
            const trimmed = line.trim();

            if (!trimmed) { i++; continue; }

            if (trimmed.startsWith('```')) {
                const body = [];
                i++;
                while (i < lines.length && !lines[i].trim().startsWith('```')) body.push(lines[i++]);
                i++;
                html.push(`<pre class="code-block"><code>${escapeHTML(body.join('\n'))}</code></pre>`);
                continue;
            }

            const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
            if (heading) {
                const level = heading[1].length;
                html.push(`<h${level}>${renderInline(heading[2].replace(/\s*#+$/, ''))}</h${level}>`);
                i++;
                continue;
            }

            if (/^(\*\s*){3,}$|^(-\s*){3,}$|^(_\s*){3,}$/.test(trimmed)) {
                html.push('<hr>');
                i++;
                continue;
            }

            if (trimmed.startsWith('|') && trimmed.includes('|', 1)) {
                const rows = [];
                while (i < lines.length && lines[i].trim().startsWith('|')) {
                    const raw = lines[i].trim();
                    if (!TABLE_DIVIDER.test(raw)) rows.push(tableRow(raw));
                    i++;
                }
                if (rows.length) {
                    const head = rows[0].map(c => `<th>${renderInline(c)}</th>`).join('');
                    const body = rows.slice(1)
                        .map(r => `<tr>${r.map(c => `<td>${renderInline(c)}</td>`).join('')}</tr>`)
                        .join('');
                    html.push(`<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
                }
                continue;
            }

            const bullet = /^[-*+]\s+(.*)$/;
            const numbered = /^\d+[.)]\s+(.*)$/;
            if (bullet.test(trimmed) || numbered.test(trimmed)) {
                const ordered = numbered.test(trimmed);
                const pattern = ordered ? numbered : bullet;
                const items = [];
                while (i < lines.length && pattern.test(lines[i].trim())) {
                    items.push(`<li>${renderInline(lines[i].trim().match(pattern)[1])}</li>`);
                    i++;
                }
                html.push(ordered ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`);
                continue;
            }

            if (trimmed.startsWith('>')) {
                const quote = [];
                while (i < lines.length && lines[i].trim().startsWith('>')) {
                    quote.push(lines[i].trim().replace(/^>\s?/, ''));
                    i++;
                }
                html.push(`<blockquote>${renderInline(quote.join(' '))}</blockquote>`);
                continue;
            }

            const paragraph = [];
            while (i < lines.length && lines[i].trim() && !/^([#>|`]|[-*+]\s|\d+[.)]\s)/.test(lines[i].trim())) {
                paragraph.push(lines[i].trim());
                i++;
            }
            if (paragraph.length) html.push(`<p>${renderInline(paragraph.join(' '))}</p>`);
        }

        return html.join('\n');
    }

    /* Provider identifiers are internal ("mock" is the offline template
       path); the interface shows what they mean to the person reading. */
    const PROVIDER_LABELS = { mock: 'Template', groq: 'Groq', openrouter: 'OpenRouter', openai: 'OpenAI' };

    function providerLabel(name) {
        if (!name) return 'Template';
        return PROVIDER_LABELS[name] || name;
    }

    /* ---------- theme ---------- */

    function initTheme() {
        let theme = 'light';
        try { theme = localStorage.getItem('theme') || 'light'; } catch { /* ignore */ }
        document.documentElement.setAttribute('data-theme', theme);
        const btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        const label = () => {
            const current = document.documentElement.getAttribute('data-theme');
            btn.textContent = current === 'dark' ? 'Light' : 'Dark';
            btn.setAttribute('aria-label', `Switch to ${current === 'dark' ? 'light' : 'dark'} appearance`);
        };
        label();
        btn.addEventListener('click', () => {
            const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            try { localStorage.setItem('theme', next); } catch { /* ignore */ }
            label();
        });
    }

    /* ---------- access key panel ---------- */

    function initAccessKeyPanel() {
        const toggle = document.getElementById('access-key-btn');
        const panel = document.getElementById('access-key-panel');
        if (!toggle || !panel) return;
        const input = panel.querySelector('#access-key-input');
        const save = panel.querySelector('#access-key-save');
        const clear = panel.querySelector('#access-key-clear');

        const reflect = () => {
            toggle.textContent = getApiKey() ? 'Access key set' : 'Access key';
            toggle.classList.toggle('is-set', Boolean(getApiKey()));
        };
        reflect();

        toggle.addEventListener('click', () => {
            const open = panel.classList.toggle('hidden');
            toggle.setAttribute('aria-expanded', String(!open));
            if (!open) {
                input.value = getApiKey();
                input.focus();
            }
        });
        save.addEventListener('click', () => {
            setApiKey(input.value.trim());
            reflect();
            panel.classList.add('hidden');
            toggle.setAttribute('aria-expanded', 'false');
            toast(getApiKey() ? 'Access key saved in this browser.' : 'Access key cleared.', 'success');
        });
        clear.addEventListener('click', () => {
            setApiKey('');
            input.value = '';
            reflect();
            toast('Access key cleared.', 'info');
        });
        panel.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                panel.classList.add('hidden');
                toggle.setAttribute('aria-expanded', 'false');
                toggle.focus();
            }
        });
    }

    /* ---------- clipboard ---------- */

    async function copy(text, buttonEl) {
        const original = buttonEl ? buttonEl.textContent : '';
        try {
            await navigator.clipboard.writeText(text || '');
            if (buttonEl) buttonEl.textContent = 'Copied';
            toast('Copied to clipboard.', 'success');
        } catch {
            if (buttonEl) buttonEl.textContent = 'Failed';
            toast('Clipboard blocked by the browser — select the text and copy manually.', 'error');
        }
        if (buttonEl) setTimeout(() => { buttonEl.textContent = original; }, 1600);
    }

    /* ---------- tabs ---------- */

    /* Roving-tabindex tab strip with arrow-key support, so the result
       surfaces are reachable without a mouse. */
    function initTabs(root) {
        const strip = root.querySelector('[role="tablist"]');
        if (!strip) return;
        const tabs = Array.from(strip.querySelectorAll('[role="tab"]'));

        function select(tab) {
            tabs.forEach(t => {
                const selected = t === tab;
                t.setAttribute('aria-selected', String(selected));
                t.tabIndex = selected ? 0 : -1;
                const panel = root.querySelector(`#${t.getAttribute('aria-controls')}`);
                if (panel) panel.classList.toggle('hidden', !selected);
            });
        }

        tabs.forEach((tab, i) => {
            tab.addEventListener('click', () => select(tab));
            tab.addEventListener('keydown', e => {
                if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
                e.preventDefault();
                const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
                next.focus();
                select(next);
            });
        });
        if (tabs.length) select(tabs[0]);
    }

    function init() {
        initTheme();
        initAccessKeyPanel();
    }

    return { escapeHTML, apiFetch, toast, renderMarkdown, providerLabel, copy, initTabs, init, getApiKey, setApiKey };
})();

document.addEventListener('DOMContentLoaded', Gutfolio.init);
