"""Download the extra tables for the spike case studies (Analysis 4), only around each event.

Usage (from the project folder):
    .venv/Scripts/python.exe src/download_events.py

For each event in EVENTS, pulls a window of +-3 hours around it:
    - DISPATCHINTERCONNECTORRES: flow and limits on every interconnector touching NSW or SA
    - DISPATCH_UNIT_SCADA: MW output of every generating unit
Plus, once:
    - DUDETAILSUMMARY: which region each unit (DUID) is in
    - AEMO's NEM Registration and Exemption List: each unit's fuel and technology
      (current list only, so units retired before today are missing and need mapping by hand)

NEMOSIS still downloads whole monthly files (cached in data/nemosis_cache/), but only
the event windows are saved, to data/raw/events/.
"""

import urllib.request

import pandas as pd
from nemosis import defaults, dynamic_data_compiler

from download import CACHE_DIR, PROJECT_DIR

EVENTS_DIR = PROJECT_DIR / "data" / "raw" / "events"
WINDOW = pd.Timedelta(hours=3)

# name: (region, first spike interval start, last spike SETTLEMENTDATE) - from notebooks/05_spikes
EVENTS = {
    "2022-08-26_SA1": ("SA1", "2022-08-26 06:30", "2022-08-26 08:30"),
    "2024-05-08_NSW1": ("NSW1", "2024-05-08 15:35", "2024-05-08 19:50"),
    "2024-11-27_NSW1": ("NSW1", "2024-11-27 14:25", "2024-11-27 15:35"),
    "2025-06-26_NSW1_SA1": ("NSW1", "2025-06-26 16:45", "2025-06-26 20:55"),
    "2026-01-26_SA1": ("SA1", "2026-01-26 18:25", "2026-01-26 21:40"),
}

REGISTRATION_LIST_URL = (
    "https://www.aemo.com.au/-/media/files/electricity/nem/participant_information/"
    "nem-registration-and-exemption-list.xlsx"
)

# Interconnectors that touch NSW or SA
INTERCONNECTORS = ["NSW1-QLD1", "N-Q-MNSP1", "VIC1-NSW1", "V-SA", "V-S-MNSP1"]

INTERCONNECTOR_COLUMNS = [
    "SETTLEMENTDATE", "INTERCONNECTORID", "INTERVENTION",
    "MWFLOW", "EXPORTLIMIT", "IMPORTLIMIT", "MARGINALVALUE",
]
# NEMOSIS only keeps its default columns when it caches a month, and those defaults leave out
# the limits. Adding them here makes the cache keep them (delete old cached months to rebuild).
defaults.table_columns["DISPATCHINTERCONNECTORRES"] = list(dict.fromkeys(
    defaults.table_columns["DISPATCHINTERCONNECTORRES"] + INTERCONNECTOR_COLUMNS
))


def nemosis_time(ts):
    return ts.strftime("%Y/%m/%d %H:%M:%S")


def event_window(first_start, last_end):
    """Return (start, end) for NEMOSIS: 3 hours either side of the event."""
    return nemosis_time(pd.Timestamp(first_start) - WINDOW), nemosis_time(pd.Timestamp(last_end) + WINDOW)


def download_interconnectors(start, end):
    df = dynamic_data_compiler(
        start_time=start, end_time=end, table_name="DISPATCHINTERCONNECTORRES",
        raw_data_location=str(CACHE_DIR), select_columns=INTERCONNECTOR_COLUMNS,
        filter_cols=["INTERCONNECTORID"], filter_values=(INTERCONNECTORS,),
        fformat="parquet", keep_csv=False,
    )
    df = df[df["INTERVENTION"] == 0].drop(columns="INTERVENTION")
    return df.sort_values(["INTERCONNECTORID", "SETTLEMENTDATE"]).reset_index(drop=True)


def download_scada(start, end):
    df = dynamic_data_compiler(
        start_time=start, end_time=end, table_name="DISPATCH_UNIT_SCADA",
        raw_data_location=str(CACHE_DIR), fformat="parquet", keep_csv=False,
    )
    return df.sort_values(["DUID", "SETTLEMENTDATE"]).reset_index(drop=True)


def download_unit_details():
    """One row per DUID: region (from DUDETAILSUMMARY, latest record) and fuel (from AEMO's registration list)."""
    dud = dynamic_data_compiler(
        start_time="2021/10/01 00:00:00", end_time="2026/10/01 00:00:00", table_name="DUDETAILSUMMARY",
        raw_data_location=str(CACHE_DIR), fformat="parquet", keep_csv=False,
    )
    dud = dud.sort_values("START_DATE").groupby("DUID").last().reset_index()[["DUID", "REGIONID", "DISPATCHTYPE", "STATIONID"]]

    # NEMOSIS's static_table() gets blocked by AEMO's website, so fetch the list directly with a browser user agent
    path = EVENTS_DIR / "nem_registration_and_exemption_list.xlsx"
    request = urllib.request.Request(REGISTRATION_LIST_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response:
        path.write_bytes(response.read())
    reg = pd.read_excel(path, sheet_name="PU and Scheduled Loads")
    reg = reg.rename(columns=str.strip)
    # Spreadsheet columns mix numbers and text (e.g. Units = 4 or "1-4"); store the text ones as text
    text_cols = reg.select_dtypes(include="object").columns
    reg[text_cols] = reg[text_cols].astype("string")
    return dud, reg


if __name__ == "__main__":
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)

    for name, (region, first_start, last_end) in EVENTS.items():
        start, end = event_window(first_start, last_end)
        print(f"\n=== {name}: {start} -> {end}")

        ic = download_interconnectors(start, end)
        ic.to_parquet(EVENTS_DIR / f"{name}_interconnectors.parquet", index=False)
        print(f"interconnectors: {len(ic):,} rows, {ic['INTERCONNECTORID'].nunique()} interconnectors")

        scada = download_scada(start, end)
        scada.to_parquet(EVENTS_DIR / f"{name}_scada.parquet", index=False)
        print(f"unit SCADA: {len(scada):,} rows, {scada['DUID'].nunique()} units")

    dud, reg = download_unit_details()
    dud.to_parquet(EVENTS_DIR / "dudetailsummary.parquet", index=False)
    reg.to_parquet(EVENTS_DIR / "generators_and_loads.parquet", index=False)
    print(f"\nunit details: {len(dud):,} DUIDs; registration list: {len(reg):,} rows")
