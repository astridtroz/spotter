from .services.fuel_planner import FuelPlan
from .services.routing import Route


def route_response(start_text: str, finish_text: str, start: tuple, finish: tuple, route: Route, plan: FuelPlan) -> dict:
    stops = []
    features = [
        {"type": "Feature", "properties": {"kind": "route"},
         "geometry": {"type": "LineString", "coordinates": route.coords}},
        {"type": "Feature", "properties": {"kind": "start", "label": start_text},
         "geometry": {"type": "Point", "coordinates": [start[1], start[0]]}},
        {"type": "Feature", "properties": {"kind": "finish", "label": finish_text},
         "geometry": {"type": "Point", "coordinates": [finish[1], finish[0]]}},
    ]

    for n, p in enumerate(plan.stops, start=1):
        st = p.candidate.station
        stops.append({
            "stop": n,
            "station": {
                "id": st.station_id, "name": st.name, "address": st.address,
                "city": st.city, "state": st.state, "price_per_gallon": round(st.price, 3),
            },
            "location": {"lat": st.lat, "lon": st.lon},
            "miles_from_start": round(p.candidate.miles_from_start, 1),
            "miles_off_route": round(p.candidate.miles_off_route, 1),
            "gallons_purchased": round(p.gallons, 2),
            "cost": round(p.cost, 2),
        })
        features.append({
            "type": "Feature",
            "properties": {"kind": "fuel_stop", "stop": n, "name": st.name,
                           "price_per_gallon": round(st.price, 3)},
            "geometry": {"type": "Point", "coordinates": [st.lon, st.lat]},
        })

    first = plan.origin_fill
    return {
        "start": {"input": start_text, "lat": start[0], "lon": start[1]},
        "finish": {"input": finish_text, "lat": finish[0], "lon": finish[1]},
        "route": {
            "distance_miles": round(route.miles, 1),
            "duration_hours": round(route.hours, 2),
            "geometry": {"type": "LineString", "coordinates": route.coords},
        },
        "fuel_stops": stops,
        "fuel_summary": {
            "total_gallons": round(plan.total_gallons, 2),
            "total_fuel_cost": round(plan.total_cost, 2),
            "currency": "USD",
            "origin_fill": first and {
                "gallons": round(first.gallons, 2),
                "price_per_gallon": round(first.price, 3),
                "cost": round(first.cost, 2),
            },
            "stop_search_corridor_miles": plan.corridor_miles,
        },
        "map_geojson": {"type": "FeatureCollection", "features": features},
    }
