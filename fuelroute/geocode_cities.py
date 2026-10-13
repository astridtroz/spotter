"""Geocode every unique (City, State) in fuel.csv once and save it to data/cities.json.

Nominatim allows 1 request per second so this takes a while. It skips cities
already in the file, so it's safe to stop and re-run.
"""
import csv
import json
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE / "data" / "fuel.csv"
OUT_PATH = BASE / "data" / "cities.json"
HEADERS = {"User-Agent": "fuelroute-takehome/1.0 (one-time city geocoding)"}


def unique_cities():
    cities = set()
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            cities.add((row["City"].strip(), row["State"].strip()))
    return sorted(cities)


def geocode(city, state, session):
    params = {"city": city, "state": state, "country": "US", "format": "json", "limit": 1}
    for attempt in range(3):
        try:
            r = session.get("https://nominatim.openstreetmap.org/search", params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
                return None
            time.sleep(5 * (attempt + 1))
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    return None


def main():
    cities = unique_cities()
    print(f"{len(cities)} unique (city, state) pairs")
    cache = json.loads(OUT_PATH.read_text()) if OUT_PATH.exists() else {}
    session = requests.Session()
    done = 0
    for city, state in cities:
        key = f"{city}|{state}"
        if key in cache:
            continue
        cache[key] = geocode(city, state, session)  # None if nominatim finds nothing
        done += 1
        if done % 25 == 0:
            OUT_PATH.write_text(json.dumps(cache, indent=0, sort_keys=True))
            print(f"{len(cache)}/{len(cities)}", flush=True)
        time.sleep(1.05)  # Nominatim usage policy: max 1 request/second
    OUT_PATH.write_text(json.dumps(cache, indent=0, sort_keys=True))
    missing = sum(1 for v in cache.values() if v is None)
    print(f"done. {len(cache)} cities, {missing} not found")


if __name__ == "__main__":
    main()
