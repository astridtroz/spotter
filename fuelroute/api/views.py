import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .exceptions import InputError, RoutingError
from .serializers import route_response
from .services.fuel_planner import plan_fuel
from .services.geocoding import in_usa, to_coords
from .services.routing import get_route


@csrf_exempt
@require_POST
def route_view(request):
    try:
        try:
            body = json.loads(request.body)
        except ValueError:
            raise InputError("body must be valid JSON")
        if not isinstance(body, dict) or "start" not in body or "finish" not in body:
            raise InputError('send JSON like {"start": "New York, NY", "finish": "Boston, MA"}')

        start = to_coords(body["start"])
        finish = to_coords(body["finish"])
        for name, (lat, lon) in (("start", start), ("finish", finish)):
            if not in_usa(lat, lon):
                raise InputError(f"{name} is outside the continental USA")

        route = get_route(start, finish)
        plan = plan_fuel(route.coords, route.miles)
    except InputError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except RoutingError as e:
        return JsonResponse({"error": str(e)}, status=e.status)

    return JsonResponse(route_response(body["start"], body["finish"], start, finish, route, plan))


def map_page(request):
    return render(request, "map.html")
