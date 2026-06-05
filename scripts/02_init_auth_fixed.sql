-- ==========================================
-- PHASE 5: Authentication & Authorization
-- ==========================================

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Extend existing files table with user information if columns don't exist
-- Add user_id column if it doesn't exist
ALTER TABLE files
ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- Add is_public column if it doesn't exist (for permission management)
ALTER TABLE files
ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE;

-- Add audit tracking columns if they don't exist
ALTER TABLE files
ADD COLUMN IF NOT EXISTS accessed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- Add file management columns used by authenticated upload/download routes
ALTER TABLE files
ADD COLUMN IF NOT EXISTS file_type VARCHAR(100);

ALTER TABLE files
ADD COLUMN IF NOT EXISTS upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE files
ADD COLUMN IF NOT EXISTS modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE files
ADD COLUMN IF NOT EXISTS download_count INTEGER DEFAULT 0;

ALTER TABLE files
ADD COLUMN IF NOT EXISTS deleted BOOLEAN DEFAULT FALSE;

ALTER TABLE files
ADD COLUMN IF NOT EXISTS storage_node VARCHAR(10);

ALTER TABLE files
ADD COLUMN IF NOT EXISTS file_path TEXT;

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_files_is_public ON files(is_public);
CREATE INDEX IF NOT EXISTS idx_files_storage_node ON files(storage_node);
CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(deleted);

-- Create audit log table for tracking file access
CREATE TABLE IF NOT EXISTS file_access_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    file_id TEXT REFERENCES files(id) ON DELETE CASCADE,
    action VARCHAR(50), -- 'download', 'view', 'delete', 'share', 'upload'
    access_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_logs_user_id ON file_access_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_file_id ON file_access_logs(file_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_action ON file_access_logs(action);
CREATE INDEX IF NOT EXISTS idx_access_logs_date ON file_access_logs(access_date);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
