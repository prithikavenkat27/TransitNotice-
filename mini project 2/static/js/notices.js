/**
 * TransitNotice - Notices Interaction & Revision History
 * Manages revision modal popups and client-side data export
 */

// Open and load revision history modal
async function openHistoryModal(noticeId) {
    const modal = document.getElementById('historyModal');
    const modalTitle = document.getElementById('historyModalTitle');
    const modalBody = document.getElementById('historyModalBody');

    if (!modal) return;

    modal.classList.add('active');
    modalBody.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="spinner-inline" style="border-top-color: #0284c7; width: 22px; height: 22px;"></div>
            <p style="margin-top: 8px; color: var(--text-muted); font-size: 0.85rem;">Retrieving revision history from database...</p>
        </div>
    `;

    try {
        const response = await fetch(`/api/notices/${noticeId}/history`);
        const data = await response.json();

        if (!data.success || !data.current) {
            modalBody.innerHTML = `<p style="color: #ef4444;">Unable to find history records for Notice #${noticeId}.</p>`;
            return;
        }

        modalTitle.textContent = `Revision Log: Route ${data.current.route_number} - Notice #${data.current.id}`;

        let timelineHTML = `
            <div style="margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid var(--border-color);">
                <span class="badge badge-active" style="margin-bottom: 6px;">CURRENT STATE (Version ${data.current.version})</span>
                <h4 style="font-size: 1rem; margin: 4px 0;">${data.current.title}</h4>
                <div style="font-size: 0.82rem; color: #0284c7; font-weight: 600; margin-bottom: 6px;">
                    Area: ${data.current.affected_area} | Effective: ${data.current.start_date} to ${data.current.end_date}
                </div>
                <p style="font-size: 0.85rem; color: var(--text-secondary);">${data.current.description}</p>
            </div>
            
            <h4 style="font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 14px;">
                Archived Revisions (${data.history.length})
            </h4>
        `;

        if (data.history.length === 0) {
            timelineHTML += `
                <p style="color: var(--text-muted); font-size: 0.85rem;">
                    This notice has no prior recorded revisions (Original Version 1).
                </p>
            `;
        } else {
            timelineHTML += `<div class="revision-timeline">`;
            data.history.forEach(item => {
                timelineHTML += `
                    <div class="revision-item">
                        <div class="revision-dot"></div>
                        <div class="revision-header">
                            <span class="revision-version">Archived Version ${item.version}</span>
                            <span class="revision-date">Logged: ${item.changed_at}</span>
                        </div>
                        <div class="revision-summary">
                            <strong>Audit Difference:</strong> ${item.change_summary || 'Service details updated in feed'}
                        </div>
                        <div style="font-size: 0.82rem; color: var(--text-secondary); margin-top: 4px;">
                            ${item.description}
                        </div>
                        <div style="font-size: 0.74rem; color: var(--text-muted); margin-top: 4px;">
                            Original Validity: ${item.start_date} &rarr; ${item.end_date}
                        </div>
                    </div>
                `;
            });
            timelineHTML += `</div>`;
        }

        modalBody.innerHTML = timelineHTML;

    } catch (err) {
        modalBody.innerHTML = `<p style="color: #ef4444;">Error loading history: ${err.message}</p>`;
    }
}

// Close revision modal
function closeHistoryModal() {
    const modal = document.getElementById('historyModal');
    if (modal) modal.classList.remove('active');
}

// Close modal when clicking backdrop
document.addEventListener('click', (e) => {
    const modal = document.getElementById('historyModal');
    if (modal && e.target === modal) {
        modal.classList.remove('active');
    }
});

// Export notices to CSV
function exportNoticesToCSV() {
    const cards = document.querySelectorAll('.notice-card');
    if (!cards || cards.length === 0) {
        alert("No notices available to export.");
        return;
    }

    const rows = [
        ["Notice ID", "Route", "Advisory Type", "Status", "Title", "Start Date", "End Date"]
    ];

    cards.forEach(card => {
        const id = card.getAttribute('data-notice-id') || '';
        const route = card.getAttribute('data-route') || '';
        const type = card.getAttribute('data-type') || '';
        const status = card.getAttribute('data-status') || '';
        const title = (card.getAttribute('data-title') || '').replace(/"/g, '""');
        const start = card.getAttribute('data-start') || '';
        const end = card.getAttribute('data-end') || '';

        rows.push([id, route, type, status, `"${title}"`, start, end]);
    });

    const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `TransitNotice_Export_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
