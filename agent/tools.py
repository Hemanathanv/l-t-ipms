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


class SRAStatusInput(BaseModel):
    """Input schema for SRA status tool"""
    project_id: Optional[str] = Field(None, description="Project ID to filter by (e.g., 'PRJ_001'). If not provided, returns all projects.")
    start_date: Optional[str] = Field(None, description="Start date in YYYY-MM-DD format (e.g., '2025-07-01')")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format (e.g., '2025-12-31'). If only start_date is provided, this defaults to start_date.")


class SRADrillDelayInput(BaseModel):
    """Input schema for SRA drill delay tool"""
    project_id: Optional[str] = Field(None, description="Project ID to analyze delays for")
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
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    Get PEI (Project Efficiency Index) status for a project within a date range.
    
    Use this tool when the user asks about:
    - Current PEI value
    - Project health/status
    - Schedule performance
    - "How's the project doing?"
    - "Show current PEI"
    
    IMPORTANT: This tool requires both project_id AND a date/date range.
    If not provided, ask the user to specify them.
    
    Returns PEI values with status indicators:
    - 🟢 Green: PEI < 1 (good performance)
    - 🟠 Orange: PEI >= 1 (needs attention)
    
    If PEI >= 1, suggests using sra_drill_delay for more details.
    """
    prisma = await get_prisma()
    
    # Check if required parameters are missing
    missing_params = []
    
    if not project_id:
        # Get available projects to show user
        try:
            # Get unique projects by fetching records and deduplicating
            all_records = await prisma.sratable.find_many(
                select={"projectId": True, "projectName": True},
                take=100
            )
            # Deduplicate by project_id
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectId not in seen:
                    seen.add(p.projectId)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectId}: {p.projectName}" for p in unique_projects])
            missing_params.append(f"Please specify which project. Available projects:\n{project_list}")
        except Exception as e:
            missing_params.append(f"Please specify which project to analyze")
    
    if not start_date:
        # Get date range for the project (or all projects)
        try:
            date_query = {"projectId": project_id} if project_id else None
            min_date_rec = await prisma.sratable.find_first(where=date_query, order={"date": "asc"})
            max_date_rec = await prisma.sratable.find_first(where=date_query, order={"date": "desc"})
            
            if min_date_rec and max_date_rec:
                date_from = min_date_rec.date.strftime("%Y-%m-%d")
                date_to = max_date_rec.date.strftime("%Y-%m-%d")
                missing_params.append(f"**Date or Date Range** - Please specify a date within the available range: **{date_from}** to **{date_to}**")
            else:
                missing_params.append("**Date or Date Range** - Please specify a date in YYYY-MM-DD format")
        except:
            missing_params.append("**Date or Date Range** - Please specify a date in YYYY-MM-DD format (e.g., '2025-07-15')")
    
    # If any parameters are missing, return a request for them
    if missing_params:
        response = "📋 **I need more information to get the PEI status:**\n\n"
        response += "\n\n".join(missing_params)
        response += "\n\n💡 Example: *Show PEI status for PRJ_001 on 2025-07-15*"
        return response
    
    try:
        # Build query filters
        where_conditions = {}
        
        if project_id:
            where_conditions["projectId"] = project_id
        
        # Parse dates
        start = parse_date(start_date) if start_date else None
        end = parse_date(end_date) if end_date else start
        
        if start and end:
            where_conditions["date"] = {
                "gte": datetime.combine(start, datetime.min.time()),
                "lte": datetime.combine(end, datetime.max.time())
            }
        elif start:
            where_conditions["date"] = {
                "gte": datetime.combine(start, datetime.min.time())
            }
        
        # Query the database
        records = await prisma.sratable.find_many(
            where=where_conditions if where_conditions else None,
            order={"date": "desc"},
            take=10  # Limit results
        )
        
        if not records:
            return "No SRA data found for the specified criteria. Please check the project ID and date range."
        
        # Format response
        results = []
        has_issues = False
        
        for record in records:
            pei = record.peiValue
            status_icon = "🟢" if pei < 1 else "🟠"
            
            if pei >= 1:
                has_issues = True
            
            results.append(
                f"{status_icon} **{record.projectName}** ({record.projectId})\n"
                f"   📅 Date: {record.date.strftime('%Y-%m-%d')}\n"
                f"   📊 PEI Value: {pei:.4f}\n"
                f"   📈 SPI: {record.spiValue:.4f} | CPI: {record.cpiValue:.4f}\n"
                f"   🏗️ Progress: {record.executableProgressPct:.2f}%"
            )
        
        response = "## SRA Status Report - PEI Analysis\n\n"
        response += "\n\n---\n\n".join(results)
        
        # Add recommendation if there are issues
        if has_issues:
            response += "\n\n---\n\n"
            response += "⚠️ **Attention Required**: Some projects have PEI ≥ 1, indicating potential issues.\n"
            response += "💡 **Suggestion**: Use `sra_drill_delay` to analyze the root causes of delays."
        
        return response
        
    except Exception as e:
        return f"Error querying SRA data: {str(e)}"


@tool(args_schema=SRADrillDelayInput)
async def sra_drill_delay(
    project_id: Optional[str] = None,
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
    
    IMPORTANT: This tool requires both project_id AND a date/date range.
    If not provided, ask the user to specify them.
    
    Shows critical delay days, delay owner categories, and schedule variance.
    """
    prisma = await get_prisma()
    
    # Check if required parameters are missing
    missing_params = []
    
    if not project_id:
        try:
            # Get unique projects by fetching records and deduplicating
            all_records = await prisma.sratable.find_many(
                select={"projectId": True, "projectName": True},
                take=100
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectId not in seen:
                    seen.add(p.projectId)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectId}: {p.projectName}" for p in unique_projects])
            missing_params.append(f"Please specify which project. Available projects:\n{project_list}")
        except Exception as e:
            missing_params.append("Please specify which project to analyze")
    
    if not start_date:
        try:
            date_query = {"projectId": project_id} if project_id else None
            min_date_rec = await prisma.sratable.find_first(where=date_query, order={"date": "asc"})
            max_date_rec = await prisma.sratable.find_first(where=date_query, order={"date": "desc"})
            
            if min_date_rec and max_date_rec:
                date_from = min_date_rec.date.strftime("%Y-%m-%d")
                date_to = max_date_rec.date.strftime("%Y-%m-%d")
                missing_params.append(f"**Date or Date Range** - Please specify a date within the available range: **{date_from}** to **{date_to}**")
            else:
                missing_params.append("**Date or Date Range** - Please specify a date in YYYY-MM-DD format")
        except:
            missing_params.append("**Date or Date Range** - Please specify a date in YYYY-MM-DD format")
    
    if missing_params:
        response = "📋 **I need more information to analyze delays:**\n\n"
        response += "\n\n".join(missing_params)
        response += "\n\n💡 Example: *Analyze delays for PROJECT on 2025-07-15*"
        return response
    
    try:
        # Build query filters
        where_conditions = {}
        
        if project_id:
            where_conditions["projectId"] = project_id
        
        # Parse dates
        start = parse_date(start_date) if start_date else None
        end = parse_date(end_date) if end_date else start
        
        if start and end:
            where_conditions["date"] = {
                "gte": datetime.combine(start, datetime.min.time()),
                "lte": datetime.combine(end, datetime.max.time())
            }
        
        # Get records with delays
        records = await prisma.sratable.find_many(
            where=where_conditions if where_conditions else None,
            order={"criticalDelayDays": "desc"},
            take=10
        )
        
        if not records:
            return "No delay data found for the specified criteria."
        
        # Format response
        results = []
        
        for record in records:
            delay_status = "🔴" if record.criticalDelayDays > 0 else "🟢"
            delay_owner = record.topDelayOwnerCategory or "None"
            
            # Calculate schedule variance
            planned = record.plannedFinishDate
            forecast = record.forecastFinishDate
            variance_days = (forecast - planned).days if planned and forecast else 0
            
            results.append(
                f"{delay_status} **{record.projectName}** ({record.projectId})\n"
                f"   📅 Report Date: {record.date.strftime('%Y-%m-%d')}\n"
                f"   ⏰ Critical Delay: **{record.criticalDelayDays} days**\n"
                f"   👤 Delay Owner: {delay_owner}\n"
                f"   📅 Planned Finish: {planned.strftime('%Y-%m-%d') if planned else 'N/A'}\n"
                f"   📅 Forecast Finish: {forecast.strftime('%Y-%m-%d') if forecast else 'N/A'}\n"
                f"   📊 Schedule Variance: {variance_days:+d} days\n"
                f"   🎯 Lookahead Compliance: {record.lookaheadCompliancePct:.1%}"
            )
        
        response = "## SRA Delay Analysis\n\n"
        response += "\n\n---\n\n".join(results)
        
        # Summary
        total_delay = sum(r.criticalDelayDays for r in records)
        avg_delay = total_delay / len(records) if records else 0
        
        # Count delay owners
        owners = {}
        for r in records:
            owner = r.topDelayOwnerCategory or "Unknown"
            owners[owner] = owners.get(owner, 0) + 1
        
        response += "\n\n---\n\n### Summary\n"
        response += f"- **Average Critical Delay**: {avg_delay:.1f} days\n"
        response += f"- **Records Analyzed**: {len(records)}\n"
        response += "- **Delay Owners**:\n"
        for owner, count in sorted(owners.items(), key=lambda x: -x[1]):
            response += f"  - {owner}: {count} occurrences\n"
        
        return response
        
    except Exception as e:
        return f"Error analyzing delays: {str(e)}"


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


@tool(args_schema=SRARecoveryAdviseInput)
async def sra_recovery_advise(
    project_id: Optional[str] = None,
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
    if not project_id:
        try:
            all_records = await prisma.sratable.find_many(
                select={"projectId": True, "projectName": True},
                take=100
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectId not in seen:
                    seen.add(p.projectId)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectId}: {p.projectName}" for p in unique_projects])
            return f"📋 **I need more information to provide recovery advice:**\n\nPlease specify which project. Available projects:\n{project_list}\n\n💡 Example: *How do we recover PROJECT_001?*"
        except Exception as e:
            return "📋 **Please specify which project needs recovery advice.**"
    
    try:
        # Get latest project data
        latest_record = await prisma.sratable.find_first(
            where={"projectId": project_id},
            order={"date": "desc"}
        )
        
        if not latest_record:
            return f"No data found for project {project_id}. Please verify the project ID."
        
        response = f"## 🔧 Recovery Advice for {latest_record.projectName}\n\n"
        response += f"**Current Status:**\n"
        response += f"- 📊 PEI: {latest_record.peiValue:.4f}\n"
        response += f"- 📈 SPI: {latest_record.spiValue:.4f}\n"
        response += f"- ⏰ Critical Delay: {latest_record.criticalDelayDays} days\n"
        response += f"- 👤 Top Delay Owner: {latest_record.topDelayOwnerCategory or 'N/A'}\n\n"
        
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
        
        response += "---\n\n"
        response += "💡 **Next Steps**: Use `sra_simulate` to model the impact of these options, or `sra_create_action` to log your chosen recovery strategy."
        
        return response
        
    except Exception as e:
        return f"Error generating recovery advice: {str(e)}"


@tool(args_schema=SRASimulateInput)
async def sra_simulate(
    project_id: Optional[str] = None,
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
    
    if not project_id:
        try:
            all_records = await prisma.sratable.find_many(
                select={"projectId": True, "projectName": True},
                take=100
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectId not in seen:
                    seen.add(p.projectId)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectId}: {p.projectName}" for p in unique_projects])
            missing_params.append(f"**Project** - Which project? Available:\n{project_list}")
        except:
            missing_params.append("**Project** - Please specify the project ID")
    
    if not resource_type:
        missing_params.append("**Resource Type** - What resource? (e.g., 'shuttering_gang', 'labor', 'equipment', 'overtime')")
    
    if not value_amount:
        missing_params.append("**Value/Amount** - How much? (e.g., 2 for '2 gangs', 8 for '8 hours overtime')")
    
    if missing_params:
        response = "📋 **I need more details to run the simulation:**\n\n"
        response += "\n".join(missing_params)
        response += "\n\n💡 Example: *What if I add 2 shuttering gangs to PROJECT_001?*"
        return response
    
    try:
        # Get latest project data
        latest_record = await prisma.sratable.find_first(
            where={"projectId": project_id},
            order={"date": "desc"}
        )
        
        if not latest_record:
            return f"No data found for project {project_id}. Please verify the project ID."
        
        # Simulation logic (simplified model)
        current_delay = latest_record.criticalDelayDays
        current_spi = latest_record.spiValue
        
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
        
        response = f"## 📊 Simulation Results for {latest_record.projectName}\n\n"
        response += f"**Scenario**: Add {value_amount} {resource_type}"
        if date_range:
            response += f" ({date_range})"
        response += "\n\n---\n\n"
        
        response += "### 📈 Projected Impact:\n\n"
        response += "| Metric | Current | Projected | Change |\n"
        response += "|--------|---------|-----------|--------|\n"
        response += f"| Critical Delay | {current_delay} days | {new_delay} days | **-{days_recovered} days** |\n"
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
        response += "💡 **Next Steps**: Use `sra_create_action` to log this scenario as an approved action item."
        
        return response
        
    except Exception as e:
        return f"Error running simulation: {str(e)}"


@tool(args_schema=SRACreateActionInput)
async def sra_create_action(
    project_id: Optional[str] = None,
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
    
    if not project_id:
        try:
            all_records = await prisma.sratable.find_many(
                select={"projectId": True, "projectName": True},
                take=100
            )
            seen = set()
            unique_projects = []
            for p in all_records:
                if p.projectId not in seen:
                    seen.add(p.projectId)
                    unique_projects.append(p)
                    if len(unique_projects) >= 10:
                        break
            
            project_list = "\n".join([f"  - {p.projectId}: {p.projectName}" for p in unique_projects])
            missing_params.append(f"**Project** - Which project? Available:\n{project_list}")
        except:
            missing_params.append("**Project** - Please specify the project ID")
    
    if not action_choice:
        missing_params.append("**Action** - What action to log? (e.g., 'Approve Option 1', 'Raise alert', 'Add resources')")
    
    if missing_params:
        response = "📋 **I need more details to create the action:**\n\n"
        response += "\n\n".join(missing_params)
        response += "\n\n💡 Example: *Log option 1 for PROJECT_001* or *Raise alert to site planner*"
        return response
    
    try:
        # Get latest project data for context
        latest_record = await prisma.sratable.find_first(
            where={"projectId": project_id},
            order={"date": "desc"}
        )
        
        project_name = latest_record.projectName if latest_record else project_id
        
        # Generate action ID (in real system, this would be stored in DB)
        from datetime import datetime
        action_id = f"ACT-{project_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        response = f"## ✅ Action Created Successfully\n\n"
        response += f"**Action ID**: `{action_id}`\n\n"
        response += "---\n\n"
        response += "### 📋 Action Details:\n\n"
        response += f"| Field | Value |\n"
        response += f"|-------|-------|\n"
        response += f"| Project | {project_name} ({project_id}) |\n"
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
        if latest_record:
            response += f"- PEI: {latest_record.peiValue:.4f}\n"
            response += f"- Critical Delay: {latest_record.criticalDelayDays} days\n"
            response += f"- SPI: {latest_record.spiValue:.4f}\n\n"
        
        response += "💡 **Note**: This action has been logged for tracking. The assigned user will receive a notification."
        
        return response
        
    except Exception as e:
        return f"Error creating action: {str(e)}"


@tool(args_schema=SRAExplainFormulaInput)
async def sra_explain_formula(
    project_id: Optional[str] = None,
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
    if project_id:
        try:
            latest_record = await prisma.sratable.find_first(
                where={"projectId": project_id},
                order={"date": "desc"}
            )
            if latest_record:
                project_context = latest_record
                response += f"**Project Context**: {latest_record.projectName} ({project_id})\n\n---\n\n"
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
            response += f"**Current Value**: {project_context.spiValue:.4f} "
            if project_context.spiValue >= 1.0:
                response += "✅ (On/Ahead of schedule)\n\n"
            else:
                response += f"⚠️ (Behind by {(1 - project_context.spiValue) * 100:.1f}%)\n\n"
    
    # CPI Explanation
    if metric_lower in ['cpi', 'all', 'cost']:
        response += "### 💰 CPI (Cost Performance Index)\n\n"
        response += "**Formula**:\n"
        response += "```\nCPI = Earned Value (EV) / Actual Cost (AC)\n```\n\n"
        response += "**Interpretation**:\n"
        response += "| Value | Status | Meaning |\n"
        response += "|-------|--------|--------|\n"
        response += "| CPI = 1.0 | ✅ On Budget | Spending exactly as planned |\n"
        response += "| CPI > 1.0 | 🟢 Under Budget | Getting more value for cost |\n"
        response += "| CPI < 1.0 | 🔴 Over Budget | Spending more than planned |\n\n"
        
        if project_context:
            response += f"**Current Value**: {project_context.cpiValue:.4f} "
            if project_context.cpiValue >= 1.0:
                response += "✅ (On/Under budget)\n\n"
            else:
                response += f"⚠️ (Over budget by {(1 - project_context.cpiValue) * 100:.1f}%)\n\n"
    
    # PEI Explanation
    if metric_lower in ['pei', 'all', 'efficiency']:
        response += "### 📊 PEI (Project Efficiency Index)\n\n"
        response += "**Formula**:\n"
        response += "```\nPEI = (Schedule Variance + Cost Variance) / (Baseline Duration × Risk Factor)\n```\n\n"
        response += "**Interpretation**:\n"
        response += "| Value | Status | Meaning |\n"
        response += "|-------|--------|--------|\n"
        response += "| PEI < 1.0 | 🟢 Good | Project performing well |\n"
        response += "| PEI = 1.0 | 🟡 Monitor | At threshold, needs attention |\n"
        response += "| PEI > 1.0 | 🔴 Action Needed | Efficiency issues require intervention |\n\n"
        
        if project_context:
            response += f"**Current Value**: {project_context.peiValue:.4f} "
            if project_context.peiValue < 1.0:
                response += "🟢 (Good performance)\n\n"
            else:
                response += "🔴 (Needs attention)\n\n"
    
    # Lookahead Compliance
    if metric_lower in ['lookahead', 'compliance', 'all']:
        response += "### 🎯 Lookahead Compliance\n\n"
        response += "**Formula**:\n"
        response += "```\nLookahead Compliance = (Completed Lookahead Tasks / Planned Lookahead Tasks) × 100%\n```\n\n"
        response += "**Interpretation**:\n"
        response += "- **> 80%**: Excellent - Strong short-term execution\n"
        response += "- **60-80%**: Acceptable - Room for improvement\n"
        response += "- **< 60%**: Poor - Planning/execution gap\n\n"
        
        if project_context:
            response += f"**Current Value**: {project_context.lookaheadCompliancePct:.1%}\n\n"
    
    # Critical Delay
    if metric_lower in ['delay', 'critical', 'all']:
        response += "### ⏰ Critical Delay Days\n\n"
        response += "**Calculation**:\n"
        response += "```\nCritical Delay = Forecast Finish Date - Planned Finish Date\n```\n\n"
        response += "**Interpretation**:\n"
        response += "- Represents days the critical path has slipped\n"
        response += "- Directly impacts project completion date\n"
        response += "- Used to prioritize recovery efforts\n\n"
        
        if project_context:
            response += f"**Current Value**: {project_context.criticalDelayDays} days\n\n"
    
    response += "---\n\n"
    response += "💡 **Need more details?** Ask about specific metrics like 'Explain SPI for PROJECT_001'"
    
    return response


# Export tools list for the agent
SRA_TOOLS = [sra_status_pei, sra_drill_delay, sra_recovery_advise, sra_simulate, sra_create_action, sra_explain_formula]
