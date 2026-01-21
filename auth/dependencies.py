"""
FastAPI dependencies for authentication.
"""
from typing import Optional
from datetime import datetime
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
    
    # Find valid session
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


async def get_optional_user(
    token: Optional[str] = Depends(get_session_token)
):
    """
    Get the current user if authenticated, otherwise return None.
    Does not raise an exception for unauthenticated requests.
    """
    if not token:
        return None
    
    try:
        prisma = await get_prisma()
        
        session = await prisma.session.find_first(
            where={
                "token": token,
                "expiresAt": {"gt": datetime.utcnow()}
            },
            include={"user": True}
        )
        
        if session and session.user and session.user.isActive:
            return session.user
        
        return None
    except Exception:
        return None
