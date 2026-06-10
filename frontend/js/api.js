// ==========================================
// Shared API configuration
// ==========================================

const API_BASE = window.location.protocol === 'file:'
    ? 'http://localhost:5000/api'
    : `${window.location.origin}/api`;
