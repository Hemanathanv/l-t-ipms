"""
Auth utilities for password hashing and session token generation.
"""
import secrets
import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'), 
            password_hash.encode('utf-8')
        )
    except Exception:
        return False


def create_session_token() -> str:
    """Generate a secure random session token."""
    return secrets.token_urlsafe(32)
