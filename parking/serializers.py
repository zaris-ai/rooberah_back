from rest_framework import serializers
from .models import ParkingUnit, ParkingSpot, ParkingSession


class ParkingUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkingUnit
        fields = ["id", "title"]


class ParkingSpotSerializer(serializers.ModelSerializer):
    unitId = serializers.IntegerField(source="unit_id", read_only=True)
    state = serializers.SerializerMethodField()

    class Meta:
        model = ParkingSpot
        fields = ["id", "unitId", "code", "row", "col", "state"]

    def get_state(self, spot):
        active_sessions = self.context.get("active_sessions", {})
        current_user_id = self.context.get("telegram_user_id")

        owner_id = active_sessions.get(spot.id)

        if not owner_id:
            return "free"

        if str(owner_id) == str(current_user_id):
            return "mine"

        return "occupied"


class ActiveParkingSessionSerializer(serializers.ModelSerializer):
    spotCode = serializers.CharField(source="spot.code")
    unitTitle = serializers.CharField(source="unit.title")
    enteredAt = serializers.DateTimeField(source="entered_at")

    class Meta:
        model = ParkingSession
        fields = ["spotCode", "unitTitle", "enteredAt"]