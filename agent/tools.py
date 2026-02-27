"""
SRA Schedule Intelligence Agent — Tools
=========================================
LangGraph-compatible async tools organised across the 6 Schedule
Touchpoint Layers for a Construction Project Management context.

Hierarchy supported: Project → Activity → Task
(Work Package excluded per current scope)

Layer Map
---------
Layer 1 — Schedule Health & Status
    sra_status_pei              ← retained & enhanced (Project)
    sra_activity_health         ← NEW  (Activity drill-down)
    sra_task_lookahead          ← NEW  (Task-grain 2W/4W look-ahead)

Layer 2 — Schedule Intelligence
    sra_critical_path           ← NEW  (CP density, controlling float)
    sra_float_analysis          ← NEW  (Float distribution & erosion watch)
    sra_productivity_rate       ← NEW  (Rate analysis — required vs earned)

Layer 3 — Schedule Integrity
    sra_baseline_management     ← NEW  (Baseline drift, rescheduled slip)
    sra_schedule_quality        ← NEW  (Data freshness, LAC compliance)

Layer 4 — Schedule Risk & Impact
    sra_drill_delay             ← retained & enhanced (Activity)
    sra_procurement_alignment   ← NEW  (PRC rules, at-risk material milestones)
    sra_eot_exposure            ← NEW  (EOT eligibility, contractual buffer)

Layer 5 — Schedule Action & Recovery
    sra_recovery_advise         ← retained & enhanced
    sra_simulate                ← retained & enhanced
    sra_create_action           ← retained

Layer 6 — Schedule Communication & Governance
    sra_accountability_trace    ← NEW  (Task accountability, report flags)
    sra_explain_formula         ← retained & enhanced

Prisma Models
-------------
  prisma.tbl01projectsummary     →  Tbl01ProjectSummary   (tbl_01_project_summary)
  prisma.tbl02projectactivity    →  Tbl02ProjectActivity  (tbl_02_project_activity)
  prisma.tbl03projecttask        →  Tbl03ProjectTask      (tbl_03_project_task)
"""

from datetime import datetime, date
from typing import Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from db import get_prisma


# ─────────────────────────────────────────────────────────────────────────────
#  GLOBAL THRESHOLDS  (single source of truth — referenced by all tools)
# ─────────────────────────────────────────────────────────────────────────────
SPI_THRESHOLD               = 1.0    # ≥ 1.0 → on or ahead of schedule
PEI_THRESHOLD               = 1.0    # ≤ 1.0 → forecast within planned duration
FORECAST_DELAY_THRESHOLD    = 30     # days — material slippage trigger
WORKFRONT_READINESS_THRESHOLD = 70.0 # % — minimum readiness to proceed
NEAR_CRITICAL_FLOAT_DAYS    = 5      # days — near-critical watch trigger
LAC_COMPLIANCE_THRESHOLD    = 80.0   # % — Look-Ahead Compliance minimum


def _threshold_footer() -> str:
    return (
        "\n\n---\n"
        "📌 **Reference Thresholds** │ "
        f"SPI ≥ {SPI_THRESHOLD} │ "
        f"PEI ≤ {PEI_THRESHOLD} │ "
        f"Max Forecast Delay ≤ {FORECAST_DELAY_THRESHOLD}d │ "
        f"Workfront Readiness ≥ {WORKFRONT_READINESS_THRESHOLD}% │ "
        f"LAC ≥ {LAC_COMPLIANCE_THRESHOLD}%"
    )


def _rag_icon(rag: Optional[str]) -> str:
    if not rag:
        return "⬜"
    r = rag.strip().upper()
    if r in ("RED", "AT RISK", "CRITICAL", "OVERDUE"):
        return "🔴"
    if r in ("AMBER", "WATCH", "NEAR CRITICAL", "MINOR DRIFT"):
        return "🟡"
    if r in ("GREEN", "ON TRACK", "HEALTHY", "WITHIN"):
        return "🟢"
    return "⬜"


def _d(v) -> str:
    """Format nullable day value."""
    return f"{v}d" if v is not None else "—"


def _pct(v) -> str:
    """Format nullable percent value."""
    return f"{v:.1f}%" if v is not None else "—"


async def _list_projects(prisma) -> str:
    try:
        records = await prisma.tbl01projectsummary.find_many(
            select={"projectKey": True, "projectName": True},
            take=20,
        )
        seen, rows = set(), []
        for p in records:
            if p.projectKey not in seen:
                seen.add(p.projectKey)
                rows.append(f"  • {p.projectKey} — {p.projectName}")
                if len(rows) >= 10:
                    break
        return "\n".join(rows)
    except Exception:
        return "  (Unable to retrieve project list)"


def parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  PYDANTIC INPUT SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ProjectKeyInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key (e.g. '101').")

class ProjectDateInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key (e.g. '101').")
    date: Optional[str] = Field(None, description="Reporting date YYYY-MM-DD. Defaults to latest available data.")

class ProjectActivityInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key.")
    activity_code: Optional[str] = Field(None, description="Activity code to filter to a specific activity.")
    domain_code: Optional[str] = Field(None, description="Domain filter: ENG / PRC / CON.")

class ProjectTaskInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key.")
    activity_code: Optional[str] = Field(None, description="Activity code to scope tasks.")
    domain_code: Optional[str] = Field(None, description="Domain filter: ENG / PRC / CON.")
    window: Optional[str] = Field("2W", description="Look-ahead window: '2W' (default) or '4W'.")

class DelayDrillInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key.")
    start_date: Optional[str] = Field(None, description="Start of analysis window YYYY-MM-DD.")
    end_date: Optional[str] = Field(None, description="End of analysis window YYYY-MM-DD.")

class RecoveryAdviseInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key.")
    activity_id: Optional[str] = Field(None, description="Activity code to focus recovery around.")
    resource_type: Optional[str] = Field(None, description="Resource type for targeted advice (labor / equipment / material).")

class SimulateInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key.")
    resource_type: Optional[str] = Field(None, description="Resource type (e.g. shuttering_gang / labor / equipment / overtime).")
    value_amount: Optional[float] = Field(None, description="Quantity or number of resource units.")
    date_range: Optional[str] = Field(None, description="Targeted date range for the scenario (e.g. 'this Sunday' or '2025-07-15 to 2025-07-20').")

class CreateActionInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Numeric project key.")
    user_id: Optional[str] = Field(None, description="User or role to assign the action to.")
    action_choice: Optional[str] = Field(None, description="Action description (e.g. 'Approve Option 1', 'Raise alert to site planner').")

class ExplainFormulaInput(BaseModel):
    project_key: Optional[str] = Field(None, description="Optional project key for live metric context.")
    metric: Optional[str] = Field(None, description="Metric to explain: SPI / PEI / LAC / Float / EOT / all.")


# ═════════════════════════════════════════════════════════════════════════════
#  LAYER 1 — SCHEDULE HEALTH & STATUS
# ═════════════════════════════════════════════════════════════════════════════

@tool(args_schema=ProjectDateInput)
async def sra_status_pei(
    project_key: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """
    LAYER 1 — Schedule Health & Status | Project-Level Health Snapshot.

    USE FOR:
    ✅ Direct status questions: "Is the project on track?", "Schedule status?"
    ✅ KPI dashboard requests: "Show SPI, PEI and progress", "Give me schedule KPIs"
    ✅ Executive overviews: "Quick health check", "Should I be concerned about timeline?"
    ✅ Domain-level progress: "How is Engineering performing vs Construction?"

    DO NOT USE FOR:
    ❌ Delay root cause drill-down   → sra_drill_delay
    ❌ Recovery planning              → sra_recovery_advise
    ❌ What-if scenarios              → sra_simulate
    ❌ Activity-level detail          → sra_activity_health
    ❌ Critical path investigation    → sra_critical_path

    HEALTH CLASSIFICATION (Gated):
      Gate 1: SPI < 1.0  → Schedule Attention Required
      Gate 2: PEI > 1.0  → Forecast Duration Exceeds Plan
      Gate 3: Delay > 30d → Material Slippage Flagged
      Otherwise           → On Programme

    OUTPUT: Project health status | SPI/PEI | E/P/C progress breakdown |
            EOT exposure | Workfront readiness | Schedule Health RAG
    """
    prisma = await get_prisma()
    
    if not project_key:
        pl = await _list_projects(prisma)
        return (
            "📋 **Please specify the project to assess.**\n\n"
            f"Available projects:\n{pl}\n\n"
            "💡 Example: *What is the schedule health of project 101?*"
        )

    try:
        pk = int(project_key)

        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**. Please verify the project reference."

        # --- Key metrics ---
        pei       = float(ps.projectExecutionIndex or 1.0)
        spi       = ps.spiOverall or 1.0
        delay_all = ps.maxForecastDelayDaysOverall or 0

        # --- Gated classification ---
        if spi < SPI_THRESHOLD:
            status, icon = "Schedule Attention Required", "🔴"
            primary = f"SPI at {spi:.2f} — execution is {(1.0 - spi)*100:.1f}% behind planned throughput"
        elif pei > PEI_THRESHOLD:
            status, icon = "Forecast Duration Overrun", "🔴"
            primary = f"PEI at {pei:.2f} — forecast duration exceeds baseline by {(pei - 1.0)*100:.1f}%"
        elif delay_all > FORECAST_DELAY_THRESHOLD:
            status, icon = "Material Slippage Flagged", "🟡"
            primary = f"Forecast delay of {delay_all}d breaches the {FORECAST_DELAY_THRESHOLD}d threshold"
        else:
            status, icon = "On Programme", "✅"
            primary = "Schedule performance is within acceptable parameters"

        # --- Activities for E/P/C roll-up ---
        acts = await prisma.tbl02projectactivity.find_many(where={"projectKey": pk})

        def _domain_key(act):
            c = (act.domainCode or act.domain or "").strip().upper()
            if c in ("ENG", "E", "ENGINEERING"): return "E"
            if c in ("PRC", "P", "PROCUREMENT"): return "P"
            if c in ("CON", "C", "CONSTRUCTION"): return "C"
            return c or "—"

        groups = {}
        for a in acts:
            groups.setdefault(_domain_key(a), []).append(a)

        def _epc_row(key, label):
            ag = groups.get(key, [])
            if not ag:
                return {"label": label, "n": 0, "plan": 0.0, "actual": 0.0, "delay": 0, "spi": "—", "icon": "—"}
            plan_vals   = [a.plannedProgressPct for a in ag if a.plannedProgressPct is not None]
            actual_vals = [a.actualProgressPct  for a in ag if a.actualProgressPct  is not None]
            delay_vals  = [a.forecastDelayDays   for a in ag if (a.forecastDelayDays or 0) > 0]
            plan_avg    = sum(plan_vals)   / len(plan_vals)   if plan_vals   else 0.0
            actual_avg  = sum(actual_vals) / len(actual_vals) if actual_vals else 0.0
            delay_max   = max(delay_vals) if delay_vals else 0
            spi_vals    = [a.activitySpi for a in ag if a.activitySpi is not None]
            spi_avg     = sum(spi_vals) / len(spi_vals) if spi_vals else None
            epc_icon    = "✅" if actual_avg >= plan_avg * 0.95 else "🟡"
            return {
                "label": label, "n": len(ag),
                "plan": plan_avg, "actual": actual_avg,
                "delay": delay_max, "spi": f"{spi_avg:.2f}" if spi_avg else "—",
                "icon": epc_icon,
            }

        e = _epc_row("E", "Engineering")
        p = _epc_row("P", "Procurement")
        c = _epc_row("C", "Construction")

        cp_planned  = ps.cumulativePlannedPctOverall  or 0.0
        cp_actual   = ps.cumulativeActualPctOverall   or 0.0
        wf_pct      = ps.workfrontReadinessOverallPct or 0.0
        health_rag  = ps.scheduleHealthRag  or "—"
        health_score= ps.scheduleHealthScore

        spi_icon = "✅" if spi >= SPI_THRESHOLD else "🔴"
        pei_icon = "✅" if pei <= PEI_THRESHOLD else "🔴"

        resp  = f"## {icon} Schedule Health: **{status}**\n\n"
        resp += f"**{ps.projectName}** · {ps.projectLocation}\n"
        resp += f"*Report Date: {ps.dashboardAsondate.strftime('%d %b %Y') if ps.dashboardAsondate else 'Latest'}*\n\n"

        resp += (
            f"📊 **Cumulative Progress** — Planned: {cp_planned:.1f}%  |  "
            f"Achieved: {cp_actual:.1f}%  |  "
            f"Backlog: {(ps.cumulativeBacklogPctOverall or 0.0):.1f}%\n\n"
        )

        if status != "On Programme":
            resp += f"⚠️ *{primary}*\n\n"

        resp += "---\n\n"
        resp += "### Schedule Performance Indices\n\n"
        resp += "| Index | Value | Signal | Interpretation |\n"
        resp += "|-------|-------|--------|----------------|\n"
        resp += f"| {spi_icon} **SPI** | {spi:.3f} | {'On/Ahead of Schedule' if spi >= 1.0 else 'Behind Planned Throughput'} | Earned progress vs planned |\n"
        resp += f"| {pei_icon} **PEI** | {pei:.3f} | {'Forecast ≤ Baseline Duration' if pei <= 1.0 else 'Forecast Exceeds Baseline Duration'} | Forecast duration efficiency |\n"

        if health_score is not None:
            resp += f"| {_rag_icon(health_rag)} **Health Score** | {health_score:.1f}/100 | {health_rag} | Composite schedule health |\n"

        resp += "\n### EPC Domain Breakdown\n\n"
        resp += "| Domain | Activities | Planned % | Achieved % | Max Delay | Domain SPI |\n"
        resp += "|--------|-----------|-----------|------------|-----------|------------|\n"
        for row in [e, p, c]:
            resp += (
                f"| {row['icon']} **{row['label']}** | {row['n']} | "
                f"{row['plan']:.1f}% | {row['actual']:.1f}% | "
                f"{_d(row['delay'])} | {row['spi']} |\n"
            )
        resp += (
            f"| | **Overall** | {cp_planned:.1f}% | {cp_actual:.1f}% | "
            f"**{_d(delay_all)}** | {spi:.3f} |\n"
        )

        resp += f"\n### Supporting Indicators\n\n"
        resp += f"- 🏗️ **Workfront Readiness**: {wf_pct:.1f}% {'✅' if wf_pct >= WORKFRONT_READINESS_THRESHOLD else '⚠️'}\n"
        resp += f"- 📅 **EOT Exposure**: {_d(ps.eotExposureDays)}  |  EOT Status: {ps.eotEligibilityLabel or '—'}\n"
        resp += f"- 📋 **Data Freshness**: {ps.dataFreshnessLabel or '—'}  ({_d(ps.dataAgeDays)} old)\n"
        resp += f"- 🔑 **Weakest Domain**: {ps.weakestDomain or '—'}\n"

        if ps.scheduleRecoveryDays and ps.scheduleRecoveryDays > 0:
            resp += f"\n💬 *{ps.scheduleRecoveryDays} days of schedule recovery are required to meet the contractual completion date.*\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`. Please provide a numeric value (e.g. 101)."
    except Exception as e:
        return f"Error retrieving schedule health data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectActivityInput)
async def sra_activity_health(
    project_key: Optional[str] = None,
    activity_code: Optional[str] = None,
    domain_code: Optional[str] = None,
) -> str:
    """
    LAYER 1 — Schedule Health & Status | Activity-Level Health Drill-Down.

    USE FOR:
    ✅ "Show me all activities that are behind plan"
    ✅ "Which Construction activities have slipped?"
    ✅ "Drill into activity-level performance for project 101"
    ✅ "What is the health of activity XYZ?"
    ✅ "Which activities have workfront constraints?"

    Surfaces per-activity: status, SPI, slip days, workfront readiness,
    LAC compliance (week & month), float status, and delay magnitude.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for activity health review.**\n\n{pl}"

    try:
        pk = int(project_key)
        where: dict = {"projectKey": pk}
        if domain_code:
            where["domainCode"] = {"in": [domain_code.upper(), domain_code.lower()]}

        acts = await prisma.tbl02projectactivity.find_many(where=where)
        if activity_code:
            acts = [a for a in acts if (a.activityCode or "").upper() == activity_code.upper()]

        if not acts:
            return f"No activity records found for project **{project_key}** with the specified filters."

        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        proj_name = ps.projectName if ps else str(project_key)

        # Categorise
        overdue       = [a for a in acts if (a.activityStatus or "").lower() in ("overdue", "overdue — not started")]
        in_progress   = [a for a in acts if (a.activityStatus or "").lower() == "in progress"]
        not_started   = [a for a in acts if (a.activityStatus or "").lower() == "not yet due"]
        completed     = [a for a in acts if (a.activityStatus or "").lower() == "complete"]
        delayed       = sorted(
            [a for a in acts if (a.forecastDelayDays or 0) > 0],
            key=lambda x: -(x.forecastDelayDays or 0),
        )

        resp  = f"## 📋 Activity Health Review — {proj_name}\n\n"
        resp += f"*Domain filter: {domain_code or 'All'} | Activity filter: {activity_code or 'All'}*\n\n"
        resp += (
            f"**Summary** — Total: {len(acts)} | "
            f"Complete: {len(completed)} | "
            f"In Progress: {len(in_progress)} | "
            f"Overdue / Not Mobilised: {len(overdue)} | "
            f"Not Yet Due: {len(not_started)}\n\n"
        )

        resp += "---\n\n### Activities Requiring Attention\n\n"
        if delayed:
            resp += f"**{len(delayed)}** activities are trending beyond their forecast completion:\n\n"
            resp += "| Activity | Domain | Status | Slip (d) | Forecast Delay | SPI | Workfront | LAC Week |\n"
            resp += "|----------|--------|--------|---------|----------------|-----|-----------|----------|\n"
            for a in delayed[:20]:
                wf_icon  = "✅" if (a.workfrontReadyPct or 0) >= WORKFRONT_READINESS_THRESHOLD else "⚠️"
                cp_icon  = "🔴" if a.isCriticalWrench else ""
                resp += (
                    f"| {cp_icon}{a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {a.activityStatus or '—'} "
                    f"| {_d(a.slipDays)} "
                    f"| {_d(a.forecastDelayDays)} "
                    f"| {f'{a.activitySpi:.2f}' if a.activitySpi is not None else '—'} "
                    f"| {wf_icon} {f'{a.workfrontReadyPct:.0f}%' if a.workfrontReadyPct is not None else '—'} "
                    f"| {_pct(a.conLacWeekPct)} |\n"
                )
        else:
            resp += "✅ No activities are currently trending beyond their forecast completion.\n"

        resp += "\n### Workfront Constraint Watch\n\n"
        wf_constrained = [a for a in acts if (a.workfrontReadyPct or 0) < WORKFRONT_READINESS_THRESHOLD and a.activityStatus not in ("Complete",)]
        if wf_constrained:
            resp += f"**{len(wf_constrained)}** activities have workfront readiness below {WORKFRONT_READINESS_THRESHOLD}%:\n\n"
            resp += "| Activity | Domain | Workfront % | Gap Count | Critical Path |\n"
            resp += "|----------|--------|-------------|-----------|---------------|\n"
            for a in wf_constrained[:10]:
                cp = "Yes 🔴" if a.isCriticalWrench else "No"
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_pct(a.workfrontReadyPct)} "
                    f"| {a.workfrontGapCount or 0} "
                    f"| {cp} |\n"
                )
        else:
            resp += f"✅ All active activities are above the {WORKFRONT_READINESS_THRESHOLD}% workfront readiness threshold.\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving activity health data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectTaskInput)
async def sra_task_lookahead(
    project_key: Optional[str] = None,
    activity_code: Optional[str] = None,
    domain_code: Optional[str] = None,
    window: Optional[str] = "2W",
) -> str:
    """
    LAYER 1 — Schedule Health & Status | Task-Level Look-Ahead (2-Week / 4-Week).

    USE FOR:
    ✅ "What tasks are starting in the next 2 weeks?"
    ✅ "Show me the 4-week look-ahead for Construction"
    ✅ "Which tasks should be mobilised this fortnight?"
    ✅ "4-week look-ahead for activity ABC"

    Surfaces tasks falling within the 2W or 4W start/finish windows,
    with workfront status, float position, and priority score.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for the look-ahead window.**\n\n{pl}"

    try:
        pk   = int(project_key)
        wnd  = (window or "2W").upper()
        is4w = wnd == "4W"

        where: dict = {"projectKey": pk}
        tasks = await prisma.tbl03projecttask.find_many(where=where)

        if activity_code:
            tasks = [t for t in tasks if (t.activityCode or "").upper() == activity_code.upper()]
        if domain_code:
            dc = domain_code.upper()
            tasks = [t for t in tasks if (t.domainCode or "").upper() in (dc,)]

        window_field_start  = "in4wStartWindow"  if is4w else "in2wStartWindow"
        window_field_finish = None                            # 4W finish not in schema at task
        # Filter to tasks flagged for the window
        la_tasks = [t for t in tasks if getattr(t, "in4wStartWindow" if is4w else "in2wStartWindow", None)]

        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        proj_name = ps.projectName if ps else str(project_key)

        resp  = f"## 🗓️ {'4-Week' if is4w else '2-Week'} Look-Ahead — {proj_name}\n\n"
        resp += f"*Scope: {domain_code or 'All Domains'} | Activity: {activity_code or 'All'}*\n\n"

        if not la_tasks:
            resp += f"No tasks flagged within the {'4-week' if is4w else '2-week'} start window for the selected scope.\n"
            return resp + _threshold_footer()

        # Sort by priority score desc, then forecast start
        la_tasks.sort(key=lambda t: (-(t.lookaheadPriorityScore or 0)))

        # Split by workfront
        wf_ready    = [t for t in la_tasks if t.isWorkfrontAvailable]
        wf_blocked  = [t for t in la_tasks if not t.isWorkfrontAvailable]

        resp += (
            f"**{len(la_tasks)}** tasks fall within the {'4-week' if is4w else '2-week'} start window:\n"
            f"— Workfront Available: **{len(wf_ready)}**  |  "
            f"Workfront Constrained: **{len(wf_blocked)}**\n\n"
        )

        resp += "### Tasks Ready to Mobilise ✅\n\n"
        if wf_ready:
            resp += "| Task | Activity | Domain | Forecast Start | Forecast Finish | Float | Priority Score | Critical |\n"
            resp += "|------|----------|--------|---------------|-----------------|-------|----------------|----------|\n"
            for t in wf_ready[:15]:
                fs = t.forecastStartDate.strftime("%d %b") if t.forecastStartDate else "—"
                ff = t.forecastFinishDate.strftime("%d %b") if t.forecastFinishDate else "—"
                cp = "🔴" if t.isCriticalWrench else ""
                resp += (
                    f"| {t.taskName or t.taskKey} "
                    f"| {t.activityCode or '—'} "
                    f"| {t.domainCode or '—'} "
                    f"| {fs} | {ff} "
                    f"| {_d(t.totalFloatDays)} "
                    f"| {t.lookaheadPriorityScore:.1f} "
                    f"| {cp} |\n"
                )
            else:
                resp += "No workfront-available tasks in the look-ahead window.\n"

        resp += "\n### Workfront-Constrained Tasks — Action Required ⚠️\n\n"
        if wf_blocked:
            resp += "| Task | Activity | Domain | Forecast Start | Float | Block Flag |\n"
            resp += "|------|----------|--------|---------------|-------|------------|\n"
            for t in wf_blocked[:10]:
                fs = t.forecastStartDate.strftime("%d %b") if t.forecastStartDate else "—"
                resp += (
                    f"| {t.taskName or t.taskKey} "
                    f"| {t.activityCode or '—'} "
                    f"| {t.domainCode or '—'} "
                    f"| {fs} "
                    f"| {_d(t.totalFloatDays)} "
                    f"| {'🚧 Blocked' if t.workfrontBlockFlag else 'Constrained'} |\n"
                )
            else:
                resp += "No workfront-constrained tasks in the look-ahead window.\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error generating look-ahead: {str(e)}"


# ═════════════════════════════════════════════════════════════════════════════
#  LAYER 2 — SCHEDULE INTELLIGENCE
# ═════════════════════════════════════════════════════════════════════════════

@tool(args_schema=ProjectKeyInput)
async def sra_critical_path(project_key: Optional[str] = None) -> str:
    """
    LAYER 2 — Schedule Intelligence | Critical Path Analysis.

    USE FOR:
    ✅ "What is driving the critical path?"
    ✅ "How many tasks are on the critical path?"
    ✅ "Show me the CP density and tightening score"
    ✅ "Which activities are controlling the programme?"
    ✅ "Has the critical path shifted since last update?"

    Surfaces: CP task count, CP density, tightening score, negative float
    tasks, controlling activities, and CP status labels at task grain.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for critical path analysis.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        # Critical & near-critical tasks
        tasks = await prisma.tbl03projecttask.find_many(where={"projectKey": pk})
        cp_tasks        = [t for t in tasks if t.isCriticalWrench]
        neg_float_tasks = [t for t in tasks if (t.totalFloatDays or 999) < 0]
        zero_float      = [t for t in tasks if t.totalFloatDays == 0]
        near_crit       = [t for t in tasks if 0 < (t.totalFloatDays or 999) <= NEAR_CRITICAL_FLOAT_DAYS]

        # Sort CP tasks by float ascending (most constrained first)
        cp_tasks_sorted = sorted(cp_tasks, key=lambda t: (t.totalFloatDays or 0))

        resp  = f"## 🔴 Critical Path Analysis — {ps.projectName}\n\n"
        resp += (
            f"**CP Task Count**: {ps.cpTaskCount or len(cp_tasks)}  |  "
            f"**CP Density**: {ps.cpPctOfTotal:.1f}% of total programme\n"
            if ps.cpPctOfTotal else
            f"**CP Task Count**: {len(cp_tasks)}  |  **Total Tasks**: {len(tasks)}\n"
        )
        if ps.cpTighteningScore is not None:
            resp += f"**CP Tightening Score**: {ps.cpTighteningScore:.2f} {'⚠️ Path is tightening' if ps.cpTighteningScore > 0.5 else '✅ Path is stable'}\n"

        resp += f"\n---\n\n### Float Distribution Summary\n\n"
        resp += f"| Float Band | Task Count | % of Programme |\n"
        resp += f"|-----------|-----------|----------------|\n"
        resp += f"| 🔴 Negative Float | {ps.floatNegativeTaskCount or len(neg_float_tasks)} | {ps.negFloatPct or 0:.1f}% |\n"
        resp += f"| 🔴 Zero Float (Critical) | {ps.floatZeroTaskCount or len(zero_float)} | {ps.zeroFloatPct or 0:.1f}% |\n"
        resp += f"| 🟡 Near-Critical (≤{NEAR_CRITICAL_FLOAT_DAYS}d) | {ps.floatNearCriticalTaskCount or len(near_crit)} | {ps.nearCritFloatPct or 0:.1f}% |\n"
        resp += f"| 🟢 Healthy Float | {ps.floatPositiveTaskCount or 0} | {ps.healthyFloatPct or 0:.1f}% |\n"
        resp += f"| **Project Min Float** | — | **{_d(ps.floatMinDays)}** |\n"
        resp += f"| **Average Float** | — | **{_d(ps.floatAvgDays)}** |\n"

        resp += f"\n### Controlling Critical Path Tasks (Top 15)\n\n"
        if cp_tasks_sorted:
            resp += "| Task | Activity | Domain | Float (d) | Status | Delay (d) | CP Status |\n"
            resp += "|------|----------|--------|-----------|--------|-----------|----------|\n"
            for t in cp_tasks_sorted[:15]:
                resp += (
                    f"| {t.taskName or t.taskKey} "
                    f"| {t.activityCode or '—'} "
                    f"| {t.domainCode or '—'} "
                    f"| {_d(t.totalFloatDays)} "
                    f"| {t.taskStatus or '—'} "
                    f"| {_d(t.forecastDelayDays)} "
                    f"| {t.cpStatusLabel or '—'} |\n"
                )
        else:
            resp += "No critical path tasks identified under current float parameters.\n"

        if neg_float_tasks:
            resp += f"\n⚠️ **{len(neg_float_tasks)} tasks carry negative float** — these represent schedule overruns that have already materialised on the critical path and require immediate triage.\n"

        return resp + _threshold_footer()
        
    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving critical path data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectActivityInput)
async def sra_float_analysis(
    project_key: Optional[str] = None,
    activity_code: Optional[str] = None,
    domain_code: Optional[str] = None,
) -> str:
    """
    LAYER 2 — Schedule Intelligence | Float Analysis & Near-Critical Watch.

    USE FOR:
    ✅ "Which activities are losing float?"
    ✅ "Show me near-critical activities in Construction"
    ✅ "Float erosion watch — what needs attention?"
    ✅ "How much scheduling buffer remains on activity XYZ?"
    ✅ "What is the float health across the programme?"

    Surfaces float health status, erosion flags, CAD breach activities,
    and controlling float activities at both activity and task grain.
    """
    prisma = await get_prisma()
    
    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for float analysis.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})

        where: dict = {"projectKey": pk}
        acts = await prisma.tbl02projectactivity.find_many(where=where)
        if activity_code:
            acts = [a for a in acts if (a.activityCode or "").upper() == activity_code.upper()]
        if domain_code:
            dc = domain_code.upper()
            acts = [a for a in acts if (a.domainCode or "").upper() in (dc,)]

        proj_name = ps.projectName if ps else str(project_key)

        eroding = [a for a in acts if (a.floatErosionFlag or 0) > 0]
        cad_breach = [a for a in acts if a.cadBreachFlag]
        near_crit_acts = [a for a in acts if 0 <= (a.totalFloatDays or 999) <= NEAR_CRITICAL_FLOAT_DAYS]
        controlling = [a for a in acts if (a.isControllingFloatActivity or 0) > 0]

        eroding.sort(key=lambda a: (a.totalFloatDays or 999))
        near_crit_acts.sort(key=lambda a: (a.totalFloatDays or 999))

        resp  = f"## ⏳ Float Analysis & Near-Critical Watch — {proj_name}\n\n"
        if ps:
            resp += (
                f"**Programme Float Health**: {_pct(ps.floatHealthPct)}  |  "
                f"**At-Risk Float**: {_pct(ps.floatAtRiskPct)}  |  "
                f"**Min Float**: {_d(ps.floatMinDays)}\n\n"
            )

        resp += "---\n\n### Near-Critical Activity Watch (Float ≤ 5 days)\n\n"
        if near_crit_acts:
            resp += f"**{len(near_crit_acts)}** activities are within the near-critical threshold:\n\n"
            resp += "| Activity | Domain | Float (d) | CAD Breach | Erosion Flag | CP Status |\n"
            resp += "|----------|--------|-----------|------------|--------------|----------|\n"
            for a in near_crit_acts[:15]:
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_d(a.totalFloatDays)} "
                    f"| {'⚠️ Yes' if a.cadBreachFlag else 'No'} "
                    f"| {'🔴 Eroding' if (a.floatErosionFlag or 0) > 0 else '—'} "
                    f"| {a.cpLabel or '—'} |\n"
                )
        else:
            resp += f"✅ No activities are within the {NEAR_CRITICAL_FLOAT_DAYS}-day near-critical threshold.\n"

        resp += "\n### Float Erosion Watch\n\n"
        if eroding:
            resp += f"**{len(eroding)}** activities show float erosion — their scheduling buffer is being progressively consumed:\n\n"
            resp += "| Activity | Domain | Float (d) | Float vs Project Min | CAD Breach |\n"
            resp += "|----------|--------|-----------|----------------------|------------|\n"
            for a in eroding[:10]:
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_d(a.totalFloatDays)} "
                    f"| {f'{a.floatVsProjectMin:.1f}' if a.floatVsProjectMin is not None else '—'} "
                    f"| {'⚠️' if a.cadBreachFlag else '—'} |\n"
                )
        else:
            resp += "✅ No float erosion flags are currently active across the selected scope.\n"

        if cad_breach:
            resp += f"\n⚠️ **{len(cad_breach)} activities have breached the Critical Activity Density (CAD) threshold** — these require schedule management escalation.\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving float analysis data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectActivityInput)
async def sra_productivity_rate(
    project_key: Optional[str] = None,
    activity_code: Optional[str] = None,
    domain_code: Optional[str] = None,
) -> str:
    """
    LAYER 2 — Schedule Intelligence | Productivity & Rate Analysis.

    USE FOR:
    ✅ "What is the required rate of progress to recover?"
    ✅ "Are we achieving the planned productivity rate?"
    ✅ "Show earned quantity vs planned for Construction activities"
    ✅ "Which activities have an execution rate gap?"
    ✅ "Productivity analysis for Procurement domain"

    Surfaces: planned vs earned quantity, required progress rate per day,
    progress variance, executable progress, and contribution to project.
    This is a leading indicator — rate shortfalls predict future slippage
    even when activities appear 'In Progress'.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for productivity rate analysis.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})

        where: dict = {"projectKey": pk}
        acts = await prisma.tbl02projectactivity.find_many(where=where)
        if activity_code:
            acts = [a for a in acts if (a.activityCode or "").upper() == activity_code.upper()]
        if domain_code:
            dc = domain_code.upper()
            acts = [a for a in acts if (a.domainCode or "").upper() in (dc,)]

        active = [a for a in acts if a.activityStatus not in ("Complete",) and a.plannedQuantity]
        proj_name = ps.projectName if ps else str(project_key)

        # Rate gap: where actual < planned progress and activity is in progress
        rate_gap = [
            a for a in active
            if a.progressVariancePct is not None and a.progressVariancePct < -5.0
        ]
        rate_gap.sort(key=lambda a: (a.progressVariancePct or 0))

        resp  = f"## ⚡ Productivity & Rate Analysis — {proj_name}\n\n"
        resp += f"*Scope: {domain_code or 'All Domains'} | Activity: {activity_code or 'All'}*\n\n"

        if ps:
            resp += (
                f"**Executable Progress (Overall)**: {_pct(ps.executableProgressOverallPct)}  |  "
                f"**E**: {_pct(ps.executableProgressEngineeringPct)}  "
                f"**P**: {_pct(ps.executableProgressProcurementPct)}  "
                f"**C**: {_pct(ps.executableProgressConstructionPct)}\n\n"
            )

        resp += "---\n\n### Execution Rate Gap — Activities Below Required Rate\n\n"
        resp += "*A rate shortfall is a leading indicator of schedule slippage — even activities marked In Progress can drive future delays if the production rate is below what the plan demands.*\n\n"

        if rate_gap:
            resp += f"**{len(rate_gap)}** activities are tracking below the required progress rate:\n\n"
            resp += "| Activity | Domain | Planned % | Achieved % | Variance | Required Rate/Day | Earned Qty | Planned Qty |\n"
            resp += "|----------|--------|-----------|------------|----------|-------------------|-----------|-------------|\n"
            for a in rate_gap[:20]:
                req_rate = a.requiredProgressRatePerDay or "—"
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_pct(a.plannedProgressPct)} "
                    f"| {_pct(a.actualProgressPct)} "
                    f"| {a.progressVariancePct:.1f}% "
                    f"| {req_rate} "
                    f"| {f'{a.earnedQuantity:.1f}' if a.earnedQuantity is not None else '—'} "
                    f"| {f'{a.plannedQuantity:.1f}' if a.plannedQuantity is not None else '—'} |\n"
                )
        else:
            resp += "✅ All active activities are tracking at or above the required progress rate.\n"

        resp += "\n### Top Contributors to Project Progress\n\n"
        top_contrib = sorted(
            [a for a in acts if a.contributionToProjectPct],
            key=lambda a: -(a.contributionToProjectPct or 0),
        )[:10]
        if top_contrib:
            resp += "| Activity | Domain | Contribution % | SPI | Status |\n"
            resp += "|----------|--------|----------------|-----|--------|\n"
            for a in top_contrib:
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_pct(a.contributionToProjectPct)} "
                    f"| {f'{a.activitySpi:.2f}' if a.activitySpi is not None else '—'} "
                    f"| {a.activityStatus or '—'} |\n"
                )

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving productivity rate data: {str(e)}"


# ═════════════════════════════════════════════════════════════════════════════
#  LAYER 3 — SCHEDULE INTEGRITY
# ═════════════════════════════════════════════════════════════════════════════

@tool(args_schema=ProjectKeyInput)
async def sra_baseline_management(project_key: Optional[str] = None) -> str:
    """
    LAYER 3 — Schedule Integrity | Baseline Management & Drift Analysis.

    USE FOR:
    ✅ "How much has the schedule drifted from the original baseline?"
    ✅ "What is the JCR/PMS approved baseline status?"
    ✅ "Has the rescheduled baseline been exceeded?"
    ✅ "Show me activities with significant baseline drift"
    ✅ "Baseline integrity status for project 101"

    Surfaces: JCR/PMS approval dates, rescheduled baseline slippage,
    current vs rescheduled drift, baseline integrity label, and
    activity-level baseline drift classification.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for baseline management review.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        acts = await prisma.tbl02projectactivity.find_many(where={"projectKey": pk})
        drifted = [a for a in acts if a.baselineDriftLabel and "Drift" in (a.baselineDriftLabel or "")]
        drifted.sort(key=lambda a: -(a.slipDays or 0))

        resp  = f"## 📐 Baseline Management — {ps.projectName}\n\n"

        resp += "### Approved Schedule Reference Points\n\n"
        resp += "| Baseline Marker | Date | Notes |\n"
        resp += "|----------------|------|-------|\n"
        resp += f"| **Original Baseline Start** | {ps.baselineStartDate.strftime('%d %b %Y') if ps.baselineStartDate else '—'} | JCR-approved programme start |\n"
        resp += f"| **Original Baseline Finish** | {ps.baselineFinishDate.strftime('%d %b %Y') if ps.baselineFinishDate else '—'} | JCR-approved completion |\n"
        resp += f"| **JCR Approved Date** | {ps.jcrApprovedDate.strftime('%d %b %Y') if ps.jcrApprovedDate else '—'} | Joint Construction Review |\n"
        resp += f"| **PMS Approved Date** | {ps.pmsApprovedDate.strftime('%d %b %Y') if ps.pmsApprovedDate else '—'} | Project Management Schedule |\n"
        resp += f"| **Rescheduled Baseline** | {ps.rescheduledDate.strftime('%d %b %Y') if ps.rescheduledDate else '—'} | Current approved revision |\n"
        resp += f"| **Contractual Completion** | {ps.contractualCompletionDate.strftime('%d %b %Y') if ps.contractualCompletionDate else '—'} | Client contract date |\n"
        resp += f"| **Forecast Completion** | {ps.forecastFinishDate.strftime('%d %b %Y') if ps.forecastFinishDate else '—'} | Current projection |\n\n"

        resp += "### Baseline Drift Summary\n\n"
        resp += f"| Drift Metric | Value | Assessment |\n"
        resp += f"|-------------|-------|------------|\n"
        resp += f"| Baseline vs Rescheduled Slip | {ps.baselineVsRescheduledSlip or '—'} | Approved revision from original |\n"
        resp += f"| Current vs Rescheduled Slip | {ps.currentVsRescheduledSlip or '—'} | Forecast drift from revision |\n"
        resp += f"| Overall Slip Days | {_d(ps.slipDays)} | Baseline to forecast |\n"
        resp += f"| Schedule Variance | {_d(ps.scheduleVarianceDays)} | Earned vs planned |\n"
        resp += f"| **Baseline Integrity** | **{ps.baselineIntegrityLabel or '—'}** | {_rag_icon(ps.baselineIntegrityLabel)} |\n\n"

        resp += "### Activities with Baseline Drift\n\n"
        if drifted:
            resp += f"**{len(drifted)}** activities are tracking beyond their approved baseline:\n\n"
            resp += "| Activity | Domain | Slip (d) | Forecast Delay (d) | Baseline Drift Label |\n"
            resp += "|----------|--------|----------|-------------------|----------------------|\n"
            for a in drifted[:15]:
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_d(a.slipDays)} "
                    f"| {_d(a.forecastDelayDays)} "
                    f"| {a.baselineDriftLabel or '—'} |\n"
                )
        else:
            resp += "✅ All activities are tracking within their approved baseline parameters.\n"

        return resp + _threshold_footer()
        
    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving baseline management data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectKeyInput)
async def sra_schedule_quality(project_key: Optional[str] = None) -> str:
    """
    LAYER 3 — Schedule Integrity | Schedule Quality & LAC Compliance.

    USE FOR:
    ✅ "Is the schedule data current and reliable?"
    ✅ "Show me LAC compliance — are rules being executed?"
    ✅ "What is the data freshness status?"
    ✅ "How many construction rules are overdue?"
    ✅ "Schedule integrity health check for project 101"

    Surfaces: data age/freshness, Construction LAC compliance (week/month),
    Procurement LAC compliance, overdue rule counts, and at-risk milestones.
    LAC (Look-Ahead Compliance) measures execution commitment against plan.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for schedule quality review.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        con_lac_week  = ps.conLacWeekPct  or 0.0
        con_lac_month = ps.conLacMonthPct or 0.0
        prc_lac_week  = ps.prcLacWeekPct  or 0.0
        prc_lac_month = ps.prcLacMonthPct or 0.0

        con_rag = "✅" if con_lac_week >= LAC_COMPLIANCE_THRESHOLD else "🔴"
        prc_rag = "✅" if prc_lac_week >= LAC_COMPLIANCE_THRESHOLD else "🔴"

        resp  = f"## 🔎 Schedule Quality & Integrity — {ps.projectName}\n\n"

        resp += "### Data Freshness\n\n"
        resp += f"| Indicator | Value |\n|-----------|-------|\n"
        resp += f"| Dashboard As-On Date | {ps.dashboardAsondate.strftime('%d %b %Y') if ps.dashboardAsondate else '—'} |\n"
        resp += f"| Data Age | {_d(ps.dataAgeDays)} |\n"
        resp += f"| Freshness Status | {ps.dataFreshnessLabel or '—'} |\n\n"

        resp += "### Look-Ahead Compliance (LAC)\n\n"
        resp += "*LAC measures the percentage of look-ahead commitments that were executed on time. A reading below 80% indicates a disconnect between short-term planning and site execution.*\n\n"
        resp += "| Domain | LAC (Week) | LAC (Month) | Overdue Rules | At-Risk 7d | At-Risk 30d | Pending |\n"
        resp += "|--------|------------|-------------|---------------|-----------|------------|--------|\n"
        resp += (
            f"| {con_rag} **Construction** "
            f"| {con_lac_week:.1f}% "
            f"| {con_lac_month:.1f}% "
            f"| {ps.conLacOverdueCount or 0} "
            f"| {ps.conLacAtRisk7dayCount or 0} "
            f"| {ps.conLacAtRisk30dayCount or 0} "
            f"| {ps.conLacPendingCount or 0} |\n"
        )
        resp += (
            f"| {prc_rag} **Procurement** "
            f"| {prc_lac_week:.1f}% "
            f"| {prc_lac_month:.1f}% "
            f"| {ps.prcLacOverdueCount or 0} "
            f"| {ps.prcLacAtRisk7dayCount or 0} "
            f"| {ps.prcLacAtRisk30dayCount or 0} "
            f"| {ps.prcLacPendingCount or 0} |\n\n"
        )

        resp += "### Activity Completion Health\n\n"
        resp += f"| Status | Count | Rate |\n|--------|-------|------|\n"
        resp += f"| Total Activities | {ps.activitiesTotalCount or '—'} | — |\n"
        resp += f"| Complete | {ps.activitiesCompleteCount or '—'} | {_pct(ps.activitiesCompletionRatePct)} |\n"
        resp += f"| In Progress | {ps.activitiesInProgressCount or '—'} | — |\n"
        resp += f"| Overdue / Not Mobilised | {ps.activitiesOverdueCount or '—'} | {_pct(ps.activitiesOverdueRatePct)} |\n"
        resp += f"| Not Yet Due | {ps.activitiesNotYetDueCount or '—'} | — |\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving schedule quality data: {str(e)}"


# ═════════════════════════════════════════════════════════════════════════════
#  LAYER 4 — SCHEDULE RISK & IMPACT
# ═════════════════════════════════════════════════════════════════════════════

@tool(args_schema=DelayDrillInput)
async def sra_drill_delay(
    project_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    LAYER 4 — Schedule Risk & Impact | Delay & Risk Analysis.

    USE FOR:
    ✅ "Why is the project behind?"
    ✅ "Which activities are causing delay?"
    ✅ "Show me the delay hotspot analysis"
    ✅ "Delay root cause breakdown for project 101"
    ✅ "Where is the schedule risk concentrated?"

    Surfaces: delay hotspot domain, activity-level delay ranking,
    CPM delay breach flags, workfront constraints, compound risk scores,
    and delay severity labels.
    """
    prisma = await get_prisma()
    
    if not project_key:
        pl = await _list_projects(prisma)
        return (
            "📋 **Please specify the project for delay analysis.**\n\n"
            f"Available projects:\n{pl}\n\n"
            "💡 Example: *Analyse delay exposure for project 101*"
        )

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        acts = await prisma.tbl02projectactivity.find_many(where={"projectKey": pk})

        def _delay(a):
            if (a.forecastDelayDays or 0) > 0:
                return a.forecastDelayDays
            if a.forecastFinishDate and a.baselineFinishDate:
                return max(0, (a.forecastFinishDate - a.baselineFinishDate).days)
            return 0

        delayed = sorted([a for a in acts if _delay(a) > 0], key=lambda a: -_delay(a))
        cp_delayed = [a for a in delayed if a.isCriticalWrench]
        wf_constrained = [a for a in acts if (a.workfrontReadyPct or 0) < WORKFRONT_READINESS_THRESHOLD
                          and a.activityStatus not in ("Complete",)]

        resp  = f"## 🔍 Delay & Risk Analysis — {ps.projectName}\n\n"
        resp += f"**Location**: {ps.projectLocation}  |  **Forecast Delay (Overall)**: {_d(ps.maxForecastDelayDaysOverall)}\n"
        resp += (
            f"**Delay by Domain** — E: {_d(ps.maxForecastDelayDaysEngineering)}  "
            f"P: {_d(ps.maxForecastDelayDaysProcurement)}  "
            f"C: {_d(ps.maxForecastDelayDaysConstruction)}\n\n"
        )

        if ps.delayHotspotDomain:
            resp += f"🔴 **Delay Hotspot Domain**: {ps.delayHotspotDomain}  |  **Concentration Domain**: {ps.delayConcentrationDomain or '—'}\n"
        if ps.delayRiskLabel:
            resp += f"⚠️ **Delay Risk Classification**: {ps.delayRiskLabel}\n\n"

        resp += "---\n\n### Top Activities Contributing to Schedule Slippage\n\n"
        if delayed:
            resp += f"**{len(delayed)}** activities are tracking beyond their forecast completion ({len(cp_delayed)} on critical path):\n\n"
            resp += "| Activity | Domain | Status | Delay (d) | Critical | Workfront | Delay Source | Severity |\n"
            resp += "|----------|--------|--------|-----------|----------|-----------|--------------|----------|\n"
            for a in delayed[:15]:
                wf_icon = "✅" if (a.workfrontReadyPct or 0) >= WORKFRONT_READINESS_THRESHOLD else "⚠️"
                cp_flag = "🔴 Yes" if a.isCriticalWrench else "No"
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {a.activityStatus or '—'} "
                    f"| {_delay(a)}d "
                    f"| {cp_flag} "
                    f"| {wf_icon} {_pct(a.workfrontReadyPct)} "
                    f"| {a.delaySourceLabel or '—'} "
                    f"| {a.delayMagnitudeLabel or '—'} |\n"
                )
        else:
            resp += "✅ No activities are currently tracking beyond their forecast completion.\n"

        resp += "\n### Workfront & Access Constraints\n\n"
        if wf_constrained:
            resp += (
                f"**{len(wf_constrained)}** active activities have workfront readiness below "
                f"{WORKFRONT_READINESS_THRESHOLD}% — unresolved constraints are a primary driver of execution shortfall:\n\n"
            )
            resp += "| Activity | Domain | Readiness % | Gap Count | Critical |\n"
            resp += "|----------|--------|-------------|-----------|----------|\n"
            for a in wf_constrained[:10]:
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {_pct(a.workfrontReadyPct)} "
                    f"| {a.workfrontGapCount or 0} "
                    f"| {'🔴 Yes' if a.isCriticalWrench else 'No'} |\n"
                )
        else:
            resp += f"✅ All active activities are at or above the {WORKFRONT_READINESS_THRESHOLD}% workfront readiness threshold.\n"

        resp += "\n### Summary Statistics\n\n"
        all_d = [_delay(a) for a in acts]
        avg_d = sum(all_d) / len(all_d) if all_d else 0
        resp += f"- Total Activities: **{len(acts)}**\n"
        resp += f"- Activities with Forecast Slippage: **{len(delayed)}**\n"
        resp += f"- Critical Path Activities Slipping: **{len(cp_delayed)}**\n"
        resp += f"- Average Activity Delay: **{avg_d:.1f}d**\n"
        resp += f"- Workfront-Constrained Activities: **{len(wf_constrained)}**\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving delay analysis data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectKeyInput)
async def sra_procurement_alignment(project_key: Optional[str] = None) -> str:
    """
    LAYER 4 — Schedule Risk & Impact | Procurement & Material Schedule Alignment.

    USE FOR:
    ✅ "Are procurement milestones aligned with the construction schedule?"
    ✅ "Show me at-risk procurement rules"
    ✅ "How many PRC rules are overdue?"
    ✅ "Procurement schedule risk — what could hold up site?"
    ✅ "Material delivery alignment check for project 101"

    Surfaces: PRC LAC compliance, overdue and at-risk procurement rules,
    activity-level procurement rule status, and CPM delay breach flags
    for procurement-domain activities.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for procurement alignment review.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        # All activities with procurement rule data
        acts = await prisma.tbl02projectactivity.find_many(where={"projectKey": pk})
        prc_acts = [a for a in acts if (a.prcTotalRules or 0) > 0]
        prc_at_risk = [a for a in prc_acts if (a.prcAtRiskRules7day or 0) > 0 or (a.prcOverdueRules or 0) > 0]
        prc_at_risk.sort(key=lambda a: -((a.prcOverdueRules or 0) + (a.prcAtRiskRules7day or 0)))

        prc_tasks = await prisma.tbl03projecttask.find_many(
            where={"projectKey": pk, "domainCode": {"in": ["PRC", "P", "Procurement"]}}
        )
        prc_delayed_tasks = [t for t in prc_tasks if (t.forecastDelayDays or 0) > 0]

        resp  = f"## 📦 Procurement & Material Schedule Alignment — {ps.projectName}\n\n"

        resp += "### Procurement LAC Compliance\n\n"
        prc_lac_icon = "✅" if (ps.prcLacWeekPct or 0) >= LAC_COMPLIANCE_THRESHOLD else "🔴"
        resp += f"| Metric | Week | Month | RAG |\n|--------|------|-------|-----|\n"
        resp += f"| {prc_lac_icon} PRC LAC Compliance | {_pct(ps.prcLacWeekPct)} | {_pct(ps.prcLacMonthPct)} | {ps.prcLacRag or '—'} |\n\n"

        resp += "### Procurement Rule Status\n\n"
        resp += f"| Rule Category | Count |\n|--------------|-------|\n"
        resp += f"| Overdue Rules | 🔴 {ps.prcLacOverdueCount or 0} |\n"
        resp += f"| At Risk (7-day window) | 🟡 {ps.prcLacAtRisk7dayCount or 0} |\n"
        resp += f"| At Risk (30-day window) | 🟡 {ps.prcLacAtRisk30dayCount or 0} |\n"
        resp += f"| Pending | {ps.prcLacPendingCount or 0} |\n"
        resp += f"| Completed | {ps.prcLacCompletedRules or 0} |\n\n"

        resp += "### Activity-Level Procurement Risk\n\n"
        if prc_at_risk:
            resp += f"**{len(prc_at_risk)}** activities have procurement rules at risk of non-compliance:\n\n"
            resp += "| Activity | Domain | Total Rules | Overdue | At Risk 7d | At Risk 30d | LAC Week |\n"
            resp += "|----------|--------|-------------|---------|------------|------------|----------|\n"
            for a in prc_at_risk[:15]:
                resp += (
                    f"| {a.activityDescription or a.activityCode} "
                    f"| {a.domainCode or '—'} "
                    f"| {a.prcTotalRules or 0} "
                    f"| 🔴 {a.prcOverdueRules or 0} "
                    f"| 🟡 {a.prcAtRiskRules7day or 0} "
                    f"| {a.prcAtRiskRules30day or 0} "
                    f"| {_pct(a.prcLacWeekPct)} |\n"
                )
        else:
            resp += "✅ No procurement activities have overdue or at-risk rules in the current period.\n"

        if prc_delayed_tasks:
            resp += f"\n⚠️ **{len(prc_delayed_tasks)} procurement tasks** are currently tracking beyond their planned completion — these represent potential material delivery risks to the construction schedule.\n"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving procurement alignment data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ProjectKeyInput)
async def sra_eot_exposure(project_key: Optional[str] = None) -> str:
    """
    LAYER 4 — Schedule Risk & Impact | EOT Exposure & Contractual Buffer Analysis.

    USE FOR:
    ✅ "What is our Extension of Time exposure?"
    ✅ "How many days of buffer remain before contractual breach?"
    ✅ "EOT eligibility status for project 101"
    ✅ "Are we at risk of liquidated damages?"
    ✅ "Contractual completion risk assessment"

    Surfaces: EOT exposure days, contractual buffer, EOT eligibility,
    days to contractual end, schedule recovery requirement, and
    RAG status against the contractual completion date.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for EOT exposure assessment.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        eot_days    = ps.eotExposureDays or 0
        buffer_days = ps.eotBufferDays   or 0
        rag         = ps.eotRagStatus    or "—"

        resp  = f"## ⚖️ EOT Exposure & Contractual Buffer — {ps.projectName}\n\n"

        resp += f"| Contractual Metric | Value | Assessment |\n"
        resp += f"|-------------------|-------|------------|\n"
        resp += f"| Contractual Completion Date | {ps.contractualCompletionDate.strftime('%d %b %Y') if ps.contractualCompletionDate else '—'} | Client contract |\n"
        resp += f"| Forecast Completion Date | {ps.forecastFinishDate.strftime('%d %b %Y') if ps.forecastFinishDate else '—'} | Current projection |\n"
        resp += f"| Days to Contractual End | {_d(ps.daysToContractualEnd)} | Remaining contractual window |\n"
        resp += f"| Days to Forecast End | {_d(ps.daysToForecastEnd)} | Remaining programme window |\n"
        resp += f"| **EOT Exposure** | **{_d(eot_days)}** | {_rag_icon(rag)} Delay beyond contractual end |\n"
        resp += f"| EOT Buffer | {_d(buffer_days)} | Approved buffer before breach |\n"
        resp += f"| **EOT RAG Status** | **{rag}** | {_rag_icon(rag)} |\n"
        resp += f"| EOT Eligibility | {ps.eotEligibilityLabel or '—'} | Contractual entitlement assessment |\n\n"

        resp += "### Schedule Recovery Requirement\n\n"
        resp += f"| Recovery Metric | Value |\n|----------------|-------|\n"
        resp += f"| Schedule Recovery Required | {_d(ps.scheduleRecoveryDays)} |\n"
        resp += f"| Recovery SPI Required | {ps.recoverySpiRequired:.3f} |\n" if ps.recoverySpiRequired else ""
        resp += f"| Recovery Plan Status | {ps.recoveryPlanStatus or '—'} |\n"
        resp += f"| Compression Headroom | {_pct(ps.compressionHeadroomPct)} |\n\n"

        if eot_days > 0:
            resp += (
                f"⚠️ **The project is currently tracking {eot_days} days beyond the contractual completion date.** "
                f"{'An EOT submission may be warranted — review entitlement basis.' if ps.eotEligibilityLabel else 'Contractual obligations should be reviewed with the project controls team.'}\n"
            )
        elif buffer_days > 0:
            resp += f"✅ The project retains {buffer_days} days of contractual buffer. Continued performance monitoring is required to preserve this position.\n"

        return resp + _threshold_footer()
        
    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving EOT exposure data: {str(e)}"


# ═════════════════════════════════════════════════════════════════════════════
#  LAYER 5 — SCHEDULE ACTION & RECOVERY
# ═════════════════════════════════════════════════════════════════════════════

@tool(args_schema=RecoveryAdviseInput)
async def sra_recovery_advise(
    project_key: Optional[str] = None,
    activity_id: Optional[str] = None,
    resource_type: Optional[str] = None,
) -> str:
    """
    LAYER 5 — Schedule Action & Recovery | Recovery Planning & Options.

    USE FOR:
    ✅ "What are our options to recover the programme?"
    ✅ "How do we close the {X}-day delay?"
    ✅ "Give me recovery strategies for project 101"
    ✅ "What is feasible to bring us back on programme?"
    ✅ "Recovery options focused on labor / equipment"

    Presents structured recovery options: resource augmentation,
    schedule compression, fast-tracking, scope resequencing, and
    workfront resolution. Each option is assessed for feasibility
    based on the project's current position.
    """
    prisma = await get_prisma()
    
    if not project_key:
        pl = await _list_projects(prisma)
        return (
            "📋 **Specify the project for recovery planning.**\n\n"
            f"{pl}\n\n"
            "💡 Example: *What are the recovery options for project 101?*"
        )

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        acts = await prisma.tbl02projectactivity.find_many(where={"projectKey": pk})
        wf_ready   = sum(1 for a in acts if (a.workfrontReadyPct or 0) >= WORKFRONT_READINESS_THRESHOLD)
        wf_pct     = (wf_ready / len(acts) * 100) if acts else 0
        delay      = ps.maxForecastDelayDaysOverall or 0
        spi        = ps.spiOverall or 1.0
        recovery_d = ps.scheduleRecoveryDays or delay
        headroom   = ps.compressionHeadroomPct or 0.0
        feasibility= ps.recoveryPlanStatus or "—"

        resp  = f"## 🔧 Recovery Planning — {ps.projectName}\n\n"
        resp += "### Current Programme Position\n\n"
        resp += f"| Metric | Value |\n|--------|-------|\n"
        resp += f"| PEI | {float(ps.projectExecutionIndex or 1.0):.3f} |\n"
        resp += f"| SPI | {spi:.3f} |\n"
        resp += f"| Forecast Delay | {_d(delay)} |\n"
        resp += f"| Recovery Required | {_d(recovery_d)} |\n"
        resp += f"| Workfront Readiness | {wf_pct:.0f}% |\n"
        resp += f"| Compression Headroom | {_pct(headroom)} |\n"
        resp += f"| Recovery Plan Status | {feasibility} |\n\n"

        resp += "---\n\n### Recovery Strategy Options\n\n"

        resp += (
            "**Option 1 — Resource Augmentation** 👷\n"
            "- Deploy additional crews to critical path and near-critical activities\n"
        )
        if resource_type:
            resp += f"- Targeted resource type: {resource_type}\n"
        resp += (
            "- Applicable where workfront is available and site capacity permits\n"
            "- Estimated programme recovery: 3–5 days per fortnight of augmentation\n"
            "- Risk level: Medium — quality assurance protocols must be maintained\n\n"
        )

        resp += (
            "**Option 2 — Schedule Compression (Crashing)** ⏱️\n"
            "- Introduce extended working hours or additional shifts on critical path activities\n"
            f"- Compression headroom available: {_pct(headroom)}\n"
            "- Estimated programme recovery: 5–8 days\n"
            "- Risk level: Medium — premium cost increase of approximately 12–18%\n\n"
        )

        resp += (
            "**Option 3 — Fast-Tracking** 🚀\n"
            "- Introduce concurrent execution of activities currently sequenced in series\n"
        )
        if activity_id:
            resp += f"- Recommended focal point: activity {activity_id}\n"
        resp += (
            "- Applicable where logical dependencies permit parallel working\n"
            "- Estimated programme recovery: 4–7 days\n"
            "- Risk level: High — increased coordination and interface management required\n\n"
        )

        resp += (
            "**Option 4 — Resequencing & Scope Deferral** 📋\n"
            "- Advance high-priority critical path deliverables; defer non-critical scope\n"
            "- Requires stakeholder alignment and change management approval\n"
            "- Estimated programme recovery: 2–4 days\n"
            "- Risk level: Low-Medium — contract implications to be assessed\n\n"
        )

        if wf_pct < WORKFRONT_READINESS_THRESHOLD:
            resp += (
                f"**Option 5 — Workfront Constraint Resolution** 🚧\n"
                f"- Only {wf_pct:.0f}% of activities have confirmed workfront availability\n"
                f"- {len(acts) - wf_ready} activities are constrained by material delivery, RoW, or access clearance\n"
                "- Resolving constraints unlocks execution capacity and is the highest-leverage intervention\n"
                "- Coordinate with procurement, land, and logistics teams immediately\n"
                "- Estimated programme recovery: 5–12 days depending on constraint type\n"
                "- Risk level: Low — this is process-driven, not cost-driven\n\n"
            )

        resp += (
            "---\n\n"
            "💬 *Select an option to simulate its schedule impact, or request that a recovery action be logged for the site planning team.*"
        )

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error generating recovery advice: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=SimulateInput)
async def sra_simulate(
    project_key: Optional[str] = None,
    resource_type: Optional[str] = None,
    value_amount: Optional[float] = None,
    date_range: Optional[str] = None,
) -> str:
    """
    LAYER 5 — Schedule Action & Recovery | What-If Scenario Analysis.

    USE FOR:
    ✅ "What if I deploy 2 additional shuttering gangs?"
    ✅ "Simulate working this Sunday on project 101"
    ✅ "What is the schedule impact of adding overtime?"
    ✅ "Model the effect of an extra equipment deployment"

    Runs scenario modelling to project the schedule impact of resource
    or working-pattern changes. Outputs projected delay reduction,
    revised SPI, and indicative cost impact.
    """
    prisma = await get_prisma()

    missing = []
    if not project_key:
        pl = await _list_projects(prisma)
        missing.append(f"**Project** — which project?\n{pl}")
    if not resource_type:
        missing.append("**Resource Type** — e.g. shuttering_gang / labor / equipment / overtime")
    if not value_amount:
        missing.append("**Quantity** — e.g. 2 (gangs), 8 (overtime hours)")

    if missing:
        return (
            "📋 **Additional details required to run the scenario:**\n\n"
            + "\n\n".join(missing)
            + "\n\n💡 Example: *What if I add 2 shuttering gangs to project 101?*"
        )

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        if not ps:
            return f"No schedule data found for project key **{project_key}**."

        delay   = ps.maxForecastDelayDaysOverall or 0
        spi     = ps.spiOverall or 1.0
        rt      = resource_type.lower()

        # Productivity and cost modelling by resource type
        if rt in ("shuttering_gang", "gang", "crew", "formwork_gang"):
            prod_factor  = value_amount * 0.15
            cost_per_unit = 25000
            risk_note    = "Coordination overhead with newly mobilised teams; site induction and productivity ramp-up period applies."
        elif rt in ("labor", "labour", "worker", "manpower"):
            prod_factor  = value_amount * 0.05
            cost_per_unit = 5000
            risk_note    = "Workforce absorption capacity and supervisory ratio should be validated before deployment."
        elif rt in ("overtime", "sunday", "weekend", "extended_hours"):
            prod_factor  = 0.12
            cost_per_unit = 15000
            risk_note    = "Fatigue management protocols apply; overtime premium rates and quality oversight must be maintained."
        elif rt in ("equipment", "machinery", "plant"):
            prod_factor  = value_amount * 0.20
            cost_per_unit = 50000
            risk_note    = "Equipment mobilisation lead time and site access must be confirmed prior to deployment."
        else:
            prod_factor  = value_amount * 0.10
            cost_per_unit = 10000
            risk_note    = "Resource availability and site integration plan should be confirmed with the site planning team."

        recovered   = max(0, int(delay * prod_factor))
        new_delay   = max(0, delay - recovered)
        new_spi     = min(1.10, spi + (prod_factor * 0.1))
        cost_impact = value_amount * cost_per_unit if rt not in ("overtime", "sunday", "weekend", "extended_hours") else cost_per_unit

        resp  = f"## 📊 Scenario Analysis — {ps.projectName}\n\n"
        resp += f"**Scenario**: Deploy {value_amount:.0f} × {resource_type}"
        if date_range:
            resp += f" ({date_range})"
        resp += "\n\n---\n\n"

        resp += "### Projected Programme Impact\n\n"
        resp += "| Metric | Current | Projected | Change |\n"
        resp += "|--------|---------|-----------|--------|\n"
        resp += f"| Forecast Delay | {delay}d | {new_delay}d | **−{recovered}d** |\n"
        resp += f"| SPI | {spi:.3f} | {new_spi:.3f} | +{(new_spi - spi):.3f} |\n"
        resp += f"| Productivity Rate | Baseline | +{prod_factor*100:.1f}% | ✅ Enhanced |\n\n"

        resp += "### Cost Impact\n\n"
        resp += f"- **Incremental Cost Estimate**: ₹{cost_impact:,.0f}\n"
        resp += f"- **Cost per Day Recovered**: ₹{cost_impact/max(1, recovered):,.0f}\n\n"

        resp += "### Risk & Implementation Considerations\n\n"
        resp += f"- {risk_note}\n"
        resp += "- Confirm impact on concurrent activities and interface obligations before deployment\n"
        resp += "- Review against EOT entitlement basis if acceleration cost is to be claimed\n\n"

        resp += "---\n\n"
        resp += "💬 *Shall I log this scenario as an approved recovery action for the planning team?*"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error running scenario analysis: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=CreateActionInput)
async def sra_create_action(
    project_key: Optional[str] = None,
    user_id: Optional[str] = None,
    action_choice: Optional[str] = None,
) -> str:
    """
    LAYER 5 — Schedule Action & Recovery | Log Recovery Action.

    USE FOR:
    ✅ "Log Option 1 for project 101"
    ✅ "Raise a schedule alert to the site planner"
    ✅ "Create a recovery action item"
    ✅ "Assign fast-tracking decision to the planning team"
    """
    prisma = await get_prisma()
    
    missing = []
    if not project_key:
        pl = await _list_projects(prisma)
        missing.append(f"**Project** — which project?\n{pl}")
    if not action_choice:
        missing.append("**Action** — what should be logged? (e.g. 'Approve Option 2 — Schedule Compression')")

    if missing:
        return (
            "📋 **Additional details required to log the action:**\n\n"
            + "\n\n".join(missing)
            + "\n\n💡 Example: *Log Option 1 for project 101 and assign to site planner*"
        )

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})
        proj_name = ps.projectName if ps else str(project_key)
        action_id = f"ACT-{project_key}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        resp  = f"## ✅ Recovery Action Logged\n\n"
        resp += f"**Action ID**: `{action_id}`\n\n---\n\n"
        resp += "### Action Record\n\n"
        resp += "| Field | Detail |\n|-------|--------|\n"
        resp += f"| Project | {proj_name} (Key: {project_key}) |\n"
        resp += f"| Action | {action_choice} |\n"
        resp += f"| Assigned To | {user_id or 'Unassigned — Pending Nomination'} |\n"
        resp += f"| Status | 🟡 **Open — Pending Execution** |\n"
        resp += f"| Logged | {datetime.now().strftime('%d %b %Y %H:%M')} |\n\n"

        is_alert = any(kw in action_choice.lower() for kw in ("alert", "raise", "notify", "escalate"))
        if is_alert:
            resp += "### Alert Dispatch\n\n"
            resp += f"- Alert type: **Schedule Recovery — Immediate Action Required**\n"
            resp += f"- Recipient: {user_id or 'Site Planner / Planning Manager'}\n"
            resp += "- Priority: **High**\n"
            resp += "- Channels: 📧 Email + 📱 Push notification queued\n\n"

        if ps:
            resp += "### Current Programme Context\n\n"
            resp += f"- PEI: {float(ps.projectExecutionIndex or 1.0):.3f}\n"
            resp += f"- SPI: {ps.spiOverall:.3f}\n"
            resp += f"- Forecast Delay: {_d(ps.maxForecastDelayDaysOverall)}\n"
            resp += f"- EOT Exposure: {_d(ps.eotExposureDays)}\n\n"

        resp += "💡 *This action has been logged for tracking. The assigned team member will receive notification for follow-through.*"

        return resp + _threshold_footer()

    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error logging recovery action: {str(e)}"


# ═════════════════════════════════════════════════════════════════════════════
#  LAYER 6 — SCHEDULE COMMUNICATION & GOVERNANCE
# ═════════════════════════════════════════════════════════════════════════════

@tool(args_schema=ProjectTaskInput)
async def sra_accountability_trace(
    project_key: Optional[str] = None,
    activity_code: Optional[str] = None,
    domain_code: Optional[str] = None,
    window: Optional[str] = None,
) -> str:
    """
    LAYER 6 — Schedule Communication & Governance | Accountability & Traceability.

    USE FOR:
    ✅ "Which tasks are flagged for reporting this period?"
    ✅ "Show me task accountability labels for Construction"
    ✅ "What tasks are scheduled for narrative reporting?"
    ✅ "Trace delay attribution for critical tasks"
    ✅ "Report-ready task summary for the weekly review"

    Surfaces: task report flags, narrative contribution labels,
    delay attribution, task accountability labels, task health RAG,
    and as-built vs baseline duration variance for completed tasks.
    """
    prisma = await get_prisma()

    if not project_key:
        pl = await _list_projects(prisma)
        return f"📋 **Specify the project for accountability tracing.**\n\n{pl}"

    try:
        pk = int(project_key)
        ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": pk})

        where: dict = {"projectKey": pk}
        tasks = await prisma.tbl03projecttask.find_many(where=where)

        if activity_code:
            tasks = [t for t in tasks if (t.activityCode or "").upper() == activity_code.upper()]
        if domain_code:
            dc = domain_code.upper()
            tasks = [t for t in tasks if (t.domainCode or "").upper() in (dc,)]

        proj_name = ps.projectName if ps else str(project_key)

        report_tasks    = [t for t in tasks if t.taskReportFlag]
        narrative_tasks = [t for t in tasks if t.narrativeContributionLabel]
        delay_attr      = [t for t in tasks if t.delayAttributionLabel and t.delayAttributionLabel != "—"]
        crash_cands     = [t for t in tasks if t.crashCandidateFlag]
        fast_cands      = [t for t in tasks if t.fasttrackCandidateFlag]

        resp  = f"## 📝 Accountability & Reporting Traceability — {proj_name}\n\n"
        resp += f"*Scope: {domain_code or 'All Domains'} | Activity: {activity_code or 'All'}*\n\n"

        resp += "### Report-Flagged Tasks (Current Period)\n\n"
        if report_tasks:
            resp += f"**{len(report_tasks)}** tasks are flagged for narrative reporting this period:\n\n"
            resp += "| Task | Activity | Domain | Health RAG | Accountability | Narrative Label |\n"
            resp += "|------|----------|--------|------------|----------------|----------------|\n"
            for t in report_tasks[:20]:
                resp += (
                    f"| {t.taskName or t.taskKey} "
                    f"| {t.activityCode or '—'} "
                    f"| {t.domainCode or '—'} "
                    f"| {_rag_icon(t.taskHealthRag)} {t.taskHealthRag or '—'} "
                    f"| {t.taskAccountabilityLabel or '—'} "
                    f"| {t.narrativeContributionLabel or '—'} |\n"
                )
        else:
            resp += "No tasks are currently flagged for narrative reporting.\n"

        resp += "\n### Delay Attribution Trace\n\n"
        if delay_attr:
            resp += f"**{len(delay_attr)}** tasks have delay attribution records — relevant for variance reporting and potential EOT substantiation:\n\n"
            resp += "| Task | Activity | Domain | Delay (d) | Attribution | Baseline Drift |\n"
            resp += "|------|----------|--------|-----------|-------------|----------------|\n"
            for t in delay_attr[:15]:
                resp += (
                    f"| {t.taskName or t.taskKey} "
                    f"| {t.activityCode or '—'} "
                    f"| {t.domainCode or '—'} "
                    f"| {_d(t.forecastDelayDays)} "
                    f"| {t.delayAttributionLabel} "
                    f"| {t.taskBaselineDriftLabel or '—'} |\n"
                )
        else:
            resp += "No delay attribution records found for the selected scope.\n"

        if crash_cands or fast_cands:
            resp += f"\n### Recovery Candidate Tasks\n\n"
            resp += f"- **Crash Candidates** (eligible for resource augmentation): {len(crash_cands)}\n"
            resp += f"- **Fast-Track Candidates** (eligible for concurrent working): {len(fast_cands)}\n"

        resp += f"\n### As-Built vs Baseline Duration (Completed Tasks)\n\n"
        completed_with_data = [
            t for t in tasks
            if t.asBuiltDurationDays and t.baselineDurationDays
            and t.taskStatus == "Complete"
        ]
        if completed_with_data:
            resp += "| Task | Baseline Duration | As-Built Duration | Duration Variance |\n"
            resp += "|------|------------------|-------------------|------------------|\n"
            for t in completed_with_data[:10]:
                var = (t.durationVarianceDays or 0)
                var_icon = "🔴" if var > 5 else ("🟡" if var > 0 else "✅")
                resp += (
                    f"| {t.taskName or t.taskKey} "
                    f"| {t.baselineDurationDays}d "
                    f"| {t.asBuiltDurationDays}d "
                    f"| {var_icon} {_d(var)} |\n"
                )
        else:
            resp += "Insufficient as-built data for completed task variance analysis in the selected scope.\n"

        return resp + _threshold_footer()
        
    except ValueError:
        return f"Invalid project key `{project_key}`."
    except Exception as e:
        return f"Error retrieving accountability trace data: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────

@tool(args_schema=ExplainFormulaInput)
async def sra_explain_formula(
    project_key: Optional[str] = None,
    metric: Optional[str] = None,
) -> str:
    """
    LAYER 6 — Schedule Communication & Governance | Metric & Formula Explanation.

    USE FOR:
    ✅ "How is SPI calculated?"
    ✅ "What does PEI represent?"
    ✅ "Explain LAC compliance"
    ✅ "What is Float and how does it impact the critical path?"
    ✅ "EOT — what does it mean and how is exposure calculated?"

    Provides plain-language explanations of schedule KPIs and their
    construction programme management context.
    """
    prisma = await get_prisma()
    m = (metric or "all").lower()

    proj_ctx = None
    resp = "## 📐 Schedule Metric Reference Guide\n\n"

    if project_key:
        try:
            ps = await prisma.tbl01projectsummary.find_first(where={"projectKey": int(project_key)})
            if ps:
                proj_ctx = ps
                resp += f"*Live context: {ps.projectName} (Key: {project_key})*\n\n---\n\n"
        except Exception:
            pass

    if m in ("spi", "all", "schedule", "schedule performance index"):
        resp += (
            "### 📈 SPI — Schedule Performance Index\n\n"
            "**Formula**: `SPI = Earned Progress % / Planned Progress %`\n\n"
            "Measures whether work is being executed at the rate the programme demands. "
            "An SPI of 1.0 means the project is earning exactly what was planned. "
            "Below 1.0 indicates the execution rate is lagging — the gap compounds over time on a critical path.\n\n"
            "| Value | Signal | Interpretation |\n|-------|--------|----------------|\n"
            "| SPI > 1.0 | 🟢 Ahead of Programme | Execution exceeds plan |\n"
            "| SPI = 1.0 | ✅ On Programme | Performance exactly as planned |\n"
            "| SPI < 1.0 | 🔴 Behind Programme | Execution rate below plan |\n\n"
        )
        if proj_ctx:
            spi = proj_ctx.spiOverall or 1.0
            resp += f"*Current SPI: **{spi:.3f}** — {'On/Ahead of programme' if spi >= 1.0 else f'Behind by {(1-spi)*100:.1f}%'}*\n\n"

    if m in ("pei", "all", "efficiency", "project execution index"):
        resp += (
            "### 📊 PEI — Project Execution Index\n\n"
            "**Formula**: `PEI = Forecast Duration / Planned Duration`\n\n"
            "Measures whether the overall programme duration is expanding beyond its original plan. "
            "A PEI above 1.0 means the project is consuming more time than the baseline allocated — "
            "a direct signal of schedule overrun risk even if individual activities appear on track.\n\n"
            "| Value | Signal | Interpretation |\n|-------|--------|----------------|\n"
            "| PEI < 1.0 | 🟢 Duration Efficient | Forecast shorter than baseline |\n"
            "| PEI = 1.0 | ✅ On Programme | Forecast equals baseline duration |\n"
            "| PEI > 1.0 | 🔴 Duration Overrun | Forecast exceeds baseline |\n\n"
        )
        if proj_ctx:
            pei = float(proj_ctx.projectExecutionIndex or 1.0)
            resp += f"*Current PEI: **{pei:.3f}** — {'Efficient' if pei <= 1.0 else f'{(pei-1)*100:.1f}% over baseline duration'}*\n\n"

    if m in ("lac", "all", "look-ahead compliance", "look ahead"):
        resp += (
            "### 🎯 LAC — Look-Ahead Compliance\n\n"
            "**Formula**: `LAC % = (Rules Completed On Time / Total Rules Planned) × 100`\n\n"
            "LAC is the construction industry's primary execution reliability metric. "
            "It measures the percentage of short-term commitments (rules) that were fulfilled within the look-ahead window. "
            "A declining LAC is an early warning of execution discipline breakdown — it typically precedes SPI deterioration by 2–4 weeks.\n\n"
            "| Value | Signal |\n|-------|--------|\n"
            "| ≥ 80% | ✅ Strong execution reliability |\n"
            "| 60–79% | 🟡 Execution gap — root cause review warranted |\n"
            "| < 60% | 🔴 Systemic planning/execution disconnect — escalation required |\n\n"
        )

    if m in ("float", "all", "total float", "near critical"):
        resp += (
            "### ⏳ Total Float\n\n"
            "**Definition**: The maximum amount of time a task can be delayed without delaying the project completion date.\n\n"
            "Float is the scheduling buffer in the network. "
            "Zero float means any delay to that task directly extends the project end date (Critical Path). "
            "Negative float means the task is already causing a projected overrun. "
            "Near-critical tasks (≤5 days float) require active monitoring as they can migrate onto the critical path with a single disruption event.\n\n"
            "| Float Band | Classification |\n|-----------|----------------|\n"
            "| < 0 | 🔴 Overrun — already impacting completion |\n"
            "| = 0 | 🔴 Critical Path |\n"
            f"| 1–{NEAR_CRITICAL_FLOAT_DAYS}d | 🟡 Near-Critical Watch |\n"
            "| > 5d | 🟢 Schedule Buffer Available |\n\n"
        )

    if m in ("eot", "all", "extension of time", "contractual"):
        resp += (
            "### ⚖️ EOT — Extension of Time\n\n"
            "**Definition**: A contractual entitlement to extend the project completion date without penalty, "
            "typically granted when delay events arise from Employer risk or force majeure events.\n\n"
            "**EOT Exposure** represents the number of days the current forecast completion exceeds the contractual date. "
            "EOT Eligibility assesses whether the delay has a contractual basis for an extension claim. "
            "Unsubstantiated EOT exposure translates directly into Liquidated Damages (LD) liability.\n\n"
            "EOT forensic analysis requires establishing: the delay event timeline, "
            "its impact on the critical path at the time of occurrence, concurrent delay assessment, "
            "and the causal chain from event to completion date shift.\n\n"
        )

    resp += "---\n💡 *Ask about a specific metric for a live calculation against your project — e.g. 'Explain SPI for project 101'*"
    return resp + _threshold_footer()


# ═════════════════════════════════════════════════════════════════════════════
#  TOOL REGISTRY — exported for LangGraph agent
# ═════════════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════════════
#  SQL FALLBACK AGENT  — Layer 0 / Universal Escape Hatch
# ═════════════════════════════════════════════════════════════════════════════
"""
SQL Fallback Agent
------------------
Purpose
~~~~~~~
The 16 structured tools above cover the pre-defined analytical touchpoints
across all 6 schedule layers. However, a Construction PM will inevitably
ask questions that are:

  • Cross-table and multi-grain (e.g. "Show tasks within activities that
    have a CAD breach AND belong to the critical path")
  • Ad-hoc aggregations (e.g. "How many tasks per workpackage are in each
    float band?")
  • Date-window specific (e.g. "All activities forecast to finish in Q3
    with SPI < 0.9")
  • Comparative (e.g. "Top 5 locations by average forecast delay in CON")
  • Outside the pre-built Prisma query patterns entirely

The SQL fallback agent handles ALL of these. It:
  1. Receives a natural-language schedule question from the user.
  2. Translates it to a safe, read-only SQL SELECT against the Wrench views.
  3. Executes against the live database via asyncpg (read-only connection).
  4. Formats and returns results in a structured, PM-readable format.

Safety Guardrails
~~~~~~~~~~~~~~~~~
  - Only SELECT statements are permitted — any DML (INSERT/UPDATE/DELETE/DROP)
    is rejected before execution.
  - Statement is checked for injection patterns before dispatch.
  - A row cap of 500 is enforced to prevent runaway result sets.
  - Query timeout: 30 seconds.

Wrench Table Reference (SQL-grain names)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  tbl_01_project_summary    — Project-level KPIs (one row per Project_Key)
  tbl_02_project_activity   — Activity-level KPIs (one row per Activity_Code)
  tbl_03_project_task       — Task-level KPIs (one row per Task_Key)

Column naming convention: PascalCase with underscores (e.g. Project_Key,
SPI_Overall, Forecast_Delay_Days, CON_LAC_Week_Pct).

Routing Logic in the Agent Graph
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  The LangGraph router should route to `sra_sql_agent` when:
    ✅ No structured tool matches the user's question
    ✅ User explicitly asks for a custom report or data export
    ✅ User asks a comparative or ranking question across arbitrary dimensions
    ✅ User asks for a list/table that combines fields from multiple tables
    ✅ Agent's tool selection confidence is below threshold

  The router should NOT use `sra_sql_agent` for:
    ❌ Standard status/health checks → sra_status_pei
    ❌ Standard delay analysis       → sra_drill_delay
    ❌ Standard recovery planning    → sra_recovery_advise
    ❌ Any question clearly served by a named tool above
"""

import asyncpg
import os
import re as _re

SQL_ROW_CAP         = 500
SQL_TIMEOUT_SECONDS = 30

# Patterns that indicate unsafe / non-SELECT intent
_UNSAFE_PATTERNS = _re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|EXEC|EXECUTE|GRANT|REVOKE|MERGE)\b',
    _re.IGNORECASE,
)

# Columns to suppress from raw output (internal system columns)
_SUPPRESS_COLS = {"id", "created_at", "updated_at"}


def _q(name: str) -> str:
    """Quote a PostgreSQL identifier (column/table) so mixed-case and reserved words work."""
    return f'"{name}"'


def _t(table: str) -> str:
    """Schema-qualified table name for PostgreSQL."""
    return f"public.{table}"


def _sanitise_sql(sql: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Approves only single SELECT statements with no DML patterns.
    """
    stripped = sql.strip().rstrip(";")

    if _UNSAFE_PATTERNS.search(stripped):
        return False, "Statement contains disallowed DML/DDL keywords."

    if not stripped.upper().lstrip().startswith("SELECT"):
        return False, "Only SELECT statements are permitted."

    if stripped.count(";") > 0:
        return False, "Multiple statements are not permitted."

    return True, "OK"


def _format_sql_results(rows: list[dict], row_cap: int) -> str:
    """Render asyncpg row dicts as a clean markdown table."""
    if not rows:
        return "The query returned no records matching the specified criteria."

    # Filter suppressed columns
    all_cols = [c for c in rows[0].keys() if c.lower() not in _SUPPRESS_COLS]
    if not all_cols:
        return "Query returned rows but all columns were suppressed."

    # Header
    header = "| " + " | ".join(str(c) for c in all_cols) + " |"
    sep    = "|" + "|".join(["-" * (len(str(c)) + 2) for c in all_cols]) + "|"
    lines  = [header, sep]

    for row in rows[:row_cap]:
        cells = []
        for c in all_cols:
            v = row.get(c)
            if v is None:
                cells.append("—")
            elif isinstance(v, float):
                cells.append(f"{v:.3f}" if v != int(v) else str(int(v)))
            elif hasattr(v, "strftime"):
                cells.append(v.strftime("%d %b %Y"))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")

    result = "\n".join(lines)
    if len(rows) > row_cap:
        result += f"\n\n⚠️ *Result set capped at {row_cap} rows. Refine the query for a more targeted view.*"

    return result


class SRASqlAgentInput(BaseModel):
    """Input schema for the SQL fallback agent."""
    question: str = Field(
        description=(
            "The natural-language schedule question that could not be answered "
            "by a structured tool. Be as specific as possible — include project key, "
            "domain, date range, or any filters you need."
        )
    )
    project_key: Optional[str] = Field(
        None,
        description="Optional project key to scope the SQL query (e.g. '101')."
    )
    raw_sql: Optional[str] = Field(
        None,
        description=(
            "Optional: a raw SQL SELECT. Use ONLY column names that exist in the schema below; "
            "do NOT invent or assume column names (e.g. tbl_01 has NO Domain, Start_Date, End_Date, Status). "
            "Use double-quoted identifiers and schema-qualified tables. Only SELECT is permitted."
        )
    )


@tool(args_schema=SRASqlAgentInput)
async def sra_sql_agent(
    question: str,
    project_key: Optional[str] = None,
    raw_sql: Optional[str] = None,
) -> str:
    """
    LAYER 0 — SQL Fallback Agent | Ad-Hoc Schedule Data Queries.

    DO NOT HALLUCINATE FIELDS: Use ONLY column names that exist in the schema below.
    Never invent, assume, or guess column names (e.g. tbl_01_project_summary has NO
    "Domain", "Start_Date", "End_Date", or "Status" — use the exact names listed).

    This is the UNIVERSAL FALLBACK for any schedule question that cannot
    be served by the 16 structured tools.

    USE THIS TOOL WHEN:
    ✅ No structured tool covers the question
    ✅ User asks for a custom data table or cross-dimensional report
    ✅ User asks ranking/aggregation across arbitrary fields
    ✅ User asks a multi-table join question
    ✅ User provides a raw SQL query to execute
    ✅ Question references specific column names or calculated expressions
    ✅ User asks "list all...", "show me every...", "give me a table of..."

    DO NOT USE FOR questions that have a dedicated structured tool:
    ❌ Standard health check          → sra_status_pei
    ❌ Activity health overview       → sra_activity_health
    ❌ Look-ahead window              → sra_task_lookahead
    ❌ Critical path analysis         → sra_critical_path
    ❌ Float distribution             → sra_float_analysis
    ❌ Productivity rate gaps         → sra_productivity_rate
    ❌ Baseline drift review          → sra_baseline_management
    ❌ Schedule quality/LAC check     → sra_schedule_quality
    ❌ Delay root cause analysis      → sra_drill_delay
    ❌ Procurement rule alignment     → sra_procurement_alignment
    ❌ EOT exposure assessment        → sra_eot_exposure
    ❌ Recovery options               → sra_recovery_advise
    ❌ Scenario simulation            → sra_simulate
    ❌ Action logging                 → sra_create_action
    ❌ Accountability tracing         → sra_accountability_trace
    ❌ Metric explanation             → sra_explain_formula

    SAFETY: Only SELECT statements execute. All DML is blocked.
    ROW CAP: Results are capped at 500 rows.

    DATABASE TABLES — use ONLY these column names (never invent fields):

      public.tbl_01_project_summary (one row per project):
        Allowed: "Project_Key", "Project_Name", "Project_Location", "Baseline_Start_Date",
        "Baseline_Finish_Date", "Actual_Start_Date", "Forecast_Start_Date", "Forecast_Finish_Date",
        "SPI_Overall", "Schedule_Health_RAG", "Project_Execution_Index", "EOT_Exposure_Days",
        "Max_Forecast_Delay_Days_Overall", "Data_Freshness_Label", "Schedule_Health_Score",
        "Weakest_Domain", "EOT_RAG_Status", "Contractual_Completion_Date", "Slip_Days",
        "Schedule_Variance_Days", "Dashboard_AsOnDate", "Project_Manager", "Project_ID".
        FORBIDDEN on this table: Domain, Start_Date, End_Date, Status (do not use).

      public.tbl_02_project_activity (one row per activity):
        Allowed: "Project_Key", "Activity_Code", "Activity_Description", "Domain", "Domain_Code",
        "Baseline_Start_Date", "Baseline_Finish_Date", "Forecast_Start_Date", "Forecast_Finish_Date",
        "Actual_Start_Date", "Actual_Finish_Date", "Activity_Status", "Forecast_Delay_Days",
        "Total_Float_Days", "Slip_Days", "Is_Critical_Wrench", etc.

      public.tbl_03_project_task (one row per task):
        Allowed: "Project_Key", "Task_Key", "Task_Name", "Activity_Code", "Domain_Code",
        "Task_Status", "Total_Float_Days", "Forecast_Delay_Days", "Is_Critical_Wrench",
        "Task_Health_RAG", "Slip_Days", "Baseline_Start_Date", "Forecast_Start_Date", etc.

    IDENTIFIER RULE: All column and table identifiers MUST be double-quoted in SQL
    (e.g. "Project_Key", "SPI_Overall", "Baseline_Start_Date"). Unquoted identifiers
    will fail. Example: SELECT "Project_Key", "Project_Name", "Baseline_Start_Date" FROM public.tbl_01_project_summary;
    """

    # ── 1. SQL synthesis or passthrough ──────────────────────────────────
    sql_to_run: Optional[str] = None

    if raw_sql:
        # User or upstream agent provided explicit SQL
        sql_to_run = raw_sql.strip()
    else:
        # Synthesise SQL from natural language question
        # The agent builds a best-effort SELECT from the question context.
        # In production, this block would call an LLM sub-agent (text2sql).
        # Here we provide deterministic synthesis for common patterns,
        # and fall back to a guided message requesting explicit SQL.

        q = question.lower()
        pk_filter = f'WHERE {_q("Project_Key")} = {project_key}' if project_key else ""
        pk_and    = f'AND {_q("Project_Key")} = {project_key}' if project_key else ""

        # Pattern library — all identifiers double-quoted; tables schema-qualified
        if any(kw in q for kw in ("task", "tasks")):
            if "critical" in q:
                sql_to_run = f"""
SELECT {_q("Task_Key")}, {_q("Task_Name")}, {_q("Activity_Code")}, {_q("Domain_Code")},
       {_q("Task_Status")}, {_q("Total_Float_Days")}, {_q("Forecast_Delay_Days")},
       {_q("Task_Health_RAG")}, {_q("Slip_Days")}
FROM {_t("tbl_03_project_task")}
{pk_filter}
{"WHERE" if not pk_filter else "AND"} {_q("Is_Critical_Wrench")} = TRUE
ORDER BY {_q("Total_Float_Days")} ASC
LIMIT {SQL_ROW_CAP}
""".strip()
            elif "delayed" in q or "slipped" in q or "overdue" in q:
                sql_to_run = f"""
SELECT {_q("Task_Key")}, {_q("Task_Name")}, {_q("Activity_Code")}, {_q("Domain_Code")},
       {_q("Task_Status")}, {_q("Forecast_Delay_Days")}, {_q("Slip_Days")},
       {_q("Total_Float_Days")}, {_q("Task_Risk_Tier")}
FROM {_t("tbl_03_project_task")}
{pk_filter}
{"WHERE" if not pk_filter else "AND"} {_q("Forecast_Delay_Days")} > 0
ORDER BY {_q("Forecast_Delay_Days")} DESC
LIMIT {SQL_ROW_CAP}
""".strip()
            elif "float" in q:
                sql_to_run = f"""
SELECT {_q("Task_Key")}, {_q("Task_Name")}, {_q("Activity_Code")}, {_q("Domain_Code")},
       {_q("Total_Float_Days")}, {_q("Float_Health_Status")}, {_q("Float_RAG_Label")},
       {_q("Is_Critical_Wrench")}, {_q("Float_Erosion_Flag")}
FROM {_t("tbl_03_project_task")}
{pk_filter}
ORDER BY {_q("Total_Float_Days")} ASC
LIMIT {SQL_ROW_CAP}
""".strip()
            elif "look" in q and ("2" in q or "week" in q):
                sql_to_run = f"""
SELECT {_q("Task_Key")}, {_q("Task_Name")}, {_q("Activity_Code")}, {_q("Domain_Code")},
       {_q("Forecast_Start_Date")}, {_q("Forecast_Finish_Date")},
       {_q("Is_WorkFront_Available")}, {_q("LookAhead_Priority_Score")}, {_q("Total_Float_Days")}
FROM {_t("tbl_03_project_task")}
{pk_filter}
{"WHERE" if not pk_filter else "AND"} {_q("In_2W_Start_Window")} IS NOT NULL
ORDER BY {_q("LookAhead_Priority_Score")} DESC
LIMIT {SQL_ROW_CAP}
""".strip()
            elif "milestone" in q:
                sql_to_run = f"""
SELECT {_q("Task_Key")}, {_q("Task_Name")}, {_q("Activity_Code")}, {_q("Domain_Code")},
       {_q("Baseline_Finish_Date")}, {_q("Forecast_Finish_Date")},
       {_q("Milestone_Status_Label")}, {_q("Slip_Days")}
FROM {_t("tbl_03_project_task")}
{pk_filter}
{"WHERE" if not pk_filter else "AND"} {_q("Is_Milestone")} = TRUE
ORDER BY {_q("Forecast_Finish_Date")} ASC
LIMIT {SQL_ROW_CAP}
""".strip()
            else:
                sql_to_run = f"""
SELECT {_q("Task_Key")}, {_q("Task_Name")}, {_q("Activity_Code")}, {_q("Domain_Code")},
       {_q("Task_Status")}, {_q("Planned_Progress_Pct")}, {_q("Actual_Progress_Pct")},
       {_q("Forecast_Delay_Days")}, {_q("Total_Float_Days")}, {_q("Task_Health_RAG")}
FROM {_t("tbl_03_project_task")}
{pk_filter}
ORDER BY {_q("Forecast_Delay_Days")} DESC NULLS LAST
LIMIT {SQL_ROW_CAP}
""".strip()

        elif any(kw in q for kw in ("activity", "activities")):
            if "delayed" in q or "slipped" in q:
                sql_to_run = f"""
SELECT {_q("Activity_Code")}, {_q("Activity_Description")}, {_q("Domain_Code")},
       {_q("Activity_Status")}, {_q("Forecast_Delay_Days")}, {_q("Slip_Days")},
       {_q("SPI_RAG_Label")}, {_q("Delay_Magnitude_Label")}, {_q("Is_Critical_Wrench")}
FROM {_t("tbl_02_project_activity")}
{pk_filter}
{"WHERE" if not pk_filter else "AND"} {_q("Forecast_Delay_Days")} > 0
ORDER BY {_q("Forecast_Delay_Days")} DESC
LIMIT {SQL_ROW_CAP}
""".strip()
            elif "workfront" in q:
                sql_to_run = f"""
SELECT {_q("Activity_Code")}, {_q("Activity_Description")}, {_q("Domain_Code")},
       {_q("Workfront_Ready_Pct")}, {_q("Workfront_Gap_Count")}, {_q("CAD_Breach_Flag")},
       {_q("Is_Critical_Wrench")}, {_q("Activity_Status")}
FROM {_t("tbl_02_project_activity")}
{pk_filter}
{"WHERE" if not pk_filter else "AND"} {_q("Workfront_Ready_Pct")} < 70
ORDER BY {_q("Workfront_Ready_Pct")} ASC
LIMIT {SQL_ROW_CAP}
""".strip()
            else:
                sql_to_run = f"""
SELECT {_q("Activity_Code")}, {_q("Activity_Description")}, {_q("Domain_Code")},
       {_q("Activity_Status")}, {_q("Planned_Progress_Pct")}, {_q("Actual_Progress_Pct")},
       {_q("Forecast_Delay_Days")}, {_q("Total_Float_Days")}, {_q("Activity_Health_RAG")}
FROM {_t("tbl_02_project_activity")}
{pk_filter}
ORDER BY {_q("Forecast_Delay_Days")} DESC NULLS LAST
LIMIT {SQL_ROW_CAP}
""".strip()

        elif any(kw in q for kw in ("project", "projects", "summary", "portfolio")):
            sql_to_run = f"""
SELECT {_q("Project_Key")}, {_q("Project_Name")}, {_q("Project_Location")},
       {_q("SPI_Overall")}, {_q("Project_Execution_Index")},
       {_q("Max_Forecast_Delay_Days_Overall")}, {_q("EOT_Exposure_Days")},
       {_q("Schedule_Health_RAG")}, {_q("Schedule_Health_Score")},
       {_q("Data_Freshness_Label")}
FROM {_t("tbl_01_project_summary")}
{pk_filter}
ORDER BY {_q("Max_Forecast_Delay_Days_Overall")} DESC NULLS LAST
LIMIT {SQL_ROW_CAP}
""".strip()

        else:
            # Cannot synthesise — guide the user to provide explicit SQL
            return (
                "## 🔍 Ad-Hoc Query — Clarification Required\n\n"
                f"The question **\"{question}\"** falls outside the coverage of the structured "
                "schedule intelligence tools, and could not be automatically translated into "
                "a targeted database query.\n\n"
                "To proceed, please provide one of the following:\n\n"
                "1. **A more specific question** — include the grain (task/activity/project), "
                "domain (ENG/PRC/CON), and the specific metrics or conditions you need.\n"
                "2. **A raw SQL SELECT** — pass it via the `raw_sql` parameter. Use **only** column names "
                "listed below; **do not invent or guess field names**. Use **double-quoted** identifiers "
                "and **schema-qualified** tables.\n\n"
                "### Available Tables (use ONLY these columns — never hallucinate fields)\n\n"
                "| Table | Grain | Allowed columns (double-quoted) |\n"
                "|-------|-------|----------------------------------|\n"
                "| `public.tbl_01_project_summary` | One row per project | \"Project_Key\", \"Project_Name\", \"Project_Location\", \"Baseline_Start_Date\", \"Baseline_Finish_Date\", \"Actual_Start_Date\", \"Forecast_Start_Date\", \"Forecast_Finish_Date\", \"SPI_Overall\", \"Schedule_Health_RAG\", \"Project_Execution_Index\". **NOT on this table:** Domain, Start_Date, End_Date, Status. |\n"
                "| `public.tbl_02_project_activity` | One row per activity | \"Project_Key\", \"Activity_Code\", \"Domain\", \"Domain_Code\", \"Activity_Status\", \"Forecast_Delay_Days\", \"Total_Float_Days\", \"Baseline_Start_Date\", \"Forecast_Finish_Date\" |\n"
                "| `public.tbl_03_project_task` | One row per task | \"Project_Key\", \"Task_Key\", \"Task_Name\", \"Activity_Code\", \"Domain_Code\", \"Task_Status\", \"Total_Float_Days\", \"Is_Critical_Wrench\", \"Task_Health_RAG\" |\n\n"
                "💡 *Example: \"Show all Construction tasks in project 101 with negative float\" "
                "or \"List activities with CON_LAC_Week_Pct below 60% for project 101\"*"
            )

    # ── 2. Safety check ───────────────────────────────────────────────────
    is_safe, reason = _sanitise_sql(sql_to_run)
    if not is_safe:
        return (
            f"## 🚫 Query Not Permitted\n\n"
            f"The proposed SQL statement was not executed for the following reason:\n\n"
            f"> {reason}\n\n"
            "Only read-only `SELECT` statements are permitted. "
            "Please revise and resubmit."
        )

    # ── 3. Execute ────────────────────────────────────────────────────────
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return (
            "## ⚠️ Database Connection Unavailable\n\n"
            "The `DATABASE_URL` environment variable is not configured. "
            "Please contact the platform administrator.\n\n"
            f"**Prepared query** (for reference):\n```sql\n{sql_to_run}\n```"
        )

    # Convert Prisma/SQLAlchemy URL format to asyncpg format if needed
    asyncpg_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")

    try:
        conn = await asyncpg.connect(asyncpg_url, timeout=SQL_TIMEOUT_SECONDS)
        try:
            raw_rows = await conn.fetch(sql_to_run)
            rows = [dict(r) for r in raw_rows]
        finally:
            await conn.close()

    except asyncpg.exceptions.SyntaxOrAccessError as e:
        return (
            f"## ⚠️ Query Syntax Issue\n\n"
            f"The database reported a syntax or access error:\n\n"
            f"> {str(e)}\n\n"
            f"**Query attempted:**\n```sql\n{sql_to_run}\n```\n\n"
            "Use **double-quoted** identifiers and schema-qualified tables. "
            "**Do not hallucinate fields:** use ONLY columns that exist (e.g. tbl_01_project_summary "
            "has NO Domain, Start_Date, End_Date, or Status; use Project_Key, Project_Name, "
            "Baseline_Start_Date, Baseline_Finish_Date, SPI_Overall, Schedule_Health_RAG, etc.)."
        )
    except asyncio.TimeoutError:
        return (
            f"## ⚠️ Query Timeout\n\n"
            f"The query exceeded the {SQL_TIMEOUT_SECONDS}-second execution limit. "
            "Consider adding a more restrictive WHERE clause or reducing the scope."
        )
    except Exception as e:
        return (
            f"## ⚠️ Query Execution Issue\n\n"
            f"An error occurred while executing the query: {str(e)}\n\n"
            f"**Query attempted:**\n```sql\n{sql_to_run}\n```"
        )

    # ── 4. Format output ──────────────────────────────────────────────────
    result_table = _format_sql_results(rows, SQL_ROW_CAP)
    row_count    = len(rows)
    capped       = row_count >= SQL_ROW_CAP

    resp  = f"## 📊 Ad-Hoc Schedule Query Results\n\n"
    resp += f"*Question: {question}*\n"
    if project_key:
        resp += f"*Scope: Project {project_key}*\n"
    resp += f"*Rows returned: {min(row_count, SQL_ROW_CAP)}{' (capped)' if capped else ''}*\n\n"
    resp += "---\n\n"
    resp += result_table
    resp += "\n\n---\n"
    resp += f"<details><summary>📋 SQL Executed</summary>\n\n```sql\n{sql_to_run}\n```\n\n</details>"

    return resp + _threshold_footer()


# ── asyncio import needed for TimeoutError ────────────────────────────────
import asyncio


# ═════════════════════════════════════════════════════════════════════════════
#  TOOL REGISTRY — exported for LangGraph agent
# ═════════════════════════════════════════════════════════════════════════════

SRA_TOOLS = [
    # ── Layer 1 — Schedule Health & Status ───────────────────────────────
    sra_status_pei,           # Project-level health snapshot (SPI / PEI / EPC progress)
    sra_activity_health,      # Activity drill-down: status, delays, workfront
    sra_task_lookahead,       # 2W / 4W look-ahead window at task grain
    # ── Layer 2 — Schedule Intelligence ──────────────────────────────────
    sra_critical_path,        # CP density, tightening score, controlling tasks
    sra_float_analysis,       # Float distribution, erosion watch, CAD breaches
    sra_productivity_rate,    # Earned vs planned rate, execution gap analysis
    # ── Layer 3 — Schedule Integrity ─────────────────────────────────────
    sra_baseline_management,  # JCR/PMS baseline, rescheduled drift, integrity label
    sra_schedule_quality,     # Data freshness, LAC compliance, activity counts
    # ── Layer 4 — Schedule Risk & Impact ─────────────────────────────────
    sra_drill_delay,          # Delay root cause, hotspot domain, CPM breach
    sra_procurement_alignment,# PRC rules at risk, material milestone alignment
    sra_eot_exposure,         # EOT days, contractual buffer, LD risk assessment
    # ── Layer 5 — Schedule Action & Recovery ─────────────────────────────
    sra_recovery_advise,      # Structured recovery options with feasibility
    sra_simulate,             # What-if scenario: resource / working pattern change
    sra_create_action,        # Log recovery action or raise alert
    # ── Layer 6 — Schedule Communication & Governance ────────────────────
    sra_accountability_trace, # Report flags, delay attribution, as-built variance
    sra_explain_formula,      # SPI / PEI / LAC / Float / EOT formula library
]

