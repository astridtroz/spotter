import hashlib
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from api.exceptions import RoutingError

METERS_PER_MILE = 1609.344


@dataclass
class Route:
    miles: float
    hours: float
    coords: list  # GeoJSON order: [lon, lat]


def get_route(start: tuple[float, float], finish: tuple[float, float]) -> Route:
    # one OSRM call gives us distance, duration and the full geometry
    key = "route-" + hashlib.md5(f"{start}{finish}".encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        return cached

    (lat1, lon1), (lat2, lon2) = start, finish
    url = f"{settings.OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"  # lon first
    try:
        resp = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=20,
        )
    except requests.RequestException:
        raise RoutingError("routing service is not responding, try again", status=502)
    if resp.status_code >= 500:
        raise RoutingError("routing service is not responding, try again", status=502)

    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError("no drivable route between those locations")

    best = data["routes"][0]
    route = Route(
        miles=best["distance"] / METERS_PER_MILE,
        hours=best["duration"] / 3600,
        coords=best["geometry"]["coordinates"],
    )
    cache.set(key, route, 3600)
    return route
