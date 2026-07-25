from rest_framework import serializers
from .models import Ticket, TicketReply, TicketSenderType, SignUpSlider, CustomerScreenSlide
from find_worker_config.model_choice import OrderStatus, UserDefault
from .models import AdminWallet
from django.db import transaction
from account.models import ServiceProviderProfile
from django.utils import timezone

# -------------------
# Ticket Reply Serializer
class TicketReplySerializer(serializers.ModelSerializer):
    reply_sender_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TicketReply
        fields = ["id", "reply_sender", "reply_sender_name", "sender_type", "message", "attachment", "created_at"]
        read_only_fields = ["id", "reply_sender", "reply_sender_name", "sender_type", "created_at"]

    def get_reply_sender_name(self, obj):
        return obj.reply_sender.username if obj.reply_sender else None

    def create(self, validated_data):
        with transaction.atomic():
            request = self.context["request"]
            user = request.user
            sender_type = user.role
            print("sender_type: ", sender_type)
            if not sender_type:
                raise Exception("Sender Type Missing!")
            
            validated_data["reply_sender"] = user
            validated_data["sender_type"] = sender_type
            return super().create(validated_data)
# -------------------

# -------------------
# Ticket Serializer
class TicketSerializer(serializers.ModelSerializer):
    replies = TicketReplySerializer(many=True, read_only=True)
    user_name = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Ticket
        fields = [
            "id", "user", "user_name", "user_profile_type", "subject", "order",
            "status", "summary", "attachment", "last_message", "last_reply_at",
            "created_at", "updated_at", "replies"
        ]
        read_only_fields = ["id", "last_message", "last_reply_at", "created_at", "updated_at", "replies"]

    def get_user_name(self, obj):
        return obj.user.username if obj.user else None

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["user"] = user
        return super().create(validated_data)
# -------------------

# -------------------
# Ticket Status Update Serializer
class TicketStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["status"]
# -------------------


# -------------------
# Helper List & Details Serializer
class ServiceCategoryField(serializers.ListField):
    child = serializers.IntegerField()

    def to_representation(self, value):
        return [
            {"id": c.id, "title": c.title} for c in value.all()
        ]

class HelperSerializer(serializers.ModelSerializer):
    service_category = ServiceCategoryField(required=True)
    company_name = serializers.CharField(required=True)
    hourly_rate = serializers.DecimalField(required=True, max_digits=9, decimal_places=2)
    min_booking_hours = serializers.DecimalField(required=True, max_digits=9, decimal_places=2)
    portfolio = serializers.SerializerMethodField(read_only=True)
    reviews_and_ratings = serializers.SerializerMethodField(read_only=True)
    office_location = serializers.SerializerMethodField(read_only=True)
    distance_km = serializers.FloatField(read_only=True)
    strike_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ServiceProviderProfile
        fields = ["id", "company_name", "logo", "details", "hourly_rate", "min_booking_hours", "office_location", "strike_count", "account_status", "availability_status", "is_verified", "complete_rate", "total_jobs", "rating", "distance_km", "service_category", "portfolio", "reviews_and_ratings"]
        read_only_fields = ["office_location", "strike_count", "account_status", "is_verified", "complete_rate", "total_jobs", "rating"]
    
    def get_strike_count(self, obj):
        now = timezone.now()
        obj.strikes.filter(
            is_active=True,
            expired_at__lte=now
        ).update(is_active=False)
        return obj.strikes.filter(
            is_active=True
        ).count()

    def get_reviews_and_ratings(self, obj):
        request = self.context.get("request")
        return [
            {
                "id": review.id,
                "customer": {
                    "id": review.customer.id,
                    "first_name": review.customer.user.first_name,
                    "last_name": review.customer.user.last_name,
                    "photo": request.build_absolute_uri(review.customer.user.photo.url) if review.customer.user.photo else None,
                },
                "rating": review.rating,
                "review": review.review,
                "created_at": review.created_at
            }
            # for review in obj.provider_reviews.all()
            for review in obj.provider_reviews.filter(send_by=UserDefault.CUSTOMER)
        ]

    def get_portfolio(self, obj):
        request = self.context.get("request")
        return [
            {
                "id": order.id,
                "title": order.title,
                "description": order.description,
                "working_date": order.working_date,
                "picture": request.build_absolute_uri(order.order_attachments.first().file.url) if order.order_attachments.exists() else None
            }
            for order in obj.orders_as_provider.filter(status=OrderStatus.COMPLETED).order_by("-working_date")
        ]
    
    def get_logo(self, obj):
        logo = getattr(obj, "logo", None)
        if logo:
            request = self.context.get("request")
            return request.build_absolute_uri(logo.url) if request else logo.url
        return None

    def get_service_category(self, obj):
        return [
            {
                "id": cat.id,
                "title": cat.title
            }
            for cat in obj.service_category.all()
        ]

    def get_office_location(self, obj):
        office = obj.office_location
        if not office:
            return None
        return {
            "id": office.id,
            "address_line": office.address_line,
            "city": office.city,
            "lat": office.lat,
            "lng": office.lng,
        }

# -------------------


# -------------------
# Admin Wallet Serializer
class AdminWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminWallet
        fields = ["current_balance", "payment_balance", "hold_balance", "total_withdraw"]
# -------------------

# -------------------
# Singup Slider Serializer
class SignUpSliderSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignUpSlider
        fields = "__all__"
# -------------------

# -------------------
# Customer Screen Slider Serializer
class CustomerScreenSlideSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerScreenSlide
        fields = "__all__"
# -------------------


