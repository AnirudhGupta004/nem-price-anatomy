"""Download AEMO MMSDM tables with NEMOSIS and save them as Parquet.

Usage (from the project folder):
    .venv/Scripts/python.exe src/download.py

Raw AEMO files are cached in data/nemosis_cache/ so re-runs don't re-download.
Output is the table exactly as AEMO publishes it (no cleaning), saved to data/raw/.
"""

from pathlib import Path

from nemosis import dynamic_data_compiler

PROJECT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_DIR / "data" / "nemosis_cache"
RAW_DIR = PROJECT_DIR / "data" / "raw"

COLUMNS = {
    "DISPATCHPRICE": ["SETTLEMENTDATE", "REGIONID", "RRP", "INTERVENTION"],
    "DISPATCHREGIONSUM": [
        "SETTLEMENTDATE", "REGIONID", "TOTALDEMAND",
        "AVAILABLEGENERATION", "NETINTERCHANGE", "INTERVENTION",
        # Semi-scheduled (utility wind + solar): dispatched MW, and what they could have produced (UIGF)
        "SEMISCHEDULE_CLEAREDMW", "UIGF",
    ],
}


def download_table(table, start, end, regions):
    """Return one AEMO table for the given regions between start and end.

    start/end are 'YYYY/MM/DD HH:MM:SS' in NEM time. NEMOSIS keeps rows with
    start < SETTLEMENTDATE <= end, and SETTLEMENTDATE is the END of each
    5-minute interval, so start='2021/10/01 00:00:00', end='2021/11/01 00:00:00'
    gives exactly the intervals that begin in October 2021.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = dynamic_data_compiler(
        start_time=start,
        end_time=end,
        table_name=table,
        raw_data_location=str(CACHE_DIR),
        select_columns=COLUMNS[table],
        filter_cols=["REGIONID"],
        filter_values=(regions,),
        fformat="parquet",
        keep_csv=False,  # cache only the Parquet copy; raw CSVs are ~16 MB/month each
    )
    return df.sort_values(["REGIONID", "SETTLEMENTDATE", "INTERVENTION"]).reset_index(drop=True)


def save(df, name):
    """Write a DataFrame to data/raw/<name>.parquet and return the path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False)
    return path


if __name__ == "__main__":
    tables = ["DISPATCHPRICE", "DISPATCHREGIONSUM"]
    regions = ["NSW1", "SA1"]
    # Sample: intervals starting 1 Oct 2021 00:00 to 30 Sep 2026 23:55 (NEM time)
    start, end = "2021/10/01 00:00:00", "2026/10/01 00:00:00"

    for table in tables:
        df = download_table(table, start, end, regions)
        path = save(df, f"{table.lower()}_2021_10_to_2026_09")

        print(f"Saved {len(df):,} rows to {path.relative_to(PROJECT_DIR)}")
        print(df.head())
        print(df.dtypes)
