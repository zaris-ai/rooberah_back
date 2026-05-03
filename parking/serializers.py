from rest_framework import serializers
from .models import ParkingUnit, ParkingSpot, ParkingSession
from .models import WeekMenu, FoodReservation


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


class WeekMenuSerializer(serializers.ModelSerializer):
    dayOfWeek = serializers.CharField(source="day_of_week")
    weekStartDate = serializers.SerializerMethodField()

    class Meta:
        model = WeekMenu
        fields = (
            "id",
            "dayOfWeek",
            "food1",
            "food2",
            "weekStartDate",
        )

    def get_weekStartDate(self, obj):
        return obj.week_start_date.isoformat() if obj.week_start_date else None


class FoodReservationSerializer(serializers.ModelSerializer):
    telegramUserId = serializers.CharField(source="telegram_user_id")
    dayOfWeek = serializers.CharField(source="day_of_week")
    foodSlot = serializers.CharField(source="food_slot")
    portionType = serializers.CharField(source="portion_type")
    portionLabel = serializers.CharField(source="portion_label")
    portionQty = serializers.SerializerMethodField()
    reservedAt = serializers.SerializerMethodField()
    weekStartDate = serializers.SerializerMethodField()

    class Meta:
        model = FoodReservation
        fields = (
            "id",
            "telegramUserId",
            "dayOfWeek",
            "food",
            "foodSlot",
            "portionType",
            "portionLabel",
            "portionQty",
            "reservedAt",
            "weekStartDate",
        )

    def get_portionQty(self, obj):
        if obj.portion_qty is None:
            return 1
        return float(obj.portion_qty)

    def get_reservedAt(self, obj):
        return obj.reserved_at.isoformat() if obj.reserved_at else None

    def get_weekStartDate(self, obj):
        return obj.week_start_date.isoformat() if obj.week_start_date else None