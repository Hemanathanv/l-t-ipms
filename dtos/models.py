from typing import Optional
from pydantic import BaseModel, EmailStr, Field

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

class SessionResponse(BaseModel):
    user: UserResponse
    token: str



class SRARecoveryAdviseInput(BaseModel):
    """Input schema for SRA recovery advise tool"""
    project_id: Optional[str] = Field(None, description="Project ID to analyze recovery options for (e.g., 'PRJ_001')")
    activity_id: Optional[str] = Field(None, description="Specific activity ID to focus recovery on")
    resource_type: Optional[str] = Field(None, description="Type of resource to consider (e.g., 'labor', 'equipment', 'material')")


class SRASimulateInput(BaseModel):
    """Input schema for SRA simulation tool"""
    project_id: Optional[str] = Field(None, description="Project ID to run simulation for")
    resource_type: Optional[str] = Field(None, description="Type of resource to simulate (e.g., 'shuttering_gang', 'labor', 'equipment')")
    value_amount: Optional[float] = Field(None, description="Quantity/amount of resource to add or modify")
    date_range: Optional[str] = Field(None, description="Date range for simulation (e.g., '2025-07-15 to 2025-07-20' or 'this Sunday')")


class SRACreateActionInput(BaseModel):
    """Input schema for SRA create action tool"""
    project_id: Optional[str] = Field(None, description="Project ID to create action for")
    user_id: Optional[str] = Field(None, description="User ID to assign action to (e.g., site planner)")
    action_choice: Optional[str] = Field(None, description="Action choice to log (e.g., 'option 1', 'raise alert')")


class SRAExplainFormulaInput(BaseModel):
    """Input schema for SRA explain formula tool"""
    project_id: Optional[str] = Field(None, description="Project ID for context")
    metric: Optional[str] = Field(None, description="The metric/formula to explain (e.g., 'SPI', 'CPI', 'PEI')")


class SRAStatusInput(BaseModel):
    """Input schema for SRA status tool"""
    project_id: Optional[str] = Field(None, description="Project ID to filter by (e.g., 'PRJ001'). Required for status check.")
    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format (e.g., '2025-01-15'). If not provided, uses latest available data.")
    response_style: Optional[str] = Field(
        "standard", 
        description="Response verbosity: 'executive' (1-2 lines), 'standard' (verdict + key metrics), 'detailed' (full analysis), 'metrics' (KPI-focused)"
    )


class SRADrillDelayInput(BaseModel):
    """Input schema for SRA drill delay tool"""
    project_id: Optional[str] = Field(None, description="Project ID to analyze delays for")
    start_date: Optional[str] = Field(None, description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format")
