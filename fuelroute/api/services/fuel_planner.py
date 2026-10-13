from dataclasses import dataclass

import numpy as np
from django.conf import settings

from api.exceptions import RoutingError

from .stations import Station, load_stations, station_coords

MILES_PER_DEG = 69.0


@dataclass
class Candidate:
    station: Station
    miles_from_start: float  # where along the route the station sits
    miles_off_route: float


@dataclass
class Purchase:
    candidate: Candidate | None  # None means the fill at the start
    gallons: float
    price: float

    @property
    def cost(self) -> float:
        return self.gallons * self.price


@dataclass
class FuelPlan:
    purchases: list[Purchase]
    corridor_miles: float

    @property
    def stops(self) -> list[Purchase]:
        return [p for p in self.purchases if p.candidate is not None]

    @property
    def origin_fill(self) -> Purchase | None:
        return next((p for p in self.purchases if p.candidate is None), None)

    @property
    def total_gallons(self) -> float:
        return sum(p.gallons for p in self.purchases)

    @property
    def total_cost(self) -> float:
        return sum(p.cost for p in self.purchases)


def thin_route(coords: list, spacing: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Keep roughly one point per mile. Returns (points as lat/lon, miles from start)."""
    pts = np.asarray(coords, dtype=float)[:, ::-1]
    dy = np.diff(pts[:, 0]) * MILES_PER_DEG
    mid_lat = np.radians((pts[:-1, 0] + pts[1:, 0]) / 2)
    dx = np.diff(pts[:, 1]) * MILES_PER_DEG * np.cos(mid_lat)
    miles = np.concatenate([[0.0], np.cumsum(np.hypot(dx, dy))])

    keep = [0]
    for i in range(1, len(pts) - 1):
        if miles[i] - miles[keep[-1]] >= spacing:
            keep.append(i)
    keep.append(len(pts) - 1)
    return pts[keep], miles[keep]


def find_candidates(pts: np.ndarray, miles: np.ndarray, corridor: float) -> list[Candidate]:
    stations = load_stations()
    lats, lons = station_coords()

    # cheap bounding box cut first so we only do distance math on nearby cities
    pad = corridor / MILES_PER_DEG + 0.3
    near = np.where(
        (lats >= pts[:, 0].min() - pad) & (lats <= pts[:, 0].max() + pad)
        & (lons >= pts[:, 1].min() - pad * 1.5) & (lons <= pts[:, 1].max() + pad * 1.5)
    )[0]

    # flat-earth approximation is fine at these distances
    cos_lat = np.cos(np.radians(pts[:, 0].mean()))
    route_y = pts[:, 0] * MILES_PER_DEG
    route_x = pts[:, 1] * MILES_PER_DEG * cos_lat

    found = []
    for i in range(0, len(near), 200):
        chunk = near[i:i + 200]
        sy = lats[chunk] * MILES_PER_DEG
        sx = lons[chunk] * MILES_PER_DEG * cos_lat
        d2 = (sy[:, None] - route_y[None, :]) ** 2 + (sx[:, None] - route_x[None, :]) ** 2
        closest = d2.argmin(axis=1)
        dist = np.sqrt(d2[np.arange(len(chunk)), closest])
        for k, idx in enumerate(chunk):
            if dist[k] <= corridor:
                found.append(Candidate(stations[idx], float(miles[closest[k]]), float(dist[k])))

    found.sort(key=lambda c: c.miles_from_start)
    return found


def start_price(candidates: list[Candidate]) -> float | None:
    # no station sits exactly at the origin, so price the first tank at the
    # cheapest one in the first 100 miles
    early = [c.station.price for c in candidates if c.miles_from_start <= 100]
    if early:
        return min(early)
    return candidates[0].station.price if candidates else None


def greedy_plan(candidates: list[Candidate], total_miles: float, max_range: float, first_price: float):
    # node 0 = start, last node = finish, stations in between
    pos = [0.0] + [c.miles_from_start for c in candidates] + [total_miles]
    price = [first_price] + [c.station.price for c in candidates] + [0.0]
    last = len(pos) - 1

    fuel = 0.0  # in miles of range
    i = 0
    bought = []  # (node, miles of fuel)
    while i < last:
        reachable = [j for j in range(i + 1, last + 1) if pos[j] - pos[i] <= max_range]
        if not reachable:
            raise RoutingError(f"no fuel station within {max_range:.0f} miles after mile {pos[i]:.0f}")

        cheaper = next((j for j in reachable if j < last and price[j] < price[i]), None)
        if pos[last] - pos[i] <= max_range and (cheaper is None or pos[last] < pos[cheaper]):
            nxt = last
            buy = max(0.0, pos[last] - pos[i] - fuel)
        elif cheaper is not None:
            nxt = cheaper
            buy = max(0.0, pos[cheaper] - pos[i] - fuel)
        else:
            # nothing cheaper ahead, fill up and go to the cheapest stop in range
            nxt = min(reachable, key=lambda j: (price[j], -pos[j]))
            buy = max_range - fuel

        if buy > 1e-9:
            bought.append((i, buy))
        fuel += buy - (pos[nxt] - pos[i])
        i = nxt

    mpg = settings.VEHICLE_MPG
    return [
        Purchase(None if node == 0 else candidates[node - 1], miles / mpg, price[node])
        for node, miles in bought
    ]


def plan_fuel(coords: list, total_miles: float) -> FuelPlan:
    max_range = settings.VEHICLE_RANGE_MILES - settings.SAFETY_MARGIN_MILES
    pts, miles = thin_route(coords)
    miles = miles * (total_miles / miles[-1]) if miles[-1] else miles  # match OSRM's road distance

    error = None
    for corridor in (settings.CORRIDOR_MILES, settings.CORRIDOR_MILES_FALLBACK):
        candidates = find_candidates(pts, miles, corridor)
        first_price = start_price(candidates)
        if first_price is None:
            continue
        try:
            purchases = greedy_plan(candidates, total_miles, max_range, first_price)
        except RoutingError as e:
            error = e
            continue
        return FuelPlan(purchases, corridor)

    raise error or RoutingError("no fuel stations found near this route")
