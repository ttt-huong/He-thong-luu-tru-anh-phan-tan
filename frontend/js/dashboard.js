// ==========================================
// Dashboard bootstrap, navigation, upload UI, and audit UI
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    initAuth();

    if (!isLoggedIn()) {
        window.location.href = 'login.html';
        return;
    }

    document.body.classList.remove('auth-pending');
    hydrateUserProfile();
    setupSectionNavigation();
    setupTransferModal();
    setupVaultFilters();
    setupUploadHandlers();
    loadFileList();
    loadAuditLogs();
    setInterval(loadFileList, 30000);
    setInterval(loadAuditLogs, 30000);
    setInterval(refreshCountdownBadges, 1000);
});

let activeVaultFilter = 'all';

function hydrateUserProfile() {
    const user = getCurrentUser();
    if (!user) return;

    document.getElementById('currentUsername').textContent = user.username;
    document.getElementById('userAvatar').textContent = user.username.charAt(0).toUpperCase();
}

function setupSectionNavigation() {
    const navItems = document.querySelectorAll('.security-nav-item');
    const sections = document.querySelectorAll('.security-section');
    const title = document.getElementById('sectionTitle');

    function activateSection(sectionName) {
        navItems.forEach((item) => {
            item.classList.toggle('active', item.dataset.section === sectionName);
        });

        sections.forEach((section) => {
            const isActive = section.id === `section-${sectionName}`;
            section.classList.toggle('active', isActive);
            if (isActive && title) {
                title.textContent = section.dataset.title || 'SecuShare';
            }
        });

        if (sectionName === 'audit') {
            loadAuditLogs();
        }
    }

    navItems.forEach((item) => {
        item.addEventListener('click', () => activateSection(item.dataset.section));
    });

    document.querySelectorAll('[data-section-jump]').forEach((button) => {
        button.addEventListener('click', () => {
            closeTransferModal();
            activateSection(button.dataset.sectionJump);
        });
    });
}

function setupTransferModal() {
    document.querySelectorAll('[data-open-transfer]').forEach((button) => {
        button.addEventListener('click', openTransferModal);
    });

    document.querySelectorAll('[data-close-transfer]').forEach((button) => {
        button.addEventListener('click', closeTransferModal);
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeTransferModal();
        }
    });
}

function openTransferModal() {
    const modal = document.getElementById('transferModal');
    if (!modal) return;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
}

function closeTransferModal() {
    const modal = document.getElementById('transferModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
}

function setupVaultFilters() {
    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
        globalSearch.addEventListener('input', applyVaultFilters);
    }

    document.querySelectorAll('.filter-chip[data-filter]').forEach((button) => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.filter-chip[data-filter]').forEach((chip) => {
                chip.classList.toggle('active', chip === button);
            });
            activeVaultFilter = button.dataset.filter || 'all';
            applyVaultFilters();
        });
    });
}

function applyVaultFilters() {
    const term = (document.getElementById('globalSearch')?.value || '').toLowerCase().trim();
    let visibleCount = 0;

    document.querySelectorAll('#fileListContainer .file-card').forEach((card) => {
        const matchesSearch = (card.dataset.name || '').includes(term);
        const matchesFilter =
            activeVaultFilter === 'all' ||
            card.dataset.visibility === activeVaultFilter ||
            (activeVaultFilter === 'expiring' && card.dataset.expiring === 'true');
        const isVisible = matchesSearch && matchesFilter;
        card.style.display = isVisible ? 'grid' : 'none';
        if (isVisible) visibleCount++;
    });

    const emptyMsg = document.getElementById('emptyMessage');
    const hasFiles = document.querySelectorAll('#fileListContainer .file-card').length > 0;
    if (emptyMsg && hasFiles) {
        emptyMsg.style.display = visibleCount === 0 ? 'block' : 'none';
    }
}

function setupUploadHandlers() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    let selectedFile = null;

    if (!dropZone || !fileInput || !uploadBtn) return;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (event) => {
        event.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (event) => {
        event.preventDefault();
        dropZone.classList.remove('dragover');

        const files = event.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    fileInput.addEventListener('change', (event) => {
        if (event.target.files.length > 0) {
            handleFileSelect(event.target.files[0]);
        }
    });

    uploadBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        const uploadedFileName = selectedFile.name;
        const btnText = uploadBtn.innerHTML;
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = '<span class="loading"></span>Đang tạo link...';

        const isPublic = document.getElementById('isPublic').checked;
        const ttlSeconds = document.getElementById('ttlSeconds').value;
        const downloadLimit = document.getElementById('downloadLimit').value;
        const success = await uploadFile(selectedFile, isPublic, ttlSeconds, downloadLimit);

        uploadBtn.disabled = false;
        uploadBtn.innerHTML = btnText;

        if (success) {
            showAlert('Khởi tạo link thành công. File đã được lưu an toàn.', 'success');
            fileInput.value = '';
            selectedFile = null;
            uploadBtn.disabled = true;
            document.getElementById('isPublic').checked = false;
            document.getElementById('ttlSeconds').value = '3600';
            document.getElementById('downloadLimit').value = '3';

            resetDropZone(dropZone);
            await loadFileList();
            logAction('UPLOAD', `File secured: ${uploadedFileName}`);
        }
    });

    function handleFileSelect(file) {
        const maxSize = 10 * 1024 * 1024;

        if (file.size > maxSize) {
            showAlert('File vượt quá giới hạn 10MB.', 'error');
            return;
        }

        selectedFile = file;
        dropZone.innerHTML = `
            <i class="fa-solid fa-file-shield" style="color: var(--accent-emerald);"></i>
            <p style="color: var(--accent-emerald);">Sẵn sàng: ${escapeHtml(file.name)}</p>
            <small style="color: var(--text-slate);">${formatFileSize(file.size)}</small>
        `;
        uploadBtn.disabled = false;
    }
}

function resetDropZone(dropZone) {
    dropZone.innerHTML = `
        <i class="fa-solid fa-cloud-arrow-up"></i>
        <p>Kéo thả file vào đây hoặc click để chọn</p>
        <small>File đi qua gateway bảo mật trước khi lưu vào storage node.</small>
    `;
}

async function loadFileList() {
    const files = await getFiles();
    const user = getCurrentUser();

    let ownFileCount = 0;
    let publicFileCount = 0;

    if (!files || files.length === 0) {
        const emptyMessage = document.getElementById('emptyMessage');
        const fileListContainer = document.getElementById('fileListContainer');
        if (emptyMessage) emptyMessage.style.display = 'block';
        if (fileListContainer) fileListContainer.innerHTML = '';
        setText('ownFileCount', '0');
        setText('publicFileCount', '0');
        return;
    }

    const emptyMessage = document.getElementById('emptyMessage');
    if (emptyMessage) emptyMessage.style.display = 'none';

    files.forEach((file) => {
        if (String(file.user_id) === String(user.userId)) {
            ownFileCount++;
        }
        if (file.is_public) {
            publicFileCount++;
        }
    });

    setText('ownFileCount', ownFileCount);
    setText('publicFileCount', publicFileCount);

    await displayFileList(files);
    applyVaultFilters();
}

async function loadAuditLogs() {
    const token = getToken();
    const auditRows = document.getElementById('auditRows');
    if (!token || !auditRows) return;

    try {
        const response = await fetch(`${API_BASE}/files/audit-logs?limit=8`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) return;

        const data = await response.json();
        const logs = data.logs || [];

        if (logs.length === 0) {
            auditRows.innerHTML = `
                <div class="audit-table-row muted">
                    <span>--</span>
                    <strong>NO_EVENT</strong>
                    <span>Chưa có sự kiện bảo mật nào.</span>
                    <em>Idle</em>
                </div>
            `;
            return;
        }

        auditRows.innerHTML = logs.map((log) => `
            <div class="audit-table-row">
                <span>${escapeHtml(formatDateTime(log.access_date))}</span>
                <strong>${escapeHtml((log.action || 'event').toUpperCase())}</strong>
                <span>${escapeHtml(shortFileId(log.file_id))}</span>
                <em>${escapeHtml(formatAuditStatus(log.action))}</em>
            </div>
        `).join('');
    } catch (error) {
        console.error('Audit load error:', error);
    }
}

function shortFileId(fileId) {
    if (!fileId) return 'Gateway';
    return `File ${String(fileId).substring(0, 8)}`;
}

function formatAuditStatus(action) {
    if (!action) return 'Recorded';
    if (action.includes('denied')) return 'Denied';
    if (action.includes('expired')) return 'Expired';
    return 'Success';
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}

function logAction(component, message) {
    const terminal = document.getElementById('terminal');
    if (!terminal) return;

    const now = new Date();
    const ts = now.toLocaleTimeString('vi-VN', { hour12: false });
    const logLine = document.createElement('div');
    logLine.className = 'log-line';
    logLine.innerHTML = `<span class="log-ts">[${ts}]</span><span class="log-comp">[${component}]</span><span class="log-msg">${escapeHtml(message)}</span>`;
    terminal.appendChild(logLine);
    terminal.scrollTop = terminal.scrollHeight;
}
