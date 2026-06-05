"""
User and File Models for Authentication & Authorization
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, BigInteger, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash

Base = declarative_base()


class User(Base):
    """User model for authentication"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships - explicitly specify foreign key for File to avoid ambiguity
    files = relationship('File', foreign_keys='File.user_id', back_populates='owner', cascade='all, delete-orphan')
    access_logs = relationship('FileAccessLog', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        """Hash and set password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password: str) -> bool:
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<User {self.username}>'


class File(Base):
    """File model with permission and ownership tracking"""
    __tablename__ = 'files'

    # Phase 1 compatible: id is TEXT (UUID), not SERIAL
    id = Column(String(36), primary_key=True)  # UUID format: 8-4-4-4-12
    # Phase 1 fields
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=True)
    primary_node = Column(String(10), nullable=False, default='node1')
    replica_nodes = Column(Text, nullable=True, default='')
    download_limit = Column(Integer, default=3)
    downloads_left = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)
    checksum = Column(String(255), nullable=True)
    is_compressed = Column(Boolean, default=False)
    has_thumbnail = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Phase 5 fields
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    is_public = Column(Boolean, default=False, index=True)
    file_type = Column(String(100), nullable=True)
    upload_date = Column(DateTime, default=datetime.utcnow, index=True)
    modified_date = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    download_count = Column(Integer, default=0)
    deleted = Column(Boolean, default=False)
    storage_node = Column(String(10), nullable=True)
    file_path = Column(Text, nullable=True)

    # Relationships - explicitly specify foreign keys to avoid ambiguity
    owner = relationship('User', foreign_keys=[user_id], back_populates='files')
    access_logs = relationship('FileAccessLog', back_populates='file', cascade='all, delete-orphan')

    def to_dict(self, include_path: bool = False):
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'filename': self.filename,
            'original_name': self.original_name,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'file_type': self.file_type or self.mime_type,
            'user_id': self.user_id,
            'is_public': self.is_public,
            'primary_node': self.primary_node,
            'replica_nodes': self.replica_nodes,
            'storage_node': self.storage_node,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'download_count': self.download_count,
            'download_limit': self.download_limit,
            'downloads_left': self.downloads_left,
            'checksum': self.checksum,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_deleted': self.is_deleted,
            'deleted': self.deleted,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None
        }
        if include_path:
            data['file_path'] = self.file_path
        return data

    def __repr__(self):
        return f'<File {self.filename}>'


class FileAccessLog(Base):
    """Audit log for file access"""
    __tablename__ = 'file_access_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    file_id = Column(String(36), ForeignKey('files.id', ondelete='CASCADE'), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)  # 'download', 'view', 'delete', 'share'
    access_date = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)
    details = Column(Text, nullable=True)

    # Relationships
    user = relationship('User', back_populates='access_logs')
    file = relationship('File', back_populates='access_logs')

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'file_id': self.file_id,
            'action': self.action,
            'access_date': self.access_date.isoformat() if self.access_date else None,
            'ip_address': self.ip_address,
            'details': self.details
        }

    def __repr__(self):
        return f'<FileAccessLog {self.action}>'

    # Relationships
    user = relationship('User', back_populates='access_logs')
    file = relationship('File', back_populates='access_logs')

    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'file_id': self.file_id,
            'action': self.action,
            'access_date': self.access_date.isoformat() if self.access_date else None,
            'ip_address': self.ip_address,
            'details': self.details
        }

    def __repr__(self):
        return f'<FileAccessLog {self.action}>'
