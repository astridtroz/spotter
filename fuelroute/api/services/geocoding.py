import hashlib

import requests
from django.conf import settings
from django.core.cache import cache

from api.exceptions import InputError, RoutingError

# lower 48 only, OSRM can't drive to Alaska or Hawaii from the mainland
US_LAT = (24.0, 49.6)
US_LON = (-125.0, -66.5)


def in_usa(lat: float, lon: float) -> bool:
    return US_LAT[0] <= lat <= US_LAT[1] and US_LON[0] <= lon <= US_LON[1]


def to_coords(place: str) -> tuple[float, float]:
    if not isinstance(place, str) or not place.strip():
        raise InputError("start and finish must be non-empty strings")
    place = place.strip()
    try:
        lat, lon = [float(x) for x in place.split(",")]
    except ValueError:
        return geocode(place)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InputError(f"coordinates out of range: {place}")
    return lat, lon


def geocode(name: str) -> tuple[float, float]:
    key = "geo-" + hashlib.md5(name.lower().encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        return cached

    try:
        resp = requests.get(
            settings.NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError):
        raise RoutingError("geocoding service is not responding, try again", status=502)

    if not results:
        raise InputError(f"couldn't find a US location for '{name}'")
    coords = (float(results[0]["lat"]), float(results[0]["lon"]))
    cache.set(key, coords, 24 * 3600)
    return coords
