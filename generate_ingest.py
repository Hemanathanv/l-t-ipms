import pandas as pd
import math
import sys

def get_parsers():
    return """
def parse_date(val):
    if pd.isna(val): return None
    try: return pd.to_datetime(val).replace(tzinfo=None)
    except: return None

def parse_int(val):
    if pd.isna(val): return None
    try: return int(float(val))
    except: return None

def parse_float(val):
    if pd.isna(val): return None
    try: return float(val)
    except: return None

def parse_bool(val):
    if pd.isna(val): return None
    if str(val).lower() in ['true', 'yes', '1', 'y']: return True
    if str(val).lower() in ['false', 'no', '0', 'n']: return False
    return None

def parse_str(val):
    if pd.isna(val): return None
    return str(val)
"""

def generate_ingest_func(model_name, file_path, lines):
    mappings = []
    for line in lines:
        if "@map" not in line: continue
        parts = line.split()
        if len(parts) < 3: continue
        prop = parts[0]
        dtype = parts[1]
        
        # extract map value
        map_val = line.split('@map("')[1].split('")')[0]
        
        parser = "parse_str"
        if "DateTime" in dtype: parser = "parse_date"
        elif "Int" in dtype: parser = "parse_int"
        elif "Float" in dtype: parser = "parse_float"
        elif "Boolean" in dtype: parser = "parse_bool"
        
        mappings.append((prop, map_val, parser))
        
    func = f"""
async def ingest_{model_name.lower()}(db: Prisma, csv_path: str):
    print(f"Ingesting {{csv_path}} into {model_name}...")
    df = pd.read_excel(csv_path + '.xlsx') if csv_path.endswith('.csv') else pd.read_csv(csv_path)
    
    # Strip whitespace from column names just in case
    df.columns = [str(c).strip() for c in df.columns]
    
    records = []
    for _, row in df.iterrows():
        record = {{}}
"""
    for prop, map_val, parser in mappings:
        func += f"        if '{map_val}' in row:\n"
        func += f"            record['{prop}'] = {parser}(row['{map_val}'])\n"
        
    func += f"""
        records.append(record)
        
    batch_size = 1000
    total_inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        await db.{model_name.lower()[0].lower() + model_name[1:]}.create_many(data=batch, skip_duplicates=True)
        total_inserted += len(batch)
        print(f"Inserted {{total_inserted}}/{{len(records)}} records into {model_name}")
        
    print(f"Finished ingesting {{total_inserted}} records into {model_name}")
"""
    return func

# Try different encodings
encodings = ['utf-8', 'utf-16', 'utf-16-le', 'cp1252']
text = None
for enc in encodings:
    try:
        with open('samples/schema_extract.txt', 'r', encoding=enc) as f:
            text = f.read()
            if 'Tbl01ProjectSummary' in text:
                print(f"Successfully read with {enc}")
                break
    except Exception as e:
        continue

if not text:
    print("Failed to read file!")
    sys.exit(1)

sections = text.split('---')

s1 = sections[0].split('\n')
s2 = sections[1].split('\n')
s3 = sections[2].split('\n')

script = "import pandas as pd\nfrom prisma import Prisma\nimport asyncio\n"
script += get_parsers()
script += generate_ingest_func("Tbl01ProjectSummary", "samples/tbl_01_project_summary.csv", s1)
script += generate_ingest_func("Tbl02ProjectActivity", "samples/tbl_02_project_activity.csv", s2)
script += generate_ingest_func("Tbl03ProjectTask", "samples/tbl_03_project_task.csv", s3)

script += """
async def main():
    db = Prisma()
    await db.connect()
    
    try:
        await db.tbl01projectsummary.delete_many()
        await db.tbl02projectactivity.delete_many()
        await db.tbl03projecttask.delete_many()
        
        await ingest_tbl01projectsummary(db, "samples/tbl_01_project_summary.csv")
        await ingest_tbl02projectactivity(db, "samples/tbl_02_project_activity.csv")
        await ingest_tbl03projecttask(db, "samples/tbl_03_project_task.csv")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
"""

with open('ingest.py', 'w') as f:
    f.write(script)
