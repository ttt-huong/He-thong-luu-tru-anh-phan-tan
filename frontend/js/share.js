const API_BASE = window.location.protocol === 'file:'
    ? 'http://localhost:5000/api'
    : `${window.location.origin}/api`;

let currentFile = null;
let countdownTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    loadSharedFile();
    document.getElementById('shareDownloadBtn')?.addEventListener('click', downloadSharedFile);
});

async function loadSharedFile() {
    const fileId = new URLSearchParams(window.location.search).get('id');
    if (!fileId) {
        showError('Link chia sẻ thiếu mã file.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/files/public/${encodeURIComponent(fileId)}`);
        const data = await response.json();

        if (!response.ok) {
            showError(data.error || 'Link không hợp lệ hoặc file đã hết hạn.');
            return;
        }

        currentFile = data.file;
        renderFile(currentFile);
    } catch (error) {
        showError('Không thể kết nối tới SecuShare. Vui lòng thử lại sau.');
    }
}

function renderFile(file) {
    document.getElementById('shareLoading').hidden = true;
    document.getElementById('shareError').hidden = true;
    document.getElementById('shareContent').hidden = false;

    const fileName = file.original_name || file.filename || 'File được chia sẻ';
    document.getElementById('shareFileName').textContent = fileName;
    document.getElementById('shareFileSize').textContent = formatFileSize(file.file_size || 0);
    document.getElementById('shareDownloadsLeft').textContent = `${file.downloads_left ?? 0} lượt`;
    document.getElementById('shareFileIcon').className = `fa-solid ${getFileIcon(fileName)}`;

    updateExpiresIn(file.expires_at);
    clearInterval(countdownTimer);
    countdownTimer = setInterval(() => updateExpiresIn(file.expires_at), 1000);
}

async function downloadSharedFile() {
    if (!currentFile) return;

    const button = document.getElementById('shareDownloadBtn');
    const originalHtml = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="loading"></span>Đang tải...';

    try {
        const response = await fetch(`${API_BASE}/files/public/${encodeURIComponent(currentFile.id)}/download`);

        if (!response.ok) {
            const data = await response.json();
            showToast(data.error || 'Tải xuống thất bại.', 'error');
            await loadSharedFile();
            return;
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = currentFile.original_name || currentFile.filename || 'file';
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);

        showToast('Đã bắt đầu tải file.', 'success');
        await loadSharedFile();
    } catch (error) {
        showToast('Không thể tải file. Vui lòng thử lại.', 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = originalHtml;
    }
}

function showError(message) {
    document.getElementById('shareLoading').hidden = true;
    document.getElementById('shareContent').hidden = true;
    document.getElementById('shareError').hidden = false;
    document.getElementById('shareErrorText').textContent = message;
}

function updateExpiresIn(dateString) {
    const element = document.getElementById('shareExpiresIn');
    if (!element) return;

    if (!dateString) {
        element.textContent = 'Không hết hạn';
        return;
    }

    const msLeft = new Date(dateString) - new Date();
    element.textContent = formatTimeLeft(msLeft);
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

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
    return `${Math.round((bytes / Math.pow(k, i)) * 100) / 100} ${sizes[i]}`;
}

function getFileIcon(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return 'fa-file-image';
    if (ext === 'pdf') return 'fa-file-pdf';
    if (ext === 'txt') return 'fa-file-lines';
    return 'fa-file-shield';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-exclamation-circle';

    toast.className = `toast-notification ${type}`;
    toast.innerHTML = `
        <i class="fa-solid ${icon} toast-icon"></i>
        <div class="toast-message">${escapeHtml(message)}</div>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
