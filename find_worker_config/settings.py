from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


from dotenv import load_dotenv
import os
ENV_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ENV_BASE_DIR, ".env"))
# load_dotenv()


SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "*").split(",")


# Application definition
INSTALLED_APPS = [
    'channels', 'daphne',
    # 'django.contrib.sites',
    
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    "import_export",
    "simple_history",
    "auditlog",

    # library app
    'rest_framework', 'rest_framework_simplejwt',
    'corsheaders', 'django_extensions', 'django_filters',
    'rest_framework_simplejwt.token_blacklist',
    'encrypted_model_fields',

    # custom app
    'account', 'chat_notify', 'core', 'task',

    'drf_spectacular',
    
]

# ================================================================================
# ==================== Authentication BackendStart====================

# ==================== Authentication BackendEnd====================
# ================================================================================

# ================================================================================
# ==================== Rest Frame Work Configurations Start====================
ENABLE_BROWSABLE_API = os.getenv('ENABLE_BROWSABLE_API', 'False') == 'True'
if ENABLE_BROWSABLE_API:
    DEFAULT_RENDERER_CLASSES_ = [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ]
else:
    DEFAULT_RENDERER_CLASSES_ = [
        'rest_framework.renderers.JSONRenderer'
    ]

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': DEFAULT_RENDERER_CLASSES_,
    
    'EXCEPTION_HANDLER': 'find_worker_config.exceptions.custom_exception_handler',
    
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    # 'PAGE_SIZE': 5,
    
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),

    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    'AUTH_HEADER_TYPES': ('Bearer',),
    'BLACKLIST_AFTER_ROTATION': True,
    'ROTATE_REFRESH_TOKENS': True,
    # 'ROTATE_REFRESH_TOKENS': False,
    
    'ACCESS_TOKEN_LIFETIME': timedelta(days=60),
    # 'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=60),
    
    "UPDATE_LAST_LOGIN": True,
}

CORS_ORIGIN_ALLOW_ALL = True



SPECTACULAR_SETTINGS = {
    'TITLE': 'Worker Hiring API',
    'DESCRIPTION': 'API documentation for your project',
    'VERSION': '1.0.0',
    'SECURITY': [{'BearerAuth': []}],
    'COMPONENTS': {
        'SECURITY_SCHEMES': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
}

# ==================== Rest Frame Work Configurations End====================
# ================================================================================

    
UNFOLD = {
    "SITE_TITLE": "Worker Hiring Admin",
    "SITE_HEADER": "Control Center",
    "SITE_SUBHEADER": "Enterprise Operations Dashboard",
    "SITE_SYMBOL": "engineering",

    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,

    "DASHBOARD": "chat_notify.admin.dashboard.chat.ChatControlDashboard",

    "COLORS": {
        "primary": {
            "50": "240 249 255",
            "100": "224 242 254",
            "200": "186 230 253",
            "300": "125 211 252",
            "400": "56 189 248",
            "500": "14 165 233",
            "600": "2 132 199",
            "700": "3 105 161",
            "800": "7 89 133",
            "900": "12 74 110",
        },
    },

    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,

        "navigation": [
            {
                "title": "Identity & Users",
                "separator": True,
                "items": [
                    {"title": "Users", "link": "/admin/account/user/"},
                    {"title": "Customers", "link": "/admin/account/customerprofile/"},
                    {"title": "Providers", "link": "/admin/account/serviceproviderprofile/"},
                    {"title": "Addresses", "link": "/admin/account/address/"},
                    {"title": "Saved Helpers", "link": "/admin/account/savedhelper/"},
                ],
            },

            {
                "title": "Marketplace Engine",
                "separator": True,
                "items": [
                    {"title": "Categories", "link": "/admin/task/servicecategory/"},
                    {"title": "Sub Categories", "link": "/admin/task/servicesubcategory/"},
                    {"title": "Orders", "link": "/admin/task/order/"},
                    {"title": "Order Changes", "link": "/admin/task/orderchangesrequest/"},
                    {"title": "Reviews", "link": "/admin/task/reviewandrating/"},
                    {"title": "Refund Requests", "link": "/admin/task/orderrefundrequest/"},
                ],
            },

            {
                "title": "Communication Hub",
                "separator": True,
                "items": [
                    {"title": "Chat Rooms", "link": "/admin/chat_notify/chatroom/"},
                    {"title": "Messages", "link": "/admin/chat_notify/chatmessage/"},
                    {"title": "Notifications", "link": "/admin/chat_notify/notification/"},
                    {"title": "Tickets", "link": "/admin/core/ticket/"},
                    {"title": "Ticket Reply", "link": "/admin/core/ticketreply/"},
                ],
            },

            {
                "title": "Finance Engine",
                "separator": True,
                "items": [
                    {"title": "Transactions", "link": "/admin/task/paymenttransaction/"},
                    {"title": "Provider Wallet", "link": "/admin/account/helperwallet/"},
                    {"title": "Admin Wallet", "link": "/admin/core/adminwallet/"},
                ],
            },

            {
                "title": "System & Operations",
                "separator": True,
                "items": [
                    {"title": "OTP Logs", "link": "/admin/account/otp/"},
                    {"title": "Email Configuaration", "link": "/admin/core/emailconfig/"},
                    {"title": "Provider Verification", "link": "/admin/account/providerverification/"},
                    {"title": "Referrals", "link": "/admin/account/referral/"},
                    {"title": "Vouchers", "link": "/admin/account/voucher/"},
                    {"title": "Activity Logs", "link": "/admin/account/activitylog/"},
                    {"title": "CMS Slides", "link": "/admin/core/signupslider/"},
                    {"title": "Customer Slides", "link": "/admin/core/customerscreenslide/"},
                ],
            },
        ]
        # "navigation": [
        #     {
        #         "title": "Identity & Users",
        #         "separator": True,
        #         "items": [
        #             {"title": "Users", "icon": "users", "link": "/admin/account/user/"},
        #             {"title": "Customers", "icon": "user", "link": "/admin/account/customerprofile/"},
        #             {"title": "Providers", "icon": "briefcase", "link": "/admin/account/serviceproviderprofile/"},
        #             {"title": "Addresses", "icon": "map", "link": "/admin/account/address/"},
        #             {"title": "Saved Helpers", "icon": "bookmark", "link": "/admin/account/savedhelper/"},
        #         ],
        #     },

        #     {
        #         "title": "Marketplace Engine",
        #         "separator": True,
        #         "items": [
        #             {"title": "Categories", "icon": "folder", "link": "/admin/task/servicecategory/"},
        #             {"title": "Sub Categories", "icon": "layers", "link": "/admin/task/servicesubcategory/"},
        #             {"title": "Orders", "icon": "shopping-cart", "link": "/admin/task/order/"},
        #             {"title": "Order Changes", "icon": "refresh", "link": "/admin/task/orderchangesrequest/"},
        #             {"title": "Reviews", "icon": "star", "link": "/admin/task/reviewandrating/"},
        #             {"title": "Refund Requests", "icon": "rotate-ccw", "link": "/admin/task/orderrefundrequest/"},
        #         ],
        #     },

        #     {
        #         "title": "Communication Hub",
        #         "separator": True,
        #         "items": [
        #             {"title": "Chat Rooms", "icon": "message", "link": "/admin/chat_notify/chatroom/"},
        #             {"title": "Messages", "icon": "mail", "link": "/admin/chat_notify/chatmessage/"},
        #             {"title": "Notifications", "icon": "bell", "link": "/admin/chat_notify/notification/"},
        #             {"title": "Tickets", "icon": "help-circle", "link": "/admin/core/ticket/"},
        #         ],
        #     },

        #     {
        #         "title": "Finance Engine",
        #         "separator": True,
        #         "items": [
        #             {"title": "Transactions", "icon": "credit-card", "link": "/admin/task/paymenttransaction/"},
        #             {"title": "Provider Wallet", "icon": "wallet", "link": "/admin/account/helperwallet/"},
        #             {"title": "Admin Wallet", "icon": "building-2", "link": "/admin/core/adminwallet/"},
        #         ],
        #     },

        #     {
        #         "title": "System & Operations",
        #         "separator": True,
        #         "items": [
        #             {"title": "OTP Logs", "icon": "key", "link": "/admin/account/otp/"},
        #             {"title": "Provider Verification", "icon": "shield-check", "link": "/admin/account/providerverification/"},
        #             {"title": "Referrals", "icon": "link", "link": "/admin/account/referral/"},
        #             {"title": "Vouchers", "icon": "gift", "link": "/admin/account/voucher/"},
        #             {"title": "Activity Logs", "icon": "activity", "link": "/admin/account/activitylog/"},
        #             {"title": "CMS Slides", "icon": "image", "link": "/admin/core/signupslider/"},
        #             {"title": "Customer Slides", "icon": "image", "link": "/admin/core/customerscreenslide/"},
        #         ],
        #     },
        # ],
    },
}



MIDDLEWARE = [
    # library middleware
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'account.middleware.UserLanguageMiddleware',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

ROOT_URLCONF = 'find_worker_config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'find_worker_config.wsgi.application'
ASGI_APPLICATION = "find_worker_config.asgi.application"

CHANNEL_LAYERS = {
    # "default": {
    #     "BACKEND": "channels_redis.core.RedisChannelLayer",
    #     "CONFIG": {"hosts": [("127.0.0.1", 6379)]},
    # }
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
# import dj_database_url
# DATABASES = {
#     'default': dj_database_url.parse(os.getenv("DATABASE_URL"))
# }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/


USE_I18N = True
USE_L10N = True

LANGUAGE_CODE = 'en'

LANGUAGES = [
    ('en', _('English')),
    ('zh', _('Chinese')),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]



TIME_ZONE = 'UTC'
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = 'media/'
MEDIA_ROOT = os.getenv('MEDIA_ROOT', default=os.path.join(BASE_DIR, 'media'))




DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'account.User'


# default is ~2.5 MB; bump to e.g. 20 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your_email@example.com'
EMAIL_HOST_PASSWORD = 'your_password'
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = 'your_email@example.com'


# ==========================================================================================
# =================API Extra Security================================
FRONTEND_APP_KEY=os.getenv("FRONTEND_APP_KEY")
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY")
# =================API Extra Security================================
# ==========================================================================================


