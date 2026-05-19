#!/usr/bin/env python3
"""
USDA MARS API — Videxport pricing surveillance puller (v3)

Pulls daily IX_FV110 (Phoenix Shipping Point Fruit Prices) reports across
all relevant Mexico-Crossings-through-Nogales commodities:
    - Grapes (all varieties)
    - Watermelons
    - Honeydews
    - Bell peppers (note: IX_FV110 carries fruits only; vegetables come via
      a separate slug — see notes at end of file)

Modes:
    FULL    : refresh entire history from FULL_START_DATE to today
    INCREMENTAL : only fetch dates after the latest already in usda_master.csv

Usage:
    python refresh_usda.py             # incremental refresh
    python refresh_usda.py full        # full historical refresh
"""

import csv
import os
import sys
import time
from datetime import date, datetime, timedelta

try:
    import requests
except ImportError:
    sys.exit("requests library is required. Run: pip install requests")


# ============================================================
# CONFIGURATION
# ============================================================
_raw_key = os.environ.get("USDA_API_KEY", "")
if not _raw_key:
    sys.exit("Error: USDA_API_KEY environment variable is not set.")
API_KEY = _raw_key

# Each report slug = one MARS endpoint
REPORTS = {
    "IX_FV110": 2402,   # Phoenix Shipping Point Fruit Prices (grapes, melons)
    "IX_FV120": 2403,   # Phoenix Shipping Point Vegetable Prices (peppers, asparagus)
}

# Commodities we want to track (case-insensitive substring match on `commodity`)
TARGET_COMMODITIES = [
    "GRAPE", "WATERMELON", "HONEYDEW",
    "PEPPER", "ASPARAGUS",
]

# Date ranges
FULL_START_DATE = "01/01/2023"     # how far back to go on a FULL refresh
OUTPUT_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "data", "usda_master.csv"
)

# ============================================================
# FETCH
# ============================================================
def fetch_range(slug_id, start_date, end_date):
    """Pull every record across a date range, paginating if needed."""
    url = f"https://marsapi.ams.usda.gov/services/v1.2/reports/{slug_id}/Report%20Details"
    params = {
        "q": f"report_date={start_date}:{end_date}",
        "allSections": "true",
    }
    try:
        r = requests.get(url, params=params, auth=(API_KEY, ""), timeout=240)
        r.raise_for_status()
        payload = r.json()
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP error: {e}")
        print(f"  Body: {r.text[:300]}")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

    records = []
    if isinstance(payload, list):
        for block in payload:
            if isinstance(block, dict) and "results" in block:
                records.extend(block["results"])
    elif isinstance(payload, dict) and "results" in payload:
        records.extend(payload["results"])
    return records


# ============================================================
# FILTER + NORMALIZE
# ============================================================
def is_target_record(rec):
    """
    Filter for Mexico-crossings rows for our target commodities.
    - Grapes, watermelons, honeydews, bell peppers: cross through Nogales, AZ.
    - Asparagus: crosses through Calexico, CA / San Luis, AZ (different port).
    """
    commodity = str(rec.get("commodity", "")).upper()
    name = str(rec.get("market_location_name", "")).upper()
    city = str(rec.get("market_location_city", "")).upper()
    district = str(rec.get("district", "")).upper()

    is_target_commodity = any(c in commodity for c in TARGET_COMMODITIES)
    if not is_target_commodity:
        return False

    is_nogales = ("NOGALES" in name or "NOGALES" in city or "NOGALES" in district)
    is_calexico_san_luis = (
        "CALEXICO" in name or "CALEXICO" in city or "CALEXICO" in district or
        "SAN LUIS" in name or "SAN LUIS" in city or "SAN LUIS" in district
    )

    # Asparagus crosses at Calexico/San Luis; everything else at Nogales.
    if "ASPARAGUS" in commodity:
        return is_calexico_san_luis
    return is_nogales


def normalize(rec, slug_name):
    return {
        "source_report": slug_name,
        "report_date": rec.get("report_date", ""),
        "commodity": rec.get("commodity", ""),
        "variety": rec.get("var", ""),
        "organic": rec.get("organic", "") or "",
        "market_location": rec.get("market_location_name", ""),
        "district": rec.get("district", ""),
        "package": rec.get("pkg", ""),
        "grade": rec.get("grade", ""),
        "size_description": rec.get("item_size", ""),
        "low_price": rec.get("low_price", ""),
        "high_price": rec.get("high_price", ""),
        "mostly_low": rec.get("mostly_low_price", ""),
        "mostly_high": rec.get("mostly_high_price", ""),
        "demand": rec.get("demand_tone_comments", ""),
        "market_tone": rec.get("market_tone_comments", ""),
        "supply_tone": rec.get("supply_tone_comments", ""),
        "commodity_comments": rec.get("commodity_comments", ""),
    }


# ============================================================
# INCREMENTAL LOGIC
# ============================================================
def latest_existing_date(path):
    """Read the existing master CSV and return the latest report_date."""
    if not os.path.exists(path):
        return None
    latest = None
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = datetime.strptime(row["report_date"], "%m/%d/%Y").date()
                if latest is None or d > latest:
                    latest = d
            except (ValueError, KeyError):
                continue
    return latest


def load_existing(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ============================================================
# MAIN
# ============================================================
def main():
    mode = "full" if (len(sys.argv) > 1 and sys.argv[1].lower() == "full") else "incremental"

    if mode == "incremental":
        latest = latest_existing_date(OUTPUT_CSV)
        if latest is None:
            print("No existing master CSV. Switching to FULL mode.")
            mode = "full"
        else:
            start_dt = latest + timedelta(days=1)
            start = start_dt.strftime("%m/%d/%Y")
            print(f"Incremental refresh: pulling {start} onward")
    if mode == "full":
        start = FULL_START_DATE
        print(f"Full refresh: pulling from {start}")

    end = date.today().strftime("%m/%d/%Y")
    print(f"End date: {end}\n")

    existing = load_existing(OUTPUT_CSV) if mode == "incremental" else []
    existing_keys = {
        (r["report_date"], r["commodity"], r["variety"], r["size_description"])
        for r in existing
    }

    new_rows = []
    for slug_name, slug_id in REPORTS.items():
        print(f"[{slug_name}] Fetching {start} to {end}...")
        recs = fetch_range(slug_id, start, end)
        print(f"[{slug_name}] Retrieved {len(recs)} raw records")
        targets = [r for r in recs if is_target_record(r)]
        print(f"[{slug_name}] Of those, {len(targets)} are Nogales target-commodity rows")
        for r in targets:
            row = normalize(r, slug_name)
            key = (row["report_date"], row["commodity"], row["variety"],
                   row["size_description"])
            if key not in existing_keys:
                new_rows.append(row)
                existing_keys.add(key)
        time.sleep(1)

    all_rows = existing + new_rows
    if not all_rows:
        print("\nNothing to write.")
        return

    fieldnames = list(all_rows[0].keys())
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nWrote {len(all_rows)} total rows ({len(new_rows)} new) to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()

# ============================================================
# NOTES ON OTHER COMMODITIES
# ============================================================
# IX_FV110 (slug 2402) carries fruits: grapes, melons (watermelons, honeydews,
# cantaloupes). All cross at Nogales for Videxport's Sonoran portfolio.
#
# Bell peppers, asparagus, and other vegetables cross at Nogales too but
# are reported in IX_FV120 (Phoenix Shipping Point Vegetable Prices,
# slug 2403). This script pulls BOTH slugs. If 2403 is the wrong slug ID
# for your account, find the right one by visiting:
# https://mymarketnews.ams.usda.gov/marketnews-home and searching
# "Phoenix Shipping Point Vegetable Prices" — the slug ID is in the URL.
#
# Pecans (Videxport's other commodity) are NOT in USDA AMS shipping-point
# reports — they're tracked through the American Pecan Council and separate
# wholesale-market reports. Pecans need a different data source.
