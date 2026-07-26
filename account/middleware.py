from django.utils import translation
from account.models import UserLanguage
from rest_framework_simplejwt.authentication import JWTAuthentication

class UserLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = UserLanguage.EN
        user = getattr(request, "user", None)
        
        if user and user.is_authenticated:
            language = request.user.language or UserLanguage.EN
        else:
            # Check for DRF JWT Token for API requests
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                try:
                    jwt_auth = JWTAuthentication()
                    validated_token = jwt_auth.get_validated_token(auth_header.split(' ')[1])
                    jwt_user = jwt_auth.get_user(validated_token)
                    if jwt_user and jwt_user.is_authenticated:
                        language = jwt_user.language or UserLanguage.EN
                except Exception:
                    pass
            elif request.session.get("language"):
                language = request.session["language"]
        
        translation.activate(language)
        request.LANGUAGE_CODE = language

        response = self.get_response(request)

        translation.deactivate()
        return response

