from django.urls import path
from . import views

urlpatterns = [
    path("units/", views.list_units, name="parking-units"),
    path("units/<int:unit_id>/spots/", views.list_spots, name="parking-spots"),
    path("sessions/active/", views.active_session, name="parking-active-session"),
    path("spots/<int:spot_id>/enter/", views.enter_spot, name="parking-enter"),
    path("sessions/exit/", views.exit_active_session, name="parking-exit"),
]