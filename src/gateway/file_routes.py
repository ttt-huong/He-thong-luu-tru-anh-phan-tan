"""
File Management Routes - authenticated upload/download with self-destruct controls.
"""

from datetime import datetime, timedelta
from io import BytesIO
import logging
import mimetypes
import os
import uuid

from flask import Blueprint, request, jsonify, send_file
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from werkzeug.utils import secure_filename

from src.gateway.storage_client import StorageNodeClient
from src.middleware.auth_models import User, File, FileAccessLog
from src.middleware.jwt_auth import jwt_required, get_current_user_id
from src.middleware.rate_limiter import rate_limited
from src.utils.file_permissions import FilePermissionManager


file_bp = Blueprint('files', __name__)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:postgres_secure_pass@postgres-master:5432/fileshare'
)
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

STORAGE_NODES = {
    'node1': os.getenv('NODE1_URL', 'http://storage-node1:8000'),
    'node2': os.getenv('NODE2_URL', 'http://storage-node2:8000'),
    'node3': os.getenv('NODE3_URL', 'http://storage-node3:8000')
}

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'txt'}
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
DANGEROUS_EXTENSIONS = {'exe', 'bat', 'cmd', 'com', 'php', 'js', 'html', 'svg', 'sh', 'ps1'}
MAX_UPLOAD_BYTES = int(os.getenv('MAX_UPLOAD_BYTES', str(500 * 1024 * 1024)))
USER_STORAGE_QUOTA_BYTES = int(os.getenv('USER_STORAGE_QUOTA_BYTES', str(2 * 1024 * 1024 * 1024)))
DEFAULT_TTL_SECONDS = int(os.getenv('DEFAULT_FILE_TTL_SECONDS', str(24 * 60 * 60)))
MAX_TTL_SECONDS = int(os.getenv('MAX_FILE_TTL_SECONDS', str(7 * 24 * 60 * 60)))
DEFAULT_DOWNLOAD_LIMIT = int(os.getenv('DEFAULT_DOWNLOAD_LIMIT', '3'))
MAX_DOWNLOAD_LIMIT = int(os.getenv('MAX_DOWNLOAD_LIMIT', '50'))


def _audit(session, user_id, file_id, action, details=None):
    """Record a small audit event without interrupting the main flow."""
    try:
        session.add(FileAccessLog(
            user_id=user_id,
            file_id=file_id,
            action=action,
            ip_address=request.remote_addr,
            details=details
        ))
    except Exception as exc:
        logger.warning(f'Could not add audit log {action}: {exc}')


def _parse_positive_int(name, default_value, max_value):
    raw_value = request.form.get(name, request.args.get(name))
    if raw_value in (None, ''):
        return default_value
    try:
        value = int(raw_value)
    except ValueError:
        raise ValueError(f'{name} must be an integer')
    if value < 1:
        raise ValueError(f'{name} must be greater than 0')
    return min(value, max_value)


def _extension(filename):
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def _validate_filename(filename):
    if not filename:
        return 'No file selected'
    if any(part in filename for part in ('../', '..\\', '/', '\\')):
        return 'Invalid filename path'

    ext = _extension(filename)
    if ext in DANGEROUS_EXTENSIONS:
        return 'Dangerous file type is not allowed'
    if ext not in ALLOWED_EXTENSIONS:
        return f'File type not allowed. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
    return None


def _validate_content(file_content, ext):
    if len(file_content) == 0:
        return 'Empty file is not allowed'
    if len(file_content) > MAX_UPLOAD_BYTES:
        return f'File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)}MB'

    if ext in IMAGE_EXTENSIONS:
        try:
            from PIL import Image
            image = Image.open(BytesIO(file_content))
            image.verify()
        except Exception:
            return 'Invalid image content'
    elif ext == 'pdf' and not file_content.startswith(b'%PDF'):
        return 'Invalid PDF content'
    elif ext == 'txt':
        try:
            file_content[:4096].decode('utf-8')
        except UnicodeDecodeError:
            return 'Invalid text file content'

    return None


def _select_storage_order():
    # Keep the MVP simple: try node1 first, then fail over to the rest.
    return list(STORAGE_NODES.keys())


def _upload_to_storage(file_content, stored_filename):
    errors = []
    for node_id in _select_storage_order():
        client = StorageNodeClient(STORAGE_NODES[node_id], node_id)
        result = client.upload_file(file_content, stored_filename)
        if result.get('status') == 'success':
            return node_id, result
        errors.append(f'{node_id}: {result.get("error", "unknown error")}')
    raise RuntimeError('; '.join(errors))


def _download_from_storage(file_record):
    node_ids = [file_record.primary_node or file_record.storage_node]
    if file_record.replica_nodes:
        node_ids.extend([n.strip() for n in file_record.replica_nodes.split(',') if n.strip()])

    tried = []
    for node_id in dict.fromkeys([n for n in node_ids if n]):
        node_url = STORAGE_NODES.get(node_id)
        if not node_url:
            continue
        try:
            client = StorageNodeClient(node_url, node_id)
            return client.download_file(file_record.filename), node_id
        except Exception as exc:
            tried.append(f'{node_id}: {exc}')

    raise RuntimeError('; '.join(tried) or 'No storage node available')


def _delete_from_storage(file_record):
    node_ids = [file_record.primary_node or file_record.storage_node]
    if file_record.replica_nodes:
        node_ids.extend([n.strip() for n in file_record.replica_nodes.split(',') if n.strip()])

    deleted_nodes = []
    for node_id in dict.fromkeys([n for n in node_ids if n]):
        node_url = STORAGE_NODES.get(node_id)
        if not node_url:
            continue
        try:
            client = StorageNodeClient(node_url, node_id)
            client.delete_file(file_record.filename)
            deleted_nodes.append(node_id)
        except Exception as exc:
            logger.warning(f'Failed to delete {file_record.id} from {node_id}: {exc}')
    return deleted_nodes


def _mark_deleted(file_record):
    file_record.deleted = True
    file_record.is_deleted = True
    file_record.deleted_at = datetime.utcnow()


def _is_expired(file_record):
    return bool(file_record.expires_at and datetime.utcnow() >= file_record.expires_at)


def _is_active_file_filter(now=None):
    now = now or datetime.utcnow()
    return (
        File.deleted.is_(False),
        File.is_deleted.is_(False),
        or_(File.expires_at.is_(None), File.expires_at > now)
    )


def _cleanup_expired_files(session, user_id=None, limit=100):
    """Mark expired files as deleted and remove physical objects from storage."""
    query = session.query(File).filter(
        File.deleted.is_(False),
        File.is_deleted.is_(False),
        File.expires_at.isnot(None),
        File.expires_at <= datetime.utcnow()
    )
    if user_id is not None:
        query = query.filter(File.user_id == int(user_id))

    expired_files = query.limit(limit).all()
    cleaned = []
    for file_record in expired_files:
        _mark_deleted(file_record)
        deleted_nodes = _delete_from_storage(file_record)
        _audit(
            session,
            file_record.user_id,
            file_record.id,
            'expired',
            f'expired_by_cleanup;nodes={",".join(deleted_nodes)}'
        )
        cleaned.append(file_record.id)
    return cleaned


def _get_user_storage_used(session, user_id):
    active_files = session.query(File).filter(
        File.user_id == int(user_id),
        *_is_active_file_filter()
    ).all()
    return sum(file.file_size or 0 for file in active_files)


def _rate_key():
    user_id = get_current_user_id()
    return f'user:{user_id}' if user_id else (request.remote_addr or 'unknown')


@file_bp.route('/upload', methods=['POST'])
@jwt_required
@rate_limited(limit=20, window_seconds=60, key_func=_rate_key)
def upload_file():
    try:
        user_id = get_current_user_id()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        upload = request.files['file']
        raw_filename = upload.filename or ''
        filename_error = _validate_filename(raw_filename)
        if filename_error:
            return jsonify({'error': filename_error}), 400
        original_name = secure_filename(raw_filename)
        if not original_name:
            return jsonify({'error': 'Invalid filename'}), 400

        file_content = upload.read()
        ext = _extension(original_name)
        content_error = _validate_content(file_content, ext)
        if content_error:
            return jsonify({'error': content_error}), 400

        try:
            ttl_seconds = _parse_positive_int('ttl_seconds', DEFAULT_TTL_SECONDS, MAX_TTL_SECONDS)
            download_limit = _parse_positive_int('download_limit', DEFAULT_DOWNLOAD_LIMIT, MAX_DOWNLOAD_LIMIT)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        is_public = request.form.get('is_public', 'false').lower() == 'true'
        file_id = str(uuid.uuid4())
        stored_filename = f'{file_id}.{ext}'
        mime_type = mimetypes.guess_type(original_name)[0] or upload.content_type or 'application/octet-stream'

        session = Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            _cleanup_expired_files(session, user_id=user_id)
            used_bytes = _get_user_storage_used(session, user_id)
            if used_bytes + len(file_content) > USER_STORAGE_QUOTA_BYTES:
                return jsonify({
                    'error': 'User storage quota exceeded',
                    'used_bytes': used_bytes,
                    'quota_bytes': USER_STORAGE_QUOTA_BYTES,
                    'file_size': len(file_content)
                }), 413

            storage_node, _ = _upload_to_storage(file_content, stored_filename)
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

            new_file = File(
                id=file_id,
                filename=stored_filename,
                original_name=original_name,
                file_size=len(file_content),
                mime_type=mime_type,
                file_type=mime_type,
                user_id=user_id,
                is_public=is_public,
                primary_node=storage_node,
                storage_node=storage_node,
                file_path=stored_filename,
                checksum='',
                download_limit=download_limit,
                downloads_left=download_limit,
                created_at=datetime.utcnow(),
                upload_date=datetime.utcnow(),
                expires_at=expires_at,
                deleted=False,
                is_deleted=False
            )
            session.add(new_file)
            _audit(session, user_id, file_id, 'upload', f'ttl={ttl_seconds};limit={download_limit};node={storage_node}')
            session.commit()

            return jsonify({
                'message': 'File uploaded successfully',
                'file': new_file.to_dict(),
                'download_url': f'/api/files/{file_id}'
            }), 201
        except Exception as exc:
            session.rollback()
            logger.error(f'Upload error: {exc}', exc_info=True)
            return jsonify({'error': 'Upload failed'}), 500
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Unexpected upload error: {exc}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@file_bp.route('', methods=['GET'])
@jwt_required
@rate_limited(limit=120, window_seconds=60, key_func=_rate_key)
def list_files():
    try:
        user_id = get_current_user_id()
        show_all = request.args.get('show_all', 'false').lower() == 'true'
        limit = min(int(request.args.get('limit', 50)), 100)
        offset = int(request.args.get('offset', 0))

        session = Session()
        try:
            _cleanup_expired_files(session, user_id=user_id)
            session.commit()

            files_list = session.query(File).filter(
                File.user_id == int(user_id),
                *_is_active_file_filter()
            ).order_by(File.upload_date.desc()).all()
            if not show_all:
                public_files = session.query(File).filter(
                    File.is_public.is_(True),
                    File.user_id != int(user_id),
                    *_is_active_file_filter()
                ).order_by(File.upload_date.desc()).limit(max(limit - len(files_list), 0)).offset(offset).all()
                own_ids = {f.id for f in files_list}
                files_list.extend([f for f in public_files if f.id not in own_ids])

            return jsonify({
                'message': 'Files retrieved successfully',
                'count': len(files_list),
                'files': [f.to_dict() for f in files_list[:limit]]
            }), 200
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'List files error: {exc}', exc_info=True)
        return jsonify({'error': 'Failed to retrieve files'}), 500


@file_bp.route('/<file_id>', methods=['GET'])
@jwt_required
@rate_limited(limit=60, window_seconds=60, key_func=_rate_key)
def download_file(file_id):
    try:
        user_id = get_current_user_id()
        session = Session()
        try:
            file_record = session.query(File).filter(File.id == file_id).first()
            if not file_record:
                return jsonify({'error': 'File not found'}), 404

            if file_record.deleted or file_record.is_deleted:
                _audit(session, user_id, file_id, 'download_denied', 'deleted')
                session.commit()
                return jsonify({'error': 'File has been deleted'}), 410

            if _is_expired(file_record):
                _mark_deleted(file_record)
                _audit(session, user_id, file_id, 'expired', 'expired_by_time')
                _delete_from_storage(file_record)
                session.commit()
                return jsonify({'error': 'File has expired'}), 410

            has_access, message = FilePermissionManager.check_file_access(
                file_record, user_id, action='download'
            )
            if not has_access:
                _audit(session, user_id, file_id, 'download_denied', message)
                session.commit()
                return jsonify({'error': message}), 403

            if file_record.downloads_left is not None and file_record.downloads_left <= 0:
                _mark_deleted(file_record)
                _audit(session, user_id, file_id, 'expired', 'expired_by_download_limit')
                _delete_from_storage(file_record)
                session.commit()
                return jsonify({'error': 'Download limit reached'}), 410

            file_content, served_node = _download_from_storage(file_record)
            file_record.download_count = (file_record.download_count or 0) + 1
            if file_record.downloads_left is not None:
                file_record.downloads_left -= 1

            details = f'node={served_node};downloads_left={file_record.downloads_left}'
            _audit(session, user_id, file_id, 'download', details)

            if file_record.downloads_left == 0:
                _mark_deleted(file_record)
                _audit(session, user_id, file_id, 'expired', 'expired_by_download_limit')
                _delete_from_storage(file_record)

            session.commit()

            return send_file(
                BytesIO(file_content),
                mimetype=file_record.mime_type or 'application/octet-stream',
                as_attachment=True,
                download_name=file_record.original_name or file_record.filename
            )
        except Exception as exc:
            session.rollback()
            logger.error(f'Download error: {exc}', exc_info=True)
            return jsonify({'error': 'Download failed'}), 500
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Unexpected download error: {exc}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@file_bp.route('/<file_id>', methods=['DELETE'])
@jwt_required
@rate_limited(limit=30, window_seconds=60, key_func=_rate_key)
def delete_file(file_id):
    try:
        user_id = get_current_user_id()
        session = Session()
        try:
            file_record = session.query(File).filter(File.id == file_id).first()
            if not file_record:
                return jsonify({'error': 'File not found'}), 404

            if not FilePermissionManager.can_delete_file(file_record, user_id):
                _audit(session, user_id, file_id, 'delete_denied', 'not_owner')
                session.commit()
                return jsonify({'error': 'Access denied: Only file owner can delete'}), 403

            deleted_nodes = _delete_from_storage(file_record)
            _mark_deleted(file_record)
            _audit(session, user_id, file_id, 'delete', f'nodes={",".join(deleted_nodes)}')
            session.commit()

            return jsonify({'message': 'File deleted successfully', 'file_id': file_id}), 200
        except Exception as exc:
            session.rollback()
            logger.error(f'Delete error: {exc}', exc_info=True)
            return jsonify({'error': 'Delete failed'}), 500
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Unexpected delete error: {exc}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@file_bp.route('/<file_id>/permissions', methods=['PUT'])
@jwt_required
@rate_limited(limit=30, window_seconds=60, key_func=_rate_key)
def update_file_permissions(file_id):
    try:
        user_id = get_current_user_id()
        data = request.get_json(silent=True)
        if not data or 'is_public' not in data:
            return jsonify({'error': 'is_public field is required'}), 400
        if not isinstance(data['is_public'], bool):
            return jsonify({'error': 'is_public must be boolean'}), 400

        session = Session()
        try:
            file_record = session.query(File).filter(File.id == file_id).first()
            if not file_record:
                return jsonify({'error': 'File not found'}), 404

            if not FilePermissionManager.can_modify_permissions(file_record, user_id):
                _audit(session, user_id, file_id, 'permission_denied', 'not_owner')
                session.commit()
                return jsonify({'error': 'Access denied: Only file owner can modify permissions'}), 403

            file_record.is_public = data['is_public']
            _audit(session, user_id, file_id, 'permission_update', f'is_public={data["is_public"]}')
            session.commit()

            status = 'public' if file_record.is_public else 'private'
            return jsonify({'message': f'File is now {status}', 'file': file_record.to_dict()}), 200
        except Exception as exc:
            session.rollback()
            logger.error(f'Permission update error: {exc}', exc_info=True)
            return jsonify({'error': 'Failed to update permissions'}), 500
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Unexpected permission error: {exc}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@file_bp.route('/audit-logs', methods=['GET'])
@jwt_required
@rate_limited(limit=60, window_seconds=60, key_func=_rate_key)
def audit_logs():
    try:
        user_id = get_current_user_id()
        limit = min(int(request.args.get('limit', 50)), 100)
        file_id = request.args.get('file_id')
        session = Session()
        try:
            query = session.query(FileAccessLog)

            if file_id:
                file_record = session.query(File).filter(File.id == file_id).first()
                if not file_record:
                    return jsonify({'error': 'File not found'}), 404
                if file_record.user_id != int(user_id):
                    return jsonify({'error': 'Access denied: Only file owner can view file audit logs'}), 403
                query = query.filter(FileAccessLog.file_id == file_id)
            else:
                query = query.filter(FileAccessLog.user_id == int(user_id))

            logs = query.order_by(FileAccessLog.access_date.desc()).limit(limit).all()
            return jsonify({'count': len(logs), 'logs': [log.to_dict() for log in logs]}), 200
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Audit log error: {exc}', exc_info=True)
        return jsonify({'error': 'Failed to retrieve audit logs'}), 500


@file_bp.route('/cleanup-expired', methods=['POST'])
@jwt_required
@rate_limited(limit=10, window_seconds=60, key_func=_rate_key)
def cleanup_expired_files():
    try:
        user_id = get_current_user_id()
        session = Session()
        try:
            cleaned = _cleanup_expired_files(session, user_id=user_id)
            session.commit()
            return jsonify({
                'message': 'Expired files cleaned',
                'count': len(cleaned),
                'file_ids': cleaned
            }), 200
        except Exception as exc:
            session.rollback()
            logger.error(f'Cleanup expired error: {exc}', exc_info=True)
            return jsonify({'error': 'Failed to clean expired files'}), 500
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Unexpected cleanup error: {exc}', exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@file_bp.route('/user/<int:user_id>/files', methods=['GET'])
def get_user_public_files(user_id):
    try:
        session = Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            public_files = session.query(File).filter(
                (File.user_id == user_id) &
                (File.is_public == True) &
                (File.deleted == False) &
                (File.is_deleted == False) &
                ((File.expires_at == None) | (File.expires_at > datetime.utcnow()))
            ).all()

            return jsonify({
                'user': user.to_dict(),
                'file_count': len(public_files),
                'files': [f.to_dict() for f in public_files]
            }), 200
        finally:
            session.close()
    except Exception as exc:
        logger.error(f'Get user files error: {exc}', exc_info=True)
        return jsonify({'error': 'Failed to retrieve user files'}), 500


@file_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'File service is running'}), 200
