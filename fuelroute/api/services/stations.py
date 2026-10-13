import csv
import json
import threading
from dataclasses import dataclass

import numpy as np
from django.conf import settings


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    address: str
    city: str
    state: str
    price: float
    lat: float
    lon: float


_lock = threading.Lock()
_stations: list[Station] | None = None
_lat_lon: tuple[np.ndarray, np.ndarray] | None = None


def load_stations() -> list[Station]:
    """Cheapest station per city, placed at the city's cached coordinates."""
    global _stations, _lat_lon
    if _stations is not None:
        return _stations

    with _lock:
        if _stations is not None:
            return _stations

        with open(settings.CITIES_JSON_PATH, encoding="utf-8") as f:
            cities = json.load(f)

        cheapest: dict[tuple[str, str], Station] = {}
        with open(settings.FUEL_CSV_PATH, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                city, state = row["City"].strip(), row["State"].strip()
                coords = cities.get(f"{city}|{state}")
                if not coords:
                    continue  # nominatim couldn't find this city
                price = float(row["Retail Price"])
                current = cheapest.get((city, state))
                if current is None or price < current.price:
                    cheapest[(city, state)] = Station(
                        row["OPIS Truckstop ID"].strip(), row["Truckstop Name"].strip(),
                        row["Address"].strip(), city, state, price, coords[0], coords[1],
                    )

        stations = list(cheapest.values())
        _lat_lon = (np.array([s.lat for s in stations]), np.array([s.lon for s in stations]))
        _stations = stations
        return _stations


def station_coords() -> tuple[np.ndarray, np.ndarray]:
    load_stations()
    return _lat_lon
