"""
API Routes - Upload, Download, File Management
Chương 5: UUID Identification
Chương 6: Caching
Chương 4: Distributed Locking
Chương 8: Load Balancing & Multi-Node Storage
"""

import os
import mimetypes
import logging
import random
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename

from src.config.settings import (
    ALLOWED_EXTENSIONS, MAX_FILE_SIZE, FILE_TTL_SECONDS
)
from src.utils.uuid_generator import generate_file_id


logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def select_storage_node(storage_manager, file_size: int) -> str:
    """
    Select best storage node using least-space (most free space) strategy
    Docker mode: queries nodes directly via HTTP /stats endpoint
    Returns node_id (node1, node2, node3)
    """
    try:
        # Get all registered nodes and check health
        nodes_health = storage_manager.check_all_health()
        if not nodes_health:
            logger.warning("No storage nodes registered, defaulting to node1")
            return 'node1'
        # Filter only online nodes
        online_nodes = {nid: health for nid, health in nodes_health.items() if health.get('status') == 'online'}
        if not online_nodes:
            logger.warning("No online nodes found, defaulting to node1")
            return 'node1'

        # Query /stats for each online node to get free space
        node_stats = {}
        for node_id in online_nodes:
            try:
                node_client = storage_manager.get_node(node_id)
                stats = node_client.get_stats()
                # Assume 100GB default if not present
                total_space = 100 * 1024 * 1024 * 1024
                used_space = stats.get('total_size', 0)
                free_space = total_space - used_space
                node_stats[node_id] = {
                    'free_space': free_space,
                    'file_count': stats.get('file_count', 0)
                }
            except Exception as e:
                logger.warning(f"Failed to get stats for {node_id}: {e}")

        if not node_stats:
            logger.warning("No stats available for online nodes, defaulting to node1")
            return 'node1'

        # Debug: log node_stats chi tiết
        logger.info(f"Node stats for selection: {node_stats}")
        # Nếu tất cả node đều có free_space bằng nhau, chọn node có ít file_count nhất
        free_spaces = [v['free_space'] for v in node_stats.values()]
        if len(set(free_spaces)) == 1:
            # All free_space equal - select by file_count with randomization for ties
            min_file_count = min(v['file_count'] for v in node_stats.values())
            candidates = [nid for nid, stats in node_stats.items() if stats['file_count'] == min_file_count]
            selected_id = random.choice(candidates)  # Random tie-break
            logger.info(f"Selected {selected_id} (tie-break by random among candidates with {min_file_count} files)")
        else:
            # Chọn node có nhiều free_space nhất
            selected_id = max(node_stats.items(), key=lambda x: x[1]['free_space'])[0]
            logger.info(f"Selected {selected_id} (free: {node_stats[selected_id]['free_space'] // (1024*1024)} MB, files: {node_stats[selected_id]['file_count']})")
        return selected_id
    except Exception as e:
        logger.error(f"Error selecting node: {e}, defaulting to node1")
        return 'node1'


def update_node_stats(db, node_id: str, file_size: int):
    """Update node statistics after file upload"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Update used_space and file_count
        cursor.execute("""
            UPDATE storage_nodes 
            SET used_space = used_space + ?,
                file_count = file_count + 1,
                last_heartbeat = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE node_id = ?
        """, (file_size, node_id))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Updated stats for {node_id}: +{file_size} bytes")
    
    except Exception as e:
        logger.error(f"Error updating node stats: {e}")


# =========================
# Simple Upload Endpoint
# =========================


@api_bp.route('/upload', methods=['POST'])
def upload_file():
    """
    Upload file endpoint with Multi-Node Load Balancing
    Chương 5: UUID Identification
    Chương 8: Load Balancing
    
    Returns:
        JSON with file_id, size, node
    """
    try:
        # Validate request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

        # Read file content
        file_content = file.read()
        file_size = len(file_content)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': f'File too large. Max: {MAX_FILE_SIZE / (1024**2):.0f}MB'}), 413
        
        # Generate UUID for file
        file_id = generate_file_id()
        
        # Get secure filename
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
        stored_filename = f"{file_id}.{file_extension}"
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(original_filename)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        logger.info(f"Uploading: {original_filename} - Size: {file_size} bytes")
        
        # Select storage node (load balancing)
        storage_manager = getattr(current_app, 'storage_manager', None)
        if not storage_manager:
            logger.error("storage_manager not found in current_app!")
            return jsonify({'error': 'Storage manager not initialized'}), 500
        
        logger.debug(f"Storage manager has {len(storage_manager.nodes)} nodes registered")
        selected_node = select_storage_node(storage_manager, file_size)
        
        logger.info(f"Selected node: {selected_node} for file {file_id}")
        
        # Upload to selected storage node via HTTP
        storage_manager = current_app.storage_manager
        node_client = storage_manager.get_node(selected_node)
        
        if not node_client:
            logger.error(f"Storage node {selected_node} not found")
            return jsonify({'error': 'Storage node unavailable'}), 503
        
        # Upload to storage node
        upload_result = node_client.upload_file(file_content, stored_filename)
        logger.info(f"Upload result from {selected_node}: {upload_result}")
        
        # Check if upload was successful (storage node returns 'status': 'success' or 'error')
        if upload_result.get('status') == 'error':
            error_msg = upload_result.get('error', 'Unknown upload error')
            logger.error(f"Upload failed to node {selected_node}: {error_msg}")
            return jsonify({'error': f'Storage upload failed: {error_msg}'}), 500
        
        if upload_result.get('status') != 'success':
            logger.warning(f"Unexpected status from {selected_node}: {upload_result.get('status')}")
            # Still treat as error if not explicitly 'success'
            return jsonify({'error': 'Storage upload returned unexpected status'}), 500
        
        logger.info(f"File uploaded successfully to {selected_node}")
        
        # Save to database
        db = current_app.db
        expires_at = (datetime.utcnow() + timedelta(seconds=FILE_TTL_SECONDS)).isoformat()
        
        db_result = db.add_file(
            file_id=file_id,
            filename=stored_filename,
            original_name=original_filename,
            file_size=file_size,
            mime_type=mime_type,
            primary_node=selected_node,
            expires_at=expires_at
        )
        
        if not db_result:
            logger.error(f"Failed to save file metadata to database for {file_id}")
            return jsonify({'error': 'Failed to save file metadata to database'}), 500
        
        logger.info(f"File metadata saved to database: {file_id}")
        
        # Replication (Phase 2)
        replication_manager = getattr(current_app, 'replication_manager', None)
        if replication_manager:
            replica_nodes = replication_manager.select_replica_nodes(selected_node)
            if replica_nodes:
                replication_results = replication_manager.replicate_file(
                    file_id=file_id,
                    filename=stored_filename,
                    primary_node=selected_node,
                    replica_nodes=replica_nodes,
                    db=db
                )
                logger.info(f"Replication results for {file_id}: {replication_results}")
        
        # Update node statistics
        update_node_stats(db, selected_node, file_size)
        
        logger.info(f"File saved: {file_id} -> {selected_node}/{stored_filename}")
        
        # Create background task for image processing
        if mime_type.startswith('image/'):
            task_id = db.add_task(file_id, 'thumbnail')
            if task_id:
                logger.info(f"📸 Thumbnail task created: {task_id} for file {file_id}")
            else:
                logger.warning(f"Failed to create thumbnail task for {file_id}")
        
        return jsonify({
            'id': file_id,
            'filename': stored_filename,
            'original_name': original_filename,
            'size': file_size,
            'node': selected_node,
            'download_url': f"/api/download/{file_id}"
        }), 200
    
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        if 'db_session' in locals():
            try:
                db_session.rollback()
            except:
                pass
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@api_bp.route('/download/<file_id>', methods=['GET'])
def download_file(file_id: str):
    """Download file endpoint with failover support (Phase 2)"""
    try:
        db = current_app.db
        file_record = db.get_file(file_id)
        if not file_record:
            return jsonify({'error': 'File not found'}), 404

        primary_node = file_record.get('primary_node', 'node1')
        filename = file_record.get('filename')
        replica_nodes = file_record.get('replica_nodes', '')
        
        if not filename:
            return jsonify({'error': 'File missing filename'}), 500

        # Parse replica nodes
        replica_list = [n.strip() for n in replica_nodes.split(',') if n.strip()] if replica_nodes else []
        
        # Try primary node first
        storage_manager = current_app.storage_manager
        replication_manager = getattr(current_app, 'replication_manager', None)
        
        nodes_to_try = [primary_node] + replica_list
        
        for try_node in nodes_to_try:
            try:
                node_client = storage_manager.get_node(try_node)
                if not node_client:
                    logger.debug(f"Node client not found for {try_node}")
                    continue
                
                file_content = node_client.download_file(filename)
                if file_content:
                    # If we had to failover, update database
                    if try_node != primary_node:
                        logger.warning(f"Failover: Downloaded {file_id} from {try_node} (primary {primary_node} failed)")
                        
                        if replication_manager:
                            replication_manager.handle_primary_failure(
                                file_id=file_id,
                                filename=filename,
                                failed_primary=primary_node,
                                replica_nodes=replica_list,
                                db=db
                            )
                    
                    # Return file content with proper headers
                    from flask import Response
                    response = Response(file_content)
                    response.headers['Content-Type'] = file_record.get('mime_type') or 'application/octet-stream'
                    response.headers['Content-Disposition'] = f'attachment; filename="{file_record.get("original_name") or filename}"'
                    return response
                    
            except Exception as e:
                logger.debug(f"Failed to download from node {try_node}: {e}")
                continue
        
        # All nodes failed
        logger.error(f"Failed to download {file_id} from all nodes: primary={primary_node}, replicas={replica_list}")
        return jsonify({'error': 'File unavailable on all nodes'}), 503
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api_bp.route('/legacy/files', methods=['GET'])
def list_legacy_files():
    """Return recent files with minimal metadata for gallery (masonry).
    
    Requires JWT authentication - returns 401 if no valid token provided
    """
    try:
        # Check for authorization header and validate token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized - missing or invalid token'}), 401
        
        # Extract and validate the token
        token = auth_header.split(' ')[1] if ' ' in auth_header else None
        if not token:
            return jsonify({'error': 'Unauthorized - missing token'}), 401
        
        # Try to import and validate the token
        try:
            from src.middleware.jwt_auth import verify_jwt_token
            payload = verify_jwt_token(token)
            if not payload:
                return jsonify({'error': 'Unauthorized - invalid or expired token'}), 401
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return jsonify({'error': 'Unauthorized - invalid token'}), 401
        
        db = current_app.db
        # Get all files from database
        all_files_data = db.get_all_files(limit=50)
        
        result = []
        for file_data in all_files_data:
            created_at = file_data.get('created_at')
            if created_at is not None and not isinstance(created_at, str):
                try:
                    created_at = created_at.isoformat()
                except Exception:
                    created_at = str(created_at)

            item = {
                'id': file_data.get('id'),
                'filename': file_data.get('filename'),
                'original_name': file_data.get('original_name'),
                'size': file_data.get('file_size', 0),
                'mime_type': file_data.get('mime_type'),
                'node': file_data.get('primary_node', 'node1'),
                'created_at': created_at,
                'download_url': f"/api/download/{file_data.get('id')}"
            }
            result.append(item)

        return jsonify({'count': len(result), 'files': result}), 200
    except Exception as e:
        logger.error(f"List files error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api_bp.route('/nodes', methods=['GET'])
def get_nodes():
    """
    Get storage nodes information with statistics
    Docker mode: queries nodes directly via HTTP health checks
    """
    try:
        # Get storage manager and query all nodes via HTTP
        storage_manager = getattr(current_app, 'storage_manager', None)
        if not storage_manager:
            logger.error("storage_manager not found in current_app for get_nodes!")
            return jsonify({'error': 'Storage manager not initialized', 'total_nodes': 0, 'nodes': []}), 500
        
        logger.info(f"Storage manager has nodes: {list(storage_manager.nodes.keys())}")
        
        nodes_health = storage_manager.check_all_health()
        logger.info(f"Nodes health check result: {nodes_health}")
        
        nodes_data = []
        for node_id, health_data in nodes_health.items():
            status = health_data.get('status', 'offline')
            file_count = health_data.get('file_count', 0)
            
            node_info = {
                'node_id': node_id,
                'host': 'docker',
                'port': '8000',
                'path': health_data.get('storage_path', '/data'),
                'is_online': status == 'online',
                'total_space': 100 * 1024 * 1024 * 1024,  # 100GB default
                'used_space': 0,  # TODO: get from node stats endpoint
                'free_space': 100 * 1024 * 1024 * 1024,
                'usage_percent': 0,
                'file_count': file_count,
                'error_count': 0,
                'last_heartbeat': health_data.get('timestamp', datetime.utcnow().isoformat()),
                'status': status
            }
            nodes_data.append(node_info)
        
        logger.info(f"Returning {len(nodes_data)} nodes")
        return jsonify({
            'total_nodes': len(nodes_data),
            'nodes': nodes_data
        }), 200
    
    except Exception as e:
        logger.error(f"Get nodes error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api_bp.route('/replication/status', methods=['GET'])
def replication_status():
    """
    Get replication status for all files
    Phase 2: Show file replicas and failover status
    """
    try:
        replication_manager = getattr(current_app, 'replication_manager', None)
        if not replication_manager:
            return jsonify({'error': 'Replication manager not initialized'}), 500
        
        db = current_app.db
        
        # Get all files with replication info
        all_files = db.get_all_files(limit=1000)
        
        files_with_replicas = []
        for file_data in all_files:
            files_with_replicas.append({
                'file_id': file_data.get('id'),
                'original_name': file_data.get('original_name'),
                'primary_node': file_data.get('primary_node'),
                'replica_nodes': file_data.get('replica_nodes', '').split(',') if file_data.get('replica_nodes') else [],
                'total_replicas': len(file_data.get('replica_nodes', '').split(',')) if file_data.get('replica_nodes') else 0,
                'size': file_data.get('file_size', 0)
            })
        
        node_health = replication_manager.get_node_health()
        
        return jsonify({
            'total_files': len(files_with_replicas),
            'files': files_with_replicas,
            'nodes_health': node_health
        }), 200
        
    except Exception as e:
        logger.error(f"Replication status error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get system statistics for admin dashboard"""
    try:
        db = current_app.db
        
        # Get all files
        all_files = db.get_all_files(limit=1000)
        
        # Get storage nodes
        nodes = db.get_storage_nodes()
        
        # Calculate statistics
        total_files = len(all_files)
        total_size = sum(f.get('file_size', 0) for f in all_files)
        
        # Group files by node
        files_by_node = {}
        size_by_node = {}
        for f in all_files:
            node = f.get('primary_node', 'unknown')
            files_by_node[node] = files_by_node.get(node, 0) + 1
            size_by_node[node] = size_by_node.get(node, 0) + f.get('file_size', 0)
        
        # Storage capacity
        total_capacity = sum(n.get('total_space', 0) for n in nodes)
        total_used = sum(n.get('used_space', 0) for n in nodes)
        total_free = total_capacity - total_used
        
        # Node status
        online_nodes = sum(1 for n in nodes if n.get('is_online', 0))
        offline_nodes = len(nodes) - online_nodes
        
        stats = {
            'files': {
                'total': total_files,
                'total_size': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'by_node': files_by_node,
                'size_by_node': size_by_node
            },
            'storage': {
                'total_capacity': total_capacity,
                'total_capacity_gb': round(total_capacity / (1024 ** 3), 2),
                'total_used': total_used,
                'total_used_mb': round(total_used / (1024 * 1024), 2),
                'total_free': total_free,
                'total_free_gb': round(total_free / (1024 ** 3), 2),
                'usage_percent': round((total_used / total_capacity * 100), 2) if total_capacity > 0 else 0
            },
            'nodes': {
                'total': len(nodes),
                'online': online_nodes,
                'offline': offline_nodes
            }
        }
        
        return jsonify(stats), 200
    
    except Exception as e:
        logger.error(f"Get stats error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """
    Get background tasks status
    
    Query parameters:
        - status: pending/processing/completed/failed (optional)
        - limit: number of tasks to return (default: 50)
    
    Returns:
        JSON array of tasks with their status
    """
    try:
        db = current_app.db
        status_filter = request.args.get('status', None)
        limit = int(request.args.get('limit', 50))
        
        # Get tasks from database
        conn = db.get_connection()
        cursor = conn.cursor()
        
        if status_filter:
            cursor.execute("""
                SELECT t.*, f.filename, f.original_name, f.mime_type
                FROM tasks t
                LEFT JOIN files f ON t.file_id = f.id
                WHERE t.status = ?
                ORDER BY t.created_at DESC
                LIMIT ?
            """, (status_filter, limit))
        else:
            cursor.execute("""
                SELECT t.*, f.filename, f.original_name, f.mime_type
                FROM tasks t
                LEFT JOIN files f ON t.file_id = f.id
                ORDER BY t.created_at DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            tasks.append({
                'id': row['id'],
                'file_id': row['file_id'],
                'filename': row['filename'],
                'original_name': row['original_name'],
                'task_type': row['task_type'],
                'status': row['status'],
                'result': row['result'],
                'error_message': row['error_message'],
                'created_at': row['created_at'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'retry_count': row['retry_count']
            })
        
        return jsonify(tasks), 200
    
    except Exception as e:
        logger.error(f"Get tasks error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


# ============ PHASE 3: Redis Cluster Health Monitoring ============

@api_bp.route('/redis/health', methods=['GET'])
def redis_health():
    """Get Redis and Sentinel cluster health status"""
    try:
        import redis
        
        sentinel_client = getattr(current_app, 'sentinel_client', None)
        
        if not sentinel_client:
            return jsonify({'error': 'Redis not initialized'}), 500
        
        # Get the actual Redis client (sentinel_client.client is redis.Redis instance)
        redis_conn = sentinel_client.client
        redis_info = redis_conn.info()
        
        # Build cluster topology
        master_info = {'host': 'redis-master', 'port': 6379}
        slaves_info = [
            {'host': 'redis-slave1', 'port': 6380},
            {'host': 'redis-slave2', 'port': 6381}
        ]
        
        # Try to detect slave info from Redis servers
        try:
            # Check if we can connect to slaves
            for i, slave_port in enumerate([6380, 6381]):
                try:
                    slave_conn = redis.Redis(
                        host='localhost',
                        port=slave_port,
                        decode_responses=True,
                        socket_connect_timeout=2
                    )
                    slave_info = slave_conn.info()
                    if slave_info.get('role') == 'slave':
                        slaves_info[i]['status'] = 'online'
                        slaves_info[i]['lag'] = slave_info.get('slave_repl_offset', 0)
                except:
                    slaves_info[i]['status'] = 'offline'
        except:
            pass
        
        response = {
            'status': 'healthy',
            'redis_cluster': {
                'master': master_info,
                'slaves': slaves_info,
                'master_name': 'fileshare-master'
            },
            'redis_stats': {
                'used_memory': redis_info.get('used_memory_human', 'N/A'),
                'used_memory_peak': redis_info.get('used_memory_peak_human', 'N/A'),
                'connected_clients': redis_info.get('connected_clients', 0),
                'role': redis_info.get('role', 'unknown'),
                'replication_offset': redis_info.get('replication_offset', 0)
            }
        }
        
        logger.info(f"Redis health response: {response}")
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Redis health check error: {e}")
        return jsonify({'error': str(e), 'status': 'error'}), 500


@api_bp.route('/redis/stats', methods=['GET'])
def redis_stats():
    """Get Redis cache statistics"""
    try:
        cache_manager = getattr(current_app, 'cache_manager', None)
        if not cache_manager:
            return jsonify({'error': 'Cache manager not initialized'}), 500
        
        cache_info = cache_manager.get_cache_info()
        
        return jsonify({
            'cache': cache_info,
            'cache_stats': {
                'hit_rate': f"{cache_info.get('keyspace_hits', 0) / max(cache_info.get('keyspace_hits', 0) + cache_info.get('keyspace_misses', 1), 1) * 100:.2f}%",
                'total_accesses': cache_info.get('keyspace_hits', 0) + cache_info.get('keyspace_misses', 0)
            }
        }), 200
    except Exception as e:
        logger.error(f"Redis stats error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/redis/sentinel/status', methods=['GET'])
def redis_sentinel_status():
    """Get detailed Sentinel cluster status"""
    try:
        sentinel_client = getattr(current_app, 'sentinel_client', None)
        if not sentinel_client:
            return jsonify({'error': 'Sentinel client not initialized'}), 500
        
        sentinel_info = sentinel_client.get_sentinel_info()
        
        return jsonify({
            'sentinel_status': 'operational',
            'master_name': sentinel_info.get('master_name'),
            'master': sentinel_info.get('master'),
            'slaves': sentinel_info.get('slaves', []),
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Sentinel status error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/locks/info/<resource_type>/<resource_id>', methods=['GET'])
def lock_info(resource_type: str, resource_id: str):
    """Get information about a distributed lock"""
    try:
        lock_manager = getattr(current_app, 'lock_manager', None)
        if not lock_manager:
            return jsonify({'error': 'Lock manager not initialized'}), 500
        
        lock_info = lock_manager.get_lock_info(resource_type, resource_id)
        
        return jsonify(lock_info), 200
    except Exception as e:
        logger.error(f"Lock info error: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# PHASE 4.2: PgBouncer Connection Pool Monitoring
# ==========================================

@api_bp.route('/pool/stats', methods=['GET'])
def pool_stats():
    """Get PgBouncer connection pool statistics"""
    try:
        from src.gateway.pgbouncer_monitor import get_pgbouncer_stats
        stats = get_pgbouncer_stats()
        return jsonify(stats), 200 if stats.get('status') == 'ok' else 500
    except Exception as e:
        logger.error(f"Pool stats error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/pool/pools', methods=['GET'])
def pool_pools():
    """Get PgBouncer pool information (client/server connections per pool)"""
    try:
        from src.gateway.pgbouncer_monitor import get_pgbouncer_pools
        pools = get_pgbouncer_pools()
        return jsonify(pools), 200 if pools.get('status') == 'ok' else 500
    except Exception as e:
        logger.error(f"Pool pools error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/pool/clients', methods=['GET'])
def pool_clients():
    """Get connected clients to PgBouncer"""
    try:
        from src.gateway.pgbouncer_monitor import get_pgbouncer_clients
        clients = get_pgbouncer_clients()
        return jsonify(clients), 200 if clients.get('status') == 'ok' else 500
    except Exception as e:
        logger.error(f"Pool clients error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/pool/config', methods=['GET'])
def pool_config():
    """Get PgBouncer configuration settings"""
    try:
        from src.gateway.pgbouncer_monitor import get_pgbouncer_config
        config = get_pgbouncer_config()
        return jsonify(config), 200 if config.get('status') == 'ok' else 500
    except Exception as e:
        logger.error(f"Pool config error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/pool/summary', methods=['GET'])
def pool_summary():
    """Get summary of connection pool metrics"""
    try:
        from src.gateway.pgbouncer_monitor import get_pool_summary
        summary = get_pool_summary()
        return jsonify(summary), 200 if summary.get('status') == 'ok' else 500
    except Exception as e:
        logger.error(f"Pool summary error: {e}")
        return jsonify({'error': str(e)}), 500
