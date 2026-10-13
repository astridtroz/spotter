# Fuel Route API

A Django API that takes a start and finish location in the USA and returns:

- the driving route (GeoJSON, ready to draw on a map)
- the cheapest fuel stops along it
- total gallons and total fuel cost

Vehicle assumptions: 500 mile maximum range, 10 miles per gallon.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd fuelroute
python manage.py runserver
```

No API keys and no database setup are needed. The station prices and their
coordinates are already in `fuelroute/data/`.

Run the tests:

```bash
cd fuelroute
python manage.py test
```

## Using the API

`POST /api/route/` with JSON. `start` and `finish` can each be a place name
or a `"lat,lon"` string.

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Dallas, TX"}'
```

There is also a small map page at <http://127.0.0.1:8000/> that calls the API
and draws the route and stops with Leaflet.

### Response

```json
{
  "start":  {"input": "Chicago, IL", "lat": 41.88, "lon": -87.63},
  "finish": {"input": "Dallas, TX",  "lat": 32.77, "lon": -96.79},
  "route": {
    "distance_miles": 966.9,
    "duration_hours": 14.2,
    "geometry": {"type": "LineString", "coordinates": [[-87.63, 41.88], "..."]}
  },
  "fuel_stops": [
    {
      "stop": 1,
      "station": {"id": "...", "name": "...", "address": "...", "city": "...",
                  "state": "..", "price_per_gallon": 3.079},
      "location": {"lat": 0.0, "lon": 0.0},
      "miles_from_start": 455.2,
      "miles_off_route": 3.1,
      "gallons_purchased": 47.5,
      "cost": 146.25
    }
  ],
  "fuel_summary": {
    "total_gallons": 96.69,
    "total_fuel_cost": 301.18,
    "currency": "USD",
    "origin_fill": {"gallons": 47.5, "price_per_gallon": 3.079, "cost": 146.25},
    "stop_search_corridor_miles": 20
  },
  "map_geojson": {"type": "FeatureCollection", "features": ["route line, start, finish, one point per stop"]}
}
```

`map_geojson` can be pasted into <https://geojson.io> to see the result.

### Errors

| Status | Meaning |
| ------ | ------- |
| 400 | Bad JSON, missing fields, unknown place name, or a location outside the continental USA |
| 405 | Not a POST |
| 422 | No drivable route, or a stretch of road with no fuel station within range |
| 502 | OSRM or Nominatim is unreachable |

Errors look like `{"error": "message"}`.

## How it works

1. **Resolve the two locations.** Coordinates are parsed locally (no network).
   Only place names are geocoded, with Nominatim (needs a `User-Agent`).
2. **Get the route with one OSRM call.** `overview=full&geometries=geojson`
   returns the distance, duration and the whole route shape in one response.
3. **Find stations near the route.** The route is thinned to about one point
   per mile. Every station within 20 miles of the route is a candidate, and
   its position along the route is recorded.
4. **Pick stops.** A greedy cheapest-fuel plan (see below) chooses where to buy
   and how much.
5. **Add up the cost.** Gallons bought at each stop times that stop's price.

### Fuel stop logic

The planner assumes an empty tank at the start and 475 usable miles per tank
(the 500 mile range minus a 25 mile safety reserve). At each station:

- If a cheaper station is reachable on the fuel in the tank plus a fill, buy
  only enough fuel to get there.
- A station only counts as "cheaper" if it saves at least 5 cents a gallon (`MIN_SAVING` in `fuel_planner.py`), so we don't make a stop for a tiny difference.
- If no cheaper station is in range, fill the tank and drive to the cheapest
  station in range.
- If the finish is in range, buy only what is needed to arrive.

This is the standard greedy solution to the "gas station problem" and gives
the minimum fuel cost for the stations considered. Buying just enough before a
cheaper station is what makes it cheaper than "fill up every 500 miles".

The first tank is priced as a fill at the start. There is no station at the
exact origin, so it uses the cheapest candidate in the first 100 miles of the
route. It is reported separately as `origin_fill`, not as a stop. Total
cost = gallons used (miles / 10) priced at the price they were bought at.

## Performance and API call count

| Call | When | Count |
| ---- | ---- | ----- |
| OSRM route | every new request | **1** |
| Nominatim geocode | only for place names, cached | 0 to 2 |
| Station geocoding | never at request time | **0** |

- **Stations have no coordinates in the CSV.** `geocode_cities.py` geocoded
  each unique (City, State) pair once, at 1 request per second as Nominatim
  requires, and saved the result to `data/cities.json`. That file is committed.
  At runtime no station is geocoded.
- **Data is loaded once at startup** (`ApiConfig.ready`). The CSV is joined to
  the cached coordinates, reduced to the cheapest station per city, and held in
  memory as numpy arrays. A request does no file reading.
- **Distance math is vectorized** with numpy, and the route is thinned to about
  1 mile spacing first, so a cross-country route is checked quickly.
- **Responses are cached** in memory (route by start and finish, geocode by
  name), so a repeated request makes no outside calls.

## Design decisions and tradeoffs

- **City-center coordinates for stations.** The CSV only has a city and state,
  so each station is placed at its city center. A truck stop is usually within
  a few miles of that, which is why the search corridor is 20 miles. The tradeoff
  is accuracy: a reported stop may be some miles from the exact exit. For
  production I would geocode the street addresses once, or use a stations
  dataset with coordinates.
- **Canadian rows are dropped.** The CSV has a few stations in Canadian provinces; the script skips them and the API only covers the USA. About 100 other cities Nominatim couldn't find are skipped too (`data/cities.json` only lists the ones it found).
- **Cheapest station per city.** Stations in one city share a coordinate, so
  only the cheapest can ever win. Keeping just that one shrinks the search.
- **Detours are not priced.** A station up to 20 miles off the route is treated
  as on the route. If no plan works with a 20 mile corridor, the search widens to
  50 miles before giving up.
- **OSRM public demo server.** It is free and needs no key, but it has no SLA.
  The routing URL is a setting (`OSRM_URL`), so a self-hosted OSRM can replace it.
- **Plain Django, no DRF.** One endpoint with JSON in and out does not need a
  framework on top.
- **Lower 48 only.** Locations are checked against a bounding box for the lower
  48 states and rejected otherwise.
- **Fixed vehicle.** 500 mile range, 10 mpg and the safety reserve are settings
  in `settings.py`.

## Project layout

```
fuelroute/
  manage.py
  geocode_cities.py       one-time script that built data/cities.json
  data/
    fuel.csv              fuel prices (given)
    cities.json           city coordinates (generated by the script above)
  fuelroute/              settings and urls
  api/
    views.py              thin: parse input, call services, return JSON
    serializers.py        builds the response dict
    exceptions.py         InputError (400) and RoutingError (422/502)
    services/
      geocoding.py        to_coords, Nominatim
      routing.py          the single OSRM call
      stations.py         loads the CSV + city coordinates once at startup
      fuel_planner.py     corridor search + greedy fuel plan
    templates/map.html    small Leaflet page
    tests/
```

The views only deal with HTTP. Everything that talks to an outside service or
does the actual planning lives in `services/`, so the planner can be tested
without Django or the network.

To rebuild the city cache run `python geocode_cities.py`. It takes over an hour
(1 request per second) and picks up where it left off if you stop it.

## What I would do next

- Geocode the street addresses (or use a dataset with real station coordinates)
  instead of city centers.
- Price the detour to a station that is off the route, not just filter by distance.
- Self-host OSRM. The public demo server is fine for this but has no uptime guarantee.
- Let the caller pass the vehicle range and mpg instead of hardcoding them in settings.
- Move the in-memory cache to Redis if this ever runs on more than one worker.
