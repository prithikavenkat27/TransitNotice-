/**
 * TransitNotice - Admin Scraper Operations & Robots.txt Auditor
 */

// Trigger Scraper from Admin Panel
async function triggerAdminScrape() {
    const btn = document.getElementById('adminScrapeBtn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-inline"></span> Crawling permitted feeds...`;

    try {
        const response = await fetch('/api/scraper/trigger', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            alert(data.message);
            window.location.reload();
        } else {
            alert("Scraper reported warning: " + data.message);
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    } catch (err) {
        alert("Crawler connection failed: " + err.message);
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

// Inspect robots.txt for arbitrary URL
async function inspectRobotsUrl() {
    const urlInput = document.getElementById('robotsTargetUrl');
    const btn = document.getElementById('checkRobotsBtn');
    const resultBox = document.getElementById('robotsResultBox');

    const targetUrl = urlInput.value.trim();
    if (!targetUrl) return;

    btn.disabled = true;
    btn.textContent = "Analyzing robots.txt...";
    resultBox.style.display = 'none';

    try {
        const response = await fetch('/api/check-robots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: targetUrl })
        });
        const data = await response.json();

        resultBox.style.display = 'block';
        if (data.allowed) {
            resultBox.style.background = '#ecfdf5';
            resultBox.style.border = '1px solid #a7f3d0';
            resultBox.style.color = '#065f46';
            resultBox.innerHTML = `
                <strong>&#10004; PERMITTED:</strong> Crawler is allowed to access this URL.<br>
                <small>${data.reason}</small>
            `;
        } else {
            resultBox.style.background = '#fef2f2';
            resultBox.style.border = '1px solid #fecaca';
            resultBox.style.color = '#991b1b';
            resultBox.innerHTML = `
                <strong>&#10006; RESTRICTED / DISALLOWED:</strong> Web crawler is restricted from accessing this path.<br>
                <small>${data.reason}</small>
            `;
        }
    } catch (err) {
        resultBox.style.display = 'block';
        resultBox.style.background = '#fef2f2';
        resultBox.style.color = '#991b1b';
        resultBox.innerHTML = `Failed to audit robots.txt: ${err.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = "Inspect Robots.txt Directives";
    }
}
