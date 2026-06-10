"""
Gateway API - Flask Application Factory
Chương 8: Load Balancing & High Availability
Chương 4: Distributed Locking (Redis)
"""

import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import logging
from datetime import datetime

# Import configuration and middleware
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config.settings import (
    DEBUG as FLASK_DEBUG,
    HOST as FLASK_HOST,
    PORT as FLASK_PORT,
    DATABASE_URL, LOGS_DIR, LOG_LEVEL,
    RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD
)
from src.middleware.models import get_db, get_session
from src.middleware.redis_client import get_redis_client
from src.middleware.redis_sentinel_client import RedisSentinelClient
from src.middleware.cache_manager import CacheManager
from src.middleware.distributed_lock_manager import DistributedLockManager
from src.gateway.storage_client import StorageNodeManager
from src.gateway.replication_manager import ReplicationManager

# Configure logging
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'gateway.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_app():
    """
    Application Factory Pattern
    Khởi tạo Flask app với tất cả dependencies
    """
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
    
    # Enable CORS for all routes
    CORS(app)
    
    # Initialize database
    try:
        app.db = get_db()
        app.db_session = get_session()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Initialize Redis client
    try:
        redis_client = get_redis_client()
        if redis_client.health_check():
            app.redis_client = redis_client
            logger.info("Redis client initialized successfully")
        else:
            raise Exception("Redis health check failed")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise
    
    # Initialize Redis Sentinel client for HA (Phase 3)
    try:
        sentinel_client = RedisSentinelClient()
        app.sentinel_client = sentinel_client
        logger.info("✅ Redis Sentinel client initialized for Phase 3: High Availability")
        
        # Get Sentinel cluster info
        sentinel_info = sentinel_client.get_sentinel_info()
        if sentinel_info:
            logger.info(f"Sentinel cluster info: {sentinel_info}")
    except Exception as e:
        logger.warning(f"Redis Sentinel not available, using direct connection: {e}")
        # Continue without Sentinel - direct connection will be used
    
    # Initialize Cache Manager (Phase 3)
    try:
        sentinel_client = getattr(app, 'sentinel_client', None) or redis_client
        cache_manager = CacheManager(sentinel_client if hasattr(sentinel_client, 'client') else None)
        app.cache_manager = cache_manager
        logger.info("✅ Cache Manager initialized (Phase 3)")
    except Exception as e:
        logger.warning(f"Cache Manager initialization failed: {e}")
    
    # Initialize Distributed Lock Manager (Phase 3)
    try:
        sentinel_client = getattr(app, 'sentinel_client', None) or redis_client
        lock_manager = DistributedLockManager(sentinel_client if hasattr(sentinel_client, 'client') else None)
        app.lock_manager = lock_manager
        logger.info("✅ Distributed Lock Manager initialized (Phase 3)")
    except Exception as e:
        logger.warning(f"Lock Manager initialization failed: {e}")
    
    # Initialize Storage Node Manager
    try:
        storage_manager = StorageNodeManager()
        # Register storage nodes from environment variables
        node1_url = os.getenv('NODE1_URL', 'http://localhost:8001')
        node2_url = os.getenv('NODE2_URL', 'http://localhost:8002')
        node3_url = os.getenv('NODE3_URL', 'http://localhost:8003')
        
        storage_manager.register_node('node1', node1_url)
        storage_manager.register_node('node2', node2_url)
        storage_manager.register_node('node3', node3_url)
        
        app.storage_manager = storage_manager
        logger.info(f"Storage nodes registered: node1={node1_url}, node2={node2_url}, node3={node3_url}")
        
        # Check health of all nodes
        health_status = storage_manager.check_all_health()
        logger.info(f"Storage nodes health: {health_status}")
    except Exception as e:
        logger.error(f"Failed to initialize storage manager: {e}")
        raise
    
    # Initialize Replication Manager for Phase 2
    try:
        node_urls = {
            'node1': os.getenv('NODE1_URL', 'http://localhost:8001'),
            'node2': os.getenv('NODE2_URL', 'http://localhost:8002'),
            'node3': os.getenv('NODE3_URL', 'http://localhost:8003')
        }
        replication_manager = ReplicationManager(node_urls)
        app.replication_manager = replication_manager
        logger.info("Replication Manager initialized for Phase 2: Node Replication & Failover")
    except Exception as e:
        logger.error(f"Failed to initialize replication manager: {e}")
        raise
    
    # Register blueprints
    from src.gateway.routes import api_bp
    from src.gateway.auth_routes import auth_bp
    from src.gateway.file_routes import file_bp
    
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(file_bp, url_prefix='/api/files')
    
    # Health check endpoint (no prefix)
    @app.route('/health', methods=['GET'])
    def health():
        """System health check endpoint"""
        try:
            # Check database
            db_healthy = app.db is not None
            
            # Check Redis
            redis_healthy = app.redis_client.health_check()

            # Check RabbitMQ (simple connect)
            rabbitmq_healthy = False
            try:
                import pika
                credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
                params = pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=credentials, blocked_connection_timeout=2)
                connection = pika.BlockingConnection(params)
                rabbitmq_healthy = connection.is_open
                connection.close()
            except Exception:
                rabbitmq_healthy = False
            
            # Overall health
            healthy = db_healthy and redis_healthy and rabbitmq_healthy
            
            return jsonify({
                'status': 'healthy' if healthy else 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {
                    'database': 'ok' if db_healthy else 'error',
                    'redis': 'ok' if redis_healthy else 'error',
                    'rabbitmq': 'ok' if rabbitmq_healthy else 'error'
                }
            }), 200 if healthy else 503
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }), 503
    
    # Frontend routes (static files)
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'frontend')
    
    @app.route('/', methods=['GET'])
    def root():
        """Serve frontend HTML"""
        response = send_from_directory(frontend_dir, 'index.html')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    @app.route('/index.html', methods=['GET'])
    def index_html():
        """Serve index.html explicitly"""
        response = send_from_directory(frontend_dir, 'index.html')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    
    @app.route('/admin', methods=['GET'])
    def admin():
        """Serve admin dashboard"""
        return send_from_directory(frontend_dir, 'admin.html')
    
    @app.route('/admin.html', methods=['GET'])
    def admin_html():
        """Serve admin.html explicitly"""
        return send_from_directory(frontend_dir, 'admin.html')

    @app.route('/login.html', methods=['GET'])
    def login_html():
        """Serve login.html explicitly"""
        return send_from_directory(frontend_dir, 'login.html')

    @app.route('/register.html', methods=['GET'])
    def register_html():
        """Serve register.html explicitly"""
        return send_from_directory(frontend_dir, 'register.html')

    @app.route('/files.html', methods=['GET'])
    def files_html():
        """Serve files.html explicitly"""
        return send_from_directory(frontend_dir, 'files.html')
    
    @app.route('/styles.css', methods=['GET'])
    def styles_css():
        """Serve styles.css"""
        return send_from_directory(frontend_dir, 'styles.css')

    @app.route('/admin.css', methods=['GET'])
    def admin_css():
        """Serve admin.css"""
        return send_from_directory(frontend_dir, 'admin.css')
    
    @app.route('/app.js', methods=['GET'])
    def app_js():
        """Serve app.js"""
        return send_from_directory(frontend_dir, 'app.js')
    
    @app.route('/js/<path:filename>', methods=['GET'])
    def js_files(filename):
        """Serve JS files from js/ directory"""
        return send_from_directory(os.path.join(frontend_dir, 'js'), filename)

    @app.route('/css/<path:filename>', methods=['GET'])
    def css_files(filename):
        """Serve CSS files from css/ directory"""
        return send_from_directory(os.path.join(frontend_dir, 'css'), filename)
    
    # Storage files route
    storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage')
    
    @app.route('/storage/<node>/<filename>', methods=['GET'])
    def serve_storage_file(node, filename):
        """Serve uploaded files from storage"""
        try:
            node_dir = os.path.join(storage_dir, node)
            return send_from_directory(node_dir, filename)
        except FileNotFoundError:
            return jsonify({'error': 'File not found'}), 404
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal error: {error}")
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({'error': 'File too large. Maximum size is 100MB'}), 413
    
    logger.info(f"Gateway application created successfully")
    return app


if __name__ == '__main__':
    app = create_app()
    logger.info(f"Starting Gateway API on {FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
