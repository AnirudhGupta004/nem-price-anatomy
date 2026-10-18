"""Clean the raw AEMO tables into one analysis-ready Parquet file.

Usage (from the project folder):
    .venv/Scripts/python.exe src/clean.py

Input:  data/raw/dispatchprice_*.parquet, data/raw/dispatchregionsum_*.parquet
Output: data/clean/nem_5min.parquet - one row per region per 5-minute interval

All timestamps are NEM time (AEST, UTC+10, no daylight saving) and are kept
as naive datetimes. Never convert them to Sydney local time.
"""

from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
CLEAN_DIR = PROJECT_DIR / "data" / "clean"
PERIOD = "2021_10_to_2026_09"

# Sample starts with 5-minute settlement (intervals starting 1 Oct 2021 00:00).
SAMPLE_START = pd.Timestamp("2021-10-01 00:00")

# June 2022 market suspension, as SETTLEMENTDATE (interval END) values, inclusive.
# AEMO suspended the spot market at 14:05 on 15 Jun 2022 and lifted it at 14:00 on 24 Jun 2022
# (AEMO media releases "AEMO suspends NEM wholesale market" and "AEMO lifts market suspension").
SUSPENSION_START = pd.Timestamp("2022-06-15 14:05")
SUSPENSION_END = pd.Timestamp("2022-06-24 14:00")

SEASONS = {
    12: "summer", 1: "summer", 2: "summer",
    3: "autumn", 4: "autumn", 5: "autumn",
    6: "winter", 7: "winter", 8: "winter",
    9: "spring", 10: "spring", 11: "spring",
}


def load_raw(table):
    """Read one raw table and keep only the INTERVENTION = 0 run."""
    df = pd.read_parquet(RAW_DIR / f"{table}_{PERIOD}.parquet")
    n_intervention = (df["INTERVENTION"] == 1).sum()
    df = df[df["INTERVENTION"] == 0].drop(columns="INTERVENTION")
    print(f"{table}: dropped {n_intervention:,} INTERVENTION = 1 rows, kept {len(df):,}")
    return df


def add_time_columns(df):
    """Add interval_start and the calendar helper columns, all derived from interval start."""
    # SETTLEMENTDATE is the END of the interval: 00:05 covers 00:00-00:05.
    df["interval_start"] = df["SETTLEMENTDATE"] - pd.Timedelta(minutes=5)
    t = df["interval_start"]

    df["date"] = t.dt.normalize()
    df["hour"] = t.dt.hour
    df["month"] = t.dt.month
    df["season"] = df["month"].map(SEASONS)
    # Australian financial year runs Jul-Jun and is named by the year it ends: Oct 2021 -> FY22.
    fy_end_year = t.dt.year + (t.dt.month >= 7)
    df["fy"] = "FY" + (fy_end_year % 100).astype(str).str.zfill(2)
    df["is_weekend"] = t.dt.dayofweek >= 5
    return df


def add_flags(df):
    """Flag intervals that need special treatment in the analysis."""
    df["is_suspension"] = df["SETTLEMENTDATE"].between(SUSPENSION_START, SUSPENSION_END)
    return df


def check(df):
    """Print duplicate and gap counts; stop if the data is not one row per region per interval."""
    dupes = df.duplicated(["REGIONID", "SETTLEMENTDATE"]).sum()
    per_day = df.groupby(["REGIONID", "date"]).size()
    short_days = per_day[per_day != 288]
    print(f"duplicates: {dupes}, days with != 288 intervals: {len(short_days)}")
    if len(short_days):
        print(short_days.to_string())
    assert dupes == 0, "duplicate intervals found"


def clean():
    price = load_raw("dispatchprice")
    regionsum = load_raw("dispatchregionsum")

    df = price.merge(regionsum, on=["SETTLEMENTDATE", "REGIONID"], how="inner", validate="1:1")
    print(f"merged: {len(df):,} rows (price {len(price):,}, regionsum {len(regionsum):,})")

    df = add_time_columns(df)
    df = df[df["interval_start"] >= SAMPLE_START]
    df = add_flags(df)
    check(df)

    df = df.sort_values(["REGIONID", "SETTLEMENTDATE"]).reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = clean()

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = CLEAN_DIR / "nem_5min.parquet"
    df.to_parquet(path, index=False)

    print(f"\nSaved {len(df):,} rows to {path.relative_to(PROJECT_DIR)}")
    print(f"suspension intervals flagged per region: {df.groupby('REGIONID')['is_suspension'].sum().to_dict()}")
    print(df.head())
    print(df.dtypes)
