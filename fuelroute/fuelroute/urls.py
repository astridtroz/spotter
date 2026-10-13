from django.contrib import admin
from django.urls import path

from api.views import map_page, route_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/route/", route_view),
    path("", map_page),
]
