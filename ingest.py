"""
ingest.py

Generic CSV -> Prisma ingestion for:
 - Tbl01ProjectSummary (tbl_01_project_summary)
 - Tbl02ProjectActivity (tbl_02_project_activity)
 - Tbl03ProjectTask (tbl_03_project_task)

Usage:
    python ingest.py --summary samples/tbl_01_project_summary.csv
    python ingest.py --activity samples/tbl_02_project_activity.csv
    python ingest.py --task samples/tbl_03_project_task.csv
    python ingest.py --all <summary.csv> <activity.csv> <task.csv>
    python ingest.py --clear-summary
    python ingest.py --clear-activity
    python ingest.py --clear-task
"""

import asyncio
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, get_args

from dotenv import load_dotenv

load_dotenv()

from prisma import Prisma
from prisma.models import Tbl01ProjectSummary, Tbl02ProjectActivity, Tbl03ProjectTask


# -------------------------
# Parsers / helpers
# -------------------------
def parse_nullable_date(date_str: str) -> datetime | None:
    if not date_str or date_str.strip() == "" or date_str.strip().upper() in ("NULL", "NONE", "NA"):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(date_str.strip())
    except Exception:
        return None


def parse_nullable_float(value: str) -> float | None:
    if value is None:
        return None
    v = str(value).strip()
    if v == "" or v.upper() in ("NULL", "NONE", "NA"):
        return None
    try:
        return float(v)
    except Exception:
        try:
            return float(v.replace(",", ""))
        except Exception:
            return None


def parse_nullable_int(value: str) -> int | None:
    if value is None:
        return None
    v = str(value).strip()
    if v == "" or v.upper() in ("NULL", "NONE", "NA"):
        return None
    try:
        return int(float(v))
    except Exception:
        try:
            return int(float(v.replace(",", "")))
        except Exception:
            return None


def parse_bool(value: str) -> bool | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v == "" or v.upper() in ("NULL", "NONE", "NA"):
        return None
    if v in ("true", "t", "yes", "y", "1", "on"):
        return True
    if v in ("false", "f", "no", "n", "0", "off"):
        return False
    return None


def parse_nullable_string(value: str) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    if v == "" or v.upper() in ("NULL", "NONE", "NA"):
        return None
    return v


# Required parsers are strict: invalid/missing returns None so row can be skipped.
def parse_required_date(value: str) -> datetime | None:
    return parse_nullable_date(value)


def parse_required_float(value: str) -> float | None:
    return parse_nullable_float(value)


def parse_required_int(value: str) -> int | None:
    return parse_nullable_int(value)


def parse_required_bool(value: str) -> bool | None:
    return parse_bool(value)


def parse_required_string(value: str) -> str | None:
    return parse_nullable_string(value)


# -------------------------
# Header -> model field name conversion
# -------------------------
_SPLIT_RE = re.compile(r"[^0-9A-Za-z]+")


def header_to_camel(header: str) -> str:
    if header is None:
        return ""
    header = header.strip().lstrip("\ufeff")
    parts = [p for p in _SPLIT_RE.split(header) if p]
    if not parts:
        return ""
    parts = [p.lower() for p in parts]
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# -------------------------
# Dynamic mapper using schema introspection
# -------------------------
def _is_optional_type(field_type: Any) -> bool:
    return type(None) in get_args(field_type)


def get_parser_for_type(model_field: str, model_class) -> tuple[callable, bool]:
    if not model_field or not hasattr(model_class, "__annotations__"):
        return parse_nullable_string, True

    field_type = model_class.__annotations__.get(model_field)
    if field_type is None:
        return parse_nullable_string, True

    type_str = str(field_type).lower()
    is_optional = _is_optional_type(field_type)

    if "int" in type_str:
        return (parse_nullable_int if is_optional else parse_required_int), is_optional
    if "float" in type_str:
        return (parse_nullable_float if is_optional else parse_required_float), is_optional
    if "bool" in type_str:
        return (parse_bool if is_optional else parse_required_bool), is_optional
    if "datetime" in type_str:
        return (parse_nullable_date if is_optional else parse_required_date), is_optional
    return (parse_nullable_string if is_optional else parse_required_string), is_optional


# -------------------------
# Generic ingest for any model
# -------------------------
MODEL_CLASS_BY_ATTR = {
    "tbl01projectsummary": Tbl01ProjectSummary,
    "tbl02projectactivity": Tbl02ProjectActivity,
    "tbl03projecttask": Tbl03ProjectTask,
}


async def ingest_generic(csv_path: str, prisma_model_attr: str, batch_size: int = 200):
    prisma = Prisma()
    await prisma.connect()

    csv_file = Path(csv_path)
    if not csv_file.exists():
        print(f"File not found: {csv_path}")
        await prisma.disconnect()
        return

    model_class = MODEL_CLASS_BY_ATTR.get(prisma_model_attr)
    if model_class is None:
        print(f"Unsupported model attribute '{prisma_model_attr}'.")
        await prisma.disconnect()
        return

    model_obj = getattr(prisma, prisma_model_attr, None)
    if model_obj is None:
        print(f"Prisma model attribute '{prisma_model_attr}' not found on Prisma client.")
        await prisma.disconnect()
        return

    known_fields = set(getattr(model_class, "__annotations__", {}).keys())
    ignored_fields = {"id", "createdAt", "updatedAt"}
    required_fields = {
        field_name
        for field_name, field_type in model_class.__annotations__.items()
        if field_name not in ignored_fields and not _is_optional_type(field_type)
    }

    with open(csv_file, "r", encoding="cp1252", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        header_map: dict[str, tuple[str, callable, bool]] = {}
        unknown_headers = []
        for header in headers:
            model_field = header_to_camel(header)
            if model_field in ignored_fields:
                continue
            if model_field not in known_fields:
                unknown_headers.append(header)
                continue
            parser, is_optional = get_parser_for_type(model_field, model_class)
            header_map[header] = (model_field, parser, is_optional)

        if unknown_headers:
            print(f"Ignoring {len(unknown_headers)} CSV headers not present in {prisma_model_attr}.")

        records = []
        total_inserted = 0
        skipped = 0

        for row_num, row in enumerate(reader, start=1):
            try:
                record = {}
                for original_header, (model_field, parser, _) in header_map.items():
                    record[model_field] = parser(row.get(original_header))

                missing_required = [f for f in required_fields if record.get(f) is None]
                if missing_required:
                    skipped += 1
                    print(f"Skipped row {row_num}: missing required fields {missing_required}")
                    continue

                records.append(record)
            except Exception as e:
                skipped += 1
                print(f"Skipped row {row_num} due to error: {e}")
                continue

            if len(records) >= batch_size:
                try:
                    await model_obj.create_many(data=records)
                    total_inserted += len(records)
                    print(f"Inserted {total_inserted} records into {prisma_model_attr}...")
                except Exception as e:
                    print(f"Error inserting batch at row {row_num}: {e}")
                records = []

        if records:
            try:
                await model_obj.create_many(data=records)
                total_inserted += len(records)
            except Exception as e:
                print(f"Error inserting final batch: {e}")

    try:
        count = await model_obj.count()
        print(f"Total records in {prisma_model_attr}: {count}")
    except Exception:
        print(f"Inserted (reported) {total_inserted} records into {prisma_model_attr}")

    if skipped > 0:
        print(f"Skipped {skipped} rows due to parse/validation errors")

    await prisma.disconnect()
    print(f"Ingestion finished for {prisma_model_attr}. Total inserted: {total_inserted}")


# -------------------------
# Specific wrappers
# -------------------------
async def ingest_tbl01_project_summary(csv_path: str, batch_size: int = 200):
    await ingest_generic(csv_path, "tbl01projectsummary", batch_size)


async def ingest_tbl02_project_activity(csv_path: str, batch_size: int = 200):
    await ingest_generic(csv_path, "tbl02projectactivity", batch_size)


async def ingest_tbl03_project_task(csv_path: str, batch_size: int = 200):
    await ingest_generic(csv_path, "tbl03projecttask", batch_size)


# -------------------------
# Clear functions
# -------------------------
async def clear_tbl01_project_summary():
    prisma = Prisma()
    await prisma.connect()
    deleted = await prisma.tbl01projectsummary.delete_many()
    print(f"Deleted {deleted} from tbl_01_project_summary")
    await prisma.disconnect()


async def clear_tbl02_project_activity():
    prisma = Prisma()
    await prisma.connect()
    deleted = await prisma.tbl02projectactivity.delete_many()
    print(f"Deleted {deleted} from tbl_02_project_activity")
    await prisma.disconnect()


async def clear_tbl03_project_task():
    prisma = Prisma()
    await prisma.connect()
    deleted = await prisma.tbl03projecttask.delete_many()
    print(f"Deleted {deleted} from tbl_03_project_task")
    await prisma.disconnect()


# -------------------------
# CLI
# -------------------------
if __name__ == "__main__":
    summary_csv_default = "samples/tbl_01_project_summary.csv"
    activity_csv_default = "samples/tbl_02_project_activity.csv"
    task_csv_default = "samples/tbl_03_project_task.csv"

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--clear-summary":
            asyncio.run(clear_tbl01_project_summary())
        elif cmd == "--clear-activity":
            asyncio.run(clear_tbl02_project_activity())
        elif cmd == "--clear-task":
            asyncio.run(clear_tbl03_project_task())
        elif cmd == "--summary":
            path = sys.argv[2] if len(sys.argv) > 2 else summary_csv_default
            asyncio.run(ingest_tbl01_project_summary(path))
        elif cmd == "--activity":
            path = sys.argv[2] if len(sys.argv) > 2 else activity_csv_default
            asyncio.run(ingest_tbl02_project_activity(path))
        elif cmd == "--task":
            path = sys.argv[2] if len(sys.argv) > 2 else task_csv_default
            asyncio.run(ingest_tbl03_project_task(path))
        elif cmd == "--all":
            summary_path = sys.argv[2] if len(sys.argv) > 2 else summary_csv_default
            activity_path = sys.argv[3] if len(sys.argv) > 3 else activity_csv_default
            task_path = sys.argv[4] if len(sys.argv) > 4 else task_csv_default
            asyncio.run(ingest_tbl01_project_summary(summary_path))
            asyncio.run(ingest_tbl02_project_activity(activity_path))
            asyncio.run(ingest_tbl03_project_task(task_path))
        else:
            print(
                "Usage: python ingest.py [--summary <file>|--activity <file>|--task <file>|--all <summary> <activity> <task>|--clear-summary|--clear-activity|--clear-task]"
            )
    else:
        asyncio.run(ingest_tbl01_project_summary(summary_csv_default))
        asyncio.run(ingest_tbl02_project_activity(activity_csv_default))
        asyncio.run(ingest_tbl03_project_task(task_csv_default))
