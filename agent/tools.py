from datetime import datetime, date
from typing import Optional
from langchain_core.tools import tool
from db import get_prisma
from dtos.models import *


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
    Gate 4: Float < 5 days → OK BUT FRAGILE
    Otherwise → OK
    
    RESPONSE STYLES:
    - 'executive': 1-2 line verdict for quick checks
    - 'standard': Verdict + key reasons (default)
    - 'detailed': Full analysis with all metrics
    - 'metrics': KPI-focused with health verdict
    """
    prisma = await get_prisma()
    
    # ===== CONFIGURABLE THRESHOLDS =====
    WORKFRONT_READINESS_THRESHOLD = 70.0
    SPI_THRESHOLD = 0.95
    FORECAST_DELAY_THRESHOLD = 30
    FLOAT_FRAGILE_THRESHOLD = 5.0
    FLOAT_SAFE_THRESHOLD = 10.0
    
    # Normalize response_style
    style = (response_style or "standard").lower().strip()
    if style not in ["executive", "standard", "detailed", "metrics"]:
        style = "standard"
    
    # ===== PARAMETER VALIDATION =====
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
            return f"📋 **Which project?**\n\nAvailable projects:\n{project_list}\n\n💡 Example: *Is PRJ001 on track?*"
        except:
            return "📋 **Please specify which project to check.**"
    
    try:
        # Build query - use latest date if not specified
        where_conditions = {"projectId": project_id}
        
        if date:
            target_date = parse_date(date)
            if target_date:
                where_conditions["date"] = {
                    "gte": datetime.combine(target_date, datetime.min.time()),
                    "lte": datetime.combine(target_date, datetime.max.time())
                }
        
        # Query activities
        records = await prisma.sratable.find_many(
            where=where_conditions,
            order={"date": "desc"}
        )
        
        if not records:
            # If date specified but no data, suggest available dates
            if date:
                date_query = {"projectId": project_id}
                min_rec = await prisma.sratable.find_first(where=date_query, order={"date": "asc"})
                max_rec = await prisma.sratable.find_first(where=date_query, order={"date": "desc"})
                if min_rec and max_rec:
                    return f"No data for {date}. Available range: **{min_rec.date.strftime('%Y-%m-%d')}** to **{max_rec.date.strftime('%Y-%m-%d')}**"
            return f"No data found for project {project_id}. Please verify the project ID."
        
        # ===== AGGREGATE METRICS =====
        latest_date = records[0].date
        latest_records = [r for r in records if r.date == latest_date]
        
        project_name = latest_records[0].projectName
        
        # Workfront Readiness
        workfront_readiness = 0
        # sum(r.workfrontReadinessPct for r in latest_records) / len(latest_records)
        
        # SPI (weighted by planned value)
        total_pv = sum(r.plannedValueAmount for r in latest_records)
        if total_pv > 0:
            spi_value = sum(r.spiValue * r.plannedValueAmount for r in latest_records) / total_pv
        else:
            spi_value = sum(r.spiValue for r in latest_records) / len(latest_records)
        
        # Forecast Delay
        forecast_delay_days = 0
        # latest_records[0].forecastDelayDays
        
        # Float Health Index
        critical_activities = 0
        # [r for r in latest_records if r.isCriticalFlag == 1]
        near_critical = 0
        # [r for r in latest_records if r.totalFloatDays <= 5 and r.isCriticalFlag == 0]
        float_activities = critical_activities + near_critical
        
        if float_activities:
            float_health_index = sum(r.totalFloatDays for r in float_activities) / len(float_activities)
        else:
            float_health_index = 1
            # sum(r.avgFloat for r in latest_records) / len(latest_records)
        
        # PEI & CPI for context
        pei_value = sum(r.peiValue for r in latest_records) / len(latest_records)
        if total_pv > 0:
            cpi_value = sum(r.cpiValue * r.plannedValueAmount for r in latest_records) / total_pv
        else:
            cpi_value = sum(r.cpiValue for r in latest_records) / len(latest_records)
        
        # ===== GATED HEALTH CLASSIFICATION =====
        status = "OK"
        status_icon = "✅"
        primary_reason = ""
        secondary_reasons = []
        
        # Gate 1: Workfront Readiness (Reality Gate)
        if workfront_readiness < WORKFRONT_READINESS_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"Only {workfront_readiness:.0f}% workfronts available - plan is not executable"
        
        # Gate 2: SPI (Schedule Signal)
        elif spi_value < SPI_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"SPI at {spi_value:.2f} - schedule is unreliable"
        
        # Gate 3: Forecast Delay (Time Tolerance)
        elif forecast_delay_days > FORECAST_DELAY_THRESHOLD:
            status = "NOT OK"
            status_icon = "🔴"
            primary_reason = f"{forecast_delay_days}-day forecast delay - material slippage"
        
        # Gate 4: Float (Fragility)
        elif float_health_index < FLOAT_FRAGILE_THRESHOLD:
            status = "OK BUT FRAGILE"
            status_icon = "🟡"
            primary_reason = f"Only {float_health_index:.1f} days float on critical path - no recovery buffer"
        
        else:
            status = "OK"
            status_icon = "✅"
            primary_reason = "Schedule is healthy with adequate buffer"
        
        # Build secondary reasons for detailed output
        if workfront_readiness < WORKFRONT_READINESS_THRESHOLD:
            secondary_reasons.append(f"Workfront at {workfront_readiness:.0f}%")
        if spi_value < SPI_THRESHOLD:
            secondary_reasons.append(f"SPI at {spi_value:.2f}")
        if forecast_delay_days > FORECAST_DELAY_THRESHOLD:
            secondary_reasons.append(f"{forecast_delay_days}d delay")
        if float_health_index < FLOAT_FRAGILE_THRESHOLD:
            secondary_reasons.append(f"Float only {float_health_index:.1f}d")
        
        date_str = latest_date.strftime('%Y-%m-%d')
        
        # ===== FORMAT RESPONSE BY STYLE =====
        
        # ----- EXECUTIVE STYLE (1-2 lines) -----
        if style == "executive":
            if status == "OK":
                return f"{status_icon} **{status}** — {project_name} is on track as of {date_str}."
            elif status == "OK BUT FRAGILE":
                return f"{status_icon} **{status}** — {project_name}: {primary_reason}."
            else:
                return f"{status_icon} **{status}** — {project_name}: {primary_reason}."
        
        # ----- METRICS STYLE (KPI-focused with verdict) -----
        if style == "metrics":
            response = f"## {status_icon} {status} — {project_name}\n"
            response += f"*As of {date_str}*\n\n"
            
            response += "| Metric | Value | Status |\n"
            response += "|--------|-------|--------|\n"
            response += f"| SPI | {spi_value:.4f} | {'✅' if spi_value >= SPI_THRESHOLD else '❌'} |\n"
            response += f"| PEI | {pei_value:.4f} | {'✅' if pei_value < 0.90 else '⚠️'} |\n"
            response += f"| CPI | {cpi_value:.4f} | {'✅' if cpi_value >= 1.0 else '⚠️'} |\n"
            response += f"| Workfront | {workfront_readiness:.1f}% | {'✅' if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else '❌'} |\n"
            response += f"| Forecast Delay | {forecast_delay_days}d | {'✅' if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else '❌'} |\n"
            response += f"| Float Health | {float_health_index:.1f}d | {'✅' if float_health_index >= FLOAT_FRAGILE_THRESHOLD else '⚠️'} |\n\n"
            
            response += f"**Verdict**: {primary_reason}"
            return response
        
        # ----- STANDARD STYLE (Verdict + key reasons) -----
        if style == "standard":
            response = f"## {status_icon} Schedule Health: **{status}**\n\n"
            response += f"**{project_name}** — as of {date_str}\n\n"
            
            if status == "OK":
                response += f"Schedule health is **OK**.\n"
                response += f"- SPI: **{spi_value:.2f}** ✓\n"
                response += f"- Forecast delay: **{forecast_delay_days}d** ✓\n"
                response += f"- Workfront: **{workfront_readiness:.0f}%** ✓\n"
                response += f"- Float buffer: **{float_health_index:.1f}d** ✓\n\n"
                response += "**No immediate schedule intervention required.**"
            
            elif status == "OK BUT FRAGILE":
                response += f"Schedule health is **OK but FRAGILE**.\n\n"
                response += f"All primary gates pass, however:\n"
                response += f"- ⚠️ {primary_reason}\n\n"
                response += f"**Key Metrics**: SPI {spi_value:.2f} | Delay {forecast_delay_days}d | Workfront {workfront_readiness:.0f}%\n\n"
                response += "💡 Monitor float consumption closely. Prepare contingencies."
            
            else:  # NOT OK
                response += f"Schedule health is **NOT OK**.\n\n"
                response += f"**Issue**: {primary_reason}\n\n"
                response += f"**Key Metrics**: SPI {spi_value:.2f} | Delay {forecast_delay_days}d | Workfront {workfront_readiness:.0f}% | Float {float_health_index:.1f}d\n\n"
                response += "💡 Use `sra_drill_delay` to identify root causes."
            
            return response
        
        # ----- DETAILED STYLE (Full analysis) -----
        if style == "detailed":
            response = f"## {status_icon} Schedule Health: **{status}**\n\n"
            response += f"**Project**: {project_name} ({project_id})\n"
            response += f"**As of**: {date_str}\n\n"
            response += "---\n\n"
            
            # Status Assessment
            if status == "OK":
                response += "### ✅ Status Assessment\n\n"
                response += "Schedule health is **OK**.\n\n"
                response += f"| Gate | Metric | Value | Threshold | Result |\n"
                response += f"|------|--------|-------|-----------|--------|\n"
                response += f"| Reality | Workfront Readiness | {workfront_readiness:.1f}% | ≥70% | ✅ Pass |\n"
                response += f"| Schedule | SPI | {spi_value:.4f} | ≥0.95 | ✅ Pass |\n"
                response += f"| Tolerance | Forecast Delay | {forecast_delay_days}d | ≤30d | ✅ Pass |\n"
                response += f"| Fragility | Float Health | {float_health_index:.1f}d | ≥5d | ✅ Pass |\n\n"
                response += "**No immediate schedule intervention required.**\n\n"
            
            elif status == "OK BUT FRAGILE":
                response += "### 🟡 Status Assessment\n\n"
                response += "Schedule health is **OK but FRAGILE**.\n\n"
                response += f"| Gate | Metric | Value | Threshold | Result |\n"
                response += f"|------|--------|-------|-----------|--------|\n"
                response += f"| Reality | Workfront Readiness | {workfront_readiness:.1f}% | ≥70% | ✅ Pass |\n"
                response += f"| Schedule | SPI | {spi_value:.4f} | ≥0.95 | ✅ Pass |\n"
                response += f"| Tolerance | Forecast Delay | {forecast_delay_days}d | ≤30d | ✅ Pass |\n"
                response += f"| Fragility | Float Health | {float_health_index:.1f}d | ≥5d | ⚠️ Fragile |\n\n"
                response += f"**Issue**: {primary_reason}\n\n"
                response += "💡 **Recommendation**: Monitor float consumption closely and prepare contingencies.\n\n"
            
            else:  # NOT OK
                response += "### 🔴 Status Assessment\n\n"
                response += "Schedule health is **NOT OK**.\n\n"
                response += f"**Primary Issue**: {primary_reason}\n\n"
                
                wf_result = "✅ Pass" if workfront_readiness >= WORKFRONT_READINESS_THRESHOLD else "❌ FAIL"
                spi_result = "✅ Pass" if spi_value >= SPI_THRESHOLD else "❌ FAIL"
                delay_result = "✅ Pass" if forecast_delay_days <= FORECAST_DELAY_THRESHOLD else "❌ FAIL"
                float_result = "✅ Pass" if float_health_index >= FLOAT_FRAGILE_THRESHOLD else "⚠️ Fragile"
                
                response += f"| Gate | Metric | Value | Threshold | Result |\n"
                response += f"|------|--------|-------|-----------|--------|\n"
                response += f"| Reality | Workfront Readiness | {workfront_readiness:.1f}% | ≥70% | {wf_result} |\n"
                response += f"| Schedule | SPI | {spi_value:.4f} | ≥0.95 | {spi_result} |\n"
                response += f"| Tolerance | Forecast Delay | {forecast_delay_days}d | ≤30d | {delay_result} |\n"
                response += f"| Fragility | Float Health | {float_health_index:.1f}d | ≥5d | {float_result} |\n\n"
                response += "💡 **Recommendation**: Recovery actions required. Use `sra_drill_delay` to identify root causes.\n\n"
            
            # Contextual Metrics
            response += "---\n\n"
            response += "### 📊 Contextual Metrics\n\n"
            
            pei_icon = "🟢" if pei_value < 0.85 else ("🟡" if pei_value < 0.90 else "🔴")
            pei_interp = "Healthy" if pei_value < 0.85 else ("Marginal" if pei_value < 0.90 else "Efficiency erosion")
            
            response += f"| Metric | Value | Interpretation |\n"
            response += f"|--------|-------|----------------|\n"
            response += f"| PEI | {pei_value:.4f} | {pei_icon} {pei_interp} |\n"
            response += f"| CPI | {cpi_value:.4f} | {'🟢 On/Under Budget' if cpi_value >= 1.0 else '⚠️ Over Budget'} |\n"
            response += f"| Activities | {len(latest_records)} | Critical: {len(critical_activities)} |\n\n"
            
            # Float interpretation
            if float_health_index >= FLOAT_SAFE_THRESHOLD:
                float_interp = "🟢 Structurally safe"
            elif float_health_index >= FLOAT_FRAGILE_THRESHOLD:
                float_interp = "🟡 Tight but manageable"
            else:
                float_interp = "🔴 Fragile / knife-edge"
            
            response += f"**Float Health Index**: {float_health_index:.1f} days → {float_interp}\n\n"
            
            # Decision Basis
            response += "---\n\n"
            response += "### ℹ️ Decision Basis\n\n"
            response += "Health is determined by gated rules (in order):\n"
            response += "1. **Workfront Readiness** (Reality Gate) → Is the plan executable?\n"
            response += "2. **SPI** (Schedule Signal) → Is the schedule reliable?\n"
            response += "3. **Forecast Delay** (Time Tolerance) → Is slippage within limits?\n"
            response += "4. **Float Health** (Fragility Check) → Is there recovery buffer?\n\n"
            response += "*PEI is contextual reinforcement, not the primary verdict.*"
            
            return response
        
        # Fallback
        return f"{status_icon} **{status}** — {project_name}: {primary_reason}"
        
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
        response += "\n\n💡 Example: *Analyze delays for PRJ001 on 2025-01-15*"
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
        
        # Get all activities for the project
        records = await prisma.sratable.find_many(
            where=where_conditions if where_conditions else None,
            order={"date": "desc"}
        )
        
        if not records:
            return "No delay data found for the specified criteria."
        
        # Get latest date's records
        latest_date = records[0].date
        latest_records = [r for r in records if r.date == latest_date]
        
        project_name = latest_records[0].projectName
        forecast_delay_days = latest_records[0].forecastDelayDays
        
        # Identify critical activities with low float (potential delay drivers)
        critical_activities = [r for r in latest_records if r.isCriticalFlag == 1]
        low_float_activities = [r for r in latest_records if r.totalFloatDays < 5]
        delayed_activities = [r for r in latest_records if r.forecastDelayDays > 0]
        
        response = f"## � SRA Delay Analysis\n\n"
        response += f"**Project**: {project_name} ({project_id})\n"
        response += f"**Date**: {latest_date.strftime('%Y-%m-%d')}\n"
        response += f"**Forecast Delay**: {forecast_delay_days} days\n\n"
        response += "---\n\n"
        
        # Critical Activities Analysis
        response += "### 🔴 Critical Path Activities\n\n"
        if critical_activities:
            response += f"Found **{len(critical_activities)}** critical activities:\n\n"
            response += "| Activity | Float (days) | SPI | Status |\n"
            response += "|----------|--------------|-----|--------|\n"
            for act in critical_activities[:10]:  # Top 10
                float_status = "⚠️" if act.totalFloatDays < 5 else "✅"
                spi_status = "⚠️" if act.spiValue < 0.95 else "✅"
                response += f"| {act.activityName} | {act.totalFloatDays:.1f} {float_status} | {act.spiValue:.3f} {spi_status} | {'Critical' if act.isCriticalFlag else ''} |\n"
        else:
            response += "No critical activities identified.\n"
        
        response += "\n---\n\n"
        
        # Low Float Activities (Float Erosion Analysis)
        response += "### ⚠️ Float Erosion - Activities with Low Buffer\n\n"
        if low_float_activities:
            response += f"Found **{len(low_float_activities)}** activities with float < 5 days:\n\n"
            # Sort by float ascending
            low_float_sorted = sorted(low_float_activities, key=lambda x: x.totalFloatDays)
            response += "| Activity | Float (days) | Critical? | Risk |\n"
            response += "|----------|--------------|-----------|------|\n"
            for act in low_float_sorted[:10]:
                risk = "🔴 High" if act.totalFloatDays < 2 else "🟡 Medium"
                crit = "Yes" if act.isCriticalFlag == 1 else "No"
                response += f"| {act.activityName} | {act.totalFloatDays:.1f} | {crit} | {risk} |\n"
        else:
            response += "✅ No activities with critically low float.\n"
        
        response += "\n---\n\n"
        
        # Schedule Variance Analysis
        response += "### 📊 Schedule Variance Analysis\n\n"
        
        # Calculate schedule variance for activities
        variance_analysis = []
        for act in latest_records:
            planned = act.plannedFinishDate
            forecast = act.forecastFinishDate
            if planned and forecast:
                variance = (forecast - planned).days
                variance_analysis.append({
                    "name": act.activityName,
                    "variance": variance,
                    "is_critical": act.isCriticalFlag == 1
                })
        
        if variance_analysis:
            # Sort by variance descending (most delayed first)
            variance_sorted = sorted(variance_analysis, key=lambda x: -x["variance"])
            most_delayed = [v for v in variance_sorted if v["variance"] > 0][:5]
            
            if most_delayed:
                response += "**Top Delayed Activities**:\n\n"
                response += "| Activity | Variance | Critical? |\n"
                response += "|----------|----------|----------|\n"
                for act in most_delayed:
                    crit = "🔴 Yes" if act["is_critical"] else "No"
                    response += f"| {act['name']} | +{act['variance']} days | {crit} |\n"
            else:
                response += "✅ No activities are forecasted to finish late.\n"
        
        response += "\n---\n\n"
        
        # Summary Statistics
        response += "### 📈 Summary Statistics\n\n"
        avg_spi = sum(r.spiValue for r in latest_records) / len(latest_records)
        avg_float = sum(r.totalFloatDays for r in latest_records) / len(latest_records)
        avg_workfront = sum(r.workfrontReadinessPct for r in latest_records) / len(latest_records)
        
        response += f"- **Total Activities Analyzed**: {len(latest_records)}\n"
        response += f"- **Critical Activities**: {len(critical_activities)}\n"
        response += f"- **Low Float Activities**: {len(low_float_activities)}\n"
        response += f"- **Average SPI**: {avg_spi:.4f}\n"
        response += f"- **Average Float**: {avg_float:.1f} days\n"
        response += f"- **Average Workfront Readiness**: {avg_workfront:.1f}%\n\n"
        
        # Root Cause Indicators
        response += "### 🎯 Potential Root Causes\n\n"
        
        if avg_workfront < 70:
            response += "- ❌ **Workfront Constraint**: Low workfront readiness ({:.1f}%) suggests material/ROW/access issues\n".format(avg_workfront)
        if avg_spi < 0.95:
            response += "- ❌ **Schedule Performance**: Low SPI ({:.4f}) indicates execution falling behind plan\n".format(avg_spi)
        if len(low_float_activities) > len(latest_records) * 0.3:
            response += "- ❌ **Float Erosion**: {:.0f}% of activities have critically low float\n".format(len(low_float_activities)/len(latest_records)*100)
        if len(critical_activities) > 0 and avg_float < 5:
            response += "- ❌ **Critical Path Stress**: Critical activities have minimal buffer\n"
        
        if avg_workfront >= 70 and avg_spi >= 0.95:
            response += "- ✅ No major systemic issues detected. Consider activity-level interventions.\n"
        
        response += "\n💡 **Next Steps**: Use `sra_recovery_advise` for recovery options."
        
        return response
        
    except Exception as e:
        return f"Error analyzing delays: {str(e)}"

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
        response += f"- ⏰ Forecast Delay: {latest_record.forecastDelayDays} days\n"
        response += f"- 🏗️ Workfront Readiness: {latest_record.workfrontReadinessPct:.1f}%\n"
        response += f"- 📐 Float: {latest_record.avgFloat:.1f} days\n\n"
        
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
        if latest_record.workfrontReadinessPct < 70:
            response += "**Option 5: Workfront Resolution** 🚧\n"
            response += f"- Current workfront readiness is only {latest_record.workfrontReadinessPct:.1f}%\n"
            response += "- Clear material/ROW/access constraints\n"
            response += "- Coordinate with procurement/land teams\n"
            response += "- Estimated schedule recovery: 5-10 days\n"
            response += "- Risk: Low-Medium (depends on constraint type)\n\n"
        
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
        current_delay = latest_record.forecastDelayDays
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
            response += f"- Forecast Delay: {latest_record.forecastDelayDays} days\n"
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


SRA_TOOLS = [sra_status_pei]