from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # read the csv once when the server starts, not on every request
        from .services.stations import load_stations

        try:
            load_stations()
        except FileNotFoundError:
            pass  # cities.json not generated yet, see geocode_cities.py
