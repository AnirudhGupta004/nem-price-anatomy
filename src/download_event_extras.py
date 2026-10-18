"""Download binding constraints and price setters for the spike case studies (Analysis 4).

Usage (from the project folder, after src/download_events.py):
    .venv/Scripts/python.exe src/download_event_extras.py

For each event in download_events.EVENTS (+-3 hours), saves to data/raw/events/:
    - <event>_constraints.parquet: every constraint that BOUND (MARGINALVALUE != 0), from DISPATCHCONSTRAINT
    - <event>_pricesetters.parquet: which unit's bid set the NSW1/SA1 energy price, from AEMO's NEMDE
      NemPriceSetter files (the same source NEMED uses)
And once, for the constraints that bound in any event:
    - constraint_interconnectors.parquet: which interconnectors each constraint contains (SPDINTERCONNECTORCONSTRAINT)
    - constraint_descriptions.parquet: AEMO's description of each constraint (GENCONDATA)
"""

import io
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
from nemosis import dynamic_data_compiler

from download import CACHE_DIR
from download_events import EVENTS, EVENTS_DIR, event_window

PRICESETTER_URL = (
    "https://www.nemweb.com.au/Data_Archive/Wholesale_Electricity/NEMDE/{y}/NEMDE_{y}_{m}/"
    "NEMDE_Market_Data/NEMDE_Files/NemPriceSetter_{y}{m}{d}_xml.zip"
)
# A NEM trading day runs 04:05 to 04:00 next day, and each NemPriceSetter zip covers one trading day
TRADING_DAY_OFFSET = pd.Timedelta(hours=4, minutes=5)


def download_constraints(start, end):
    """Constraints that bound (non-zero marginal value) in the window, INTERVENTION = 0 run only."""
    df = dynamic_data_compiler(
        start_time=start, end_time=end, table_name="DISPATCHCONSTRAINT",
        raw_data_location=str(CACHE_DIR), fformat="parquet", keep_csv=False,
        select_columns=["SETTLEMENTDATE", "CONSTRAINTID", "INTERVENTION", "RHS", "LHS", "MARGINALVALUE", "VIOLATIONDEGREE"],
    )
    df = df[(df["INTERVENTION"] == 0) & (df["MARGINALVALUE"] != 0)].drop(columns="INTERVENTION")
    return df.sort_values(["SETTLEMENTDATE", "CONSTRAINTID"]).reset_index(drop=True)


def read_pricesetter_day(day):
    """All energy-market price-setting rows for one trading day, from AEMO's NEMDE archive."""
    url = PRICESETTER_URL.format(y=day.strftime("%Y"), m=day.strftime("%m"), d=day.strftime("%d"))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))

    rows = []
    for name in archive.namelist():
        for el in ET.fromstring(archive.read(name)).iter("PriceSetting"):
            if el.get("Market") == "Energy" and el.get("RegionID") in ("NSW1", "SA1"):
                rows.append(el.attrib)
    df = pd.DataFrame(rows)
    # PeriodID is the interval END, like SETTLEMENTDATE; drop the +10:00 suffix to match NEM time elsewhere
    df["SETTLEMENTDATE"] = pd.to_datetime(df["PeriodID"].str[:19])
    # BandNo is usually 1-10 but can be an offer identifier, so it stays as text
    for col in ["Price", "RRNBandPrice", "BandCost", "Increase"]:
        df[col] = pd.to_numeric(df[col])
    return df.drop(columns=["PeriodID", "Market"])


def download_pricesetters(start, end):
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    days = pd.date_range((t0 - TRADING_DAY_OFFSET).normalize(), (t1 - TRADING_DAY_OFFSET).normalize(), freq="D")
    df = pd.concat([read_pricesetter_day(day) for day in days], ignore_index=True)
    df = df[(df["SETTLEMENTDATE"] > t0) & (df["SETTLEMENTDATE"] <= t1)]
    return df.sort_values(["RegionID", "SETTLEMENTDATE"]).reset_index(drop=True)


def download_constraint_details(constraint_ids):
    """Interconnector terms and descriptions for the given constraints (latest version of each)."""
    common = dict(start_time="2021/10/01 00:00:00", end_time="2026/10/01 00:00:00",
                  raw_data_location=str(CACHE_DIR), fformat="parquet", keep_csv=False)

    ic = dynamic_data_compiler(table_name="SPDINTERCONNECTORCONSTRAINT", **common)
    ic = ic[ic["GENCONID"].isin(constraint_ids)]
    ic = ic.sort_values(["EFFECTIVEDATE", "VERSIONNO"]).groupby(["GENCONID", "INTERCONNECTORID"]).last().reset_index()

    desc = dynamic_data_compiler(table_name="GENCONDATA", **common)
    desc = desc[desc["GENCONID"].isin(constraint_ids)]
    desc = desc.sort_values(["EFFECTIVEDATE", "VERSIONNO"]).groupby("GENCONID").last().reset_index()
    return ic[["GENCONID", "INTERCONNECTORID", "FACTOR"]], desc[["GENCONID", "CONSTRAINTTYPE", "DESCRIPTION", "LIMITTYPE", "REASON"]]


if __name__ == "__main__":
    all_ids = set()
    for name, (region, first_start, last_end) in EVENTS.items():
        start, end = event_window(first_start, last_end)
        print(f"\n=== {name}: {start} -> {end}")

        cons = download_constraints(start, end)
        cons.to_parquet(EVENTS_DIR / f"{name}_constraints.parquet", index=False)
        all_ids |= set(cons["CONSTRAINTID"])
        print(f"binding constraints: {len(cons):,} rows, {cons['CONSTRAINTID'].nunique()} constraints")

        ps = download_pricesetters(start, end)
        ps.to_parquet(EVENTS_DIR / f"{name}_pricesetters.parquet", index=False)
        print(f"price setters: {len(ps):,} rows, {ps['Unit'].nunique()} units")

    ic, desc = download_constraint_details(all_ids)
    ic.to_parquet(EVENTS_DIR / "constraint_interconnectors.parquet", index=False)
    desc.to_parquet(EVENTS_DIR / "constraint_descriptions.parquet", index=False)
    print(f"\nconstraint details: {ic['GENCONID'].nunique()} with interconnector terms, {len(desc)} descriptions")
