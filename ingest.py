"""
Ingest Script for SRA Dataset
Loads sra_single_dataset.csv into PostgreSQL sratable
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from prisma import Prisma


def parse_date(date_str: str) -> datetime:
    """Parse date string in M/D/YYYY format to datetime"""
    if not date_str:
        return datetime.now()
    try:
        return datetime.strptime(date_str, "%m/%d/%Y")
    except ValueError:
        # Try alternative formats
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return datetime.now()


def parse_float(value: str) -> float:
    """Parse float value, return 0.0 if empty or invalid"""
    if not value or value.strip() == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_int(value: str) -> int:
    """Parse int value, return 0 if empty or invalid"""
    if not value or value.strip() == "":
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def parse_nullable_string(value: str) -> str | None:
    """Parse string, return None if 'None' or empty"""
    if not value or value.strip() == "" or value.lower() == "none":
        return None
    return value.strip()


def parse_nullable_date(date_str: str) -> datetime | None:
    """Parse date string, return None if 'NULL', 'None', or empty"""
    if not date_str or date_str.strip() == "" or date_str.strip().upper() == "NULL" or date_str.strip().lower() == "none":
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except ValueError:
            try:
                return datetime.strptime(date_str.strip(), "%d:%M.%S")
            except ValueError:
                return None


def parse_nullable_float(value: str) -> float | None:
    """Parse float value, return None if empty or invalid"""
    if not value or value.strip() == "" or value.strip().upper() == "NULL" or value.strip().lower() == "none":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_nullable_int(value: str) -> int | None:
    """Parse int value, return None if empty or invalid"""
    if not value or value.strip() == "" or value.strip().upper() == "NULL" or value.strip().lower() == "none":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_bool(value: str) -> bool | None:
    """Parse boolean value from various string representations"""
    if not value or value.strip() == "" or value.strip().upper() == "NULL" or value.strip().lower() == "none":
        return None
    v = value.strip().lower()
    if v in ("true", "yes", "1", "y"):
        return True
    if v in ("false", "no", "0", "n"):
        return False
    return None


async def ingest_csv(csv_path: str, batch_size: int = 100):
    """
    Ingest CSV data into PostgreSQL sratable.
    
    Args:
        csv_path: Path to the CSV file
        batch_size: Number of records to insert per batch
    """
    prisma = Prisma()
    await prisma.connect()
    
    print(f"📂 Reading CSV from: {csv_path}")
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ File not found: {csv_path}")
        await prisma.disconnect()
        return
    
    records = []
    total_inserted = 0
    
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            record = {
                "projectId": row.get("project_id", ""),
                "date": parse_date(row.get("date", "")),
                "projectName": row.get("project_name", ""),
                "plannedFinishDate": parse_date(row.get("planned_finish_date", "")),
                "forecastFinishDate": parse_date(row.get("forecast_finish_date", "")),
                "plannedValueAmount": parse_float(row.get("planned_value_amount", "0")),
                "earnedValueAmount": parse_float(row.get("earned_value_amount", "0")),
                "actualCostAmount": parse_float(row.get("actual_cost_amount", "0")),
                "spiValue": parse_float(row.get("spi_value", "0")),
                "cpiValue": parse_float(row.get("cpi_value", "0")),
                "billingReadinessPct": parse_float(row.get("billing_readiness_pct", "0")),
                "peiValue": parse_float(row.get("pei_value", "0")),
                "totalScopeQty": parse_float(row.get("total_scope_qty", "0")),
                "rowAvailableQty": parse_float(row.get("row_available_qty", "0")),
                "executedQty": parse_float(row.get("executed_qty", "0")),
                "executableProgressPct": parse_float(row.get("executable_progress_pct", "0")),
                "remainingScopeQty": parse_float(row.get("remaining_scope_qty", "0")),
                "requiredRateQty": parse_float(row.get("required_rate_qty", "0")),
                "maxAchievedRateQty": parse_float(row.get("max_achieved_rate_qty", "0")),
                "requiredRateFeasibilityPct": parse_float(row.get("required_rate_feasibility_pct", "0")),
                "criticalDelayDays": parse_int(row.get("critical_delay_days", "0")),
                "topDelayOwnerCategory": parse_nullable_string(row.get("top_delay_owner_category", "")),
                "lookaheadPlannedCountWeek": parse_int(row.get("lookahead_planned_count_week", "0")),
                "lookaheadCompletedCountWeek": parse_int(row.get("lookahead_completed_count_week", "0")),
                "lookaheadCompliancePct": parse_float(row.get("lookahead_compliance_pct", "0")),
                "criticalDensityPct": parse_float(row.get("critical_density_pct", "0")),
            }
            records.append(record)
            
            # Insert in batches
            if len(records) >= batch_size:
                await prisma.sratable.create_many(data=records)
                total_inserted += len(records)
                print(f"✅ Inserted {total_inserted} records...")
                records = []
    
    # Insert remaining records
    if records:
        await prisma.sratable.create_many(data=records)
        total_inserted += len(records)
    
    print(f"🎉 Ingestion complete! Total records inserted: {total_inserted}")
    
    # Verify count
    count = await prisma.sratable.count()
    print(f"📊 Total records in sratable: {count}")
    
    await prisma.disconnect()


async def clear_table():
    """Clear all records from sratable"""
    prisma = Prisma()
    await prisma.connect()
    
    deleted = await prisma.sratable.delete_many()
    print(f"🗑️ Deleted {deleted} records from sratable")
    
    await prisma.disconnect()


async def ingest_activity_csv(csv_path: str, batch_size: int = 100):
    """
    Ingest activity-level CSV data into PostgreSQL sra_activity_table.
    
    Args:
        csv_path: Path to the CSV file
        batch_size: Number of records to insert per batch
    """
    prisma = Prisma()
    await prisma.connect()
    
    print(f"📂 Reading Activity CSV from: {csv_path}")
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ File not found: {csv_path}")
        await prisma.disconnect()
        return
    
    records = []
    total_inserted = 0
    
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            record = {
                "date": parse_date(row.get("date", "")),
                "projectId": row.get("project_id", ""),
                "projectName": row.get("project_name", ""),
                "activityId": row.get("activity_id", ""),
                "activityName": row.get("activity_name", ""),
                "isCriticalFlag": parse_int(row.get("is_critical_flag", "0")),
                "plannedFinishDate": parse_date(row.get("planned_finish_date", "")),
                "forecastFinishDate": parse_date(row.get("forecast_finish_date", "")),
                "plannedStartDate": parse_date(row.get("planned_start_date", "")),
                "plannedFinishActivityDate": parse_date(row.get("planned_finish_activity_date", "")),
                "plannedValueAmount": parse_float(row.get("planned_value_amount", "0")),
                "earnedValueAmount": parse_float(row.get("earned_value_amount", "0")),
                "totalScopeQty": parse_float(row.get("total_scope_qty", "0")),
                "rowAvailableQty": parse_float(row.get("row_available_qty", "0")),
                "executedQty": parse_float(row.get("executed_qty", "0")),
                "totalFloatDays": parse_float(row.get("total_float_days", "0")),
                "cpiValue": parse_float(row.get("cpi_value", "0")),
                "billingReadinessPct": parse_float(row.get("billing_readiness_pct", "0")),
                "riskProfile": parse_float(row.get("risk_profile", "0")),
                "spiValue": parse_float(row.get("spi_value", "0")),
                "peiValue": parse_float(row.get("pei_value", "0")),
                "forecastDelayDays": parse_int(row.get("forecast_delay_days", "0")),
                "workfrontReadinessPct": parse_float(row.get("workfront_readiness_pct", "0")),
                "avgFloat": parse_float(row.get("avg_float", "0")),
            }
            records.append(record)
            
            # Insert in batches
            if len(records) >= batch_size:
                await prisma.sraactivitytable.create_many(data=records)
                total_inserted += len(records)
                print(f"✅ Inserted {total_inserted} activity records...")
                records = []
    
    # Insert remaining records
    if records:
        await prisma.sraactivitytable.create_many(data=records)
        total_inserted += len(records)
    
    print(f"🎉 Activity ingestion complete! Total records inserted: {total_inserted}")
    
    # Verify count
    count = await prisma.sraactivitytable.count()
    print(f"📊 Total records in sra_activity_table: {count}")
    
    await prisma.disconnect()


async def clear_activity_table():
    """Clear all records from sra_activity_table"""
    prisma = Prisma()
    await prisma.connect()
    
    deleted = await prisma.sraactivitytable.delete_many()
    print(f"🗑️ Deleted {deleted} records from sra_activity_table")
    
    await prisma.disconnect()


async def ingest_project_summary_csv(csv_path: str, batch_size: int = 100):
    """
    Ingest tbl_01_Project_summary.csv into PostgreSQL tbl_01_project_summary table.
    
    Args:
        csv_path: Path to the CSV file
        batch_size: Number of records to insert per batch
    """
    prisma = Prisma()
    await prisma.connect()
    
    print(f"📂 Reading Project Summary CSV from: {csv_path}")
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ File not found: {csv_path}")
        await prisma.disconnect()
        return
    
    records = []
    total_inserted = 0
    skipped = 0
    
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                record = {
                    # Identity
                    "projectKey": parse_int(row.get("Project_Key", row.get("\ufeffProject_Key", "0"))),
                    "projectId": row.get("Project_ID", ""),
                    "projectDescription": row.get("Project_Name", ""),
                    "projectLocation": row.get("Project_Location", ""),

                    # Dates
                    "baselineStartDate": parse_date(row.get("Baseline_Start_Date", "")),
                    "baselineFinishDate": parse_date(row.get("Baseline_Finish_Date", "")),
                    "forecastStartDate": parse_nullable_date(row.get("Forecast_Start_Date", "")),
                    "forecastFinishDate": parse_nullable_date(row.get("Forecast_Finish_Date", "")),
                    "actualStartDate": parse_nullable_date(row.get("Actual_Start_Date", "")),
                    "contractualEndDate": parse_date(row.get("Contractual_Completion_Date", "")),

                    # Duration
                    "baselineDurationDays": parse_int(row.get("Baseline_Duration_Days", "0")),
                    "forecastDurationDays": parse_int(row.get("Forecast_Duration_Days", "0")),
                    "adjustedTotalDurationDays": parse_int(row.get("Adjusted_Total_Duration_Days", "0")),

                    # Slip / variance
                    "slipDays": parse_int(row.get("Slip_Days", "0")),
                    "scheduleVarianceDays": parse_int(row.get("Schedule_Variance_Days", "0")),

                    # PEI
                    "projectExecutionIndex": parse_float(row.get("Project_Execution_Index", "0")),

                    # EOT
                    "eotExposureDays": parse_int(row.get("EOT_Exposure_Days", "0")),

                    # SPI per E/P/C
                    "spiOverall": parse_float(row.get("SPI_Overall", "0")),
                    "spiEngineering": parse_float(row.get("SPI_Engineering", "0")),
                    "spiProcurement": parse_float(row.get("SPI_Procurement", "0")),
                    "spiConstruction": parse_float(row.get("SPI_Construction", "0")),

                    # Cumulative progress — Overall
                    "cumulativePlannedOverall": parse_float(row.get("Cumulative_Planned_Pct_Overall", "0")),
                    "cumulativeActualOverall": parse_float(row.get("Cumulative_Actual_Pct_Overall", "0")),
                    "cumulativeBacklogOverall": parse_float(row.get("Cumulative_Backlog_Pct_Overall", "0")),

                    # Cumulative progress — Engineering
                    "cumulativePlannedEngineering": parse_float(row.get("Cumulative_Planned_Pct_Engineering", "0")),
                    "cumulativeActualEngineering": parse_float(row.get("Cumulative_Actual_Pct_Engineering", "0")),
                    "cumulativeBacklogEngineering": parse_float(row.get("Cumulative_Backlog_Pct_Engineering", "0")),

                    # Cumulative progress — Procurement
                    "cumulativePlannedProcurement": parse_float(row.get("Cumulative_Planned_Pct_Procurement", "0")),
                    "cumulativeActualProcurement": parse_float(row.get("Cumulative_Actual_Pct_Procurement", "0")),
                    "cumulativeBacklogProcurement": parse_float(row.get("Cumulative_Backlog_Pct_Procurement", "0")),

                    # Cumulative progress — Construction
                    "cumulativePlannedConstruction": parse_float(row.get("Cumulative_Planned_Pct_Construction", "0")),
                    "cumulativeActualConstruction": parse_float(row.get("Cumulative_Actual_Pct_Construction", "0")),
                    "cumulativeBacklogConstruction": parse_float(row.get("Cumulative_Backlog_Pct_Construction", "0")),

                    # Max forecast delay per E/P/C
                    "maxForecastDelayDaysOverall": parse_int(row.get("Max_Forecast_Delay_Days_Overall", "0")),
                    "maxForecastDelayDaysEngineering": parse_int(row.get("Max_Forecast_Delay_Days_Engineering", "0")),
                    "maxForecastDelayDaysProcurement": parse_int(row.get("Max_Forecast_Delay_Days_Procurement", "0")),
                    "maxForecastDelayDaysConstruction": parse_int(row.get("Max_Forecast_Delay_Days_Construction", "0")),

                    # Float stats
                    "floatTotalTaskCount": parse_int(row.get("Float_Total_Task_Count", "0")),
                    "floatNegativeTaskCount": parse_int(row.get("Float_Negative_Task_Count", "0")),
                    "floatZeroTaskCount": parse_int(row.get("Float_Zero_Task_Count", "0")),
                    "floatNearCriticalCount": parse_int(row.get("Float_Near_Critical_Task_Count", "0")),
                    "floatPositiveTaskCount": parse_int(row.get("Float_Positive_Task_Count", "0")),
                    "floatAvgDays": parse_float(row.get("Float_Avg_Days", "0")),
                    "floatMinDays": parse_int(row.get("Float_Min_Days", "0")),
                    "floatAtRiskPct": parse_float(row.get("Float_At_Risk_Pct", "0")),

                    # CAD (Critical Activity Density)
                    "cadOverallPct": parse_float(row.get("CAD_Overall_Pct", "0")),
                    "cadEngineeringPct": parse_float(row.get("CAD_Engineering_Pct", "0")),
                    "cadProcurementPct": parse_float(row.get("CAD_Procurement_Pct", "0")),
                    "cadConstructionPct": parse_float(row.get("CAD_Construction_Pct", "0")),

                    # WR (Workfront Readiness)
                    "wrOverallPct": parse_float(row.get("Workfront_Readiness_Overall_Pct", "0")),
                    "wrEngineeringPct": parse_float(row.get("Workfront_Readiness_Engineering_Pct", "0")),
                    "wrProcurementPct": parse_float(row.get("Workfront_Readiness_Procurement_Pct", "0")),
                    "wrConstructionPct": parse_float(row.get("Workfront_Readiness_Construction_Pct", "0")),

                    # EP (Executable Progress)
                    "epOverallPct": parse_float(row.get("Executable_Progress_Overall_Pct", "0")),
                    "epEngineeringPct": parse_float(row.get("Executable_Progress_Engineering_Pct", "0")),
                    "epProcurementPct": parse_float(row.get("Executable_Progress_Procurement_Pct", "0")),
                    "epConstructionPct": parse_float(row.get("Executable_Progress_Construction_Pct", "0")),

                    # Contribution to project
                    "contributionOverallPct": parse_float(row.get("Contribution_To_Project_Overall_Pct", "0")),
                    "contributionEngineeringPct": parse_float(row.get("Contribution_To_Project_Engineering_Pct", "0")),
                    "contributionProcurementPct": parse_float(row.get("Contribution_To_Project_Procurement_Pct", "0")),
                    "contributionConstructionPct": parse_float(row.get("Contribution_To_Project_Construction_Pct", "0")),

                    # Activity counts
                    "activitiesTotalCount": parse_int(row.get("Activities_Total_Count", "0")),
                    "activitiesCompleteCount": parse_int(row.get("Activities_Complete_Count", "0")),
                    "activitiesInProgressCount": parse_int(row.get("Activities_In_Progress_Count", "0")),
                    "activitiesOverdueCount": parse_int(row.get("Activities_Overdue_Count", "0")),
                    "activitiesNotYetDueCount": parse_int(row.get("Activities_Not_Yet_Due_Count", "0")),

                    # Construction LAC
                    "conLacWeekPct": parse_float(row.get("CON_LAC_Week_Pct", "0")),
                    "conLacMonthPct": parse_float(row.get("CON_LAC_Month_Pct", "0")),
                    "conLacCompletedRules": parse_int(row.get("CON_LAC_Completed_Rules", "0")),
                    "conLacOverdueCount": parse_int(row.get("CON_LAC_Overdue_Count", "0")),
                    "conLacAtRisk7DayCount": parse_int(row.get("CON_LAC_At_Risk_7Day_Count", "0")),
                    "conLacAtRisk30DayCount": parse_int(row.get("CON_LAC_At_Risk_30Day_Count", "0")),
                    "conLacPendingCount": parse_int(row.get("CON_LAC_Pending_Count", "0")),

                    # Procurement LAC
                    "prcLacWeekPct": parse_float(row.get("PRC_LAC_Week_Pct", "0")),
                    "prcLacMonthPct": parse_float(row.get("PRC_LAC_Month_Pct", "0")),
                    "prcLacCompletedRules": parse_int(row.get("PRC_LAC_Completed_Rules", "0")),
                    "prcLacOverdueCount": parse_int(row.get("PRC_LAC_Overdue_Count", "0")),
                }
                records.append(record)
            except Exception as e:
                skipped += 1
                print(f"⚠️ Skipped row due to error: {e}")
                continue
            
            # Insert in batches
            if len(records) >= batch_size:
                await prisma.tbl01projectsummary.create_many(data=records)
                total_inserted += len(records)
                print(f"✅ Inserted {total_inserted} project summary records...")
                records = []
    
    # Insert remaining records
    if records:
        await prisma.tbl01projectsummary.create_many(data=records)
        total_inserted += len(records)
    
    print(f"🎉 Project summary ingestion complete! Total records inserted: {total_inserted}")
    if skipped > 0:
        print(f"⚠️ Skipped {skipped} rows due to errors")
    
    # Verify count
    count = await prisma.tbl01projectsummary.count()
    print(f"📊 Total records in tbl_01_project_summary: {count}")
    
    await prisma.disconnect()


async def ingest_project_activity_csv(csv_path: str, batch_size: int = 100):
    """
    Ingest tbl_02_ProjectActivity.csv into PostgreSQL tbl_project_activity table.
    
    Args:
        csv_path: Path to the CSV file
        batch_size: Number of records to insert per batch
    """
    prisma = Prisma()
    await prisma.connect()
    
    print(f"📂 Reading Project Activity CSV from: {csv_path}")
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"❌ File not found: {csv_path}")
        await prisma.disconnect()
        return
    
    records = []
    total_inserted = 0
    skipped = 0
    
    # Use current date/time as load metadata since CSV doesn't include it
    load_date = datetime.now()
    
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row_num, row in enumerate(reader, start=1):
            try:
                record = {
                    # Identity
                    "projectKey": parse_int(row.get("Project_Key", row.get("\ufeffProject_Key", "0"))),
                    "activityCode": row.get("Activity_Code", "").strip(),
                    "activityDescription": row.get("Activity_Description", "").strip(),
                    "domain": parse_nullable_string(row.get("Domain", "")),
                    "domainCode": parse_nullable_string(row.get("Domain_Code", "")),
                    "customScurve": parse_nullable_string(row.get("SCurve", "")),

                    # Dates
                    "baselineStartDate": parse_nullable_date(row.get("Baseline_Start_Date", "")),
                    "baselineFinishDate": parse_nullable_date(row.get("Baseline_Finish_Date", "")),
                    "forecastStartDate": parse_nullable_date(row.get("Forecast_Start_Date", "")),
                    "forecastFinishDate": parse_nullable_date(row.get("Forecast_Finish_Date", "")),
                    "actualStartDate": parse_nullable_date(row.get("Actual_Start_Date", "")),
                    "actualFinishDate": parse_nullable_date(row.get("Actual_Finish_Date", "")),

                    # Duration
                    "baselineDurationDays": parse_nullable_int(row.get("Baseline_Duration_Days", "")),
                    "forecastDurationDays": parse_nullable_int(row.get("Forecast_Duration_Days", "")),
                    "adjustedTotalDurationDays": parse_nullable_int(row.get("Adjusted_Total_Duration_Days", "")),
                    "slipDays": parse_nullable_int(row.get("Slip_Days", "")),
                    "scheduleVarianceDays": parse_nullable_int(row.get("Schedule_Variance_Days", "")),

                    # Status
                    "activityStatus": parse_nullable_string(row.get("Activity_Status", "")),

                    # Float & Critical
                    "totalFloat": parse_nullable_float(row.get("Total_Float_Days", "")),
                    "isCriticalWrench": parse_bool(row.get("Is_Critical_Wrench", "")),
                    "projectMinFloatDays": parse_nullable_int(row.get("Project_Min_Float_Days", "")),
                    "isControllingFloat": parse_bool(row.get("Is_Controlling_Float_Activity", "")),
                    "floatHealthStatus": parse_nullable_string(row.get("Float_Health_Status", "")),
                    "floatHealthSortOrder": parse_nullable_int(row.get("Float_Health_Sort_Order", "")),

                    # Progress
                    "criticalActivityDensityPct": parse_nullable_float(row.get("Critical_Activity_Density_Pct", "")),
                    "workfrontReadyPct": parse_nullable_float(row.get("Workfront_Ready_Pct", "")),
                    "plannedProgressPct": parse_nullable_float(row.get("Planned_Progress_Pct", "")),
                    "actualProgressPct": parse_nullable_float(row.get("Actual_Progress_Pct", "")),
                    "forecastProgressPct": parse_nullable_float(row.get("Forecast_Progress_Pct", "")),
                    "progressVariancePct": parse_nullable_float(row.get("Progress_Variance_Pct", "")),

                    # Quantities
                    "plannedQuantity": parse_nullable_float(row.get("Planned_Quantity", "")),
                    "earnedQuantity": parse_nullable_float(row.get("Earned_Quantity", "")),
                    "executableProgressPct": parse_nullable_float(row.get("Executable_Progress_Pct", "")),

                    # Contribution & SPI
                    "contributionToProjectPct": parse_nullable_float(row.get("Contribution_To_Project_Pct", "")),
                    "activitySpi": parse_nullable_float(row.get("Activity_SPI", "")),

                    # Forecast delay
                    "forecastDelayDays": parse_nullable_int(row.get("Forecast_Delay_Days", "")),

                    # Cumulative progress
                    "cumulativePlannedProgress": parse_nullable_float(row.get("Cumulative_Planned_Progress", "")),
                    "cumulativeActualProgress": parse_nullable_float(row.get("Cumulative_Actual_Progress", "")),
                    "cumulativeBacklogPct": parse_nullable_float(row.get("Cumulative_Backlog_Pct", "")),
                    "domainSpi": parse_nullable_float(row.get("Domain_SPI", "")),

                    # Construction LAC rules
                    "conTotalRules": parse_nullable_int(row.get("CON_Total_Rules", "")),
                    "conCompletedRules": parse_nullable_int(row.get("CON_Completed_Rules", "")),
                    "conOverdueRules": parse_nullable_int(row.get("CON_Overdue_Rules", "")),
                    "conAtRiskRules7Day": parse_nullable_int(row.get("CON_At_Risk_Rules_7Day", "")),
                    "conAtRiskRules30Day": parse_nullable_int(row.get("CON_At_Risk_Rules_30Day", "")),
                    "conPendingRules": parse_nullable_int(row.get("CON_Pending_Rules", "")),
                    "conLacWeekPct": parse_nullable_float(row.get("CON_LAC_Week_Pct", "")),
                    "conLacMonthPct": parse_nullable_float(row.get("CON_LAC_Month_Pct", "")),

                    # Procurement LAC rules
                    "prcTotalRules": parse_nullable_int(row.get("PRC_Total_Rules", "")),
                    "prcCompletedRules": parse_nullable_int(row.get("PRC_Completed_Rules", "")),
                    "prcOverdueRules": parse_nullable_int(row.get("PRC_Overdue_Rules", "")),
                    "prcAtRiskRules7Day": parse_nullable_int(row.get("PRC_At_Risk_Rules_7Day", "")),
                    "prcAtRiskRules30Day": parse_nullable_int(row.get("PRC_At_Risk_Rules_30Day", "")),
                    "prcPendingRules": parse_nullable_int(row.get("PRC_Pending_Rules", "")),
                    "prcLacWeekPct": parse_nullable_float(row.get("PRC_LAC_Week_Pct", "")),
                    "prcLacMonthPct": parse_nullable_float(row.get("PRC_LAC_Month_Pct", "")),
                }
                records.append(record)
            except Exception as e:
                skipped += 1
                print(f"⚠️ Skipped row {row_num} due to error: {e}")
                continue
            
            # Insert in batches
            if len(records) >= batch_size:
                await prisma.tbl02projectactivity.create_many(data=records)
                total_inserted += len(records)
                print(f"✅ Inserted {total_inserted} project activity records...")
                records = []
    
    # Insert remaining records
    if records:
        await prisma.tbl02projectactivity.create_many(data=records)
        total_inserted += len(records)
    
    print(f"🎉 Project activity ingestion complete! Total records inserted: {total_inserted}")
    if skipped > 0:
        print(f"⚠️ Skipped {skipped} rows due to errors")
    
    # Verify count
    count = await prisma.tbl02projectactivity.count()
    print(f"📊 Total records in tbl_project_activity: {count}")
    
    await prisma.disconnect()


async def clear_project_summary_table():
    """Clear all records from tbl_01_project_summary"""
    prisma = Prisma()
    await prisma.connect()
    
    deleted = await prisma.tbl01projectsummary.delete_many()
    print(f"🗑️ Deleted {deleted} records from tbl_01_project_summary")
    
    await prisma.disconnect()


async def clear_project_activity_table():
    """Clear all records from tbl_project_activity"""
    prisma = Prisma()
    await prisma.connect()
    
    deleted = await prisma.tbl02projectactivity.delete_many()
    print(f"🗑️ Deleted {deleted} records from tbl_project_activity")
    
    await prisma.disconnect()


if __name__ == "__main__":
    import sys
    
    project_summary_csv_path = "samples/tbl_01_Project_summary.csv"
    project_activity_csv_path = "samples/tbl_02_ProjectActivity.csv"
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--clear-summary":
            print("🗑️ Clearing project summary table...")
            asyncio.run(clear_project_summary_table())
        elif cmd == "--clear-activity":
            print("🗑️ Clearing project activity table...")
            asyncio.run(clear_project_activity_table())
        elif cmd == "--clear-all":
            print("🗑️ Clearing all tables...")
            asyncio.run(clear_project_summary_table())
            asyncio.run(clear_project_activity_table())
        elif cmd == "--summary":
            path = sys.argv[2] if len(sys.argv) > 2 else project_summary_csv_path
            asyncio.run(ingest_project_summary_csv(path))
        elif cmd == "--activity":
            path = sys.argv[2] if len(sys.argv) > 2 else project_activity_csv_path
            asyncio.run(ingest_project_activity_csv(path))
        elif cmd == "--all":
            summary_path = sys.argv[2] if len(sys.argv) > 2 else project_summary_csv_path
            activity_path = sys.argv[3] if len(sys.argv) > 3 else project_activity_csv_path
            asyncio.run(ingest_project_summary_csv(summary_path))
            asyncio.run(ingest_project_activity_csv(activity_path))
        else:
            print("Usage: python ingest.py [--summary|--activity|--all|--clear-summary|--clear-activity|--clear-all]")
    else:
        # Default: ingest both
        asyncio.run(ingest_project_summary_csv(project_summary_csv_path))
        asyncio.run(ingest_project_activity_csv(project_activity_csv_path))
