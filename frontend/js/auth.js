// ==========================================
// Authentication Token Management
// ==========================================

const TOKEN_KEY = 'token';
const USERNAME_KEY = 'username';
const USER_ID_KEY = 'user_id';
const TOKEN_EXPIRY_KEY = 'token_expiry';
const CHECK_TOKEN_INTERVAL = 60000; // Check token every 1 minute
const AUTH_API_BASE = window.location.protocol === 'file:'
    ? 'http://localhost:5000/api'
    : `${window.location.origin}/api`;

let tokenCheckInterval = null;

/**
 * Parse JWT token to get payload (decode without verification - for client-side only)
 */
function parseJWT(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(
            atob(base64)
                .split('')
                .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
                .join('')
        );
        return JSON.parse(jsonPayload);
    } catch (error) {
        console.error('Error parsing JWT:', error);
        return null;
    }
}

/**
 * Get token expiration time from token
 */
function getTokenExpiryTime(token) {
    const payload = parseJWT(token);
    if (payload && payload.exp) {
        return payload.exp * 1000; // Convert to milliseconds
    }
    return null;
}

/**
 * Save token and set expiry
 */
function saveToken(token, username, userId) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
    localStorage.setItem(USER_ID_KEY, userId);
    
    const expiryTime = getTokenExpiryTime(token);
    if (expiryTime) {
        localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
    }
    
    startTokenCheckInterval();
}

/**
 * Get token from localStorage
 */
function getToken() {
    const token = localStorage.getItem(TOKEN_KEY);
    
    // Check if token is expired
    if (token && isTokenExpired()) {
        logout();
        return null;
    }
    
    return token;
}

/**
 * Get current user info
 */
function getCurrentUser() {
    const token = getToken();
    
    if (!token) {
        return null;
    }
    
    return {
        token: token,
        username: localStorage.getItem(USERNAME_KEY),
        userId: localStorage.getItem(USER_ID_KEY)
    };
}

/**
 * Check if token is expired
 */
function isTokenExpired() {
    const expiryTime = localStorage.getItem(TOKEN_EXPIRY_KEY);
    
    if (!expiryTime) {
        return false;
    }
    
    const expiryTimeMs = parseInt(expiryTime);
    const now = Date.now();
    
    // Consider token expired if less than 5 minutes left
    const bufferMs = 5 * 60 * 1000;
    
    return now >= (expiryTimeMs - bufferMs);
}

/**
 * Check if user is logged in
 */
function isLoggedIn() {
    const token = getToken();
    return !!token && !isTokenExpired();
}

/**
 * Logout user
 */
function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    localStorage.removeItem(USER_ID_KEY);
    localStorage.removeItem(TOKEN_EXPIRY_KEY);
    
    stopTokenCheckInterval();
    
    window.location.href = 'login.html';
}

/**
 * Show session expired alert
 */
function showSessionExpiredAlert() {
    const container = document.getElementById('toastContainer') || document.body;
    const alert = document.createElement('div');
    alert.className = 'toast-notification error';
    alert.style.cssText = 'position: fixed; top: 24px; right: 24px; z-index: 10000; max-width: 380px; width: calc(100% - 48px);';
    alert.innerHTML = `
        <i class="fa-solid fa-clock-rotate-left toast-icon" style="color: var(--color-danger);"></i>
        <div class="toast-message">Phiên đăng nhập của bạn đã hết hạn. Vui lòng đăng nhập lại.</div>
    `;
    container.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
        logout();
    }, 3000);
}

/**
 * Start periodic token check
 */
function startTokenCheckInterval() {
    // Clear any existing interval
    stopTokenCheckInterval();
    
    tokenCheckInterval = setInterval(() => {
        if (isTokenExpired()) {
            stopTokenCheckInterval();
            showSessionExpiredAlert();
        }
    }, CHECK_TOKEN_INTERVAL);
}

/**
 * Stop periodic token check
 */
function stopTokenCheckInterval() {
    if (tokenCheckInterval) {
        clearInterval(tokenCheckInterval);
        tokenCheckInterval = null;
    }
}

/**
 * Fetch with token in header
 */
async function fetchWithAuth(url, options = {}) {
    const token = getToken();
    
    if (!token) {
        window.location.href = 'login.html';
        return null;
    }

    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };

    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        // If unauthorized (401), redirect to login
        if (response.status === 401) {
            showSessionExpiredAlert();
            return null;
        }

        // If forbidden (403), show error
        if (response.status === 403) {
            console.error('Access denied');
        }

        return response;
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

/**
 * Redirect to login if not authenticated
 */
function requireAuth() {
    if (!isLoggedIn()) {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

/**
 * Redirect to index if already logged in
 */
function redirectIfLoggedIn() {
    if (isLoggedIn()) {
        window.location.href = 'files.html';
    }
}

/**
 * Initialize auth on page load
 */
function initAuth() {
    if (isLoggedIn()) {
        startTokenCheckInterval();
    }
}
