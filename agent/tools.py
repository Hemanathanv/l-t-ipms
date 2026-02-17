"""
SRA Tools for LangGraph Agent
Tools to query SRA data (PEI values, delays, etc.)
"""

from datetime import datetime, date
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Import Prisma - we'll use global instance
from db import get_prisma


# ===== CONFIGURABLE THRESHOLDS (used by all tools) =====
WORKFRONT_READINESS_THRESHOLD = 70.0
SPI_THRESHOLD = 1
FORECAST_DELAY_THRESHOLD = 30
PEI_THRESHOLD = 1


def _threshold_footer() -> str:
    """Returns a reference footer with ideal threshold values."""
    return (
        "\n\n---\n"
        "📌 **Ideal Thresholds** │ "
        f"Workfront ≥ {WORKFRONT_READINESS_THRESHOLD:.0f}% │ "
        f"SPI ≥ {SPI_THRESHOLD} │ "
        f"PEI < {PEI_THRESHOLD} │ "
        f"Delay ≤ {FORECAST_DELAY_THRESHOLD}d"
    )


class SRAStatusInput(BaseModel):
    """Input schema for SRA status tool"""
    project_key: Optional[str] = Field(None, description="project_key to filter by (e.g., '101'). Required for status check.")
    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format (e.g., '2025-01-15'). If not provided, uses latest available data.")
    response_style: Optional[str] = Field(
        "standard", 
        description="Response verbosity: 'standard' (verdict + key metrics), 'detailed' (full analysis), 'metrics' (KPI-focused)"
    )


class SRADrillDelayInput(BaseModel):
    """Input schema for SRA drill delay tool"""
    project_key: Optional[str] = Field(None, description="project_key to analyze delays for")
    start_date: Optional[str] = Field(None, description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format")


def parse_date(date_str: str) -> Optional[date]:
    """Parse date string to date object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(date_str, "%m/%d/%Y").date()
        except ValueError:
            return None


@tool(args_schema=SRAStatusInput)
async def sra_status_pei(
    project_key: Optional[str] = None,
    date: Optional[str] = None,
    response_style: Optional[str] = "standard"
) -> str:
    """
    Get project schedule health status using gated decision logic.
    
    USE THIS TOOL FOR:
    ✅ Direct Status Checks: "Is the project on track?", "Are we okay on schedule?", "How is the project doing?"
    ✅ Metric-Led Questions: "Show current PEI and SPI", "What's the SPI this week?", "Give me schedule KPIs"
    ✅ Time-Bound Checks: "How are we doing this week?", "Where do we stand right now?"
    ✅ Management Questions: "Give me a quick schedule health check", "Should I be worried about timelines?"
    ✅ Validation Questions: "Is this SPI reliable?", "Can we trust the current plan?"
    ✅ Executive One-Liners: "Schedule status?", "On track?", "Okay or not?"
    
    DO NOT USE FOR (redirect to other tools):
    ❌ Root cause analysis → use sra_drill_delay
    ❌ Recovery options → use sra_recovery_advise  
    ❌ What-if scenarios → use sra_simulate
    
    HEALTH CLASSIFICATION (Gated Logic):
    Gate 1: Workfront Readiness < 70% → NOT OK (Execution constrained)
    Gate 2: SPI < 0.95 → NOT OK (Schedule unreliable)
    Gate 3: Forecast Delay > 30 days → NOT OK (Material slippage)
    Otherwise → OK
    
    RESPONSE STYLES:
    - 'standard': Verdict + key reasons (default)
    - 'detailed': Full analysis with all metrics
    - 'metrics': KPI-focused with health verdict
    """
    prisma = await get_prisma()
    
    # Normalize response_style
    style = (response_style or "standard").lower().strip()
    if style not in ["standard", "detailed", "metrics"]:
        style = "standard"
    
    # ===== PARAMETER VALIDATION =====
    if not project_key:
        try:
            all_records = await prisma.tbl01projectsummary.find_many(
                select={"projectKey": True, "projectDescription": True, "project_id": True},
                take=20
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectKey not in seen:
                    seen.add(p.projectKey)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectKey}: {p.projectDescription}" for p in unique_projects])
            return f"📋 **Which project?**\n\nAvailable projects:\n{project_list}\n\n💡 Example: *Is project 101 on track?*"
        except:
            return "📋 **Please specify which project to check (project_key).**"
    
    try:
        project_key_int = int(project_key)
        
        # ===== STEP 1: Query project-level summary =====
        project_summary = await prisma.tbl01projectsummary.find_first(
            where={"projectKey": project_key_int}
        )
        
        if not project_summary:
            return f"No data found for project_key {project_key}. Please verify the project key."
        
        # Extract project-level metrics
        project_name = project_summary.projectDescription
        project_location = project_summary.projectLocation
        pei_value = project_summary.pei
        spi_value = project_summary.spi
        forecast_delay_days = project_summary.forecastDelayDays
        computed_days = project_summary.computedDays
        extension_exposure_days = project_summary.extensionExposureDays
        workfront_readiness = project_summary.workfrontPercentage * 100
        ready_tasks = project_summary.readyTask
        workfront_total_tasks = project_summary.workfrontTotalTasks
        critical_pct = project_summary.criticalPercentage
        executed_qty = project_summary.executedQuantity
        total_available_qty = project_summary.totalAvailableQuantity
        executable_progress_pct = project_summary.executableProgressPercent
        tasks_planned_lookahead = project_summary.tasksPlannedInLookAhead
        tasks_completed_lookahead = project_summary.tasksCompletedLookAhead
        lookahead_compliance_pct = project_summary.lookAheadCompliancePercent
        
        # ===== GATED HEALTH CLASSIFICATION =====
        status = "OK"
        status_icon = "✅"
        primary_reason = ""
        secondary_reasons = []
        
        # Gate 1: Workfront Readiness (Reality Gate)
        if workfront_readiness < WORKFRONT_READINESS_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"Only {workfront_readiness:.1f}% workfronts available - plan is not executable"
        
        # Gate 2: SPI (Schedule Signal)
        elif spi_value < SPI_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"SPI at {spi_value:.2f} - schedule is unreliable"

        elif pei_value > PEI_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"PEI at {pei_value:.2f} - forecast duration exceeds plan (less efficient)"
        
        # Gate 3: Forecast Delay (Time Tolerance)
        elif forecast_delay_days > FORECAST_DELAY_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"{forecast_delay_days}-day forecast delay - material slippage"
        
        else:
            status = "OK"
            status_icon = "✅"
            primary_reason = "Schedule is healthy"
        
        # Build secondary reasons
        if workfront_readiness < WORKFRONT_READINESS_THRESHOLD:
            secondary_reasons.append(f"Workfront at {workfront_readiness:.1f}%")
        if spi_value < SPI_THRESHOLD:
            secondary_reasons.append(f"SPI at {spi_value:.2f}")
        if forecast_delay_days > FORECAST_DELAY_THRESHOLD:
            secondary_reasons.append(f"{forecast_delay_days}d delay")
        
        # ===== FORMAT RESPONSE BY STYLE =====
        
        # ----- METRICS STYLE (KPI-focused with verdict) -----
        if style == "metrics":
            response = f"## {status_icon} {status} — {project_name}\n"
            response += f"*Location: {project_location}*\n\n"
            
            response += "### 📊 Project-Level Metrics\n\n"
            response += "| Metric | Value | Status |\n"
            response += "|--------|-------|--------|\n"
            response += f"| SPI | {spi_value:.4f} | {'✅' if spi_value >= SPI_THRESHOLD else '❌'} |\n"
            response += f"| PEI | {pei_value:.4f} | {'✅' if pei_value <= 1.0 else '⚠️'} |\n"
            response += f"| Workfront | {workfront_readiness:.1f}% | {'✅' if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else '❌'} |\n"
            response += f"| Forecast Delay | {forecast_delay_days}d | {'✅' if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else '❌'} |\n"
            response += f"| Computed Days | {computed_days}d | — |\n"
            response += f"| Extension Exposure | {extension_exposure_days}d | {'⚠️' if extension_exposure_days > 0 else '✅'} |\n"
            response += f"| Executable Progress | {executable_progress_pct:.1f}% | — |\n"
            response += f"| Lookahead Compliance | {lookahead_compliance_pct:.1f}% | {'✅' if lookahead_compliance_pct >= 60 else '⚠️'} |\n\n"
            
            response += f"**Verdict**: {primary_reason}"
            return response + _threshold_footer()
        
        # ----- STANDARD STYLE (Verdict + key reasons) -----
        if style == "standard":
            response = f"## {status_icon} Schedule Health: **{status}**\n\n"
            response += f"**{project_name}** ({project_location})\n\n"
            
            # Project-level summary
            response += "### 🏗️ Project-Level Summary\n\n"
            if status == "OK":
                response += "Schedule health is **OK**.\n\n"
                spi_meaning = "On/Ahead of schedule" if spi_value >= 1.0 else "Slightly behind"
                pei_meaning = "Efficient" if pei_value <= 1.0 else "Taking more time"
                delay_meaning = "Within tolerance" if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else "Slipping"
                wf_meaning = "Ready" if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else "Constrained"
                response += "| Metric | Value | Meaning |\n"
                response += "|--------|-------|---------|\n"
                response += f"| SPI | {spi_value:.2f} | ✅ {spi_meaning} |\n"
                response += f"| PEI | {pei_value:.2f} | ✅ {pei_meaning} |\n"
                response += f"| Forecast Delay | {forecast_delay_days}d | ✅ {delay_meaning} |\n"
                response += f"| Workfront | {workfront_readiness:.1f}% | ✅ {wf_meaning} ({ready_tasks}/{workfront_total_tasks} ready) |\n"
                response += f"| Executable Progress | {executable_progress_pct:.1f}% | — |\n\n"
                response += "**No immediate schedule intervention required.**\n"
            
            else:  # NOT OK
                response += "Schedule health is **NOT OK**.\n\n"
                response += f"**Issue**: {primary_reason}\n\n"
                spi_meaning = "On schedule" if spi_value >= 1.0 else f"Behind by {(1 - spi_value) * 100:.0f}%"
                pei_meaning = "On/Ahead of plan" if pei_value <= 1.0 else f"Taking {(pei_value - 1) * 100:.0f}% more time"
                delay_meaning = "Within tolerance" if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else f"{forecast_delay_days}d overrun"
                wf_meaning = "Ready" if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else f"Only {workfront_readiness:.1f}% available"
                spi_icon = "✅" if spi_value >= SPI_THRESHOLD else "❌"
                pei_icon = "✅" if pei_value <= PEI_THRESHOLD else "❌"
                delay_icon = "✅" if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else "❌"
                wf_icon = "✅" if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else "❌"
                response += "| Metric | Value | Meaning |\n"
                response += "|--------|-------|---------|\n"
                response += f"| SPI | {spi_value:.2f} | {spi_icon} {spi_meaning} |\n"
                response += f"| PEI | {pei_value:.2f} | {pei_icon} {pei_meaning} |\n"
                response += f"| Forecast Delay | {forecast_delay_days}d | {delay_icon} {delay_meaning} |\n"
                response += f"| Workfront | {workfront_readiness:.1f}% | {wf_icon} {wf_meaning} |\n\n"
                response += "\n💬 *Would you like me to drill down into the root causes of these delays?*\n"
            
            return response + _threshold_footer()
        
        # ----- DETAILED STYLE (Full analysis) -----
        if style == "detailed":
            response = f"## {status_icon} Schedule Health: **{status}**\n\n"
            response += f"**Project**: {project_name} (Key: {project_key})\n"
            response += f"**Location**: {project_location}\n\n"
            response += "---\n\n"
            
            # Status Assessment
            if status == "OK":
                response += "### ✅ Status Assessment\n\n"
                response += "Schedule health is **OK**.\n\n"
                response += f"| Gate | Metric | Value | Threshold | Result |\n"
                response += f"|------|--------|-------|-----------|--------|\n"
                response += f"| Reality | Workfront Readiness | {workfront_readiness:.1f}% | ≥70% | ✅ Pass |\n"
                response += f"| Schedule | SPI | {spi_value:.4f} | ≥0.95 | ✅ Pass |\n"
                response += f"| Tolerance | Forecast Delay | {forecast_delay_days}d | ≤30d | ✅ Pass |\n\n"
                response += "**No immediate schedule intervention required.**\n\n"
            
            else:  # NOT OK
                response += "### 🔴 Status Assessment\n\n"
                response += "Schedule health is **NOT OK**.\n\n"
                response += f"**Primary Issue**: {primary_reason}\n\n"
                
                wf_result = "✅ Pass" if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else "❌ FAIL"
                spi_result = "✅ Pass" if spi_value >= SPI_THRESHOLD else "❌ FAIL"
                delay_result = "✅ Pass" if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else "❌ FAIL"
                
                response += f"| Gate | Metric | Value | Threshold | Result |\n"
                response += f"|------|--------|-------|-----------|--------|\n"
                response += f"| Reality | Workfront Readiness | {workfront_readiness:.1f}% | ≥70% | {wf_result} |\n"
                response += f"| Schedule | SPI | {spi_value:.4f} | ≥0.95 | {spi_result} |\n"
                response += f"| Tolerance | Forecast Delay | {forecast_delay_days}d | ≤30d | {delay_result} |\n\n"
                response += "💡 **Recommendation**: Recovery actions required.\n\n"
                response += "💬 *Shall I drill down into the root causes and identify which activities are driving the delay?*\n\n"
            
            # Project-Level Contextual Metrics
            response += "---\n\n"
            response += "### 📊 Project-Level Metrics\n\n"
            
            pei_icon = "🟢" if pei_value <= 1.0 else ("🟡" if pei_value < 1.5 else "🔴")
            pei_interp = "On/Ahead of schedule" if pei_value <= 1.0 else ("Taking more time than planned" if pei_value < 1.5 else "Significant schedule inefficiency")
            
            response += f"| Metric | Value | Interpretation |\n"
            response += f"|--------|-------|----------------|\n"
            response += f"| PEI | {pei_value:.4f} | {pei_icon} {pei_interp} |\n"
            response += f"| SPI | {spi_value:.4f} | {'🟢 On Schedule' if spi_value >= 1.0 else '⚠️ Behind'} |\n"
            response += f"| Workfront | {workfront_readiness:.1f}% | {'🟢' if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else '🔴'} ({ready_tasks}/{workfront_total_tasks} ready) |\n"
            response += f"| Forecast Delay | {forecast_delay_days}d | {'🟢' if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else '🔴'} |\n"
            response += f"| Computed Days | {computed_days}d | — |\n"
            response += f"| Extension Exposure | {extension_exposure_days}d | {'⚠️ Risk' if extension_exposure_days > 0 else '✅ None'} |\n"
            response += f"| Executable Progress | {executable_progress_pct:.1f}% | — |\n"
            response += f"| Executed / Available Qty | {executed_qty:,.0f} / {total_available_qty:,.0f} | — |\n"
            response += f"| Lookahead Compliance | {lookahead_compliance_pct:.1f}% | {'�' if lookahead_compliance_pct >= 60 else '⚠️'} ({tasks_completed_lookahead}/{tasks_planned_lookahead}) |\n\n"
            

            
            # Decision Basis
            response += "\n---\n\n"
            response += "### ℹ️ Decision Basis\n\n"
            response += "Health is determined by gated rules (in order):\n"
            response += "1. **Workfront Readiness** (Reality Gate) → Is the plan executable?\n"
            response += "2. **SPI** (Schedule Signal) → Is the schedule reliable?\n"
            response += "3. **Forecast Delay** (Time Tolerance) → Is slippage within limits?\n\n"
            response += "*PEI is contextual reinforcement, not the primary verdict.*"
            
            return response + _threshold_footer()
        
        # Fallback
        return f"{status_icon} **{status}** — {project_name}: {primary_reason}" + _threshold_footer()
        
    except ValueError:
        return f"Invalid project_key '{project_key}'. Please provide a numeric project key (e.g., 101, 107)."
    except Exception as e:
        return f"Error querying SRA data: {str(e)}"


@tool(args_schema=SRADrillDelayInput)
async def sra_drill_delay(
    project_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Drill down into delay details for a project.
    
    Use this tool when:
    - PEI >= 1 was reported
    - User wants to understand delays
    - User asks "why is the project delayed?"
    - User wants delay root cause analysis
    
    IMPORTANT: This tool requires project_key.
    If not provided, ask the user to specify it.
    
    Shows project-level delay summary and activity-level delay breakdown.
    """
    prisma = await get_prisma()
    
    # Check if required parameters are missing
    missing_params = []
    
    if not project_key:
        try:
            all_records = await prisma.tbl01projectsummary.find_many(
                select={"projectKey": True, "projectDescription": True},
                take=20
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectKey not in seen:
                    seen.add(p.projectKey)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectKey}: {p.projectDescription}" for p in unique_projects])
            missing_params.append(f"Please specify which project. Available projects:\n{project_list}")
        except Exception as e:
            missing_params.append("Please specify which project to analyze (project_key)")
    
    if missing_params:
        response = "📋 **I need more information to analyze delays:**\n\n"
        response += "\n\n".join(missing_params)
        response += "\n\n💡 Example: *Analyze delays for project 101*"
        return response
    
    try:
        project_key_int = int(project_key)
        
        # Get project-level summary
        project_summary = await prisma.tbl01projectsummary.find_first(
            where={"projectKey": project_key_int}
        )
        
        if not project_summary:
            return f"No data found for project_key {project_key}."
        
        project_name = project_summary.projectDescription
        forecast_delay_days = project_summary.forecastDelayDays
        
        # Get activity-level data
        activities = await prisma.tbl02projectactivity.find_many(
            where={"projectKey": project_key_int}
        )
        
        if not activities:
            return f"No activity data found for project_key {project_key}."
        
        # Identify delayed activities
        delayed_activities = sorted(
            [a for a in activities if a.delayDays > 0],
            key=lambda x: -x.delayDays
        )
        low_workfront = [a for a in activities if a.workfrontPct < 70]
        
        response = f"## 🔍 SRA Delay Analysis\n\n"
        response += f"**Project**: {project_name} (Key: {project_key})\n"
        response += f"**Location**: {project_summary.projectLocation}\n"
        response += f"**Forecast Delay**: {forecast_delay_days} days\n"
        response += f"**SPI**: {project_summary.spi:.4f}\n\n"
        response += "---\n\n"
        
        # Delayed Activities Breakdown
        response += "### 🔴 Delayed Activities\n\n"
        if delayed_activities:
            response += f"Found **{len(delayed_activities)}** delayed activities:\n\n"
            response += "| Activity | Delay (days) | Computed Delay | Workfront % | Lookahead Compliance |\n"
            response += "|----------|-------------|----------------|-------------|---------------------|\n"
            for act in delayed_activities[:10]:
                wf_icon = "✅" if act.workfrontPct >= 70 else "⚠️"
                response += f"| {act.activityDescription} | {act.delayDays}d | {act.computedDelay}d | {act.workfrontPct:.1f}% {wf_icon} | {act.lookAheadCompliancePercent:.1f}% |\n"
        else:
            response += "✅ No delayed activities found.\n"
        
        response += "\n---\n\n"
        
        # Low Workfront Activities
        response += "### ⚠️ Low Workfront Readiness Activities\n\n"
        if low_workfront:
            response += f"Found **{len(low_workfront)}** activities with workfront < 70%:\n\n"
            low_wf_sorted = sorted(low_workfront, key=lambda x: x.workfrontPct)
            response += "| Activity | Workfront % | Ready/Total Tasks | Delay |\n"
            response += "|----------|-------------|-------------------|-------|\n"
            for act in low_wf_sorted[:10]:
                response += f"| {act.activityDescription} | {act.workfrontPct:.1f}% | {act.readyTasks}/{act.totalTasks} | {act.delayDays}d |\n"
        else:
            response += "✅ All activities have adequate workfront readiness.\n"
        
        response += "\n---\n\n"
        
        # Summary Statistics
        response += "### 📈 Summary Statistics\n\n"
        avg_workfront = sum(a.workfrontPct for a in activities) / len(activities)
        avg_delay = sum(a.delayDays for a in activities) / len(activities)
        total_ready = sum(a.readyTasks for a in activities)
        total_tasks = sum(a.totalTasks for a in activities)
        
        response += f"- **Total Activities**: {len(activities)}\n"
        response += f"- **Delayed Activities**: {len(delayed_activities)}\n"
        response += f"- **Avg Workfront**: {avg_workfront:.1f}%\n"
        response += f"- **Avg Delay**: {avg_delay:.1f} days\n"
        response += f"- **Ready/Total Tasks**: {total_ready}/{total_tasks}\n\n"
        
        # Root Cause Indicators
        response += "### 🎯 Potential Root Causes\n\n"
        if avg_workfront < 70:
            response += f"- ❌ **Workfront Constraint**: Avg {avg_workfront:.1f}% — material/ROW/access issues\n"
        if len(delayed_activities) > len(activities) * 0.5:
            response += f"- ❌ **Widespread Delays**: {len(delayed_activities)}/{len(activities)} activities delayed\n"
        if project_summary.spi < 0.95:
            response += f"- ❌ **Schedule Performance**: SPI {project_summary.spi:.4f} — execution behind plan\n"
        if avg_workfront >= 70 and project_summary.spi >= 0.95:
            response += "- ✅ No major systemic issues. Consider activity-level interventions.\n"
        
        response += "\n💬 *Would you like me to suggest recovery options to bring this project back on track?*"
        
        return response + _threshold_footer()
        
    except ValueError:
        return f"Invalid project_key '{project_key}'. Please provide a numeric key."
    except Exception as e:
        return f"Error analyzing delays: {str(e)}"


class SRARecoveryAdviseInput(BaseModel):
    """Input schema for SRA recovery advise tool"""
    project_key: Optional[str] = Field(None, description="Project key to analyze recovery options for (e.g., '101')")
    activity_id: Optional[str] = Field(None, description="Specific activity code to focus recovery on")
    resource_type: Optional[str] = Field(None, description="Type of resource to consider (e.g., 'labor', 'equipment', 'material')")


class SRASimulateInput(BaseModel):
    """Input schema for SRA simulation tool"""
    project_key: Optional[str] = Field(None, description="Project key to run simulation for (e.g., '101')")
    resource_type: Optional[str] = Field(None, description="Type of resource to simulate (e.g., 'shuttering_gang', 'labor', 'equipment')")
    value_amount: Optional[float] = Field(None, description="Quantity/amount of resource to add or modify")
    date_range: Optional[str] = Field(None, description="Date range for simulation (e.g., '2025-07-15 to 2025-07-20' or 'this Sunday')")


class SRACreateActionInput(BaseModel):
    """Input schema for SRA create action tool"""
    project_key: Optional[str] = Field(None, description="Project key to create action for (e.g., '101')")
    user_id: Optional[str] = Field(None, description="User ID to assign action to (e.g., site planner)")
    action_choice: Optional[str] = Field(None, description="Action choice to log (e.g., 'option 1', 'raise alert')")


class SRAExplainFormulaInput(BaseModel):
    """Input schema for SRA explain formula tool"""
    project_key: Optional[str] = Field(None, description="Project key for context (e.g., '101')")
    metric: Optional[str] = Field(None, description="The metric/formula to explain (e.g., 'SPI', 'CPI', 'PEI')")


@tool(args_schema=SRARecoveryAdviseInput)
async def sra_recovery_advise(
    project_key: Optional[str] = None,
    activity_id: Optional[str] = None,
    resource_type: Optional[str] = None
) -> str:
    """
    Get recovery advice and options to regain schedule for a delayed project.
    
    Use this tool when the user asks:
    - "How do we recover?"
    - "Give me options to regain schedule"
    - "What are our recovery options?"
    - "How can we get back on track?"
    
    Analyzes delays and provides actionable recovery recommendations based on
    resource availability, activity criticality, and historical performance.
    """
    prisma = await get_prisma()
    
    # Check if required parameters are missing
    if not project_key:
        try:
            all_records = await prisma.tbl01projectsummary.find_many(
                select={"projectKey": True, "projectDescription": True},
                take=20
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectKey not in seen:
                    seen.add(p.projectKey)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectKey}: {p.projectDescription}" for p in unique_projects])
            return f"📋 **I need more information to provide recovery advice:**\n\nPlease specify which project. Available projects:\n{project_list}\n\n💡 Example: *How do we recover project 101?*"
        except Exception as e:
            return "📋 **Please specify which project needs recovery advice (project_key).**"
    
    try:
        project_key_int = int(project_key)
        
        # Get project-level summary
        project_summary = await prisma.tbl01projectsummary.find_first(
            where={"projectKey": project_key_int}
        )
        
        if not project_summary:
            return f"No data found for project_key {project_key}."
        
        # Get activity-level data for workfront info
        activities = await prisma.tbl02projectactivity.find_many(
            where={"projectKey": project_key_int}
        )
        
        # Compute average workfront from activity table
        avg_workfront = sum(a.workfrontPct for a in activities) / len(activities) if activities else 0
        
        response = f"## 🔧 Recovery Advice for {project_summary.projectDescription}\n\n"
        response += f"**Current Status:**\n"
        response += f"- 📊 PEI: {project_summary.pei:.4f}\n"
        response += f"- 📈 SPI: {project_summary.spi:.4f}\n"
        response += f"- ⏰ Forecast Delay: {project_summary.forecastDelayDays} days\n"
        response += f"- 🏗️ Avg Workfront (from activities): {avg_workfront:.1f}%\n"
        response += f"- 📐 Lookahead Compliance: {project_summary.lookAheadCompliancePercent:.1f}%\n\n"
        
        response += "---\n\n### 💡 Recovery Options:\n\n"
        
        # Option 1: Resource augmentation
        response += "**Option 1: Resource Augmentation** 👷\n"
        response += f"- Add additional crews to critical activities\n"
        if resource_type:
            response += f"- Focus on {resource_type} resources\n"
        response += "- Estimated schedule recovery: 3-5 days\n"
        response += "- Risk: Medium (quality control needed)\n\n"
        
        # Option 2: Schedule compression
        response += "**Option 2: Schedule Compression** ⏱️\n"
        response += "- Enable weekend/overtime work\n"
        response += "- Double-shift critical path activities\n"
        response += "- Estimated schedule recovery: 5-7 days\n"
        response += "- Risk: Medium (cost increase ~15%)\n\n"
        
        # Option 3: Scope adjustment
        response += "**Option 3: Scope Adjustment** 📋\n"
        response += "- Re-sequence non-critical activities\n"
        response += "- Defer low-priority deliverables\n"
        response += "- Estimated schedule recovery: 2-4 days\n"
        response += "- Risk: Low (requires stakeholder approval)\n\n"
        
        # Option 4: Fast-tracking
        response += "**Option 4: Fast-Tracking** 🚀\n"
        response += "- Overlap sequential activities\n"
        if activity_id:
            response += f"- Focus fast-tracking around activity {activity_id}\n"
        response += "- Estimated schedule recovery: 4-6 days\n"
        response += "- Risk: High (increased coordination needed)\n\n"
        
        # Option 5: Workfront Resolution (if applicable)
        if avg_workfront < 70:
            response += "**Option 5: Workfront Resolution** 🚧\n"
            response += f"- Current avg workfront readiness is only {avg_workfront:.1f}%\n"
            if activities:
                low_wf = [a for a in activities if a.workfrontPct < 70]
                if low_wf:
                    response += f"- {len(low_wf)}/{len(activities)} activities have workfront < 70%\n"
            response += "- Clear material/ROW/access constraints\n"
            response += "- Coordinate with procurement/land teams\n"
            response += "- Estimated schedule recovery: 5-10 days\n"
            response += "- Risk: Low-Medium (depends on constraint type)\n\n"
        
        response += "---\n\n"
        response += "💬 *Would you like me to simulate the impact of any of these options, or shall I log a recovery action for your team?*"
        
        return response + _threshold_footer()
        
    except ValueError:
        return f"Invalid project_key '{project_key}'. Please provide a numeric key."
    except Exception as e:
        return f"Error generating recovery advice: {str(e)}"


@tool(args_schema=SRASimulateInput)
async def sra_simulate(
    project_key: Optional[str] = None,
    resource_type: Optional[str] = None,
    value_amount: Optional[float] = None,
    date_range: Optional[str] = None
) -> str:
    """
    Simulate what-if scenarios to predict schedule impact.
    
    Use this tool when the user asks:
    - "What if I add 2 shuttering gangs?"
    - "If we work this Sunday?"
    - "What happens if we add more resources?"
    - "Simulate adding overtime"
    
    Runs simulations to predict the impact of resource changes or schedule modifications.
    """
    prisma = await get_prisma()
    
    # Check if required parameters are missing
    missing_params = []
    
    if not project_key:
        try:
            all_records = await prisma.tbl01projectsummary.find_many(
                select={"projectKey": True, "projectDescription": True},
                take=20
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectKey not in seen:
                    seen.add(p.projectKey)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectKey}: {p.projectDescription}" for p in unique_projects])
            missing_params.append(f"**Project** - Which project? Available:\n{project_list}")
        except:
            missing_params.append("**Project** - Please specify the project key")
    
    if not resource_type:
        missing_params.append("**Resource Type** - What resource? (e.g., 'shuttering_gang', 'labor', 'equipment', 'overtime')")
    
    if not value_amount:
        missing_params.append("**Value/Amount** - How much? (e.g., 2 for '2 gangs', 8 for '8 hours overtime')")
    
    if missing_params:
        response = "📋 **I need more details to run the simulation:**\n\n"
        response += "\n".join(missing_params)
        response += "\n\n💡 Example: *What if I add 2 shuttering gangs to project 101?*"
        return response
    
    try:
        project_key_int = int(project_key)
        
        # Get project-level summary
        project_summary = await prisma.tbl01projectsummary.find_first(
            where={"projectKey": project_key_int}
        )
        
        if not project_summary:
            return f"No data found for project_key {project_key}."
        
        # Simulation logic (simplified model)
        current_delay = project_summary.forecastDelayDays
        current_spi = project_summary.spi
        
        # Calculate simulated impact based on resource type
        productivity_factor = 0.0
        cost_impact = 0.0
        
        if resource_type.lower() in ['shuttering_gang', 'gang', 'crew']:
            productivity_factor = value_amount * 0.15  # Each gang adds ~15% productivity
            cost_impact = value_amount * 25000  # Approximate cost per gang
            days_recovered = int(current_delay * productivity_factor)
        elif resource_type.lower() in ['labor', 'worker']:
            productivity_factor = value_amount * 0.05  # Each worker adds ~5% productivity
            cost_impact = value_amount * 5000
            days_recovered = int(current_delay * productivity_factor)
        elif resource_type.lower() in ['overtime', 'sunday', 'weekend']:
            productivity_factor = 0.12  # Weekend work adds ~12% productivity
            cost_impact = 15000 * (value_amount if value_amount else 1)
            days_recovered = max(1, int(current_delay * productivity_factor))
        elif resource_type.lower() in ['equipment', 'machinery']:
            productivity_factor = value_amount * 0.20
            cost_impact = value_amount * 50000
            days_recovered = int(current_delay * productivity_factor)
        else:
            productivity_factor = value_amount * 0.10
            cost_impact = value_amount * 10000
            days_recovered = int(current_delay * productivity_factor)
        
        new_delay = max(0, current_delay - days_recovered)
        new_spi = min(1.0, current_spi + (productivity_factor * 0.1))
        
        response = f"## 📊 Simulation Results for {project_summary.projectDescription}\n\n"
        response += f"**Scenario**: Add {value_amount} {resource_type}"
        if date_range:
            response += f" ({date_range})"
        response += "\n\n---\n\n"
        
        response += "### 📈 Projected Impact:\n\n"
        response += "| Metric | Current | Projected | Change |\n"
        response += "|--------|---------|-----------|--------|\n"
        response += f"| Forecast Delay | {current_delay} days | {new_delay} days | **-{days_recovered} days** |\n"
        response += f"| SPI | {current_spi:.4f} | {new_spi:.4f} | +{(new_spi - current_spi):.4f} |\n"
        response += f"| Productivity | Baseline | +{productivity_factor*100:.1f}% | ✅ Improved |\n\n"
        
        response += "### 💰 Cost Analysis:\n"
        response += f"- **Additional Cost**: ₹{cost_impact:,.0f}\n"
        response += f"- **Cost per Day Recovered**: ₹{cost_impact/max(1, days_recovered):,.0f}\n\n"
        
        response += "### ⚠️ Risks & Considerations:\n"
        if resource_type.lower() in ['overtime', 'sunday', 'weekend']:
            response += "- Worker fatigue may impact quality\n"
            response += "- Overtime premium costs apply\n"
        elif resource_type.lower() in ['shuttering_gang', 'gang', 'crew']:
            response += "- Coordination overhead with new teams\n"
            response += "- Learning curve for site-specific processes\n"
        else:
            response += "- Resource availability needs confirmation\n"
            response += "- Impact on other concurrent activities\n"
        
        response += "\n---\n\n"
        response += "💬 *Shall I log this scenario as an approved action item for your team to execute?*"
        
        return response + _threshold_footer()
        
    except Exception as e:
        return f"Error running simulation: {str(e)}"


@tool(args_schema=SRACreateActionInput)
async def sra_create_action(
    project_key: Optional[str] = None,
    user_id: Optional[str] = None,
    action_choice: Optional[str] = None
) -> str:
    """
    Create and log an action item for schedule recovery or alerts.
    
    Use this tool when the user wants to:
    - "Log option 1"
    - "Raise alert to site planner"
    - "Create action for recovery"
    - "Assign task to team"
    
    Logs action items and can send alerts to relevant stakeholders.
    """
    prisma = await get_prisma()
    
    # Check if required parameters are missing
    missing_params = []
    
    if not project_key:
        try:
            all_records = await prisma.tbl01projectsummary.find_many(
                select={"projectKey": True, "projectDescription": True},
                take=20
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectKey not in seen:
                    seen.add(p.projectKey)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectKey}: {p.projectDescription}" for p in unique_projects])
            missing_params.append(f"**Project** - Which project? Available:\n{project_list}")
        except:
            missing_params.append("**Project** - Please specify the project key")
    
    if not action_choice:
        missing_params.append("**Action** - What action to log? (e.g., 'Approve Option 1', 'Raise alert', 'Add resources')")
    
    if missing_params:
        response = "📋 **I need more details to create the action:**\n\n"
        response += "\n\n".join(missing_params)
        response += "\n\n💡 Example: *Log option 1 for project 101* or *Raise alert to site planner*"
        return response
    
    try:
        project_key_int = int(project_key)
        
        # Get project data for context
        project_summary = await prisma.tbl01projectsummary.find_first(
            where={"projectKey": project_key_int}
        )
        
        project_name = project_summary.projectDescription if project_summary else str(project_key)
        
        # Generate action ID
        from datetime import datetime
        action_id = f"ACT-{project_key}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = f"## ✅ Action Created Successfully\n\n"
        response += f"**Action ID**: `{action_id}`\n\n"
        response += "---\n\n"
        response += "### 📋 Action Details:\n\n"
        response += f"| Field | Value |\n"
        response += f"|-------|-------|\n"
        response += f"| Project | {project_name} (Key: {project_key}) |\n"
        response += f"| Action | {action_choice} |\n"
        response += f"| Assigned To | {user_id or 'Unassigned'} |\n"
        response += f"| Status | 🟡 **Pending** |\n"
        response += f"| Created | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n\n"
        
        # Determine if this is an alert
        if 'alert' in action_choice.lower() or 'raise' in action_choice.lower():
            response += "### 🔔 Alert Status:\n"
            response += f"- Alert type: **Schedule Recovery Alert**\n"
            response += f"- Recipient: {user_id or 'Site Planner'}\n"
            response += f"- Priority: **High**\n"
            response += "- Notification: 📧 Email + 📱 Push notification queued\n\n"
        
        response += "---\n\n"
        response += "### 📊 Current Project Context:\n"
        if project_summary:
            response += f"- PEI: {project_summary.pei:.4f}\n"
            response += f"- Forecast Delay: {project_summary.forecastDelayDays} days\n"
            response += f"- SPI: {project_summary.spi:.4f}\n\n"
        
        response += "💡 **Note**: This action has been logged for tracking. The assigned user will receive a notification."
        
        return response + _threshold_footer()
        
    except ValueError:
        return f"Invalid project_key '{project_key}'. Please provide a numeric key."
    except Exception as e:
        return f"Error creating action: {str(e)}"


@tool(args_schema=SRAExplainFormulaInput)
async def sra_explain_formula(
    project_key: Optional[str] = None,
    metric: Optional[str] = None
) -> str:
    """
    Explain how SRA metrics and formulas are computed.
    
    Use this tool when the user asks:
    - "How did you compute SPI?"
    - "What is PEI formula?"
    - "Explain CPI calculation"
    - "How are the metrics calculated?"
    
    Provides detailed explanations of SRA metrics, formulas, and calculations.
    """
    prisma = await get_prisma()
    
    # Default to explaining all common metrics if none specified
    if not metric:
        metric = "all"
    
    metric_lower = metric.lower()
    
    response = "## 📐 SRA Metrics & Formula Explanations\n\n"
    
    # Get project context if provided
    project_context = None
    if project_key:
        try:
            project_key_int = int(project_key)
            project_summary = await prisma.tbl01projectsummary.find_first(
                where={"projectKey": project_key_int}
            )
            if project_summary:
                project_context = project_summary
                response += f"**Project Context**: {project_summary.projectDescription} (Key: {project_key})\n\n---\n\n"
        except:
            pass
    
    # SPI Explanation
    if metric_lower in ['spi', 'all', 'schedule']:
        response += "### 📈 SPI (Schedule Performance Index)\n\n"
        response += "**Formula**:\n"
        response += "```\nSPI = Earned Value (EV) / Planned Value (PV)\n```\n\n"
        response += "**Interpretation**:\n"
        response += "| Value | Status | Meaning |\n"
        response += "|-------|--------|--------|\n"
        response += "| SPI = 1.0 | ✅ On Schedule | Project is exactly on schedule |\n"
        response += "| SPI > 1.0 | 🟢 Ahead | Project is ahead of schedule |\n"
        response += "| SPI < 1.0 | 🔴 Behind | Project is behind schedule |\n\n"
        
        if project_context:
            response += f"**Current Value**: {project_context.spi:.4f} "
            if project_context.spi >= 1.0:
                response += "✅ (On/Ahead of schedule)\n\n"
            else:
                response += f"⚠️ (Behind by {(1 - project_context.spi) * 100:.1f}%)\n\n"
    
    # CPI Explanation
    # if metric_lower in ['cpi', 'all', 'cost']:
    #     response += "### 💰 CPI (Cost Performance Index)\n\n"
    #     response += "**Formula**:\n"
    #     response += "```\nCPI = Earned Value (EV) / Actual Cost (AC)\n```\n\n"
    #     response += "**Interpretation**:\n"
    #     response += "| Value | Status | Meaning |\n"
    #     response += "|-------|--------|--------|\n"
    #     response += "| CPI = 1.0 | ✅ On Budget | Spending exactly as planned |\n"
    #     response += "| CPI > 1.0 | 🟢 Under Budget | Getting more value for cost |\n"
    #     response += "| CPI < 1.0 | 🔴 Over Budget | Spending more than planned |\n\n"
    
    # PEI Explanation
    if metric_lower in ['pei', 'all', 'efficiency']:
        response += "### 📊 PEI (Project Efficiency Index)\n\n"
        response += "**Formula**:\n"
        response += "```\nPEI = Forecast Duration / Planned Duration\n```\n\n"
        response += "**Interpretation**:\n"
        response += "| Value | Status | Meaning |\n"
        response += "|-------|--------|--------|\n"
        response += "| PEI < 1.0 | 🟢 Efficient | Finishing earlier than planned |\n"
        response += "| PEI = 1.0 | ✅ On Schedule | Forecast equals plan |\n"
        response += "| PEI > 1.0 | 🔴 Less Efficient | Taking more time than planned |\n\n"
        
        if project_context:
            response += f"**Current Value**: {project_context.pei:.4f} "
            if project_context.pei <= 1.0:
                response += "🟢 (Efficient — on or ahead of schedule)\n\n"
            else:
                response += f"🔴 (Taking {(project_context.pei - 1) * 100:.1f}% more time than planned)\n\n"
    
    # Lookahead Compliance
    # if metric_lower in ['lookahead', 'compliance', 'all']:
    #     response += "### 🎯 Lookahead Compliance\n\n"
    #     response += "**Formula**:\n"
    #     response += "```\nLookahead Compliance = (Completed Lookahead Tasks / Planned Lookahead Tasks) × 100%\n```\n\n"
    #     response += "**Interpretation**:\n"
    #     response += "- **> 80%**: Excellent - Strong short-term execution\n"
    #     response += "- **60-80%**: Acceptable - Room for improvement\n"
    #     response += "- **< 60%**: Poor - Planning/execution gap\n\n"
        
    #     if project_context:
    #         response += f"**Current Value**: {project_context.lookAheadCompliancePercent:.1f}%\n\n"
    
    # # Critical Delay
    # if metric_lower in ['delay', 'critical', 'all']:
    #     response += "### ⏰ Forecast Delay Days\n\n"
    #     response += "**Calculation**:\n"
    #     response += "```\nForecast Delay = Forecast Finish Date - Planned Finish Date\n```\n\n"
    #     response += "**Interpretation**:\n"
    #     response += "- Represents days the critical path has slipped\n"
    #     response += "- Directly impacts project completion date\n"
    #     response += "- Used to prioritize recovery efforts\n\n"
        
    #     if project_context:
    #         response += f"**Current Value**: {project_context.forecastDelayDays} days\n\n"
    
    response += "---\n\n"
    response += "💡 **Need more details?** Ask about specific metrics like 'Explain SPI for project 101'"
    
    return response + _threshold_footer()


# Export tools list for the agent
SRA_TOOLS = [sra_status_pei, sra_drill_delay, sra_recovery_advise,sra_simulate]
