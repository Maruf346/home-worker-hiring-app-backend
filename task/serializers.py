from .models import ServiceCategory, ServiceSubCategory, Order, ReviewAndRating, PaymentTransaction, ServiceSubCategory, OrderRefundRequest, OrderPaymentStatus, OrderAttachment, OrderChangesRequest
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from find_worker_config.model_choice import OrderStatus, UserDefault, OrderChangesRequestStatus, ChangesRequestType, HelperSlotExceptionType, ReviewRatingChoice, OrderChangeRequestAction
from account.models import ServiceProviderProfile, HelperSlotException
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework import serializers
from datetime import datetime, timedelta
from django.db import transaction
from account.utils import generate_otp
from math import radians, cos, sin, asin, sqrt
from core.services.slot_status_engine import SlotStatusEngine
from django.utils import timezone
import requests
from account.models import CustomerProfile

# ============================================================
# Category Serializers Section ===================
class ServiceSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceSubCategory
        fields = "__all__"

class ServiceCategorySerializer(serializers.ModelSerializer):
    subcategory = ServiceSubCategorySerializer(many=True, read_only=True)

    class Meta:
        model = ServiceCategory
        fields = "__all__"

# Category Serializers Section ===================
# ============================================================



# ==========================================================================================
# =================== Order Section Start===================================
class CustomerInfoSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    photo = serializers.ImageField(source="user.photo", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["id","username","full_name","email","phone","photo", "rating","total_orders","completed_orders","is_verified"]

class ProviderInfoSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    photo = serializers.ImageField(source="user.photo", read_only=True)
    company_logo = serializers.ImageField(source="logo", read_only=True)

    class Meta:
        model = ServiceProviderProfile
        fields = ["id", "company_name", "company_logo", "logo", "username", "full_name", "email", "phone", "photo", "hourly_rate", "rating", "availability_status", "is_verified",]

class OrderAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderAttachment
        fields = ["id", "file"]
    
    def get_file(self, obj):
        file = getattr(obj, "file", None)
        if file:
            request = self.context.get("request")
            return request.build_absolute_uri(file.url) if request else file.url
        return None

class OrderSerializerAll(serializers.ModelSerializer):
    provider_id = serializers.IntegerField(write_only=True)
    attachments = serializers.ListField(child=serializers.FileField(), write_only=True, required=False)
    
    customer = CustomerInfoSerializer(read_only=True)
    provider = ProviderInfoSerializer(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    working_start_time = serializers.TimeField(input_formats=["%I:%M %p", "%H:%M"])
    working_hour = serializers.IntegerField(required=False)
    
    # -------- Order Property Fields --------
    end_time = serializers.ReadOnlyField()
    end_datetime = serializers.ReadOnlyField()

    is_provider_review = serializers.ReadOnlyField()
    is_customer_review = serializers.ReadOnlyField()
    is_cancel_request = serializers.ReadOnlyField()
    cancel_request_by = serializers.ReadOnlyField()
    cancel_request_accept_by = serializers.ReadOnlyField()

    changes_request_pending = serializers.ReadOnlyField()
    
    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ["status", "payment_status", "accepted_at", "started_at", "completed_at", "created_at", "updated_at"]
    
    def to_representation(self, instance):
        context = self.context
        profile_type = context.get("profile_type")
        
        data = super().to_representation(instance)
        attachments_list = OrderAttachmentSerializer(instance.order_attachments, many=True, context=self.context).data
        data["attachments"] = attachments_list
        
        customer_review = instance.order_review.filter(send_by=UserDefault.CUSTOMER).first()
        data["customer_review"] = ReviewAndRatingSerializer(customer_review, context=self.context).data if customer_review else None
        provider_review = instance.order_review.filter(send_by=UserDefault.PROVIDER).first()
        data["provider_review"] = ReviewAndRatingSerializer(provider_review, context=self.context).data if provider_review else None

        if profile_type == UserDefault.PROVIDER:
            data.pop("confirmation_OTP")
        
        return data

    def validate_provider_id(self, value):
        if not ServiceProviderProfile.objects.filter(id=value).exists():
            raise serializers.ValidationError(_("Provider not found"))
        return value

    def validate(self, attrs):        
        provider = ServiceProviderProfile.objects.get(id=attrs.get("provider_id"))
        date = attrs.get("working_date")
        time = attrs.get("working_start_time")
        working_hour = attrs.get("working_hour", 1)

        if not date and not time:
            raise serializers.ValidationError(_("Date or time must be provided."))

        slot_start_dt = datetime.combine(date, time)
        slot_end_dt = slot_start_dt + timedelta(hours=working_hour)

        # SLOT ENGINE CALL
        slot_engine = SlotStatusEngine()
        slot_status = slot_engine.get_status(
            provider=provider,
            date_obj=date,
            slot_start=slot_start_dt,
            slot_end=slot_end_dt
        )

        if slot_status != HelperSlotExceptionType.AVAILABLE:
            status_map = {
                "BOOKED": _("Already booked"),
                "UNAVAILABLE": _("Provider unavailable"),
                "FREEZED": _("Temporarily locked"),
            }
            raise serializers.ValidationError({
                "slot": status_map.get(slot_status, _("Not available"))
            })
        return attrs
    
    def create(self, validated_data):
        request = self.context.get("request")
        attachments = validated_data.pop("attachments", [])

        validated_data["customer"] = request.user.customer_profile
        validated_data["provider"] = ServiceProviderProfile.objects.get(id=validated_data.pop("provider_id"))

        order = Order.objects.create(
            **validated_data
        )
        for file in attachments:
            OrderAttachment.objects.create(order=order, file=file)
        return order

# =================================================================
class CounterSerializer(serializers.Serializer):
    budget = serializers.DecimalField(max_digits=9, decimal_places=2)
    message = serializers.CharField(required=False)

    def save(self, **kwargs):
        budget = self.validated_data.get("budget")
        message = self.validated_data.get("message")
        order = kwargs.get("order")
        profile_type = kwargs.get("profile_type")
        
        if order.status != OrderStatus.PENDING:
            raise Exception(_("Order is already {}").format(order.status))
        if OrderChangesRequest.objects.filter(order=order, status=OrderChangesRequestStatus.NO_RESPONSE).exists():
            raise ValueError(_("One Changes Request not response!"))
        if OrderChangesRequest.objects.filter(order=order, request_by=profile_type, changes_type=ChangesRequestType.COUNTER).exists():
            raise ValueError(_("Only One counter each side!"))
        if profile_type == UserDefault.CUSTOMER and not OrderChangesRequest.objects.filter(order=order, request_by=UserDefault.PROVIDER).exists():
            raise ValueError(_("Provider can send first counter."))
        with transaction.atomic():
            changes_object = OrderChangesRequest.objects.create(
                order=order,
                status=OrderChangesRequestStatus.ACCEPT,
                request_by=profile_type,
                changes_type=ChangesRequestType.COUNTER,
                changes_data={
                    "budget": f"{budget}",
                    "message": message
                }
            )
            self.changes_object = changes_object
            
            if profile_type == UserDefault.PROVIDER:
                order_change_action = OrderChangeRequestAction.PROVIDER_COUNTER_SEND
            elif profile_type == UserDefault.CUSTOMER:
                order_change_action = OrderChangeRequestAction.CUSTOMER_COUNTER_SEND
            
            order.amount = budget
            order.order_change_action = order_change_action
            order.save()
            return order
    
    def get_changes_object(self):
        return self.changes_object

class SetHourSerializer(serializers.Serializer):
    set_hour = serializers.IntegerField(required=True,error_messages={
            "required": _("Hour is required"),
            "invalid": _("Hour must be a valid number"),
            "null": _("Hour cannot be empty")
        })
    message = serializers.CharField(required=False)

    def generate_hour_slots(self, start_dt, hours):
        slots = []
        current = start_dt

        for _ in range(hours):
            end = current + timedelta(hours=1)
            slots.append((current, end))
            current = end

        return slots

    def validate(self, attrs):
        order = self.context.get("order")
        if not order:
            raise serializers.ValidationError({
                "order": _("Order is required in serializer context")
            })
        
        slot_exception = HelperSlotException.objects.filter(order=order).first()
        if slot_exception:
            slot_exception.is_active = False
            slot_exception.save()
        
        set_hour = attrs.get("set_hour") or order.working_hour
        date = order.working_date
        time = order.working_start_time

        if not date and not time and not set_hour:
            raise serializers.ValidationError(_("Date or time and Working Hour must be provided."))

        slot_start_dt = datetime.combine(date, time)
        # slot_end_dt = slot_start_dt + timedelta(hours=set_hour)

        slots = self.generate_hour_slots(slot_start_dt, set_hour)

        # SLOT ENGINE CALL
        status_map = {
            "BOOKED": _("Already booked"),
            "UNAVAILABLE": _("Provider unavailable"),
            "FREEZED": _("Temporarily locked"),
        }
        slot_engine = SlotStatusEngine()
        for slot_start, slot_end in slots:
            slot_status = slot_engine.get_status(
                provider=order.provider,
                date_obj=date,
                slot_start=slot_start,
                slot_end=slot_end
            )
            if slot_status in [HelperSlotExceptionType.BOOKED, HelperSlotExceptionType.FREEZED]:
                if slot_exception:
                    slot_exception.is_active = True
                    slot_exception.save()
                raise serializers.ValidationError({
                    "slot": status_map.get(slot_status, _("Not available"))
                })
        
        if slot_exception:
            slot_exception.is_active = True
            slot_exception.save()
        return attrs

    def get_changes_object(self):
        return self.changes_object
    
    def save(self, **kwargs):
        available_status = [OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS]
        hour = self.validated_data.get("set_hour")
        message = self.validated_data.get("message")
        order = kwargs.get("order")
        if order.status not in available_status:
            raise ValueError(_("Set Hour not accept when order is {}").format(order.status))
        
        with transaction.atomic():
            self.changes_object = OrderChangesRequest.objects.create(
                order=order,
                status=OrderChangesRequestStatus.ACCEPT,
                request_by=UserDefault.PROVIDER,
                changes_type=ChangesRequestType.SET_HOUR,
                changes_data={
                    "hour": f"{hour}",
                    "message": message
                }
            )
            order.working_hour = hour
            order.save(update_fields=["working_hour"])
            return order

class ProposeNewTimeSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    time = serializers.TimeField(input_formats=["%I:%M %p", "%H:%M"])
    message = serializers.CharField(required=False)

    def validate(self, attrs):
        order = self.context.get("order")
        if not order:
            raise serializers.ValidationError({
                "order": _("Order is required in serializer context")
            })
        
        date = attrs.get("date") or order.working_date
        time = attrs.get("time") or order.working_start_time

        if not date and not time:
            raise serializers.ValidationError(_("Date or time must be provided."))

        slot_start_dt = datetime.combine(date, time)
        slot_end_dt = slot_start_dt + timedelta(hours=order.working_hour)

        # SLOT ENGINE CALL
        slot_engine = SlotStatusEngine()
        slot_status = slot_engine.get_status(
            provider=order.provider,
            date_obj=date,
            slot_start=slot_start_dt,
            slot_end=slot_end_dt
        )

        if slot_status != HelperSlotExceptionType.AVAILABLE:
            status_map = {
                "BOOKED": _("Already booked"),
                "UNAVAILABLE": _("Provider unavailable"),
                "FREEZED": _("Temporarily locked"),
            }
            raise serializers.ValidationError({
                "slot": status_map.get(slot_status, _("Not available"))
            })
        return attrs

    def get_data(self, order, profile_type, validated_data):
        date = validated_data.get("date", None)
        time = validated_data.get("time", None)
        message = validated_data.get("message", None)
        data = {
            "order": order,
            "status": OrderChangesRequestStatus.NO_RESPONSE,
            "request_by": profile_type
        }

        changes_data = {"message": message}

        if date and time:
            data["changes_type"] = ChangesRequestType.TIME_AND_DATE
            changes_data.update({
                "date": date.isoformat(),
                "time": time.isoformat(),
                # "time": time.strftime("%H:%M:%S"),
            })

        elif date:
            data["changes_type"] = ChangesRequestType.DATE
            changes_data.update({
                "date": date.isoformat(),
            })

        elif time:
            data["changes_type"] = ChangesRequestType.TIME
            changes_data.update({
                "time": time.isoformat(),
            })
        else:
            raise ValueError(_("Time or date must be submit!"))
        data["changes_data"] = changes_data
        response_message = _("Request sent successfully")
        return data, response_message

    def get_changes_object(self):
        return self.changes_object
    
    def save(self, **kwargs):
        order = kwargs.get("order")
        profile_type = kwargs.get("profile_type")

        if OrderChangesRequest.objects.filter(
            order=order,
            status=OrderChangesRequestStatus.NO_RESPONSE
        ).exists():
            raise ValueError(_("Already sent a request!"))
        data, response_message = self.get_data(
            order,
            profile_type,
            self.validated_data
        )

        with transaction.atomic():
            self.response_message = response_message
            self.changes_object = OrderChangesRequest.objects.create(**data)
            
            if profile_type == UserDefault.PROVIDER:
                order_change_action = OrderChangeRequestAction.PROVIDER_TIME_CHANGE_REQUEST_SEND
            elif profile_type == UserDefault.CUSTOMER:
                order_change_action = OrderChangeRequestAction.CUSTOMER_TIME_CHANGE_REQUEST_SEND
            
            order.order_change_action = order_change_action
            order.save()

            return self.changes_object
    
    def get_response_message(self):
        return self.response_message

class ProposeNewTimeActionSerializer(serializers.Serializer):
    status = serializers.CharField(required=True)
    request_id = serializers.IntegerField(required=True, write_only=True)

    def validate_slot(self, order, changes_request):
        changes_data = changes_request.changes_data
        date_obj = order.working_date
        slot_start = order.working_start_time

        if changes_request.changes_type in [ChangesRequestType.TIME_AND_DATE, ChangesRequestType.DATE]:
            date_str = changes_data.get("date")
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if changes_request.changes_type in [ChangesRequestType.TIME_AND_DATE, ChangesRequestType.TIME]:
            time_str = changes_data.get("time")
            slot_start = datetime.strptime(time_str, "%H:%M:%S").time()

        slot_start_dt = datetime.combine(date_obj, slot_start)
        slot_end_dt = (
            datetime.combine(date_obj, slot_start) +
            timedelta(hours=order.working_hour)
        )

        # SLOT ENGINE CALL
        slot_engine = SlotStatusEngine()
        slot_status = slot_engine.get_status(
            provider=order.provider,
            date_obj=date_obj,
            slot_start=slot_start_dt,
            slot_end=slot_end_dt
        )

        status_map = {
            "BOOKED": _("Already booked"),
            "UNAVAILABLE": _("Provider unavailable"),
            "FREEZED": _("Temporarily locked")
        }
        if slot_status != HelperSlotExceptionType.AVAILABLE:
            raise ValueError(status_map.get(slot_status, _("Not available")))

    def get_response_message(self):
        return self.response_message
    
    def order_update(self, order, changes_request):
        if changes_request.changes_type == ChangesRequestType.TIME_AND_DATE:
            changes_data = changes_request.changes_data
            date_str = changes_data.get("date")
            time_str = changes_data.get("time")
            order.working_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            order.working_start_time = datetime.strptime(time_str, "%H:%M:%S").time()
            self.response_message = _("Propose New Time & Date Accept!")
        elif changes_request.changes_type == ChangesRequestType.DATE:
            changes_data = changes_request.changes_data
            date_str = changes_data.get("date")
            order.working_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            self.response_message = _("Propose New Date Accept!")
        elif changes_request.changes_type == ChangesRequestType.TIME:
            changes_data = changes_request.changes_data
            time_str = changes_data.get("time")
            order.working_start_time = datetime.strptime(time_str, "%H:%M:%S").time()
            self.response_message = _("Propose New Time Accept!")
        order.order_change_action = OrderChangeRequestAction.NO_ACTION
        order.save()
        return order
    
    def get_changes_object(self):
        return self.changes_object
    
    def save(self, **kwargs):
        order = kwargs.get("order")
        request_id = self.validated_data.get("request_id", None)
        profile_type = kwargs.get("profile_type")
        changes_request = OrderChangesRequest.objects.get(id=request_id, order=order)
        self.changes_object = changes_request
        status = self.validated_data.get("status", None)
        if changes_request.request_by == profile_type:
            raise ValueError(_("You can't action your request."))
        elif changes_request.status in [OrderChangesRequestStatus.ACCEPT, OrderChangesRequestStatus.DECLINED]:
            raise ValueError(_("This request is alread {}").format(changes_request.status))
        
        with transaction.atomic():
            status = status.upper()
            changes_request.status = status
            changes_request.save()
            if status == OrderChangesRequestStatus.ACCEPT:
                self.validate_slot(order, changes_request)
                order = self.order_update(order, changes_request)
                return order
            if status == OrderChangesRequestStatus.DECLINED:
                self.response_message = _("Time Changes Request {}").format(status)
                return order

class StartWorkSerializer(serializers.Serializer):
    start = serializers.BooleanField(required=True)
    address = serializers.CharField(required=False)
    lat = serializers.FloatField(required=True)
    lng = serializers.FloatField(required=True)

    def is_within_100m(self, lat1, lon1, lat2, lon2):
        lon1, lat1, lon2, lat2 = map(
            radians, [lon1, lat1, lon2, lat2]
        )
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        distance_km = 6371 * c
        print("distance_km: ", distance_km)
        distance_m = distance_km * 1000
        print("distance_m: ", distance_m)
        return distance_m <= 100

    def work_start(self, **kwargs):
        order = kwargs.get("order")
        start = self.validated_data.get("start", None)
        address = self.validated_data.get("address", None)
        helper_lat = self.validated_data.get("lat", None)
        helper_lng = self.validated_data.get("lng", None)
        if start and helper_lat and helper_lng and order:
            with transaction.atomic():
                order_lat = order.lat
                order_lng = order.lng
                is_near = self.is_within_100m(helper_lat, helper_lng, order_lat, order_lng)
                if not is_near:
                    raise ValueError(_("You are not under 100m at work space!"))
                
                Order.objects.filter(pk=order.id).update(
                    status=OrderStatus.IN_PROGRESS,
                    confirmation_OTP=generate_otp(6),
                    started_at=timezone.now(),
                    updated_at=timezone.now()
                )
                order.refresh_from_db()
                return order
        else:
            raise ValueError(_("Something wrong!"))

class CompleteSerializer(serializers.Serializer):
    otp = serializers.CharField(required=True)

    def complete(self, **kwargs):
        order = kwargs.get("order")
        otp = self.validated_data.get("otp", None)
        if otp and order.confirmation_OTP == otp:
            with transaction.atomic():
                order = Order.objects.get(pk=order.id)
                order.status = OrderStatus.COMPLETED
                order.completed_at = timezone.now()
                order.updated_at = timezone.now()
                order.save()
                HelperSlotException.objects.filter(order=order).update(is_active=True)
                order.refresh_from_db()
                return order
        else:
            raise ValueError(_("OTP or Invalid OTP"))

class ReviewAndRatingSerializer(serializers.ModelSerializer):
    review = serializers.CharField(required=False, allow_blank=True)
    rating = serializers.ChoiceField(
        choices=ReviewRatingChoice.choices,
        required=True
    )
    attachment = serializers.FileField(required=False, allow_null=True)
    image = serializers.FileField(required=False, allow_null=True)
    
    class Meta:
        model = ReviewAndRating
        fields = ["id", "order", "customer", "provider", "send_by", "rating", "review", "attachment", "image", "is_approved", "created_at", "updated_at"]
        read_only_fields = ["id", "order", "customer", "provider", "send_by", "is_approved", "created_at", "updated_at"]
    
    def to_internal_value(self, data):
        mutable_data = data.copy() if hasattr(data, "copy") else dict(data)
        request = self.context.get("request")
        if request and hasattr(request, "FILES") and request.FILES:
            if "attachment" not in mutable_data or not mutable_data["attachment"]:
                for key in ["attachment", "image", "file", "photo", "document"]:
                    if key in request.FILES:
                        mutable_data["attachment"] = request.FILES[key]
                        break
                if ("attachment" not in mutable_data or not mutable_data["attachment"]):
                    first_file = next(iter(request.FILES.values()), None)
                    if first_file:
                        mutable_data["attachment"] = first_file

        if ("attachment" not in mutable_data or not mutable_data["attachment"]):
            for key in ["image", "file", "photo", "document"]:
                if key in mutable_data and mutable_data[key]:
                    mutable_data["attachment"] = mutable_data[key]
                    break

        return super().to_internal_value(mutable_data)

    def validate(self, attrs):
        if "image" in attrs and not attrs.get("attachment"):
            attrs["attachment"] = attrs.get("image")
        attrs.pop("image", None)
        return super().validate(attrs)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        file_url = None
        if instance.attachment:
            file_url = request.build_absolute_uri(instance.attachment.url) if request else instance.attachment.url
        data["attachment"] = file_url
        data["image"] = file_url
        if instance.provider:
            logo_url = None
            if instance.provider.logo:
                logo_url = request.build_absolute_uri(instance.provider.logo.url) if request else instance.provider.logo.url
            data["company_name"] = instance.provider.company_name
            data["company_logo"] = logo_url
            data["logo"] = logo_url
        return data

    def create(self, validated_data):
        with transaction.atomic():
            order = self.context.get("order")
            send_by = self.context.get("send_by")
            if not any(order and send_by):
                raise ValueError(_("Somthing Wrong!"))
            if ReviewAndRating.objects.filter(order=order, send_by=send_by).filter():
                raise ValueError(_("Your feedback already submited!"))
            validated_data["order"] = order
            validated_data["customer"] = order.customer
            validated_data["provider"] = order.provider
            validated_data["send_by"] = send_by
            return super().create(validated_data)

# ==================================================================
# =================== Order Section End===================================
# ==========================================================================================




# ==========================================================================================
# =================== Payment transaction Section Start===================================
class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = "__all__"

class PaymentTransactionDetailSerializer(serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        exclude = ["user"]

    def get_user(self, obj):
        return {
            "id": obj.user.id if obj.user else None,
            "name": str(obj.user) if obj.user else None,
        }

    def get_customer(self, obj):
        return {
            "id": obj.customer.id if obj.customer else None,
            "name": str(obj.customer) if obj.customer else None,
        }

    def get_provider(self, obj):
        return {
            "id": obj.provider.id if obj.provider else None,
            "name": str(obj.provider) if obj.provider else None,
        }

    def get_order(self, obj):
        if obj.order:
            return {
                "id": obj.order.id,
                "title": obj.order.title,
                "amount": obj.order.amount,
            }
        return None

# =================== Payment transaction Section End===================================
# ==========================================================================================
