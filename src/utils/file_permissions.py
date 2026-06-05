"""
File Permissions and Authorization Logic
"""

from typing import Tuple, Optional
from sqlalchemy.orm import Session
from src.middleware.auth_models import File, User


class FilePermissionManager:
    """Manages file access permissions"""
    
    @staticmethod
    def can_view_file(file: File, requesting_user_id: Optional[int]) -> bool:
        """
        Check if user can view file
        
        Args:
            file: File object
            requesting_user_id: ID of user requesting access
        
        Returns:
            True if user can view, False otherwise
        """
        # Owner can always view
        if requesting_user_id and file.user_id == requesting_user_id:
            return True
        
        # Public files can be viewed by anyone
        if file.is_public:
            return True
        
        # Private files can only be viewed by owner
        return False
    
    @staticmethod
    def can_download_file(file: File, requesting_user_id: Optional[int]) -> bool:
        """
        Check if user can download file
        
        Args:
            file: File object
            requesting_user_id: ID of user requesting access
        
        Returns:
            True if user can download, False otherwise
        """
        # Same logic as viewing for now
        return FilePermissionManager.can_view_file(file, requesting_user_id)
    
    @staticmethod
    def can_delete_file(file: File, requesting_user_id: Optional[int]) -> bool:
        """
        Check if user can delete file
        
        Args:
            file: File object
            requesting_user_id: ID of user requesting access
        
        Returns:
            True if user can delete, False otherwise
        """
        # Only owner can delete
        if requesting_user_id and file.user_id == requesting_user_id:
            return True
        
        return False
    
    @staticmethod
    def can_modify_permissions(file: File, requesting_user_id: Optional[int]) -> bool:
        """
        Check if user can modify file permissions
        
        Args:
            file: File object
            requesting_user_id: ID of user requesting access
        
        Returns:
            True if user can modify, False otherwise
        """
        # Only owner can modify permissions
        if requesting_user_id and file.user_id == requesting_user_id:
            return True
        
        return False
    
    @staticmethod
    def check_file_access(
        file: File, 
        requesting_user_id: Optional[int], 
        action: str = 'view'
    ) -> Tuple[bool, str]:
        """
        Check if user has permission for specific action
        
        Args:
            file: File object
            requesting_user_id: ID of user requesting access
            action: 'view', 'download', 'delete', 'modify_permissions'
        
        Returns:
            Tuple of (has_access: bool, message: str)
        """
        if action == 'view' or action == 'download':
            if FilePermissionManager.can_view_file(file, requesting_user_id):
                return True, 'Access granted'
            return False, 'Access denied: File is private'
        
        elif action == 'delete':
            if FilePermissionManager.can_delete_file(file, requesting_user_id):
                return True, 'Access granted'
            return False, 'Access denied: Only file owner can delete'
        
        elif action == 'modify_permissions':
            if FilePermissionManager.can_modify_permissions(file, requesting_user_id):
                return True, 'Access granted'
            return False, 'Access denied: Only file owner can modify permissions'
        
        return False, f'Unknown action: {action}'


def get_user_files(session: Session, user_id: int, include_deleted: bool = False) -> list:
    """
    Get all files belonging to a user
    
    Args:
        session: SQLAlchemy session
        user_id: User ID
        include_deleted: Include deleted files
    
    Returns:
        List of File objects
    """
    query = session.query(File).filter(File.user_id == int(user_id))
    
    if not include_deleted:
        query = query.filter(File.deleted.is_(False), File.is_deleted.is_(False))
    
    return query.all()


def get_public_files(session: Session, limit: int = 50, offset: int = 0) -> list:
    """
    Get all public files
    
    Args:
        session: SQLAlchemy session
        limit: Maximum number of files
        offset: Offset for pagination
    
    Returns:
        List of File objects
    """
    return session.query(File).filter(
        File.is_public.is_(True),
        File.deleted.is_(False),
        File.is_deleted.is_(False)
    ).order_by(File.upload_date.desc()).limit(limit).offset(offset).all()


def toggle_file_privacy(session: Session, file_id: int, make_public: bool) -> Tuple[bool, str]:
    """
    Toggle file privacy status
    
    Args:
        session: SQLAlchemy session
        file_id: File ID
        make_public: True to make public, False to make private
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        file = session.query(File).filter(File.id == file_id).first()
        
        if not file:
            return False, 'File not found'
        
        file.is_public = make_public
        session.commit()
        
        status = 'public' if make_public else 'private'
        return True, f'File is now {status}'
    
    except Exception as e:
        session.rollback()
        return False, f'Error updating file privacy: {str(e)}'
