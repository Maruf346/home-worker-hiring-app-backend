# import datetime
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _
from django.shortcuts import render, get_object_or_404
from rest_framework.response import Response
from rest_framework.generics import RetrieveUpdateDestroyAPIView, CreateAPIView, GenericAPIView
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from .models import Address, CustomerProfile, HelperSlotException, HelperSpecialDate, HelperWallet, HelperWeeklyAvailability, ServiceProviderProfile, CustomerPaymentMethod, ProviderPayoutMethod, UserLanguage, Referral, Voucher, SavedHelper, ActivityLog, ProviderVerification
from .serializers import (
    HelperWeeklyAvailabilitySerializer, ProviderEarningsViewSerializer, ReviewAndRatingProfileSerializer, UserAddressSerializer, ProviderVerificationSerializer, CustomerPaymentMethodSerializer, ProviderPayoutMethodSerializer, ReferralSerializer, VoucherSerializer, ApplyVoucherSerializer, CurrentUserInfoSerializer, CurrentUserHelperSerializer, SaveHelperProfileSerializer
)
from core.models import AddOfferVoucher
from django.db.models import F, Q, Avg, ExpressionWrapper, FloatField, Sum, Value
from rest_framework.viewsets import GenericViewSet
from find_worker_config.model_choice import (
    DateStatus, OrderStatus, OrderPaymentStatus , UserRole, UserDefault, DocumentStatus, UserStatus, VOUCHER_DISCOUNT_TYPE, VOUCHER_TYPE, WeekDay, DayStatus, HelperSlotExceptionType, PaymentAction, LogStatus
)
from core.serializers import HelperSerializer
from .utils import generate_otp, get_otp_object
from find_worker_config.utils import UpdateModelViewSet, UpdateReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.contrib.auth import get_user_model
from task.models import Order, ReviewAndRating
from math import radians, cos, sin, asin, sqrt
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from collections import defaultdict
from task.serializers import PaymentTransaction, PaymentTransactionDetailSerializer, OrderSerializerAll

from rest_framework.decorators import action
User = get_user_model()

from core.services.log_engine import handle_log_engine




class WelComeAPI(APIView):
    # permission_classes = [permissions.AllowAny, IsValidFrontendRequest]
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "status": True,
                "message": _("APi Active!!!")
            }, status=status.HTTP_200_OK
        )


# User Info Current ===========================
class CurrentUserInfoView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CurrentUserInfoSerializer

    def get_object(self):
        user = self.request.user
        return user
    
    def get_user_mode_profile(self, user_mode):
        user = self.get_object()
        if user_mode == UserDefault.CUSTOMER:
            profile, _ = CustomerProfile.objects.get_or_create(user=user)
            if not ServiceProviderProfile.objects.filter(user=user).exists() and not user.default_profile:
                user.default_profile = UserDefault.CUSTOMER
        elif user_mode == UserDefault.PROVIDER:
            profile = get_object_or_404(ServiceProviderProfile, user=user)
            if not profile:
                raise Exception(_("Helper Profile Not Created!"))
            if not CustomerProfile.objects.filter(user=user).exists() and not user.default_profile:
                user.default_profile = UserDefault.PROVIDER
        else:
            return None
        user.save(update_fields=["default_profile"])
        return profile
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context
    
    def retrieve(self, request, *args, **kwargs):
        user_mode = request.query_params.get("user_mode")
        self.get_user_mode_profile(user_mode)
        instance = self.get_object()
        return Response(
            {
                'status': True,
                'data': self.get_serializer(instance).data
            }, status=status.HTTP_200_OK
        )

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                partial = kwargs.pop('partial', False)
                instance = self.get_object()
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)

                if getattr(instance, '_prefetched_objects_cache', None):
                    instance._prefetched_objects_cache = {}
                
                handle_log_engine(
                    request=request, action="PROFILE UPDATE", status=LogStatus.SUCCESS, message="User Profile Update.", perform_user=self.request.user
                )
                return Response(
                    {
                        "status": True,
                        "data": serializer.data
                    }
                )
        except ValidationError as e:
            handle_log_engine(
                request=request, action="PROFILE UPDATE", status=LogStatus.FAILED, message="Failed to Update Profile.", perform_user=self.request.user
            )
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )

class UserAddressViews(UpdateModelViewSet):
    model = Address
    queryset = Address.objects.all()
    serializer_class = UserAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_user(self):
        return self.request.user

    def get_queryset(self):
        user = self.get_user()
        if self.request.user.role == UserRole.USER:
            return Address.objects.filter(user=user)
        elif self.request.user.role in (UserRole.ADMIN):
            return Address.objects.all()
        raise Exception(_("Wrong user!"))
    
    def list(self, request, *args, **kwargs):
        try:
            response = UserAddressSerializer(self.get_queryset(), many=True)
            return Response(
                {
                    'status': True,
                    'count': len(response.data),
                    'data': response.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'messgae': str(e),
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_create(self, serializer):
        address_serializer = serializer.save(is_default=True)
        handle_log_engine(
            request=self.request, action="CREATE ADDRESS", status=LogStatus.SUCCESS, message="Add New User Address.", entity=address_serializer,
            perform_user=self.request.user
        )
        return address_serializer
    
    def perform_update(self, serializer):
        address_serializer = serializer.save(is_default=True)
        handle_log_engine(
            request=self.request, action="UPDATE ADDRESS", status=LogStatus.SUCCESS, message="Update User Address.", entity=address_serializer,
            perform_user=self.request.user
        )
        return address_serializer

    def perform_retrieve(self, serializer):
        instance = self.get_object()
        instance.is_default = True
        instance.save(update_fields=["is_default"])
        serializer = self.get_serializer(instance)
        return Response(
            {
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK
        )
    
    def destroy(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                handle_log_engine(
                    request=request, action="DELETE ADDRESS", status=LogStatus.SUCCESS, message="Delete User Address.",
                    perform_user=self.request.user
                )
                super().destroy(request, *args, **kwargs)
                return Response(
                    {
                        'status': True,
                        'message': self.delete_message,
                    }, status=status.HTTP_200_OK
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="DELETE ADDRESS", status=LogStatus.FAILED, message="Failed to Delete User Address.",
                perform_user=self.request.user
            )
            return Response(
                {
                    'status': False,
                    'message': str(e),
                }, status=status.HTTP_400_BAD_REQUEST
            )

class UserDefaultLanguage(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            print("session language: ", request.session.get("language"))
            print("user language: ", request.user.language)

            if request.session.get("language"):
                return Response(
                    {
                        "status": True,
                        "language": request.session["language"]
                    }
                )
            elif request.user.is_authenticated:
                language = request.user.language
            else:
                language = UserLanguage.EN
            request.session["language"] = language
            return Response(
                {
                    "status": True,
                    "language": language
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "language": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
    
    def post(self, request):
        data = request.data
        lan = data.get("language" or UserLanguage.EN)
        if lan in [UserLanguage.EN, UserLanguage.ZH]:
            language = lan
        else:
            language = UserLanguage.EN

        user = self.request.user
        user.language = language
        user.save()
        
        request.session["language"] = language
        return Response(
            {
                "status": True,
                "language": request.session["language"]
            }
        )

class ReviewAndRatingProfileViewSet(GenericViewSet):
    serializer_class = ReviewAndRatingProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["profile_type"] = self.request.headers.get("profile_type", "").upper()
        return context
    
    @action(detail=False, methods=["get"], url_path="customer(?:/(?P<review_id>[^/.]+))?")
    def customer_reviews(self, request, review_id=None):
        if review_id:
            review = get_object_or_404(
                ReviewAndRating,
                id=review_id,
                customer=request.user.customer_profile,
                send_by=UserDefault.PROVIDER
            )
            serializer = self.get_serializer(review)
        else:
            reviews = ReviewAndRating.objects.filter(
                customer=request.user.customer_profile,
                send_by=UserDefault.PROVIDER
            )
            serializer = self.get_serializer(reviews, many=True)

        return Response({
            "status": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="customer/submitted/review(?:/(?P<review_id>[^/.]+))?")
    def customer_submitted_reviews(self, request, review_id=None):
        if review_id:
            review = get_object_or_404(
                ReviewAndRating,
                id=review_id,
                customer=request.user.customer_profile,
                send_by=UserDefault.CUSTOMER
            )
            serializer = self.get_serializer(review)
        else:
            reviews = ReviewAndRating.objects.filter(
                customer=request.user.customer_profile,
                send_by=UserDefault.CUSTOMER
            )
            serializer = self.get_serializer(reviews, many=True)
        return Response({
            "status": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="provider(?:/(?P<review_id>[^/.]+))?")
    def provider_reviews(self, request, review_id=None):
        if review_id:
            review = get_object_or_404(
                ReviewAndRating,
                id=review_id,
                provider=request.user.hasServiceProviderProfile,
                send_by=UserDefault.CUSTOMER
            )
            serializer = self.get_serializer(review)
        else:
            reviews = ReviewAndRating.objects.filter(
                provider=request.user.hasServiceProviderProfile, send_by=UserDefault.CUSTOMER
            )
            serializer = self.get_serializer(reviews, many=True)
        return Response(
            {
                "status": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["get"], url_path="provider/submitted/review(?:/(?P<review_id>[^/.]+))?")
    def provider_submitted_reviews(self, request, review_id=None):
        if review_id:
            review = get_object_or_404(
                ReviewAndRating,
                id=review_id,
                customer=request.user.customer_profile,
                send_by=UserDefault.PROVIDER
            )
            serializer = self.get_serializer(review)
        else:
            reviews = ReviewAndRating.objects.filter(
                customer=request.user.customer_profile,
                send_by=UserDefault.PROVIDER
            )
            serializer = self.get_serializer(reviews, many=True)
        return Response({
            "status": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)

# User Info Current ===========================


# ===============================================================================
# Helper/Provider User Related API Views Start================================

class CreateUserHelperView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CurrentUserHelperSerializer

    def get_object(self):
        user = self.request.user
        if self.get_helper_profile(user):
            raise Exception(_("Helper profile already created!"))
        return user
    
    def get_helper_profile(self, user):
        if ServiceProviderProfile.objects.filter(user=user).exists():
            return True
        return False

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.save(user=self.get_object())

                handle_log_engine(
                    request=self.request, action="CREATE HELPER", status=LogStatus.SUCCESS, message="Create User Helper Profile.", entity=serializer.instance,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True,
                    role=UserRole.USER, notification_message="Successfully Create Your Helper Profile."
                )
                return Response(
                    {
                        "status": True,
                        "data": serializer.data
                    }, status=status.HTTP_201_CREATED
                )
        except ValidationError as e:
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            handle_log_engine(
                request=self.request, action="CREATE HELPER", status=LogStatus.FAILED, message="Failed to Create User Helper Profile.",
                perform_user=self.request.user
            )
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )

class CurrentUserHelperView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CurrentUserHelperSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context
    
    def get_object(self):
        user = self.request.user
        try:
            return ServiceProviderProfile.objects.get(user=user)
        except ServiceProviderProfile.DoesNotExist:
            raise NotFound(detail="Helper Profile Not Created")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(
            {
                'status': True,
                'data': self.get_serializer(instance).data
            }, status=status.HTTP_200_OK
        )

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                partial = kwargs.pop('partial', False)
                instance = self.get_object()
                serializer = self.get_serializer(instance, data=request.data, partial=partial)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)

                if getattr(instance, '_prefetched_objects_cache', None):
                    instance._prefetched_objects_cache = {}
                
                handle_log_engine(
                    request=self.request, action="UPDATE HELPER", status=LogStatus.SUCCESS, message="Update User Helper Profile.", entity=instance,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
                )
                return Response(
                    {
                        "status": True,
                        "data": serializer.data
                    }
                )
        except ValidationError as e:
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            handle_log_engine(
                request=self.request, action="UPDATE HELPER", status=LogStatus.FAILED, message="Failed to Update User Helper Profile.",
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )


class ProviderVerificationViews(APIView):
    serializer_class = ProviderVerificationSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            if request.user.role == UserRole.USER:
                serializer = self.serializer_class(request.user.service_provider_profile.verification, context={"request": request})
            elif request.user.role == UserRole.ADMIN:
                serializer = self.serializer_class(ProviderVerification.objects.all(), many=True, context={"request": request})
            else:
                raise Exception(_("Wrong user."))
            
            return Response(
                {
                    "status": True,
                    "data": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }
            )
    
    def post(self, request):
        try:
            with transaction.atomic():
                provider = getattr(request.user, "service_provider_profile", None)
                if not provider:
                    raise Exception(_("This user have no provider profile."))

                verification, created = ProviderVerification.objects.get_or_create(
                    provider=provider
                )
                if request.user.status == UserStatus.ACTIVE and provider.is_verified and verification.is_verified:
                    raise Exception(_("Already Verified!"))

                serializer = self.serializer_class(verification, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                image_path = verification.document.path

                # service = KYCVerificationService(image_path, request.user)
                # result = service.verify()
                result = {"verified": True, "status": DocumentStatus.APPROVED}

                provider.is_verified = result.get('verified', False)
                provider.save(update_fields=["is_verified"])
                verification.is_verified = result.get('verified', False)
                verification.status = DocumentStatus.APPROVED if result.get('verified', False) else result.get("status", DocumentStatus.FAILED)
                verification.save(update_fields=["is_verified", "status"])

                handle_log_engine(
                    request=request, action="Provider Verification", status=LogStatus.SUCCESS, message="Provider Document Verification Complete", entity=verification,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER, notify=True, role=UserRole.USER, send_to=self.request.user,
                    send_to_type=UserDefault.PROVIDER
                )
                return Response(
                    {
                        "status": True,
                        "kyc_result": result
                    },
                    status=status.HTTP_200_OK
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="Provider Verification", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ProviderAddressUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            if not self.request.user.hasServiceProviderProfile:
                raise Exception(_("This user have no provider profile."))
            provider = request.user.hasServiceProviderProfile
            data = request.data
            address_object_id = data.get("address_object_id", None)
            if address_object_id is None:
                raise Exception(_("Address object id is required."))
            address = get_object_or_404(
                Address, id=address_object_id, user=request.user
            )
            if not address:
                raise Exception(_("Address not found with this id for this user."))
            provider.office_location = address
            provider.save(update_fields=["office_location"])

            handle_log_engine(
                request=request, action="OFFICE LOCATION UPDATE", status=LogStatus.SUCCESS, message="Update Your Office Location", entity=address,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": True,
                    "message": _("Office location updated successfully.")
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="OFFICE LOCATION UPDATE", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HelperWeeklyAvailabilityViewSet(UpdateModelViewSet):
    serializer_class = HelperWeeklyAvailabilitySerializer
    permission_classes = [IsAuthenticated]
    weekly_day_list = WeekDay.values

    def convert_to_24h(self, time_str):
        try:
            return datetime.strptime(time_str, "%I:%M %p").time()
        except ValueError:
            raise ValidationError(_("Invalid time format. Expected format like '09:00 AM'"))

    def get_queryset(self):
        return HelperWeeklyAvailability.objects.filter(provider=self.request.user.service_provider_profile)
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "status": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=["get"], url_path="weekly-day-list")
    def get_weekly_day_list(self, request, *args, **kwargs):
        return Response(
            {
                "status": True,
                "data": self.weekly_day_list
            }, status=status.HTTP_200_OK
        )
    
    def check_for_set_weekly_availability(self, available_days, start_time, end_time, day_status=None):
        if type(available_days) is str:
            available_days = [available_days]
        if not 1 <= len(available_days) <= 7:
            raise Exception(_("You must select at least 1 day and at most 7 days for availability."))
        elif not all(isinstance(day, str) and day in WeekDay.values for day in available_days):
            raise Exception(_("Days must be a list of valid week days."))
        elif not start_time or not end_time:
            raise Exception(_("Start time and end time are required."))
        elif self.convert_to_24h(start_time) >= self.convert_to_24h(end_time):
            raise Exception(_("Start time must be before end time."))
        elif day_status and day_status not in [DayStatus.AVAILABLE, DayStatus.OFF, DayStatus.UNAVAILABLE]:
            raise Exception(_("Invalid day status."))

    @action(detail=False, methods=["post"], url_path="update-availability/(?P<day>[^/.]+)")
    def update_availability(self, request, day):
        try:
            available_day, created = HelperWeeklyAvailability.objects.get_or_create(provider=request.user.service_provider_profile, day=day)
            data = request.data
            start_time = data.get("start_time", available_day.start_time.strftime("%I:%M %p") if available_day.start_time else None)
            end_time = data.get("end_time", available_day.end_time.strftime("%I:%M %p") if available_day.end_time else None)
            slot_duration_minutes = data.get("slot_duration_minutes", 60)
            day_status = DayStatus.AVAILABLE if data.get("day_status") == 1 else DayStatus.OFF if data.get("day_status") == 0 else available_day.day_status
            self.check_for_set_weekly_availability(day, start_time, end_time, day_status)
            
            with transaction.atomic():
                available_day.day_status = day_status
                available_day.start_time = self.convert_to_24h(start_time)
                available_day.end_time = self.convert_to_24h(end_time)
                available_day.slot_duration_minutes = slot_duration_minutes
                available_day.save()
                
                handle_log_engine(
                    request=request, action="UPDATE DAY AVAILABILITY", status=LogStatus.SUCCESS, message="Successfully Update Day Weekly Availability", entity=available_day,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
                )
            return Response(
                {
                    "status": True,
                    "message": _("Day availability updated successfully.")
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="UPDATE DAY AVAILABILITY", status=LogStatus.FAILED, message=str(e), entity=self.request.user.service_provider_profile,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["post"], url_path="set-weekly-availability")
    def set_weekly_availability(self, request):
        try:
            data = request.data
            available_days = data.get("days", [])
            start_time = data.get("start_time")
            end_time = data.get("end_time")
            slot_duration_minutes = data.get("slot_duration_minutes", 60)
            self.check_for_set_weekly_availability(available_days, start_time, end_time)
            
            with transaction.atomic():
                self.get_queryset().delete()
                availability_objects = [
                    HelperWeeklyAvailability(
                        provider=request.user.service_provider_profile,
                        day=day, day_status=DayStatus.AVAILABLE if day in available_days else DayStatus.OFF,start_time=self.convert_to_24h(start_time), end_time=self.convert_to_24h(end_time), slot_duration_minutes=slot_duration_minutes
                    )
                    for day in self.weekly_day_list
                ]
                HelperWeeklyAvailability.objects.bulk_create(availability_objects)


                handle_log_engine(
                    request=request, action="SET WEEKLY AVAILABILITY", status=LogStatus.SUCCESS, message="Successfully Set Your Weekly Availability", entity=self.request.user.service_provider_profile,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, role=UserRole.USER, send_to=self.request.user, send_to_type=UserDefault.PROVIDER
                )
            return Response(
                {
                    "status": True,
                    "message": _("Weekly availability set successfully.")
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="SET WEEKLY AVAILABILITY", status=LogStatus.FAILED, message=str(e), entity=self.request.user.service_provider_profile,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=["get"], url_path="date-slot-list/(?P<date>[^/.]+)")
    def get_date_slot_list(self, request, date):
        from core.services.slot_status_engine import SlotStatusEngine
        try:
            provider = request.user.service_provider_profile
            date_obj = datetime.strptime(date, "%d-%m-%Y").date()
            weekday = date_obj.strftime("%a")

            # Load Weekly Availability and show "No available slots for this date." if no availability for this date
            availability = HelperWeeklyAvailability.objects.filter(provider=provider, day=weekday).first()
            slot_duration = availability.slot_duration_minutes if availability else 60
            # Full Day Slot Generation (12:00 AM to 11:59 PM)
            day_start = datetime.combine(date_obj, datetime.min.time())
            day_end = datetime.combine(date_obj + timedelta(days=1), datetime.min.time())
            
            # Slot Generation
            slots = []
            current_time = day_start
            while current_time + timedelta(minutes=slot_duration) <= day_end:
                slot_start = current_time
                slot_end = current_time + timedelta(minutes=slot_duration)

                # SLOT STATUS ENGINE CALL
                slot_engine = SlotStatusEngine()
                slot_status = slot_engine.get_status(
                    provider=provider,
                    date_obj=date_obj,
                    slot_start=slot_start,
                    slot_end=slot_end
                )

                slots.append({
                    "slot": f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}",
                    "start_time": slot_start.strftime("%I:%M %p"),
                    "end_time": slot_end.strftime("%I:%M %p"),
                    "status": slot_status
                })
                current_time += timedelta(minutes=slot_duration)
            return Response(
                {
                    "status": True,
                    "count": len(slots),
                    "data": {
                        "date": date_obj,
                        "day": weekday,
                        "slots": slots
                    }
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )


    # Specific Time Slot Exception
    @action(detail=False, methods=["post"], url_path="slot-exception/(?P<date>[^/.]+)")
    def add_slot_exception(self, request, date):
        try:
            with transaction.atomic():
                data = request.data
                start_time = data.get("start_time")
                end_time = data.get("end_time")
                is_available = data.get("is_available")

                if not date or not start_time or not end_time:
                    raise Exception(_("Date, start time and end time are required."))
                elif self.convert_to_24h(start_time) >= self.convert_to_24h(end_time):
                    raise Exception(_("Start time must be before end time."))
                
                excep, created = HelperSlotException.objects.get_or_create(
                    provider=request.user.service_provider_profile,
                    date=datetime.strptime(date, "%d-%m-%Y").date(),
                    start_time=self.convert_to_24h(start_time),
                    end_time=self.convert_to_24h(end_time)
                )
                excep.type = HelperSlotExceptionType.AVAILABLE if is_available is True else HelperSlotExceptionType.UNAVAILABLE
                excep.save()

                handle_log_engine(
                    request=request, action="ADD SLOT EXCEPTION", status=LogStatus.SUCCESS, message=f"Add New Slot Exception for {excep.type}.",
                    entity=excep, perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, role=UserRole.USER, send_to=self.request.user, send_to_type=UserDefault.PROVIDER
                )
                return Response(
                    {
                        "status": True,
                        "message": _("Slot exception added successfully.")
                    }, status=status.HTTP_200_OK
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="ADD SLOT EXCEPTION", status=LogStatus.FAILED, message=str(e), entity=self.request.user.service_provider_profile,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    # Specific Date Availability
    @action(detail=False, methods=["post"], url_path="special-date/(?P<date>[^/.]+)")
    def special_date(self, request, date):
        try:
            with transaction.atomic():
                data = request.data
                start_time = data.get("start_time")
                end_time = data.get("end_time")
                description = data.get("description", "")
                date_status = data.get("date_status", "").upper()

                if not date or not start_time or not end_time:
                    raise Exception(_("Date, start time and end time are required."))
                elif self.convert_to_24h(start_time) >= self.convert_to_24h(end_time):
                    raise Exception(_("Start time must be before end time."))
                elif date_status not in [DateStatus.AVAILABLE, DateStatus.UNAVAILABLE]:
                    raise Exception(_("Invalid date status."))
                
                special_date, _ = HelperSpecialDate.objects.update_or_create(
                    provider=request.user.service_provider_profile,
                    date=datetime.strptime(date, "%d-%m-%Y").date(),
                    defaults={
                        'start_time': self.convert_to_24h(start_time),
                        'end_time': self.convert_to_24h(end_time),
                        'description': description,
                        'date_status': date_status,
                    }
                )


                handle_log_engine(
                    request=request, action="SPECIAL DATE AVAILABILITY", status=LogStatus.SUCCESS, message="Set Your Special Date Availability.",
                    entity=special_date, perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, role=UserRole.USER, send_to=self.request.user, send_to_type=UserDefault.PROVIDER
                )
                return Response(
                    {
                        "status": True,
                        "message": _("Special date added successfully.")
                    }, status=status.HTTP_200_OK
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="SPECIAL DATE AVAILABILITY", status=LogStatus.FAILED, message=str(e), entity=self.request.user.service_provider_profile,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class NextJobOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from task.serializers import OrderSerializerAll
        try:
            provider = request.user.hasServiceProviderProfile
            next_orders = Order.objects.filter(
                provider=provider,
                status__in=[OrderStatus.ACCEPT, OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS],
                payment_status__in=[OrderPaymentStatus.PAID]
            ).order_by('working_date')[:3]
            serializer = OrderSerializerAll(next_orders, many=True, context={"request": request})
            return Response(
                {
                    "status": True,
                    "data": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )


class ProviderEarningsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_reports(self):
        now = timezone.now()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)

        last_7_total = PaymentTransaction.objects.filter(
            user=self.request.user,
            profile=UserDefault.PROVIDER,
            action=PaymentAction.SEND_PROVIDER,
            created_at__gte=last_7_days
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0

        last_30_total = PaymentTransaction.objects.filter(
            user=self.request.user,
            profile=UserDefault.PROVIDER,
            action=PaymentAction.SEND_PROVIDER,
            created_at__gte=last_30_days
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0

        return {
            "last_7_total": last_7_total,
            "last_30_total": last_30_total
        }

    def get(self, request):
        # try:
        with transaction.atomic():
            provider = request.user.hasServiceProviderProfile
            if not provider:
                raise Exception(_("This user have no provider profile."))
            helper_earnings, created = HelperWallet.objects.get_or_create(provider=request.user.hasServiceProviderProfile)
            return Response(
                {
                    "status": True,
                    "data": ProviderEarningsViewSerializer(helper_earnings).data,
                    "reports": self.get_reports()
                }, status=status.HTTP_200_OK
            )
        # except Exception as e:
        #     return Response(
        #         {
        #             "status": False,
        #             "message": str(e)
        #         }, status=status.HTTP_400_BAD_REQUEST
        #     )

class ProviderEarningsTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_grouped_data(self, data, transactions):
        grouped_data = defaultdict(list)
        for item in data:
            date_key = timezone.localtime(
                transactions.get(id=item["id"]).created_at
            ).strftime("%d-%m-%Y")
            grouped_data[date_key].append(item)
        return grouped_data

    def get(self, request):
        try:
            provider = request.user.hasServiceProviderProfile
            if not provider:
                raise Exception(_("This user have no provider profile."))
            
            transactions = PaymentTransaction.objects.filter(user=request.user, profile=UserDefault.PROVIDER, action=PaymentAction.SEND_PROVIDER).select_related(
               "order"
            ).order_by("-created_at")
            
            serializer = PaymentTransactionDetailSerializer(transactions, many=True, context={"request": request})
            grouped_data = self.get_grouped_data(serializer.data, transactions)
            return Response(
                {
                    "status": True,
                    "data": grouped_data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

# Helper/Provider User Related API Views End==================================
# ===============================================================================


# ===============================================================================
# Customer User Related API Views Start================================
class MyActivityViews(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        active_orders = Order.objects.filter(
            customer=self.request.user.customer_profile, status__in=[OrderStatus.ACCEPT, OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS]
        ).count()
        completed_orders = Order.objects.filter(
            customer=self.request.user.customer_profile, status__in=[OrderStatus.COMPLETED]
        ).count()
        total_spent = Order.objects.filter(
            customer=self.request.user.customer_profile, status__in=[OrderStatus.COMPLETED]
        ).aggregate(total=Sum('amount'))['total'] or 0
        avg_rating = ReviewAndRating.objects.filter(
            customer=self.request.user.customer_profile
        ).aggregate(avg=Avg('rating'))['avg'] or 0

        my_activity = {
            "active_orders": active_orders,
            "completed_orders": completed_orders,
            "total_spent": total_spent,
            "avg_rating": round(avg_rating, 2)
        }

        recent_activities = ActivityLog.objects.filter(
            user=self.request.user, user_type=UserDefault.CUSTOMER
        ).order_by('-created_at')[:5]
        recent_activity_data = [
            {
                "id": activity.id,
                "action": activity.action,
                "timestamp": activity.created_at
            }
            for activity in recent_activities
        ]
        return Response(
            {
                "status": True,
                "data": {
                    "my_activity": my_activity,
                    "recent_activities": recent_activity_data
                }
            }, status=status.HTTP_200_OK
        )

class SaveHelperProfileViews(UpdateReadOnlyModelViewSet):
    queryset = SavedHelper.objects.all()
    serializer_class = SaveHelperProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SavedHelper.objects.filter(customer=self.request.user.customer_profile)
    
    @action(detail=False, methods=["post"], url_path="add-helper/(?P<helper_id>[^/.]+)")
    def add_helper(self, request, helper_id):
        try:
            helper_profile = ServiceProviderProfile.objects.get(id=helper_id)
            if not ServiceProviderProfile.objects.filter(id=helper_id).exists():
                raise Exception(_("This helper does not exist. Please check if the helper id was keyed in correctly."))
            elif ServiceProviderProfile.objects.get(id=helper_id).user == request.user:
                raise Exception(_("You can't save your own profile!"))
            elif self.get_queryset().filter(helper__id=helper_id).exists():
                raise Exception(_("You've already saved this one! Find in Saved Helpers"))
            
            with transaction.atomic():
                SavedHelper.objects.create(
                    customer=request.user.customer_profile,
                    helper=helper_profile
                )

                handle_log_engine(
                    request=request, action="MARK SAVED HELPER", status=LogStatus.SUCCESS, message="Helper Profile Saved Mark.",
                    entity=helper_profile, perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                )
                return Response(
                    {
                        "status": True,
                        "message": _("{} {} Add in your saved helpers. Find in Saved Helpers.").format(helper_profile.user.first_name, helper_profile.user.last_name)
                    }, status=status.HTTP_200_OK
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="MARK SAVED HELPER", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=["delete"], url_path="remove-helper")
    def remove_helper(self, request, pk=None):
        try:
            saved_helper = self.get_object()
            saved_helper.delete()

            handle_log_engine(
                request=request, action="REMOVE SAVED HELPER", status=LogStatus.SUCCESS, message="Helper Remove From Your Saved Object.",
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": True,
                    "message": _("Helper removed from saved helpers.")
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="REMOVE SAVED HELPER", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class GetMyReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "status": True,
                "referral_code": self.request.user.referral_code or None
            }, status=status.HTTP_200_OK
        )

class RecommendationHelperViewSet(UpdateReadOnlyModelViewSet):
    serializer_class = HelperSerializer
    permission_classes = [IsAuthenticated]
    
    def haversine(self, lat2, lon2):
        lon1, lat1, lon2, lat2 = map(
            radians, [self.user_lng, self.user_lat, lon2, lat2]
        )
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return round(6371 * c, 2)
    
    def get_serializer_context(self):
        return {
            "request": self.request
        }

    def get_current_location_lat_lng(self):
        current_location = self.request.query_params.get("current_location", None)
        if current_location:
            try:
                lat, lng = map(float, current_location.split(","))
                return lat, lng
            except ValueError:
                return None, None
        else:
            current_location = self.request.user.addresses.filter(is_default=True).first()
            if current_location:
                return current_location.lat, current_location.lng
        return None, None
    
    def get_queryset(self):
        location = self.get_current_location_lat_lng()
        if not location:
            return ServiceProviderProfile.objects.none()
        user_lat, user_lng = location
        self.user_lat = user_lat
        self.user_lng = user_lng
        
        queryset = ServiceProviderProfile.objects.filter(
            is_verified=True,
            office_location__isnull=False,
            office_location__lat__isnull=False,
            office_location__lng__isnull=False,
        ).select_related(
            "office_location",
            "user"
        )
        helpers = []
        for helper in queryset:
            office = helper.office_location
            if not office or not office.lat or not office.lng:
                continue
            distance = self.haversine(office.lat, office.lng)
            helper.distance_km = distance
            if distance <= float(5):
                    helpers.append(helper)
        return helpers[:3]
    
    def list(self, request, *args, **kwargs):
        helpers = self.get_queryset()
        page = self.paginate_queryset(helpers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(helpers, many=True)
        return Response({
            "status": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)
    
    def get_object(self):
        return get_object_or_404(ServiceProviderProfile, pk=self.kwargs.get("pk"))
    
    def retrieve(self, request, *args, **kwargs):
        with transaction.atomic():
            instance = self.get_object()
            serializer = self.get_serializer(instance)

            instance.total_profile_view += 1
            instance.save(update_fields=["total_profile_view"])

            handle_log_engine(
                request=request, action="Helper Profile View", status=LogStatus.SUCCESS, message="Helper profile visit", entity=instance,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            if instance.total_profile_view == 50:
                handle_log_engine(
                    request=request, action="50+ Views", status=LogStatus.SUCCESS, message="50+ views your profile",
                    entity=instance, logify=False, notify=True,
                    role=UserRole.USER, send_to=instance.user, send_to_type=UserDefault.PROVIDER
                )
            elif instance.total_profile_view == 100:
                handle_log_engine(
                    request=request, action="100+ Views", status=LogStatus.SUCCESS, message="100+ views your profile",
                    entity=instance, logify=False, notify=True,
                    role=UserRole.USER, send_to=instance.user, send_to_type=UserDefault.PROVIDER
                )
            return self.perform_retrieve(serializer)

# -------------------------------
# My Referral Views
class MyReferralViewSet(UpdateReadOnlyModelViewSet):
    serializer_class = ReferralSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Referral.objects.filter(referrer=self.request.user) 
# -------------------------------
# Voucher Views
class MyVoucherViewSet(UpdateReadOnlyModelViewSet):
    serializer_class = VoucherSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        vouchers = Voucher.objects.filter(
            Q(user=self.request.user, voucher_type=VOUCHER_TYPE.FOR_USER) | Q(voucher_type=VOUCHER_TYPE.FOR_GLOBAL)
        )
        return vouchers

    @action(detail=False, methods=["post"], url_path="add-voucher")
    def add_voucher(self, request):
        try:
            voucher_code = request.data.get("voucher_code")
            if not voucher_code:
                raise Exception(_("Voucher code field is empty!"))
            elif self.get_queryset().filter(code=voucher_code).exists():
                raise Exception(_("You've already saved this one! Find in Vouchers"))
            elif not AddOfferVoucher.objects.filter(code=voucher_code).exists():
                raise Exception(_("This voucher does not exist. Please check if the voucher code was keyed in correctly."))
            
            with transaction.atomic():
                offer_voucher = AddOfferVoucher.objects.get(code=voucher_code)
                new_voucher = Voucher.objects.create(
                    user=self.request.user,
                    voucher_type=VOUCHER_TYPE.FOR_USER,
                    name=offer_voucher.name,
                    code=offer_voucher.code,
                    discount_type=offer_voucher.discount_type,
                    value=offer_voucher.value,
                    minimum_value=offer_voucher.minimum_value,
                    upto_value=offer_voucher.upto_value,
                    expiry_date=offer_voucher.expiry_date,
                )

                handle_log_engine(
                    request=request, action="ADD NEW VOUCHER", status=LogStatus.SUCCESS, message="Add New Promo Voucher", entity=new_voucher,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER, notify=True, role=UserRole.USER
                )
                return Response(
                    {
                        "status": True,
                        "message": _("{} Add in your account. Find in Vouchers.").format(voucher_code)
                    }
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="ADD NEW VOUCHER", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
# -------------------------------
# Apply Voucher (Important)
class ApplyVoucherView(GenericAPIView):
    serializer_class = ApplyVoucherSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            voucher = serializer.validated_data["voucher"]
            amount = serializer.validated_data["order_amount"]

            # Calculate discount
            if voucher.discount_type == VOUCHER_DISCOUNT_TYPE.PERCENTAGE:
                discount = (voucher.value / 100) * amount
            else:
                discount = voucher.value

            if voucher.upto_value:
                discount = min(discount, voucher.upto_value)

            final_amount = amount - discount

            handle_log_engine(
                request=request, action="Apply Voucher Code", status=LogStatus.SUCCESS, message="Voucher Code Apply For a Order.",
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response({
                "voucher_id": voucher.id,
                "voucher_code": voucher.code,
                "original_amount": amount,
                "discount": discount,
                "final_amount": final_amount
            }, status=status.HTTP_200_OK)
        except ValidationError:
            errors = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="Apply Voucher Code", status=LogStatus.FAILED, message="Failed to Apply Voucher Code.",
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": False,
                    "message": errors
                }
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="Apply Voucher Code", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }
            )
# -------------------------------

# Customer User Related API Views End==================================
# ===============================================================================







# =================================================================
# Payment & Payout method Viewsets ===========================
class CustomerPaymentMethodViewSet(UpdateModelViewSet):
    serializer_class = CustomerPaymentMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CustomerPaymentMethod.objects.filter(
            user=self.request.user
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        handle_log_engine(
            request=self.request, action="ADD NEW PAYMENT METHOD", status=LogStatus.SUCCESS, message="Add New Payment Method.", entity=serializer.instance,
            perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER, notify=True, role=UserRole.USER
        )
    
    def perform_update(self, serializer):
        serializer.save()
        handle_log_engine(
            request=self.request, action="UPDATE PAYMENT METHOD", status=LogStatus.SUCCESS, message="Update Payment Method.", entity=serializer.instance,
            perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
        )
    
    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        try:
            with transaction.atomic():
                obj = self.get_object()
                self.get_queryset().update(is_default=False)
                obj.is_default = True
                obj.save()

                handle_log_engine(
                    request=self.request, action="SET DEFAULT PAYMENT METHOD", status=LogStatus.SUCCESS, message="Set Default Payment Method.", entity=obj,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
                )
                return Response({"status": True, "message": _("Default updated")}, status=status.HTTP_200_OK)
        except Exception as e:
            handle_log_engine(
                request=self.request, action="SET DEFAULT PAYMENT METHOD", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": True,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    def perform_destroy(self, instance):
        instance.delete()
        handle_log_engine(
            request=self.request, action="REMOVE PAYMENT METHOD", status=LogStatus.SUCCESS, message="Remove Payment Method.",
            perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
        )

class ProviderPayoutMethodViewSet(UpdateModelViewSet):
    serializer_class = ProviderPayoutMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProviderPayoutMethod.objects.filter(
            provider=self.request.user.hasServiceProviderProfile
        )

    def perform_create(self, serializer):
        serializer.save(
            provider=self.request.user.hasServiceProviderProfile
        )
        handle_log_engine(
            request=self.request, action="ADD NEW PAYOUT METHOD", status=LogStatus.SUCCESS, message="Add New Payout Method.", entity=serializer.instance,
            perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER, notify=True, role=UserRole.USER
        )
    
    def perform_update(self, serializer):
        serializer.save()
        handle_log_engine(
            request=self.request, action="UPDATE PAYOUT METHOD", status=LogStatus.SUCCESS, message="Update Payout Method.", entity=serializer.instance,
            perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
        )
    
    def perform_destroy(self, instance):
        instance.delete()
        handle_log_engine(
            request=self.request, action="REMOVE PAYOUT METHOD", status=LogStatus.SUCCESS, message="Remove Payout Method.",
            perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
        )

    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request, pk=None):
        try:
            with transaction.atomic():
                obj = self.get_object()
                self.get_queryset().update(is_default=False)
                obj.is_default = True
                obj.save()
                handle_log_engine(
                    request=self.request, action="SET DEFAULT PAYOUT METHOD", status=LogStatus.SUCCESS, message="Set Default Payout Method.", entity=obj,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
                )
                return Response({"status": True, "message": _("Default updated")}, status=status.HTTP_200_OK)
        except Exception as e:
            handle_log_engine(
                request=self.request, action="SET DEFAULT PAYOUT METHOD", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": True,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

# Payment & Payout method Viewsets ===========================
# =================================================================



