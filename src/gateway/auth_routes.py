"""
Authentication Routes - Register, Login, User Profile
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import logging

from src.middleware.auth_models import Base, User
from src.middleware.jwt_auth import create_jwt_token, jwt_required, get_current_user_id

# Setup
auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres_secure_pass@postgres-master:5432/fileshare')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

COMMON_PASSWORDS = {
    'password',
    'password1',
    'password123',
    'admin',
    'admin123',
    'admin1234',
    'qwerty123',
    '12345678',
    '123456789',
    'letmein123',
    'welcome1',
    'welcome123',
}


def validate_password_policy(password: str):
    """Return an error message if password does not meet the MVP policy."""
    if password.lower() in COMMON_PASSWORDS:
        return 'password is too common'
    if len(password) < 8:
        return 'password must be at least 8 characters'
    if not any(ch.isupper() for ch in password):
        return 'password must contain at least one uppercase letter'
    if not any(ch.islower() for ch in password):
        return 'password must contain at least one lowercase letter'
    if not any(ch.isdigit() for ch in password):
        return 'password must contain at least one number'
    return None


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register new user
    
    Request body:
    {
        "username": "john_doe",
        "email": "john@example.com",
        "password": "securepassword123",
        "full_name": "John Doe"
    }
    
    Returns:
        JWT token if successful
    """
    try:
        data = request.get_json()
        
        # Validation
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        full_name = data.get('full_name', '').strip()
        
        if not username or not email or not password:
            return jsonify({'error': 'username, email, and password are required'}), 400
        
        if len(username) < 3:
            return jsonify({'error': 'username must be at least 3 characters'}), 400
        
        password_error = validate_password_policy(password)
        if password_error:
            return jsonify({'error': password_error}), 400
        
        if '@' not in email:
            return jsonify({'error': 'Invalid email format'}), 400
        
        session = Session()
        try:
            # Check if user already exists
            existing_user = session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing_user:
                return jsonify({'error': 'Username or email already exists'}), 409
            
            # Create new user
            new_user = User(
                username=username,
                email=email,
                full_name=full_name or username
            )
            new_user.set_password(password)
            
            session.add(new_user)
            session.commit()
            
            # Generate JWT token
            token = create_jwt_token(new_user.id, new_user.username, new_user.email)
            
            return jsonify({
                'message': 'User registered successfully',
                'user': new_user.to_dict(),
                'token': token
            }), 201
        
        except Exception as e:
            session.rollback()
            logger.error(f'Registration error: {str(e)}')
            return jsonify({'error': 'Registration failed'}), 500
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f'Unexpected error in register: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login user
    
    Request body:
    {
        "username": "john_doe",
        "password": "securepassword123"
    }
    
    Returns:
        JWT token if successful
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'username and password are required'}), 400
        
        session = Session()
        try:
            # Find user by username or email
            user = session.query(User).filter(
                (User.username == username) | (User.email == username)
            ).first()
            
            if not user or not user.check_password(password):
                return jsonify({'error': 'Invalid username or password'}), 401
            
            if not user.is_active:
                return jsonify({'error': 'Account is inactive'}), 403
            
            # Generate JWT token
            token = create_jwt_token(user.id, user.username, user.email)
            
            return jsonify({
                'message': 'Login successful',
                'user': user.to_dict(),
                'token': token
            }), 200
        
        except Exception as e:
            logger.error(f'Login error: {str(e)}')
            return jsonify({'error': 'Login failed'}), 500
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f'Unexpected error in login: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/profile', methods=['GET'])
@jwt_required
def get_profile():
    """
    Get current user profile
    Requires: Authorization header with JWT token
    
    Returns:
        User profile data
    """
    try:
        user_id = get_current_user_id()
        
        session = Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            return jsonify({
                'user': user.to_dict()
            }), 200
        
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f'Profile error: {str(e)}')
        return jsonify({'error': 'Failed to retrieve profile'}), 500


@auth_bp.route('/profile', methods=['PUT'])
@jwt_required
def update_profile():
    """
    Update current user profile
    Requires: Authorization header with JWT token
    
    Request body:
    {
        "full_name": "John Doe Updated",
        "email": "newemail@example.com"
    }
    
    Returns:
        Updated user profile
    """
    try:
        user_id = get_current_user_id()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        session = Session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Update fields if provided
            if 'full_name' in data:
                user.full_name = data['full_name'].strip()
            
            if 'email' in data:
                new_email = data['email'].strip()
                # Check if email already exists
                existing = session.query(User).filter(
                    (User.email == new_email) & (User.id != user_id)
                ).first()
                if existing:
                    return jsonify({'error': 'Email already in use'}), 409
                user.email = new_email
            
            session.commit()
            
            return jsonify({
                'message': 'Profile updated successfully',
                'user': user.to_dict()
            }), 200
        
        except Exception as e:
            session.rollback()
            logger.error(f'Profile update error: {str(e)}')
            return jsonify({'error': 'Failed to update profile'}), 500
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f'Unexpected error in update_profile: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'Auth service is running'}), 200
