from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from api.exceptions import RoutingError
from api.services import fuel_planner
from api.services.stations import Station

# a straight east-west road at latitude 40, one point per mile
MILES_PER_LON = 69.0 * np.cos(np.radians(40))


def road(miles):
    return [[-100 + i / MILES_PER_LON, 40.0] for i in range(int(miles) + 1)]


def station(mile, price, name=None, lat_offset=0.0):
    lon = -100 + mile / MILES_PER_LON
    return Station(str(mile), name or f"S{mile}", "I-80", "Town", "NE", price, 40.0 + lat_offset, lon)


def plan(stations, miles):
    lats = np.array([s.lat for s in stations])
    lons = np.array([s.lon for s in stations])
    with mock.patch.object(fuel_planner, "load_stations", return_value=stations), \
         mock.patch.object(fuel_planner, "station_coords", return_value=(lats, lons)):
        return fuel_planner.plan_fuel(road(miles), float(miles))


class PlanFuelTests(SimpleTestCase):
    def test_short_trip_has_no_stops(self):
        p = plan([station(10, 3.00)], 200)
        self.assertEqual(p.stops, [])
        self.assertAlmostEqual(p.total_gallons, 20, places=1)
        self.assertAlmostEqual(p.total_cost, 60, places=1)

    def test_gallons_match_distance(self):
        p = plan([station(m, 3.50) for m in (0, 300, 450, 700, 900, 1100)], 1200)
        self.assertGreaterEqual(len(p.stops), 2)
        self.assertAlmostEqual(p.total_gallons, 120, delta=0.5)

    def test_never_drives_past_range(self):
        p = plan([station(m, 3.0 + (m % 7) * 0.1) for m in range(0, 1500, 60)], 1500)
        spots = [0] + [s.candidate.miles_from_start for s in p.stops] + [1500]
        for a, b in zip(spots, spots[1:]):
            self.assertLessEqual(b - a, 475.5)

    def test_buys_more_where_it_is_cheap(self):
        p = plan([station(5, 3.00), station(200, 4.50), station(400, 2.50), station(800, 3.90)], 1000)
        cheap = next(s for s in p.stops if s.candidate.station.name == "S400")
        self.assertGreater(cheap.gallons, 30)

    def test_ignores_stations_far_from_route(self):
        far = station(250, 1.00, name="FAR", lat_offset=1.0)  # about 69 miles away
        near = station(250, 4.00, name="NEAR")
        names = [s.candidate.station.name for s in plan([station(5, 3.0), far, near], 700).stops]
        self.assertIn("NEAR", names)
        self.assertNotIn("FAR", names)

    def test_gap_with_no_station_raises(self):
        with self.assertRaises(RoutingError):
            plan([station(5, 3.0), station(900, 3.0)], 1000)

    def test_total_cost_is_sum_of_purchases(self):
        p = plan([station(m, 3.0 + (m % 5) * 0.2) for m in range(0, 1300, 80)], 1300)
        self.assertAlmostEqual(p.total_cost, sum(x.gallons * x.price for x in p.purchases), places=6)
