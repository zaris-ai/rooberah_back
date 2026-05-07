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
    occupiedByTelegramUserId = serializers.SerializerMethodField()
    occupiedByUsername = serializers.SerializerMethodField()
    occupiedByFirstName = serializers.SerializerMethodField()
    occupiedByLastName = serializers.SerializerMethodField()

    class Meta:
        model = ParkingSpot
        fields = [
            "id",
            "unitId",
            "code",
            "row",
            "col",
            "state",
            "occupiedByTelegramUserId",
            "occupiedByUsername",
            "occupiedByFirstName",
            "occupiedByLastName",
        ]

    def _get_session_data(self, spot):
        active_sessions = self.context.get("active_sessions", {})
        return active_sessions.get(spot.id)

    def get_state(self, spot):
        session_data = self._get_session_data(spot)
        current_user_id = self.context.get("telegram_user_id")

        if not session_data:
            return "free"

        owner_id = session_data.get("telegram_user_id")

        if str(owner_id) == str(current_user_id):
            return "mine"

        return "occupied"

    def get_occupiedByTelegramUserId(self, spot):
        session_data = self._get_session_data(spot)

        if not session_data:
            return None

        owner_id = session_data.get("telegram_user_id")
        return str(owner_id) if owner_id else None

    def get_occupiedByUsername(self, spot):
        session_data = self._get_session_data(spot)

        if not session_data:
            return None

        return session_data.get("username")

    def get_occupiedByFirstName(self, spot):
        session_data = self._get_session_data(spot)

        if not session_data:
            return None

        return session_data.get("first_name")

    def get_occupiedByLastName(self, spot):
        session_data = self._get_session_data(spot)

        if not session_data:
            return None

        return session_data.get("last_name")
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
            "food3",
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