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
    Ingest tbl_01_Project_summary.csv into PostgreSQL tbl_01_Project_summary table.
    
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
    
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            record = {
                "project_id": row.get("\ufeffProject_ID", ""),
                "projectKey": parse_int(row.get("Project_Key", "0")),
                "projectDescription": row.get("Project_Description", ""),
                "startDate": parse_nullable_date(row.get("start_date", "")),
                "endDate": parse_nullable_date(row.get("end_date", "")),
                "projectLocation": row.get("Project_Location", ""),
                "pei": parse_float(row.get("PEI", "0")),
                "spi": parse_float(row.get("SPI", "0")),
                "forecastDelayDays": parse_int(row.get("ForecastDelayDays", "0")),
                "computedDays": parse_int(row.get("ComputedDays", "0")),
                "extensionExposureDays": parse_int(row.get("ExtensionExposureDays", "0")),
                "workfrontPercentage": parse_float(row.get("Workfront_Percentage", "0")),
                "readyTask": parse_int(row.get("ReadyTask", "0")),
                "workfrontTotalTasks": parse_int(row.get("WorkfrontTotalTasks", "0")),
                "criticalPercentage": parse_float(row.get("Critical_Percentage", "0")),
                "criticalYesCount": parse_int(row.get("CriticalYes_Count", "0")),
                "criticalNoCount": parse_int(row.get("CriticalNo_Count", "0")),
                "criticalTotalTasks": parse_int(row.get("CriticalTotalTasks", "0")),
                "executedQuantity": parse_float(row.get("Executed_Quantity", "0")),
                "totalAvailableQuantity": parse_float(row.get("Total_Available_Quantity", "0")),
                "executableProgressPercent": parse_float(row.get("Executable_Progress_Percent", "0")),
                "tasksPlannedInLookAhead": parse_int(row.get("Tasks_Planned_In_LookAhead", "0")),
                "tasksCompletedLookAhead": parse_int(row.get("Tasks_Completed_LookAhead", "0")),
                "lookAheadCompliancePercent": parse_float(row.get("Look_Ahead_Compliance_Percent", "0")),
            }
            records.append(record)
            
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
    
    # Verify count
    count = await prisma.tbl01projectsummary.count()
    print(f"📊 Total records in tbl_01_Project_summary: {count}")
    
    await prisma.disconnect()


async def ingest_project_activity_csv(csv_path: str, batch_size: int = 100):
    """
    Ingest tbl_02_ProjectActivity.csv into PostgreSQL tbl_02_ProjectActivity table.
    
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
    
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            record = {
                "projectKey": parse_int(row.get("\ufeffProject_Key", "0")),
                "activityCode": row.get("Activity_Code", ""),
                "activityDescription": row.get("Activity_Description", ""),
                "workfrontPct": parse_float(row.get("Workfront_Pct", "0")),
                "readyTasks": parse_int(row.get("Ready_Tasks", "0")),
                "totalTasks": parse_int(row.get("TotalTasks", "0")),
                "criticalPercentage": parse_float(row.get("Critical_Percentage", "0")),
                "tasksPlannedInLookAhead": parse_int(row.get("Tasks_Planned_In_LookAhead", "0")),
                "tasksCompleted": parse_int(row.get("Tasks_Completed", "0")),
                "lookAheadCompliancePercent": parse_float(row.get("Look_Ahead_Compliance_Percent", "0")),
                "delayDays": parse_int(row.get("DelayDays", "0")),
                "computedDelay": parse_int(row.get("ComputedDelay", "0")),
                "taskActualStartDate": parse_nullable_date(row.get("Task_Actual_Start_Date", "")),
                "taskActualFinishDate": parse_nullable_date(row.get("Task_Actual_Finish_Date", "")),
                "taskForecastStartDate": parse_nullable_date(row.get("Task_Forecast_Start_Date", "")),
                "taskForecastFinishDate": parse_nullable_date(row.get("Task_Forecast_Finish_Date", "")),
                "taskPlanStartDate": parse_nullable_date(row.get("Task_Plan_Start_Date", "")),
                "taskPlanFinishDate": parse_nullable_date(row.get("Task_Plan_Finish_Date", "")),
                "taskKey": row.get("Task_Key", ""),
            }
            records.append(record)
            
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
    
    # Verify count
    count = await prisma.tbl02projectactivity.count()
    print(f"📊 Total records in tbl_02_ProjectActivity: {count}")
    
    await prisma.disconnect()


if __name__ == "__main__":
    import sys
    
    # Default CSV paths
    # csv_path = "samples/sra_single_dataset.csv"
    # activity_csv_path = "samples/sra_status_pei_activity_level_10projects_365days.csv"
    # project_summary_csv_path = "samples/tbl_01_Project_summary.csv"
    project_activity_csv_path = "samples/tbl_02_ProjectActivity.csv"
    
    # Check for command line arguments
    # if len(sys.argv) > 1:
    # if sys.argv[1] == "--clear":
    #     print("🗑️ Clearing sratable...")
    #     asyncio.run(clear_table())
    # elif sys.argv[1] == "--clear-activity":
    #     print("🗑️ Clearing sra_activity_table...")
    #     asyncio.run(clear_activity_table())
    # if sys.argv[0] == "--activity":
        # Ingest activity-level data
        # if len(sys.argv) > 2:
    # activity_csv_path = sys.argv[1]
    asyncio.run(ingest_project_activity_csv(project_activity_csv_path))
    # else:
    #     pass
            # csv_path = sys.argv[1]
            # asyncio.run(ingest_csv(csv_path))
    # else:
    #     pass
        # asyncio.run(ingest_csv(csv_path))

