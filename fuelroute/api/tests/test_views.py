import json
from unittest import mock

from django.test import TestCase

from api import views
from api.exceptions import InputError, RoutingError
from api.services.fuel_planner import FuelPlan, Purchase
from api.services.geocoding import to_coords
from api.services.routing import Route


class RouteViewTests(TestCase):
    def post(self, data):
        body = data if isinstance(data, str) else json.dumps(data)
        return self.client.post("/api/route/", data=body, content_type="application/json")

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/api/route/").status_code, 405)

    def test_bad_json(self):
        self.assertEqual(self.post("not json").status_code, 400)

    def test_missing_finish(self):
        r = self.post({"start": "Boston"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.json())

    def test_outside_usa(self):
        r = self.post({"start": "51.5,-0.12", "finish": "42.36,-71.05"})  # london
        self.assertEqual(r.status_code, 400)
        self.assertIn("outside", r.json()["error"])

    def test_success(self):
        route = Route(miles=215.0, hours=4.0, coords=[[-74.0, 40.7], [-71.0, 42.3]])
        plan = FuelPlan([Purchase(None, 21.5, 3.0)], corridor_miles=20)
        with mock.patch.object(views, "get_route", return_value=route), \
             mock.patch.object(views, "plan_fuel", return_value=plan):
            r = self.post({"start": "40.7,-74.0", "finish": "42.3,-71.0"})

        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["route"]["distance_miles"], 215.0)
        self.assertEqual(data["fuel_stops"], [])
        self.assertEqual(data["fuel_summary"]["total_fuel_cost"], 64.5)
        self.assertEqual(data["map_geojson"]["type"], "FeatureCollection")

    def test_unroutable(self):
        with mock.patch.object(views, "get_route", side_effect=RoutingError("no drivable route")):
            r = self.post({"start": "40.7,-74.0", "finish": "42.3,-71.0"})
        self.assertEqual(r.status_code, 422)


class ToCoordsTests(TestCase):
    def test_coordinates_skip_the_network(self):
        with mock.patch("api.services.geocoding.requests.get") as get:
            self.assertEqual(to_coords("40.7, -74.0"), (40.7, -74.0))
            get.assert_not_called()

    def test_place_name_is_geocoded(self):
        resp = mock.Mock()
        resp.json.return_value = [{"lat": "42.36", "lon": "-71.05"}]
        with mock.patch("api.services.geocoding.requests.get", return_value=resp) as get:
            self.assertEqual(to_coords("Boston, MA (test)"), (42.36, -71.05))
            get.assert_called_once()

    def test_blank_input(self):
        with self.assertRaises(InputError):
            to_coords("   ")
