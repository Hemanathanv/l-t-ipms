"""
Bulk test and debug script for SRA tools and agent.
Runs tools (and optionally the full agent), captures tool output and insights,
and writes results to an Excel sheet.

Usage:
  python -m agent.bulk_test_tools                    # tool-only mode, default project 101
  python -m agent.bulk_test_tools --agent            # also run agent with NL queries (tool + insight)
  python -m agent.bulk_test_tools --output report.xlsx
  python -m agent.bulk_test_tools --project 202     # use project_key 202

Requires: openpyxl (pip install openpyxl)
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
from typing import Any

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from db import get_prisma, close_prisma
from agent.tools import (
    SRA_TOOLS,
    sra_status_pei,
    sra_activity_health,
    sra_task_lookahead,
    sra_critical_path,
    sra_float_analysis,
    sra_productivity_rate,
    sra_baseline_management,
    sra_schedule_quality,
    sra_drill_delay,
    sra_procurement_alignment,
    sra_eot_exposure,
    sra_recovery_advise,
    sra_simulate,
    sra_create_action,
    sra_accountability_trace,
    sra_explain_formula,
    sra_sql_agent,
)

# Map tool name to tool instance for ainvoke
TOOL_BY_NAME = {t.name: t for t in SRA_TOOLS}

# ─── Tool-only test cases: (description, tool_name, kwargs) ─────────────────
TOOL_TEST_CASES = [
    ("PEI/status for project", "sra_status_pei", {"project_key": "101"}),
    ("Activity health", "sra_activity_health", {"project_key": "101"}),
    ("Task lookahead 2W", "sra_task_lookahead", {"project_key": "101", "window": "2W"}),
    ("Critical path", "sra_critical_path", {"project_key": "101"}),
    ("Float analysis", "sra_float_analysis", {"project_key": "101"}),
    ("Productivity rate", "sra_productivity_rate", {"project_key": "101"}),
    ("Baseline management", "sra_baseline_management", {"project_key": "101"}),
    ("Schedule quality", "sra_schedule_quality", {"project_key": "101"}),
    ("Drill delay", "sra_drill_delay", {"project_key": "101"}),
    ("Procurement alignment", "sra_procurement_alignment", {"project_key": "101"}),
    ("EOT exposure", "sra_eot_exposure", {"project_key": "101"}),
    ("Recovery advise", "sra_recovery_advise", {"project_key": "101", "resource_type": "labor"}),
    ("Simulate shuttering", "sra_simulate", {"project_key": "101", "resource_type": "shuttering_gang", "value_amount": 2}),
    ("Create action", "sra_create_action", {"project_key": "101", "action_choice": "Approve Option 1"}),
    ("Accountability trace", "sra_accountability_trace", {"project_key": "101"}),
    ("Explain SPI", "sra_explain_formula", {"project_key": "101", "metric": "SPI"}),
    ("SQL fallback (project list)", "sra_sql_agent", {"question": "List project key and name for first 5 projects", "project_key": "101"}),
]

# ─── Agent (full graph) test queries: natural language → we capture tool output + insight ───
AGENT_TEST_QUERIES = [
    "What is the schedule health of project 101?",
    "Why is project 101 delayed?",
    "How do we recover for project 101?",
    "Explain the SPI formula.",
]


def _truncate(text: str, max_len: int = 8000) -> str:
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""
    return text[:max_len] + "..." if len(text) > max_len else text


def _parse_agent_response(content: str) -> tuple[str, str]:
    """Split saved content into tool_output and insight by <!-- INSIGHT -->."""
    if not content:
        return "", ""
    marker = "\n\n<!-- INSIGHT -->\n\n"
    if marker in content:
        parts = content.split(marker, 1)
        return (parts[0].strip(), parts[1].strip() if len(parts) > 1 else "")
    return content.strip(), ""


async def run_tool_tests(project_key: str) -> list[dict]:
    """Run each tool with test kwargs; return list of result rows."""
    rows = []
    for desc, tool_name, kwargs in TOOL_TEST_CASES:
        # Override project_key if passed
        if project_key and "project_key" in kwargs:
            kwargs = {**kwargs, "project_key": project_key}
        tool = TOOL_BY_NAME.get(tool_name)
        if not tool:
            rows.append({
                "run_id": len(rows) + 1,
                "mode": "tool",
                "tool_or_query": tool_name,
                "input_summary": desc,
                "tool_output": "",
                "insight": "",
                "error": f"Tool not found: {tool_name}",
                "duration_sec": 0,
                "timestamp": datetime.now().isoformat(),
            })
            continue
        start = datetime.now()
        err_msg = ""
        out = ""
        try:
            out = await tool.ainvoke(kwargs)
            if isinstance(out, dict) and "output" in out:
                out = out.get("output", "")
            out = str(out) if out is not None else ""
        except Exception as e:
            err_msg = str(e)
        elapsed = (datetime.now() - start).total_seconds()
        rows.append({
            "run_id": len(rows) + 1,
            "mode": "tool",
            "tool_or_query": tool_name,
            "input_summary": desc,
            "tool_output": _truncate(out),
            "insight": "",
            "error": err_msg,
            "duration_sec": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
        })
    return rows


async def run_agent_tests(project_key: str) -> list[dict]:
    """Run full agent (graph) for each NL query; capture tool output and insight from state."""
    try:
        from agent.graph import create_agent
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    except ImportError as e:
        return [{
            "run_id": 1,
            "mode": "agent",
            "tool_or_query": "N/A",
            "input_summary": "Import graph",
            "tool_output": "",
            "insight": "",
            "error": str(e),
            "duration_sec": 0,
            "timestamp": datetime.now().isoformat(),
        }]

    rows = []
    agent = await create_agent(checkpointer=None)
    thread_prefix = f"bulk-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    for i, query in enumerate(AGENT_TEST_QUERIES):
        thread_id = f"{thread_prefix}-{i}"
        start = datetime.now()
        err_msg = ""
        tool_out = ""
        insight = ""
        try:
            context = (
                f"\n\n[CONTEXT]\nSelected Project: Project {project_key} ({project_key})\n"
                f"When calling tools, use project_id='{project_key}'.\n[/CONTEXT]"
            ) if project_key else ""
            user_message = HumanMessage(content=query + context)
            result = await agent.ainvoke(
                {"messages": [user_message], "thread_id": thread_id},
                config={"configurable": {"thread_id": thread_id}},
            )
            messages = result.get("messages", [])
            # Last ToolMessage = tool output; last AIMessage with content (no tool_calls) = insight
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage) and getattr(msg, "content", None):
                    tool_out = msg.content or ""
                    break
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and getattr(msg, "content", None) and not getattr(msg, "tool_calls", None):
                    insight = msg.content or ""
                    break
        except Exception as e:
            err_msg = str(e)
        elapsed = (datetime.now() - start).total_seconds()
        rows.append({
            "run_id": len(rows) + 1,
            "mode": "agent",
            "tool_or_query": _truncate(query, 200),
            "input_summary": query,
            "tool_output": _truncate(tool_out),
            "insight": _truncate(insight),
            "error": err_msg,
            "duration_sec": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
        })
    return rows


def write_excel(rows: list[dict], path: str) -> None:
    """Write result rows to Excel. Columns: run_id, mode, tool_or_query, input_summary, tool_output, insight, error, duration_sec, timestamp."""
    df = pd.DataFrame(rows)
    cols = ["run_id", "mode", "tool_or_query", "input_summary", "tool_output", "insight", "error", "duration_sec", "timestamp"]
    df = df[[c for c in cols if c in df.columns]]
    base, ext = os.path.splitext(path)
    try:
        df.to_excel(path, index=False, engine="openpyxl")
        print(f"Wrote {len(df)} rows to {path}")
    except Exception as e:
        csv_path = base + ".csv"
        df.to_csv(csv_path, index=False)
        print(f"Excel write failed ({e}); wrote CSV to {csv_path}")


async def main():
    parser = argparse.ArgumentParser(description="Bulk test SRA tools and optionally agent; output to Excel.")
    parser.add_argument("--output", "-o", default="agent_bulk_test_report.xlsx", help="Output Excel file path")
    parser.add_argument("--project", "-p", default="101", help="Project key for tool/agent tests")
    parser.add_argument("--agent", action="store_true", help="Also run full agent with NL queries (captures insight)")
    parser.add_argument("--tool-only", action="store_true", help="Only run tool tests (default if neither --agent nor --tool-only)")
    args = parser.parse_args()

    run_agent = args.agent
    run_tool = args.tool_only or not run_agent
    if not run_agent and not run_tool:
        run_tool = True

    print("Bulk test: DB connect...")
    await get_prisma()
    all_rows = []

    try:
        if run_tool:
            print("Running tool-only tests...")
            tool_rows = await run_tool_tests(args.project)
            all_rows.extend(tool_rows)
        if run_agent:
            print("Running agent (NL) tests for insight capture...")
            agent_rows = await run_agent_tests(args.project)
            all_rows.extend(agent_rows)
    finally:
        await close_prisma()

    if not all_rows:
        print("No results to write.")
        return
    for i, r in enumerate(all_rows, 1):
        r["run_id"] = i
    write_excel(all_rows, args.output)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
