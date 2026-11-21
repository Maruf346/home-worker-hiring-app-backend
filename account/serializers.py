from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from task.models import ReviewAndRating
from .models import HelperWallet, HelperWeeklyAvailability, SavedHelper, User, OTP, Address, CustomerProfile, ServiceProviderProfile, ProviderVerification, Referral, Voucher, CustomerPaymentMethod, ProviderPayoutMethod, User
from .utils import generate_otp
from find_worker_config.model_choice import OTPType, VOUCHER_DISCOUNT_TYPE, VOUCHER_TYPE, OrderStatus, UserDefault, UserStatus
from django.core.exceptions import ObjectDoesNotExist
from find_worker_config.model_choice import UserRole
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from task.models import ServiceCategory

# OAuth2 imports
from google.oauth2 import id_token
from google.auth.transport import requests
import requests as req
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.files.base import ContentFile
from .emailsend import EmailOTPSend
# User = get_user_model()



# =================================================================
# Login With OTP Start===========================
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def get_user(self):
        return self.user

class LoginOTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        self.phone = attrs.get("phone", None)
        self.email = attrs.get("email", None)

        if not self.phone and not self.email:
            raise serializers.ValidationError(
                _("Either phone or email must be provided.")
            )
        try:
            self.user = self.get_user()
        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                _("No user found with the provided phone/email.")
            )
        return attrs

    def get_user(self):
        if self.phone:
            return User.objects.get(phone=self.phone)
        return User.objects.get(email=self.email)

    def del_unused_otp_object(self):
        OTP.objects.filter(user=self.user, purpose=OTPType.LOGIN).delete()

    def send_otp(self, request):
        self.del_unused_otp_object()
        otp_code = generate_otp(length=6)
        otp_obj = OTP.objects.create(
            phone=self.phone,
            email=self.email,
            user=self.user,
            code=otp_code,
            purpose=OTPType.LOGIN,
        )
        
        EmailOTPSend(otp_obj, request)
        if self.phone:
            return {"phone": self.phone}
        return {"email": self.email}

class LoginOTPVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    otp = serializers.CharField()

    def authenticated(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "default_profile": user.default_profile
        }
# Login With OTP End============================
# =================================================================

# =================================================================
# SignUp With OTP Start===========================
class SignUpOTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        if not attrs.get("phone") and not attrs.get("email"):
            raise serializers.ValidationError(
                _("Either phone or email must be provided.")
            )
        return attrs

class SignUpOTPVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    otp = serializers.CharField()

    def validate(self, attrs):
        if not attrs.get("phone") and not attrs.get("email"):
            raise Exception(
                _("Either phone or email must be provided.")
            )
        return attrs

    def authenticated(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "default_profile": user.default_profile
        }

class SignupSerializer(serializers.ModelSerializer):
    address = serializers.JSONField(write_only=True)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(required=True)
    referral_code = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "password", "address", "referral_code"]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_("Email already exists"))
        return value

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError(_("Phone already exists"))
        return value
    
    def create_address(self, user, address_data):
        return Address.objects.create(
            user=user,
            address_line=address_data.get("address_line"),
            city=address_data.get("city"),
            lat=address_data.get("lat"),
            lng=address_data.get("lng"),
            is_default=True
        )
    
    def create_referral_object(self, user, referral_code):
        new_user_voucher_value = 10
        if referral_code:
            new_user_voucher_value = 15
            referrer_user = User.objects.get(
                referral_code=referral_code
            )
            Referral.objects.create(
                referrer=referrer_user,
                referred=user,
                code=referral_code,
                reward_given=False
            )
        return Voucher.objects.create(
            voucher_type=VOUCHER_TYPE.FOR_USER,
            user=user,
            name="NEW USER VOUCHER",
            code="NEWUSER100",
            discount_type=VOUCHER_DISCOUNT_TYPE.PERCENTAGE,
            value=new_user_voucher_value,
            minimum_value=100,
            upto_value=15,
            is_used=False,
            is_active=True,
            expiry_date=timezone.now() + timedelta(days=30)
        )

    def create(self, validated_data):
        with transaction.atomic():
            address_data = validated_data.pop("address")
            password = validated_data.pop("password")
            referral_code = validated_data.pop("referral_code", None)

            user = User(**validated_data)
            user.set_password(password)
            user.save()
            self.user = user
            self.create_address(user, address_data)
            self.create_referral_object(user, referral_code)
            return user
    
    def send_code(self, request):
        otp = OTP.objects.create(
            user=self.user,
            email=self.user.email,
            purpose=OTPType.SIGNUP
        )
        EmailOTPSend(otp, request)
        return otp.email

# SignUp With OTP End===========================
# =================================================================

# =================================================================
# Password Change & Reset---------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_("User with this email does not exist."))
        self.user_email = value
        return value
    
    def get_user(self):
        return User.objects.get(email=self.user_email)
    
    def send_code(self, request):
        # send_mail(
        #     subject="Password Reset",
        #     message=f"Reset your password using this link:\n{reset_link}",
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     recipient_list=[user.email],
        # )
        otp = OTP.objects.create(
            user=self.get_user(),
            email=self.user_email,
            purpose=OTPType.RESET_PASSWORD
        )
        EmailOTPSend(otp, request)
        return otp

class PasswordResetConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    otp = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value):
        validate_password(value)
        self.password = value
        return value
    
    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone"):
            raise Exception(_("email or phone is required"))
        return super().validate(attrs)
    
    def set_new_password(self, user):
        user.set_password(self.password)
        user.save()
        return True

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_new_password= serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value
    
    def validate(self, attrs):
        if attrs.get("confirm_new_password") != attrs.get("new_password"):
            raise Exception(_("New password & confirm password not same."))
        request = self.context.get("request")
        user = request.user
        if not user.check_password(attrs["old_password"]):
            raise ValidationError({"old_password": _("Wrong password")})
        self.new_set_password = attrs.get("new_password")
        return user
    
    def set_password(self):
        user = self.validated_data
        user.set_password(self.new_set_password)
        user.save()
        return True

# Password Change & Reset---------------
# =================================================================




# =================================================================
# Social Auth Login System Serializer Start---------------

# Social Auth Login System Serializer END---------------
# =================================================================



# =================================================================
# User Info Current ===========================
class UserAddressSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    class Meta:
        model = Address
        fields = "__all__"
        extra_kwargs = {
            "address_line": {"required": True},
            "city": {"required": True},
            "lat": {"required": True},
            "lng": {"required": True},
        }

# ---------main---------
class ServiceCategoryField(serializers.ListField):
    child = serializers.IntegerField()

    def to_representation(self, value):
        return [
            {"id": c.id, "title": c.title} for c in value.all()
        ]


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerProfile
        fields = ["rating", "total_orders"]
        depth = True

class CurrentUserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "username", "email", "phone", "photo", "language", "default_profile"]
    
    def get_photo_url(self, photo, request):
        if photo and request:
            return request.build_absolute_uri(photo)
        else:
            return None
    
    def get_user_profile_address(self, user):
        address_objects = Address.objects.filter(
            user=user, is_default=True
        )
        if address_objects:
            address = address_objects.first()
        elif Address.objects.filter(user=user).exists():
            address = Address.objects.filter(user=user).first()
        
        if address:
            return {
                "id": address.id,
                "display_address": f"{address.address_line} {address.city}",
                "lat": address.lat,
                "lng": address.lng
            }
        else:
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        data["photo"] = self.get_photo_url(data.get("photo"), request)
        data["address"] = self.get_user_profile_address(instance)
        return data


class CurrentUserHelperSerializer(serializers.ModelSerializer):
    service_category = ServiceCategoryField(required=True)
    company_name = serializers.CharField(required=True)
    hourly_rate = serializers.DecimalField(required=True, max_digits=9, decimal_places=2)
    min_booking_hours = serializers.DecimalField(required=True, max_digits=9, decimal_places=2)
    portfolio = serializers.SerializerMethodField(read_only=True)
    reviews_and_ratings = serializers.SerializerMethodField(read_only=True)
    office_location = serializers.SerializerMethodField(read_only=True)
    strike_count = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = ServiceProviderProfile
        fields = ["id", "company_name", "logo", "details", "hourly_rate", "min_booking_hours", "office_location", "strike_count", "account_status", "availability_status", "is_verified", "complete_rate", "total_jobs", "rating", "service_category", "portfolio", "reviews_and_ratings"]
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
                "attachment": request.build_absolute_uri(review.attachment.url) if (review.attachment and request) else (review.attachment.url if review.attachment else None),
                "image": request.build_absolute_uri(review.attachment.url) if (review.attachment and request) else (review.attachment.url if review.attachment else None),
                "created_at": review.created_at
            }
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
        if obj.office_location:
            office = obj.office_location
            return {
                "id": office.id,
                "address_line": office.address_line,
                "city": office.city,
                "lat": office.lat,
                "lng": office.lng,
            }
        return None


# -------------------------------
# Referral Serializer
class ReferralSerializer(serializers.ModelSerializer):
    referrer_email = serializers.EmailField(source="referrer.email", read_only=True)
    referred_email = serializers.EmailField(source="referred.email", read_only=True)

    class Meta:
        model = Referral
        fields = ["id", "referrer", "referrer_email", "referred", "referred_email", "code", "reward_given", "created_at"]
        read_only_fields = ["code", "reward_given", "created_at"]
# -------------------------------
# Voucher Serializer
class VoucherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voucher
        fields = "__all__"
        read_only_fields = ["code", "is_used", "created_at"]

    def validate(self, data):
        if data.get("expiry_date") and data["expiry_date"] < timezone.now():
            raise serializers.ValidationError(_("Expiry date must be in the future"))

        if data.get("discount_type") == "percentage":
            if data.get("value") > 100:
                raise serializers.ValidationError(_("Percentage cannot be more than 100"))
        return data
# -------------------------------
# Apply Voucher Serializer
class ApplyVoucherSerializer(serializers.Serializer):
    code = serializers.CharField()
    order_amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, data):
        request = self.context["request"]
        try:
            voucher = Voucher.objects.get(code=data["code"], user=request.user, is_active=True)
        except Voucher.DoesNotExist:
            raise Exception(_("Invalid voucher"))

        if voucher.expiry_date < timezone.now():
            raise Exception(_("Voucher expired"))

        if voucher.is_used:
            raise Exception(_("Voucher already used"))

        if voucher.minimum_value and data["order_amount"] < voucher.minimum_value:
            raise Exception(_("Minimum order value not met"))

        data["voucher"] = voucher
        return data
# -------------------------------



class ProviderVerificationSerializer(serializers.ModelSerializer):
    dob = serializers.DateField(input_formats=["%d-%m-%Y"])
    
    class Meta:
        model = ProviderVerification
        fields = "__all__"
        read_only_fields = ["provider"]
    
    def validate(self, attrs):
        required_fields = {
            "full_name": _("Full name is required."),
            "document_id": _("Document ID is required."),
            "dob": _("Date of birth is required."),
            "document": _("Document image is required."),
            "document_type": _("Document type is required."),
        }
        errors = {}
        for field, message in required_fields.items():
            value = attrs.get(field)
            if not value and not getattr(self.instance, field, None):
                errors[field] = str(message)
        if errors:
            raise ValidationError(errors)
        return attrs
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request.user.role == UserRole.USER:
            data.pop("provider", None)
        elif request.user.role == UserRole.ADMIN:
            def build_user_profile(id, user):
                return {
                    "id": id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "photo": request.build_absolute_uri(user.photo.url) if user.photo else None,
                    "email": user.email,
                    "phone": user.phone,
                }
            data["provider"] = build_user_profile(instance.provider.id, instance.provider.user)
        return data

class SaveHelperProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedHelper
        fields = "__all__"
    
    def to_representation(self, instance):
        if not instance.helper:
            return None
        request = self.context.get("request")
        data = {}
        def build_user_profile(helper):
            profile = {
                "id": helper.id,
                "first_name": helper.user.first_name,
                "last_name": helper.user.last_name,
                "company_name": helper.company_name,
                "details": helper.details,
                "hourly_rate": helper.hourly_rate,
                "account_status": helper.account_status,
                "availability_status": helper.availability_status,
                "is_verified": helper.is_verified,
                "complete_rate": helper.complete_rate,
                "total_jobs": helper.total_jobs,
                "rating": helper.rating,
                "logo": request.build_absolute_uri(helper.logo.url) if helper.logo else None,
                "email": helper.user.email,
                "phone": helper.user.phone,
            }
            if helper.office_location:
                profile["office_location"] = {
                    "address_line": helper.office_location.address_line or "",
                    "city": helper.office_location.city or "",
                    "lat": helper.office_location.lat or "",
                    "lng": helper.office_location.lng or "",
                }
            return profile
        data["id"] = instance.id
        data["helper"] = build_user_profile(instance.helper)
        return data

class ReviewAndRatingProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = ReviewAndRating
        fields = "__all__"
        read_only_fields = ["customer", "provider", "order"]
    
    def get_provider_data(self, instance):
        request = self.context.get("request")
        if instance.provider:
            user = getattr(instance.provider, "user", None)
            photo_url = None
            if user and user.photo:
                photo_url = request.build_absolute_uri(user.photo.url) if request else user.photo.url
            logo_url = None
            if instance.provider.logo:
                logo_url = request.build_absolute_uri(instance.provider.logo.url) if request else instance.provider.logo.url

            return {
                "id": instance.provider.id,
                "first_name": user.first_name if user else "",
                "last_name": user.last_name if user else "",
                "photo": photo_url,
                "company_name": instance.provider.company_name,
                "company_logo": logo_url,
                "logo": logo_url,
            }
        return None

    def get_customer_data(self, instance):
        request = self.context.get("request")
        if instance.customer and instance.customer.user:
            return {
                "id": instance.customer.id,
                "first_name": instance.customer.user.first_name,
                "last_name": instance.customer.user.last_name,
                "photo": request.build_absolute_uri(instance.customer.user.photo.url) if instance.customer.user.photo else None,
            }
        return None
    
    def clean_data(self, data):
        data.pop("send_by", None)
        data.pop("created", None)
        data.pop("order", None)
        return data

    def to_representation(self, instance):
        data = self.clean_data(super().to_representation(instance))
        request = self.context.get("request")
        file_url = None
        if instance.attachment:
            file_url = request.build_absolute_uri(instance.attachment.url) if request else instance.attachment.url
        data["attachment"] = file_url
        data["image"] = file_url
        profile_type = self.context.get("profile_type")
        
        if profile_type == UserDefault.CUSTOMER:
            data.pop("customer", None)
            provider_data = self.get_provider_data(instance)
            data["provider"] = provider_data
            data["company_name"] = instance.provider.company_name if instance.provider else None
            data["company_logo"] = provider_data.get("company_logo") if provider_data else None
            data["logo"] = provider_data.get("logo") if provider_data else None
        elif profile_type == UserDefault.PROVIDER:
            data.pop("provider", None)
            data["customer"] = self.get_customer_data(instance)
        else:
            # If profile_type header was not set or different, still provide provider data if present
            if instance.provider:
                provider_data = self.get_provider_data(instance)
                data["provider"] = provider_data
                data["company_name"] = instance.provider.company_name
                data["company_logo"] = provider_data.get("company_logo") if provider_data else None
                data["logo"] = provider_data.get("logo") if provider_data else None
        return data



# --------------------Helper Side Serializers Start-----------------------
class HelperWeeklyAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = HelperWeeklyAvailability
        fields = "__all__"

class ProviderEarningsViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelperWallet
        fields = ["total_payout", "upcoming_payout", "available_payout", "payout_processing"]

# --------------------Helper Side Serializers End-----------------------

# User Info Current ===========================
# =================================================================



# =================================================================
# Payment & Payout method ===========================
class CustomerPaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerPaymentMethod
        fields = ["id", "provider", "method_type", "payment_token", "brand", "last4", "method_data", "is_default", "created_at"]
        read_only_fields = ["id", "created_at"]
    
    def create(self, validated_data):
        user = self.context["request"].user
        if validated_data.get("is_default"):
            CustomerPaymentMethod.objects.filter(
                user=user, is_default=True
            ).update(is_default=False)

        return CustomerPaymentMethod.objects.create(
            **validated_data
        )

class ProviderPayoutMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderPayoutMethod
        fields = ["id", "method_type", "account_token", "account_holder_name", "bank_name", "account_number", "ifsc_code", "paypal_email", "method_data", "is_verified", "is_default", "created_at"]
        read_only_fields = ["id", "is_verified", "created_at"]

    def validate(self, data):
        method_type = data.get("method_type")
        if method_type == "BANK":
            if not data.get("account_number") or not data.get("ifsc_code"):
                raise serializers.ValidationError(_("Bank details required"))

        elif method_type == "PAYPAL":
            if not data.get("paypal_email"):
                raise serializers.ValidationError(_("PayPal email required"))

        return data

    def create(self, validated_data):
        provider = self.context["request"].user.hasServiceProviderProfile

        if validated_data.get("is_default"):
            ProviderPayoutMethod.objects.filter(
                provider=provider, is_default=True
            ).update(is_default=False)

        return ProviderPayoutMethod.objects.create(
            **validated_data
        )
# Payment & Payout method ===========================
# =================================================================
