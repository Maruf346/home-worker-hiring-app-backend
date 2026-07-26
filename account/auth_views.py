from rest_framework_simplejwt.views import TokenObtainPairView, TokenVerifyView, TokenRefreshView
from .serializers import (
    LoginOTPRequestSerializer, LoginOTPVerifySerializer, SignUpOTPRequestSerializer, SignUpOTPVerifySerializer, ChangePasswordSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer, SignupSerializer, CustomTokenObtainPairSerializer
)
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import OTP
from find_worker_config.model_choice import OTPType, UserRole, LogStatus
from django.utils.translation import gettext as _
from django.core.files.base import ContentFile
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.request import Request
from rest_framework.exceptions import ValidationError
from .utils import  get_otp_object
from django.shortcuts import get_object_or_404
from account.models import User
from django.db.models import Q
from core.services.log_engine import LogActivityEngine
import requests
from .emailsend import EmailOTPSend



class PasswordLoginViews(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.get_user()
            data = serializer.validated_data
            data["default_profile"] = user.default_profile
            data["email"] = user.email

            log_data = {
                "action": "New Login",
                "status": LogStatus.SUCCESS,
                "message": "New Device Login",
                "request": self.request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log(user)
            log_engine.send_notification(UserRole.USER, receiver=user)
            return Response(
                {
                    "status": True,
                    "data": data
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": "Failed to Login",
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }
            )
        except Exception as e:
            data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

# Login With OTP Start===========================
class LoginOTPRequestView(GenericAPIView):
    serializer_class = LoginOTPRequestSerializer

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.send_otp(request)

            log_data = {
                "action": "New Login",
                "status": LogStatus.SUCCESS,
                "message": "Send OTP for New Login",
                "request": request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log(serializer.get_user())
            return Response(
                {
                    "status": True,
                    "message": _("OTP sent."),
                    "data": data
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            log_data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": "Send OTP for New Login",
                "request": request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log(serializer.get_user())
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            log_data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log(serializer.get_user())
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class LoginOTPVerifyView(APIView):

    def get_otp_object(self, data):
        otp = data.get("otp")
        email = data.get("email")
        phone = data.get("phone")

        query = Q(code=otp, is_used=False, purpose=OTPType.LOGIN)
        if phone:
            query &= Q(phone=phone)
        if email:
            query &= Q(email=email)
        otp_object = OTP.objects.filter(query).last()

        if not otp_object:
            raise Exception(_("Invalid OTP."))

        if otp_object.is_expired():
            raise Exception(_("OTP expired."))

        otp_object.is_used = True
        otp_object.save(update_fields=["is_used"])
        return otp_object
    
    def post(self, request):
        try:
            with transaction.atomic():
                serializer = LoginOTPVerifySerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                otp = self.get_otp_object(serializer.validated_data)

                log_data = {
                    "action": "New Login",
                    "status": LogStatus.SUCCESS,
                    "message": "New Device Login",
                    "entity": otp,
                    "request": self.request
                }
                log_engine = LogActivityEngine(log_data)
                log_engine.create_log(otp.user)
                log_engine.send_notification(UserRole.USER, receiver=otp.user)
                return Response(
                    {
                        "status": True,
                        "data": serializer.authenticated(otp.user)
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            log_data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": "Failed to New Login",
                "request": self.request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log()
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            log_data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": self.request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log()
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

# Login With OTP End============================


# SignUp With OTP Start===========================
class SignUpOTPRequestView(APIView):
    def get_otp_object(self, data):
        otp = generate_otp(6)
        email = data.get("email", None)
        phone = data.get("phone", None)
        if email and User.objects.filter(email=email).exists():
            raise Exception(_("Email already taken."))
        if phone and User.objects.filter(phone=phone).exists():
            raise Exception(_("Phone already taken."))
        otp_obj = OTP.objects.create(
            phone=phone,
            email=email,
            code=otp,
            purpose=OTPType.SIGNUP
        )
        return otp_obj

    def get_response(self, otp_object: OTP):
        if otp_object.phone is not None:
            return {"phone": otp_object.phone}
        elif otp_object.email is not None:
            return {"email": otp_object.email}

    def post(self, request):
        try:
            serializer = SignUpOTPRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp_object = self.get_otp_object(serializer.validated_data)
            return Response(
                {
                    "status": True,
                    "message": _("OTP sent."),
                    "data": self.get_response(otp_object)
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class SignUpOTPVerifyView(APIView):
    def get_otp_object(self, data):
        otp = data.get("otp")
        email = data.get("email")
        phone = data.get("phone")

        query = Q(code=otp, is_used=False, purpose=OTPType.SIGNUP)
        if phone:
            query &= Q(phone=phone)
        if email:
            query &= Q(email=email)
        otp_object = OTP.objects.filter(query).last()

        if not otp_object:
            raise Exception(_("Invalid OTP."))

        if otp_object.is_expired():
            raise Exception(_("OTP expired."))

        otp_object.is_used = True
        otp_object.save(update_fields=["is_used"])
        return otp_object
    
    def get_and_create_user(self, otp_object: OTP):
        if otp_object.phone:
            user, created = User.objects.get_or_create(
                phone=otp_object.phone, role=UserRole.USER, is_phone_verified=True
            )
        elif otp_object.email:
            user, created = User.objects.get_or_create(
                email=otp_object.email, role=UserRole.USER, is_email_verified=True
            )
        else:
            raise Exception(_("User not created, something went wrong."))
        otp_object.user = user
        otp_object.save(update_fields=["user"])
        return user

    def post(self, request):
        try:
            serializer = SignUpOTPVerifySerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp_obj = self.get_otp_object(serializer.validated_data)
            user = self.get_and_create_user(otp_obj)
            return Response(
                {
                    "status": True,
                    "data": serializer.authenticated(user)
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
# -------------------------------------------------
class SignUpViews(GenericAPIView):
    serializer_class = SignupSerializer
    
    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                user = serializer.save()
                email = serializer.send_code(request)

                data = {
                    "action": "New Registration",
                    "status": LogStatus.SUCCESS,
                    "message": "User Registration & Verify",
                    "entity": user,
                    "request": request
                }
                log_engine = LogActivityEngine(data)
                log_engine.create_log(user)
                return Response(
                    {
                        "status": True,
                        "message": _("OTP sent to your email address."),
                        "data": email
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            data = {
                "action": "New Registration",
                "status": LogStatus.FAILED,
                "message": "Failed to User Registration & Verify",
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            data = {
                "action": "New Registration",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            return Response(
                {
                    'status': False,
                    'message': str(e),
                },status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UserSignUpOTPVerifyView(GenericAPIView):
    serializer_class = SignUpOTPVerifySerializer

    def post(self, request):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                otp_obj = get_otp_object(serializer.validated_data, OTPType.SIGNUP)
                user = otp_obj.user
                if not user:
                    raise Exception(_("Could not find user for this OTP."))
                user.is_email_verified=True
                user.save()
                
                data = {
                    "action": "Account Verification",
                    "status": LogStatus.SUCCESS,
                    "message": "User Successfully Verified",
                    "entity": user,
                    "request": request
                }
                log_engine = LogActivityEngine(data)
                log_engine.create_log(user)
                return Response(
                    {
                        "status": True,
                        "data": serializer.authenticated(user)
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            data = {
                "action": "Account Verification",
                "status": LogStatus.FAILED,
                "message": "Failed to User Registration & Verify",
                "entity": user,
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            error = {kay: str(value[0]) for kay, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            data = {
                "action": "Account Verification",
                "status": LogStatus.FAILED,
                "message": str(e),
                "entity": user,
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class SignUpOTPResend(APIView):
    def get_user_by_email(self, email):
        return get_object_or_404(User, email=email)

    def send_code(self, email):
        user = self.get_user_by_email(email)
        if not user:
            raise Exception(_("User not found with this email."))
        otp = OTP.objects.create(
            user=user,
            email=email,
            purpose=OTPType.SIGNUP
        )
        EmailOTPSend(otp, self.request)
        return otp
    
    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            email = data.get("email", None)
            if not email:
                raise Exception(_("Email is required to resend OTP."))
            otp_object = self.send_code(email)

            data = {
                "action": "Verification OTP Resend",
                "status": LogStatus.SUCCESS,
                "message": "Signup OTP Verification Code Resend",
                "entity": otp_object,
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log(self.get_user_by_email(email))
            return Response(
                {
                    "status": True,
                    "message": _("OTP resent.")
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            data = {
                "action": "Verification OTP Resend",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": request
            }
            log_engine = LogActivityEngine(data)
            log_engine.create_log()
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

# SignUp With OTP End===========================


# =================================================================
# Social Auth Login System Views Start---------------
class GoogleLoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def google_response(self, access_token: str) -> dict:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            # "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5
        )
        if response.status_code != 200:
            raise Exception(_("Invalid Google token."))
        google_data = response.json()
        return google_data
    
    def save_google_profile_photo(self, user: object, picture_url: str) -> bool:
        response = requests.get(picture_url, timeout=10)
        if response.status_code != 200:
            return
        filename = f"user_{user.id}_google.jpg"
        user.photo.save(filename, ContentFile(response.content), save=True)
        return True

    def get_user(self, google_data: dict) -> object:
        email = google_data.get("email")
        first_name = google_data.get("given_name", "")
        last_name = google_data.get("family_name", "")
        picture = google_data.get("picture", "")

        if not email:
            raise Exception(_("Email not available."))

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name
            }
        )

        if created and not user.phone and picture:
            self.save_google_profile_photo(user, picture)

        return user

    def post(self, request):
        try:
            with transaction.atomic():
                access_token = request.data.get('access_token')

                if not access_token:
                    raise Exception(_("access_token is required."))
                
                google_data = self.google_response(access_token)

                user = self.get_user(google_data)
                refresh = RefreshToken.for_user(user)

                log_data = {
                    "action": "New Login",
                    "status": LogStatus.SUCCESS,
                    "message": "Login New Device with Google",
                    "request": request
                }
                log_engine = LogActivityEngine(log_data)
                log_engine.create_log(user)
                log_engine.send_notification(UserRole.USER, receiver=user)
                return Response(
                    {
                        "status": True,
                        "data": {
                            "access": str(refresh.access_token),
                            "refresh": str(refresh),
                            "default_profile": user.default_profile
                        }
                    }, status=status.HTTP_200_OK
                )
        except Exception as e:
            log_data = {
                "action": "New Login",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": self.request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log()
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }
            )

class AppleLoginAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def google_response(self, access_token: str) -> dict:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            # "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5
        )
        if response.status_code != 200:
            raise Exception(_("Invalid Google token."))
        google_data = response.json()

        # if data.get("aud") != settings.GOOGLE_CLIENT_ID:
        #     raise Exception("Token audience mismatch")

        return google_data
    
    def save_google_profile_photo(self, user: object, picture_url: str) -> bool:
        response = requests.get(picture_url, timeout=10)
        if response.status_code != 200:
            return
        filename = f"user_{user.id}_google.jpg"
        user.photo.save(filename, ContentFile(response.content), save=True)
        return True

    def get_user(self, google_data: dict) -> object:
        email = google_data.get("email")
        first_name = google_data.get("given_name", "")
        last_name = google_data.get("family_name", "")
        picture = google_data.get("picture", "")

        if not email:
            raise Exception(_("Email not available."))

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name
            }
        )

        if created and not user.phone and picture:
            self.save_google_profile_photo(user, picture)

        return user

    def post(self, request):
        try:
            with transaction.atomic():
                access_token = request.data.get('access_token')

                if not access_token:
                    raise Exception(_("access_token is required."))
                
                google_data = self.google_response(access_token)

                user = self.get_user(google_data)
                refresh = RefreshToken.for_user(user)
                return Response(
                    {
                        "status": True,
                        "data": {
                            "access": str(refresh.access_token),
                            "refresh": str(refresh),
                        }
                    }, status=status.HTTP_200_OK
                )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }
            )

# Social Auth Login System Views END---------------
# =================================================================



# Token & Password Start=================================
class UpdateTokenVerifyView(TokenVerifyView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            return Response(
                {
                    "status": False,
                    "message": _("Token is valid.")
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

class UpdateTokenRefreshView(TokenRefreshView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            return Response(
                {
                    "status": True,
                    "data": serializer.validated_data
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    "status": False,
                    "message": error
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )


class ChangePasswordView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data, context={"request": request})
                serializer.is_valid(raise_exception=True)
                serializer.set_password()
                
                log_data = {
                    "action": "Password Change",
                    "status": LogStatus.SUCCESS,
                    "message": "Recently Change Your Password.",
                    "request": request
                }
                log_engine = LogActivityEngine(log_data)
                log_engine.create_log(self.request.user)
                log_engine.send_notification(UserRole.USER, receiver=self.request.user)
                return Response(
                    {
                        "status": True,
                        "message": _("Password changed successfully.")
                    },
                    status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            log_data = {
                "action": "Password Change",
                "status": LogStatus.FAILED,
                "message": "Failed to Change Your Password.",
                "request": request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log(self.request.user)
            return Response(
                {
                    "status": False,
                    "message": error
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            log_data = {
                "action": "Password Change",
                "status": LogStatus.FAILED,
                "message": str(e),
                "request": request
            }
            log_engine = LogActivityEngine(log_data)
            log_engine.create_log(self.request.user)
            return Response(
                {
                    "status": False,
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PasswordResetRequestView(GenericAPIView):
    serializer_class = PasswordResetRequestSerializer

    def handle_log(self, request, status, message, user=None, otp_object=None, notify=False):
        log_data = {
            "action": "Password Reset Request",
            "status": status,
            "message": message,
            "entity": otp_object,
            "request": request
        }
        log_engine = LogActivityEngine(log_data)
        log_engine.create_log(user)
        if notify:
            log_engine.send_notification(UserRole.USER, receiver=user)
    
    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp_object = serializer.send_code(request)

            self.handle_log(request=request, user=serializer.get_user(), otp_object=otp_object, status=LogStatus.SUCCESS, message="Send Password Reset Request.", notify=True)
            return Response(
                {
                    "status": True,
                    "message": _("OTP sent to reset your password."),
                    "send_to": otp_object.email if otp_object.email else otp_object.phone
                },
                status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            self.handle_log(request=request, status=LogStatus.FAILED, message="Failed to Send Password Reset Request.")
            return Response(
                {
                    "status": False,
                    "message": error
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            self.handle_log(request=request, status=LogStatus.FAILED, message=str(e))
            return Response(
                {
                    "status": False,
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PasswordResetConfirmView(GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer

    def handle_log(self, request, status, message, user=None, otp_object=None, notify=False):
        log_data = {
            "action": "Password Reset Confirm",
            "status": status,
            "message": message,
            "entity": otp_object,
            "request": request
        }
        log_engine = LogActivityEngine(log_data)
        log_engine.create_log(user)
        if notify:
            log_engine.send_notification(UserRole.USER, receiver=user)

    def post(self, request):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp = get_otp_object(serializer.validated_data, OTPType.RESET_PASSWORD)
            serializer.set_new_password(otp.user)

            self.handle_log(request=request, user=otp.user, otp_object=otp, status=LogStatus.SUCCESS, message="Password Reset Confirm.", notify=True)
            return Response(
                {
                    "status": True,
                    "message": _("Password reset successfully."),
                },
                status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            self.handle_log(request=request, status=LogStatus.FAILED, message="Password Reset Confirm.")
            return Response(
                {
                    "status": False,
                    "message": error
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            self.handle_log(request=request, status=LogStatus.FAILED, message=str(e))
            return Response(
                {
                    "status": False,
                    "message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Token & Password End=================================
