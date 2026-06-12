import sqlite3
from pathlib import Path
import pandas as pd

csv_dir = Path(__file__).resolve().parent / "data CSV files"
db_file = Path(__file__).resolve().parent / "data_csv_files.db"

if not csv_dir.exists():
    raise FileNotFoundError(f"CSV directory not found: {csv_dir}")

csv_files = sorted(csv_dir.glob("*.csv"))
if not csv_files:
    raise FileNotFoundError(f"No CSV files found in: {csv_dir}")

print(f"Creating SQLite database: {db_file}")
print(f"Loading {len(csv_files)} CSV files from: {csv_dir}")

with sqlite3.connect(db_file) as conn:
    for csv_path in csv_files:
        table_name = csv_path.stem.strip().lower().replace(" ", "_").replace("-", "_")
        print(f"  - Importing '{csv_path.name}' as table '{table_name}'")
        df = pd.read_csv(csv_path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)

print("Done.")
