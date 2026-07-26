from rest_framework.permissions import BasePermission
from find_worker_config.model_choice import UserRole
from django.conf import settings
from django.utils.translation import gettext_lazy as _

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.CUSTOMER

class IsServiceProvider(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.PROVIDER

class IsServicePostCustomerGetOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated and (request.user.role == UserRole.CUSTOMER or request.user.role == UserRole.PROVIDER)
        return request.user.is_authenticated and request.user.role == UserRole.PROVIDER

class IsCustomerPostServiceGetOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated and (request.user.role == UserRole.CUSTOMER or request.user.role == UserRole.PROVIDER)
        return request.user.is_authenticated and request.user.role == UserRole.CUSTOMER



class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == UserRole.ADMIN

class IsAuthenticatedForWrite(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_authenticated

class IsAdminWritePermissionOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == UserRole.ADMIN




class IsValidFrontendRequest(BasePermission):
    message = _("You are not allowed to access this API from this client.")
    def has_permission(self, request, view):
        app_key = request.headers.get("X-FRONTEND-KEY")
        origin = request.headers.get("Origin")

        print("app_key: ", app_key)
        print("origin: ", origin)
        if not app_key or not origin:
            return False
        if origin not in [
            "https://yourfrontend.com",
            "http://localhost:3000"
        ]:
            return False

        return app_key == settings.FRONTEND_APP_KEY




# ===================New Permission Start======================
class HasCustomerProfileSafeModeTypeHeader(BasePermission):
    def has_permission(self, request, view):
        profile_type = request.headers.get("profile-type", "").lower()
        if not profile_type:
            raise Exception(_("Profile Type must be set in headers."))
            # return False
        user = request.user
        if not user.is_authenticated:
            return False
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            if profile_type != "customer":
                return False

        if profile_type == "customer":
            return hasattr(user, "customer_profile")
        elif profile_type == "provider":
            return hasattr(user, "service_provider_profile")
        elif profile_type == "admin":
            return user.role == UserRole.ADMIN
        else:
            return False

class ForCustomerProfile(BasePermission):
    def has_permission(self, request, view):
        profile_type = request.headers.get("profile-type", "").lower()
        if not profile_type:
            return False
        user = request.user
        if not user.is_authenticated:
            return False
        if profile_type == "customer":
            return hasattr(user, "customer_profile")
        else:
            return False

class ForProviderProfile(BasePermission):
    def has_permission(self, request, view):
        profile_type = request.headers.get("profile-type", "").lower()
        if not profile_type:
            return False
        user = request.user
        if not user.is_authenticated:
            return False
        if profile_type == "provider":
            return hasattr(user, "service_provider_profile")
        else:
            return False

class ForAdminProfile(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.role == UserRole.ADMIN
# ===================New Permission End======================


# class IsAdminCreatePermission(BasePermission):
#     def has_permission(self, request, view):
#         if request.method in SAFE_METHODS:
#             return True
#         user = request.user
#         return user.is_authenticated and user.role == UserRole.ADMIN

