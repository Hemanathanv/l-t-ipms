from typing import Optional
import uuid
from fastapi import Request, APIRouter, HTTPException, Depends, Response
from db import get_prisma
from auth.utils import hash_password, verify_password, create_session_token
from auth.dependencies import get_current_user, get_session_token, validate_token
from datetime import datetime, timedelta
from config import settings
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix=settings.API_SLUG + "/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    systemRole: str
    isActive: bool



@router.post("/login")
async def login(request: LoginRequest, response: Response):
    prisma = await get_prisma()
    
    try:
        user = await prisma.user.find_unique(where={"email": request.email.lower()})
    except Exception as e:
        print(f"Error querying user: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(request.password, user.passwordHash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user.isActive:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(days=7)
    try:
        await prisma.session.create(
            data={
                "id": str(uuid.uuid4()),
                "userId": user.id,
                "token": token,
                "expiresAt": expires_at,
                "createdAt": datetime.utcnow()
            }
        )
    except Exception as e:
        print(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail="Could not create session")
    
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )
    return {
        "status": "success",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "systemRole": user.systemRole,
            "isActive": user.isActive,
        },
        "token": token,
    }

@router.post("/logout")
async def logout(
    response: Response,
    token: Optional[str] = Depends(get_session_token)
):
    """
    Invalidate the current session.
    """
    if token:
        prisma = await get_prisma()
        try:
            await prisma.session.delete_many(
                where={"token": token}
            )
        except Exception:
            pass  # Session might not exist
    
    # Clear cookie
    response.delete_cookie(key="session_token")
    
    return {"status": "success", "message": "Logged out"}

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user = Depends(get_current_user)
):
    prisma = await get_prisma()
    user_password_hash = user.passwordHash
    
    if not verify_password(request.old_password, user_password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    
    if len(request.new_password) > 50:
        raise HTTPException(status_code=400, detail="New password is too long")
    
    new_hash = hash_password(request.new_password)
    try:
        await prisma.user.update(
            where={"id": user.id},
            data={"passwordHash": new_hash}
        )
    except Exception as e:
        print(f"Error updating password: {e}")
        raise HTTPException(status_code=500, detail="Could not update password")
    
    return {"status": "success", "message": "Password changed successfully"}
 
@router.get("/projects")
async def get_projects(token: Optional[str] = Depends(get_session_token)):
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token missing or malformed")
    
    if(await validate_token(token) == False):
        raise HTTPException(status_code=401, detail="Not authenticated")
    prisma = await get_prisma()

    try:
        # Get distinct projects from project summary table
        all_projects = await prisma.tbl01projectsummary.find_many(
            distinct=["projectKey"],
            order={"projectName": "asc"}
        )

        # Build unique projects list with start/end date variants for display
        seen = set()
        projects = []
        for row in all_projects:
            if row.projectKey not in seen:
                seen.add(row.projectKey)
                # Serialize dates for frontend (priority: Actual → Forecast → Baseline for start; same + Contractual for end)
                def _iso(d):
                    return d.isoformat() if d is not None else None
                projects.append({
                    "project_key": row.projectKey,
                    "name": row.projectId,
                    "project_description": row.projectName,
                    "location": row.projectLocation,
                    "start_date": _iso(row.baselineStartDate),
                    "end_date": _iso(row.baselineFinishDate),
                    "actual_start_date": _iso(row.actualStartDate),
                    "forecast_start_date": _iso(row.forecastStartDate),
                    "baseline_start_date": _iso(row.baselineStartDate),
                    "forecast_finish_date": _iso(row.forecastFinishDate),
                    "contractual_finish_date": _iso(row.contractualCompletionDate),
                    "baseline_finish_date": _iso(row.baselineFinishDate),
                    "contract_start_date": None,
                    "contract_end_date": _iso(row.contractualCompletionDate),
                    "progress_pct": float(row.projectElapsedPct) if row.projectElapsedPct is not None else None,
                    "elapsed_days": row.projectAgeDays,
                    "total_days": row.baselineDurationDays,
                    "max_forecast_delay_days_engineering": row.maxForecastDelayDaysEngineering,
                    "max_forecast_delay_days_construction": row.maxForecastDelayDaysConstruction,
                    "max_forecast_delay_days_procurement": row.maxForecastDelayDaysProcurement,
                    "max_forecast_delay_days_overall": row.maxForecastDelayDaysOverall,
                })

        return {"projects": projects}
    except AttributeError as e:
        # Prisma model not found (e.g. client not regenerated)
        return {"projects": [], "error": "Projects table unavailable"}
    except Exception as e:
        return {"projects": [], "error": str(e)}
