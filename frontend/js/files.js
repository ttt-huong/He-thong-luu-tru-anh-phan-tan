// ==========================================
// File Management API & UI
// ==========================================

let currentFilesCache = [];

async function uploadFile(file, isPublic = false, ttlSeconds = 3600, downloadLimit = 3) {
    const token = getToken();
    if (!token) {
        showAlert('Session expired. Please sign in again.', 'error');
        return null;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('is_public', isPublic ? 'true' : 'false');
    formData.append('ttl_seconds', ttlSeconds);
    formData.append('download_limit', downloadLimit);

    try {
        const response = await fetch(`${API_BASE}/files/upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (response.ok) {
            const data = await response.json();
            return data.file;
        }

        const error = await response.json();
        showAlert(error.error || error.message || 'Upload failed.', 'error');
        return null;
    } catch (error) {
        console.error('Upload error:', error);
        showAlert('Upload error: ' + error.message, 'error');
        return null;
    }
}

async function getFiles() {
    const token = getToken();
    if (!token) {
        showAlert('Session expired. Please sign in again.', 'error');
        return [];
    }

    try {
        const response = await fetch(`${API_BASE}/files`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();
            return data.files || [];
        }

        if (response.status === 401) {
            showSessionExpiredAlert();
            return [];
        }

        const error = await response.json();
        console.error('Get files error:', error);
        showAlert(error.error || error.message || 'Failed to load files.', 'error');
        return [];
    } catch (error) {
        console.error('Get files error:', error);
        showAlert('File list error: ' + error.message, 'error');
        return [];
    }
}

async function deleteFile(fileId) {
    const token = getToken();
    if (!token) {
        showAlert('Session expired. Please sign in again.', 'error');
        return false;
    }

    try {
        const response = await fetch(`${API_BASE}/files/${fileId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) return true;

        if (response.status === 401) {
            showSessionExpiredAlert();
            return false;
        }

        const error = await response.json();
        showAlert(error.message || 'Delete failed.', 'error');
        return false;
    } catch (error) {
        console.error('Delete error:', error);
        showAlert('Delete error: ' + error.message, 'error');
        return false;
    }
}

async function toggleFilePermissions(fileId, isPublic) {
    const token = getToken();
    if (!token) {
        showAlert('Session expired. Please sign in again.', 'error');
        return false;
    }

    try {
        const response = await fetch(`${API_BASE}/files/${fileId}/permissions`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                is_public: isPublic
            })
        });

        if (response.ok) return true;

        if (response.status === 401) {
            showSessionExpiredAlert();
            return false;
        }

        const error = await response.json();
        showAlert(error.message || 'Permission update failed.', 'error');
        return false;
    } catch (error) {
        console.error('Toggle permissions error:', error);
        showAlert('Permission update error: ' + error.message, 'error');
        return false;
    }
}

async function displayFileList(files = null) {
    const container = document.getElementById('fileListContainer');
    if (!container) return;

    if (!files) {
        files = await getFiles();
    }
    currentFilesCache = files || [];

    const emptyMsg = document.getElementById('emptyMessage');
    if (!files || files.length === 0) {
        if (emptyMsg) emptyMsg.style.display = 'block';
        container.innerHTML = '';
        return;
    }

    if (emptyMsg) emptyMsg.style.display = 'none';
    const user = getCurrentUser();
    container.innerHTML = '';

    files.forEach((file) => {
        const isOwner = String(file.user_id) === String(user.userId);
        container.appendChild(createFileCard(file, isOwner));
    });
}

function createFileCard(file, isOwner) {
    const card = document.createElement('div');
    const fileName = file.original_name || file.filename || 'Untitled file';
    const iconClass = getFileIcon(fileName);
    const statusClass = file.is_public ? 'public' : 'private';
    const statusText = file.is_public ? 'Công khai' : 'Riêng tư';
    const downloadsLeft = file.downloads_left ?? 0;
    const shareUrl = `${window.location.origin}/share.html?id=${encodeURIComponent(file.id)}`;
    const expired = hasExpired(file.expires_at);
    card.className = 'file-card vault-file-row';
    card.dataset.name = fileName.toLowerCase();
    card.dataset.visibility = file.is_public ? 'public' : 'private';
    card.dataset.expiring = isExpiringSoon(file.expires_at) ? 'true' : 'false';
    card.dataset.expired = expired ? 'true' : 'false';

    card.innerHTML = `
        <div class="file-card-info">
            <div class="file-card-icon ${isOwner ? 'owner' : ''}">
                <i class="fa-solid ${iconClass}"></i>
            </div>
            <div class="file-card-meta">
                <div class="file-card-name" title="${escapeHtml(fileName)}">${escapeHtml(fileName)}</div>
                <div class="file-card-details">
                    <span>${formatFileSize(file.file_size || file.size || 0)}</span>
                    <span class="file-card-divider">-</span>
                    <span>${formatDate(file.upload_date || file.created_at)}</span>
                    ${isOwner ? '' : `
                        <span class="file-card-divider">-</span>
                        <span><i class="fa-solid fa-user" style="margin-right: 4px;"></i> ${escapeHtml(file.owner_username || 'Người chia sẻ')}</span>
                    `}
                </div>
            </div>
        </div>
        <div class="file-card-security">
            <span class="status-badge ${statusClass}">
                <i class="fa-solid ${file.is_public ? 'fa-unlock' : 'fa-lock'}"></i>
                ${statusText}
            </span>
        </div>
        <div class="file-card-policy">
            ${renderExpiryBadge(file.expires_at)}
            ${renderDownloadBadge(downloadsLeft)}
        </div>
    `;

    const actions = document.createElement('div');
    actions.className = 'file-card-actions';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn copy';
    copyBtn.innerHTML = '<i class="fa-solid fa-link"></i>';
    copyBtn.title = file.is_public ? 'Sao chép link chia sẻ' : 'Chỉ chia sẻ được file công khai';
    copyBtn.onclick = async () => {
        if (hasExpired(file.expires_at)) {
            showAlert('File đã hết hạn nên không thể lấy link chia sẻ.', 'error');
            await displayFileList();
            return;
        }

        if (!file.is_public) {
            showAlert('File đang riêng tư. Hãy chuyển sang công khai trước khi chia sẻ link.', 'error');
            return;
        }

        const copied = await copyToClipboard(shareUrl);
        if (!copied) {
            showAlert('Không thể tự sao chép link. Link: ' + shareUrl, 'error');
            return;
        }

        showAlert('Đã sao chép link chia sẻ tự hủy.', 'success');
        if (typeof logAction === 'function') {
            logAction('SHARE', `Copied link for ${file.id.substring(0, 8)}.`);
        }
    };
    actions.appendChild(copyBtn);

    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'action-btn download';
    downloadBtn.innerHTML = '<i class="fa-solid fa-download"></i>';
    downloadBtn.title = 'Tải xuống';
    downloadBtn.disabled = expired;
    downloadBtn.onclick = async () => {
        if (hasExpired(file.expires_at)) {
            showAlert('File đã hết hạn nên không thể tải xuống.', 'error');
            await displayFileList();
            return;
        }
        downloadFile(file.id, fileName);
    };
    actions.appendChild(downloadBtn);

    if (isOwner) {
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'action-btn toggle';
        toggleBtn.innerHTML = file.is_public ? '<i class="fa-solid fa-lock-open"></i>' : '<i class="fa-solid fa-lock"></i>';
        toggleBtn.title = file.is_public ? 'Chuyển về riêng tư' : 'Chuyển sang công khai';
        toggleBtn.onclick = async () => {
            toggleBtn.disabled = true;
            const newStatus = !file.is_public;
            if (await toggleFilePermissions(file.id, newStatus)) {
                file.is_public = newStatus;
                await displayFileList();
                showAlert(newStatus ? 'File đã chuyển sang công khai.' : 'File đã chuyển sang riêng tư.', 'success');
                if (typeof logAction === 'function') {
                    logAction('POLICY', `Access changed for ${file.id.substring(0, 8)} to ${newStatus ? 'public' : 'private'}.`);
                }
            }
            toggleBtn.disabled = false;
        };
        actions.appendChild(toggleBtn);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'action-btn delete';
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.title = 'Xóa file';
        deleteBtn.onclick = async () => {
            if (confirm('Xóa file này ngay bây giờ?')) {
                deleteBtn.disabled = true;
                if (await deleteFile(file.id)) {
                    card.remove();
                    showAlert('Đã xóa file.', 'success');
                    await displayFileList();
                    if (typeof logAction === 'function') {
                        logAction('DELETE', `Deleted file ${file.id.substring(0, 8)}.`);
                    }
                } else {
                    deleteBtn.disabled = false;
                }
            }
        };
        actions.appendChild(deleteBtn);
    }

    card.appendChild(actions);
    return card;
}

function getFileIcon(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext)) return 'fa-file-image';
    if (ext === 'pdf') return 'fa-file-pdf';
    if (ext === 'txt') return 'fa-file-lines';
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return 'fa-file-zipper';
    return 'fa-file';
}

function renderDownloadBadge(downloadsLeft) {
    if (downloadsLeft <= 1) {
        return `<span class="status-badge danger"><i class="fa-solid fa-circle-down"></i> ${downloadsLeft} lượt</span>`;
    }
    if (downloadsLeft <= 3) {
        return `<span class="status-badge warning"><i class="fa-solid fa-circle-down"></i> ${downloadsLeft} lượt</span>`;
    }
    return `<span class="status-badge private"><i class="fa-solid fa-circle-down"></i> ${downloadsLeft} lượt</span>`;
}

function renderExpiryBadge(dateString) {
    if (!dateString) {
        return '<span class="status-badge private"><i class="fa-solid fa-clock"></i> Không hết hạn</span>';
    }

    const expiresAt = parseApiDate(dateString);
    const msLeft = expiresAt - new Date();

    if (Number.isNaN(expiresAt.getTime())) {
        return '<span class="status-badge private"><i class="fa-solid fa-clock"></i> Không rõ</span>';
    }
    if (msLeft < 0) {
        return '<span class="status-badge danger"><i class="fa-solid fa-triangle-exclamation"></i> Đã hết hạn</span>';
    }
    if (msLeft < 30 * 60 * 1000) {
        return `<span class="status-badge warning countdown-badge" data-expires-at="${escapeHtml(dateString)}"><i class="fa-solid fa-clock"></i> ${formatTimeLeft(msLeft)}</span>`;
    }
    return `<span class="status-badge private countdown-badge" data-expires-at="${escapeHtml(dateString)}"><i class="fa-solid fa-clock"></i> ${formatTimeLeft(msLeft)}</span>`;
}

function isExpiringSoon(dateString) {
    if (!dateString) return false;
    const msLeft = parseApiDate(dateString) - new Date();
    return msLeft > 0 && msLeft < 60 * 60 * 1000;
}

function hasExpired(dateString) {
    if (!dateString) return false;
    const expiresAt = parseApiDate(dateString);
    return !Number.isNaN(expiresAt.getTime()) && expiresAt <= new Date();
}

function formatTimeLeft(msLeft) {
    if (msLeft <= 0) return 'Đã hết hạn';
    const totalSeconds = Math.floor(msLeft / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (days > 0) return `${days} ngày ${hours} giờ`;
    if (hours > 0) return `${hours} giờ ${minutes} phút`;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function refreshCountdownBadges() {
    let shouldReload = false;

    document.querySelectorAll('.countdown-badge').forEach((badge) => {
        const expiresAt = badge.dataset.expiresAt;
        const msLeft = parseApiDate(expiresAt) - new Date();
        const wasExpired = badge.dataset.expired === 'true';
        const isExpired = msLeft <= 0;
        badge.classList.toggle('warning', msLeft > 0 && msLeft < 30 * 60 * 1000);
        badge.classList.toggle('danger', isExpired);
        badge.dataset.expired = isExpired ? 'true' : 'false';
        badge.innerHTML = `<i class="fa-solid ${isExpired ? 'fa-triangle-exclamation' : 'fa-clock'}"></i> ${formatTimeLeft(msLeft)}`;
        if (isExpired && !wasExpired) {
            shouldReload = true;
        }
    });

    if (shouldReload) {
        setTimeout(() => displayFileList(), 500);
    }
}

async function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (error) {
            console.warn('Clipboard API failed, using fallback:', error);
        }
    }

    try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const copied = document.execCommand('copy');
        textarea.remove();
        return copied;
    } catch (error) {
        console.error('Clipboard fallback failed:', error);
        return false;
    }
}

async function downloadFile(fileId, filename) {
    const token = getToken();
    if (!token) {
        showAlert('Session expired. Please sign in again.', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/files/${fileId}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            const error = await response.json();
            showAlert(error.error || 'Tải xuống thất bại.', 'error');
            await displayFileList();
            return;
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename || 'file';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        await displayFileList();

        if (typeof logAction === 'function') {
            logAction('DOWNLOAD', `Downloaded file: ${filename}`);
        }
    } catch (error) {
        console.error('Download error:', error);
        showAlert('Lỗi tải xuống: ' + error.message, 'error');
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function formatDate(dateString) {
    if (!dateString) return 'Unknown';
    const date = parseApiDate(dateString);
    if (Number.isNaN(date.getTime())) return 'Unknown';

    const diffMs = new Date() - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hr ago`;
    if (diffDays < 7) return `${diffDays} days ago`;

    return date.toLocaleDateString('vi-VN');
}

function formatDateTime(dateString) {
    if (!dateString) return 'Unknown';
    const date = parseApiDate(dateString);
    if (Number.isNaN(date.getTime())) return 'Unknown';
    return date.toLocaleString('vi-VN');
}

function parseApiDate(dateString) {
    if (!dateString) return new Date(NaN);
    const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(dateString);
    return new Date(hasTimezone ? dateString : `${dateString}Z`);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showAlert(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
        let fallbackContainer = document.getElementById('fallbackToastContainer');
        if (!fallbackContainer) {
            fallbackContainer = document.createElement('div');
            fallbackContainer.id = 'fallbackToastContainer';
            fallbackContainer.className = 'toast-container';
            document.body.appendChild(fallbackContainer);
        }
        createToast(fallbackContainer, message, type);
        return;
    }
    createToast(container, message, type);
}

function createToast(container, message, type) {
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;

    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-exclamation-circle';

    toast.innerHTML = `
        <i class="fa-solid ${icon} toast-icon"></i>
        <div class="toast-message">${escapeHtml(message)}</div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
