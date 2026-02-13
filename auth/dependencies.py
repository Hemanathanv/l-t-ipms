from typing import Optional, Callable
from datetime import datetime
from functools import wraps
from fastapi import Request, HTTPException, Depends, Cookie
from db import get_prisma


async def get_session_token(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias="session_token")
) -> Optional[str]:
    """Extract session token from cookie or Authorization header."""
    # Try cookie first
    if session_token:
        return session_token
    
    # Try Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    return None


async def is_authenticated(
    token: Optional[str] = Depends(get_session_token)
) -> bool:
    """
    Check if user is authenticated. Returns True or False.
    
    Can be used as a decorator:
        @router.get("/protected")
        @is_authenticated
        async def protected_route():
            return {"message": "You are authenticated"}
    
    Or as a dependency:
        @router.get("/protected")
        async def protected_route(authenticated = Depends(is_authenticated)):
            if not authenticated:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return {"message": "You are authenticated"}
    
    Returns:
        bool: True if user is authenticated, False otherwise
    """
    if not token:
        return False
    
    try:
        prisma = await get_prisma()
        
        session = await prisma.session.find_first(
            where={
                "token": token,
                "expiresAt": {"gt": datetime.utcnow()}
            },
            include={"user": True}
        )
        
        if not session or not session.user:
            return False
        
        if not session.user.isActive:
            return False
        
        return True
        
    except Exception:
        return False


def authenticate(func: Callable) -> Callable:
    """
    Decorator to check authentication and raise error if not authenticated.
    Returns True/False from is_authenticated().
    
    Usage:
        @router.get("/protected")
        @authenticate
        async def protected_route():
            return {"message": "You are authenticated"}
    
    Raises:
        HTTPException (401): If user is not authenticated or inactive
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        is_auth = await is_authenticated()
        if not is_auth:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated"
            )
        return await func(*args, **kwargs)
    return wrapper


async def get_current_user(
    token: Optional[str] = Depends(get_session_token)
):
    """
    Get the current authenticated user from session token.
    Raises HTTPException if not authenticated.
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    
    prisma = await get_prisma()
    
    session = await prisma.session.find_first(
        where={
            "token": token,
            "expiresAt": {"gt": datetime.utcnow()}
        },
        include={"user": True}
    )
    
    if not session or not session.user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session"
        )
    
    if not session.user.isActive:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )
    
    return session.user

async def validate_token(token: str) -> bool:
    """
    Check if a given token is valid or not.
    Returns only boolean response.
    
    Usage:
        # In your code
        is_valid = await validate_token(user_token)
        if is_valid:
            print("Token is valid")
        else:
            print("Token is invalid")
    
    Args:
        token (str): The token string to validate
    
    Returns:
        bool: True if token is valid, False otherwise
    
    Checks:
        - Token exists in database
        - Token has not expired
        - User account is active
    """
    
    
    print(token, "TOKENNN")
    if not token or not isinstance(token, str) or token.strip() == "":
        return False
    
    try:
        prisma = await get_prisma()
        
        session = await prisma.session.find_first(
            where={
                "token": token.strip(),
                "expiresAt": {"gt": datetime.utcnow()}
            },
            include={"user": True}
        )
        
        print(session, "SESSION")
        if not session or not session.user:
            return False
        
        if not session.user.isActive:
            return False
        
        return True
         
    except Exception:
        return False