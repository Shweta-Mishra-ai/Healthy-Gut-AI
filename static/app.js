document.getElementById('generate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // UI Elements
    const formPanel = document.querySelector('.generator-panel');
    const loading = document.getElementById('loading');
    const resultsPanel = document.getElementById('results');
    const btn = document.getElementById('generate-btn');
    
    // Toggle UI state
    btn.disabled = true;
    loading.classList.remove('hidden');
    resultsPanel.classList.add('hidden');
    
    // FormData
    const formData = new FormData(e.target);
    
    try {
        const response = await fetch('/generate', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok || data.error) {
            alert('Error generating article: ' + (data.error || 'Server error'));
        } else {
            renderResults(data);
        }
    } catch (err) {
        console.error(err);
        alert('Failed to connect to backend.');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
});

function renderResults(data) {
    const resultsPanel = document.getElementById('results');
    
    // Markdown to HTML conversion using Marked.js
    const renderedHTML = marked.parse(data.optimized_article_markdown || "No article content generated.");
    
    const density = data.metrics?.keywordDensity?.keywordDensityPercent || 0;
    const readability = data.metrics?.readability?.fleschReadingEase || 0;
    
    resultsPanel.innerHTML = `
        <div class="results-header">
            <h2>Generated Output</h2>
            <button class="btn-primary" style="width: auto; padding: 0.5rem 1.5rem; margin-top:0;" onclick="window.print()">Print / PDF</button>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>${density}%</h3>
                <p>Keyword Density</p>
            </div>
            <div class="metric-card">
                <h3>${readability}</h3>
                <p>Readability Score</p>
            </div>
        </div>
        
        <div class="article-content">
            ${renderedHTML}
        </div>
        
        <div class="seo-meta">
            <p><strong>Meta Description:</strong> ${data.meta_description}</p>
            <p><strong>URL Slug:</strong> /${data.url_slug}</p>
            <p><strong>Soft CTA:</strong> ${data.cta_soft}</p>
            <p><strong>Direct CTA:</strong> ${data.cta_direct}</p>
        </div>
    `;
    
    resultsPanel.classList.remove('hidden');
    resultsPanel.scrollIntoView({ behavior: 'smooth' });
}
