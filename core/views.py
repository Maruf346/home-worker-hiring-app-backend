from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Ticket, SignUpSlider, CustomerScreenSlide
from .serializers import TicketSerializer, TicketReplySerializer, TicketStatusUpdateSerializer, AdminWalletSerializer, SignUpSliderSerializer, CustomerScreenSlideSerializer, HelperSerializer
from find_worker_config.model_choice import UserRole, TicketStatus, LogStatus, UserDefault
from find_worker_config.utils import UpdateModelViewSet, UpdateReadOnlyModelViewSet
from django.db import transaction
from rest_framework.views import APIView
from .models import AdminWallet
from find_worker_config.permissions import IsAdminWritePermissionOnly
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from .paginations import DefaultPagination
from account.models import User, Address, ServiceProviderProfile
from math import radians, cos, sin, asin, sqrt
from .services.log_engine import handle_log_engine
from django.db.models import Q
import os


# ----------------------------------------------------------
# Ticket ViewSet
class TicketViewSet(UpdateModelViewSet):
    queryset = Ticket.objects.all().order_by("-created_at")
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    def get_user_profile_type(self):
        if self.request.user.role == UserRole.ADMIN:
            raise Exception("Admin can't create tickets!")
        profile_type = self.request.headers.get("profile-type")
        if not profile_type:
            raise Exception("Profile Type Missing")
        return profile_type.upper()

    def get_queryset(self):
        user = self.request.user
        profile_type = self.request.headers.get("profile-type", "").upper()
        tickets = Ticket.objects.all().order_by("-updated_at")
        
        if user.role == UserRole.USER and profile_type:
            return tickets.filter(user=user, user_profile_type=profile_type)
        elif user.role == UserRole.ADMIN:
            return tickets
        return None

    def get_serializer_class(self):
        if self.action == "reply":
            return TicketReplySerializer
        elif self.action in ["update_status"]:
            return TicketStatusUpdateSerializer
        return TicketSerializer
    
    def perform_create(self, serializer):
        user = self.request.user
        user_profile_type = self.get_user_profile_type()
        if user_profile_type not in UserDefault.values:
            raise Exception("Invalid Profile Type")
        with transaction.atomic():
            instance = serializer.save(user=user, user_profile_type=user_profile_type)
            
            handle_log_engine(
                request=self.request, action="CREATE NEW TICKET", status=LogStatus.SUCCESS, message="Create a New Ticket.", entity=instance,
                perform_user=self.request.user, perform_user_type=user_profile_type, notify=True, role=UserRole.USER
            )
            handle_log_engine(
                request=self.request, action="CREATE NEW TICKET", status=LogStatus.SUCCESS, message="Create a New Ticket.", entity=instance,
                notify=True, role=UserRole.ADMIN
            )
            return instance
    
    def check_user(self, ticket: object):
        if not (self.request.user.role == UserRole.ADMIN or ticket.user == self.request.user):
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

    # -------------------
    # Reply to a ticket
    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        ticket = self.get_object()
        current_user_role = self.request.user.role
        log_user_type = ticket.user_profile_type if current_user_role == UserRole.USER else None
        self.check_user(ticket)
        try:
            serializer = TicketReplySerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                ticket_reply = serializer.save(ticket=ticket)
                if ticket.status == TicketStatus.CLOSED:
                    ticket.status = TicketStatus.OPEN
                ticket.save()

                # Handle Log and Notification---
                handle_log_engine(
                    request=request, action="REPLY FOR TICKET", status=LogStatus.SUCCESS, message="Send Reply for this Ticket.", entity=ticket_reply,
                    perform_user=self.request.user, perform_user_type=log_user_type, notify=False, logify=True
                )
                if current_user_role == UserRole.ADMIN:
                    handle_log_engine(
                        request=request, action="TICKET REPLY RECEIVED", status=LogStatus.SUCCESS, message="Received a Reply For this Ticket.", entity=ticket_reply,
                        # perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER, 
                        notify=True, logify=False,
                        role=UserRole.USER, send_to=ticket.user, send_to_type=ticket.user_profile_type
                    )
                else:
                    handle_log_engine(
                        request=request, action="TICKET REPLY RECEIVED", status=LogStatus.SUCCESS, message="Received a Reply For this Ticket.", entity=ticket_reply,
                        notify=True, logify=False,
                        role=UserRole.ADMIN
                    )
                return Response(
                    {
                        "status": True,
                        "data": serializer.data
                    }, status=status.HTTP_201_CREATED
                )
        except ValidationError:
            handle_log_engine(
                request=request, action="REPLY FOR TICKET", status=LogStatus.FAILED, message="Failed to Reply for this Ticket.",
                perform_user=self.request.user, perform_user_type=log_user_type or None
            )
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="REPLY FOR TICKET", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=log_user_type or None
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
    # -------------------

    # -------------------
    # Close a ticket (only admin or owner)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        ticket = self.get_object()
        current_user_role = self.request.user.role
        log_user_type = ticket.user_profile_type if current_user_role == UserRole.USER else None
        self.check_user(ticket)
        try:
            with transaction.atomic():
                ticket.status = "closed"
                ticket.save()
                serializer = self.get_serializer(ticket)

                # Hanlde Log and Notification---
                handle_log_engine(
                    request=request, action="TICKET CLOSE", status=LogStatus.SUCCESS, message="Mark Close this Ticket.", entity=ticket,
                    perform_user=self.request.user, perform_user_type=log_user_type, notify=False, logify=True
                )
                if current_user_role == UserRole.ADMIN:
                    handle_log_engine(
                        request=request, action="TICKET CLOSE", status=LogStatus.SUCCESS, message="Mark Close this Ticket.", entity=ticket,
                        # perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER, 
                        notify=True, logify=False,
                        role=UserRole.USER, send_to=ticket.user, send_to_type=ticket.user_profile_type
                    )
                else:
                    handle_log_engine(
                        request=request, action="TICKET CLOSE", status=LogStatus.SUCCESS, message="Mark Close this Ticket.", entity=ticket,
                        # perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER, 
                        notify=True, logify=False,
                        role=UserRole.ADMIN
                    )
                return Response(
                    {
                        "status": True,
                        "data": serializer.data
                    }
                )
        except Exception as e:
            handle_log_engine(
                request=request, action="TICKET CLOSE", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=log_user_type or None
            )
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )
    # -------------------
# ----------------------------------------------------------

# -------------------
# Admin Wallet Views
class AdminWalletViews(APIView):
    permission_classes = [IsAdminUser]

    def get_wallet(self):
        wallet, _ = AdminWallet.objects.get_or_create()
        return wallet
    
    def get(self, request):
        serializer = AdminWalletSerializer(self.get_wallet())
        return Response(
            {
                "status": True,
                "data": serializer.data
            }
        )
# -------------------

# -------------------
# Singup Slider Viewsets
class SignUpSliderViewset(UpdateModelViewSet):
    queryset = SignUpSlider.objects.all()
    serializer_class = SignUpSliderSerializer
    permission_classes = [IsAdminWritePermissionOnly]
# -------------------

# -------------------
# Customer Screen Slider Viewsets
class CustomerScreenSlideViewset(UpdateModelViewSet):
    queryset = CustomerScreenSlide.objects.all()
    serializer_class = CustomerScreenSlideSerializer
    permission_classes = [IsAdminWritePermissionOnly]
# -------------------

# ----------------------------------------------------------
# Buyer/Helper List for Customer/Client
class HelperListViewset(UpdateReadOnlyModelViewSet):
    serializer_class = HelperSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination

    def get_serializer_context(self):
        return {"request": self.request}
    
    def haversine(self, lat2, lon2):
        lon1, lat1, lon2, lat2 = map(
            radians, [self.user_lng, self.user_lat, lon2, lat2]
        )
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return round(6371 * c, 2)
    
    def get_map_distance(self,  lat2, lon2):
        api_key = os.getenv("GOOGLE_MAP_API_KEY")
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": f"{lat1},{lon1}",
            "destinations": f"{lat2},{lon2}",
            "key": api_key
        }
        response = requests.get(url, params=params)
        print("Google Maps API Response:", response.text)  # Debug log
        if response.status_code != 200:
            return None
        data = response.json()
        try:
            distance_text = data["rows"][0]["elements"][0]["distance"]["text"]
            distance_value = float(distance_text.replace(" km", "").replace(",", ""))
            return distance_value
        except (KeyError, IndexError, ValueError):
            return None

    def get_filter_data(self, queryset):
        # ---- Query Params ----
        q = self.request.query_params.get("q")
        category_id = self.request.query_params.get("category_id")
        distance_radius = self.request.query_params.get("distance_radius")
        budget = self.request.query_params.get("budget")
        min_rating = self.request.query_params.get("rating")
        availability = self.request.query_params.get("availability")

        # ---- Search Filter ----
        if q:
            queryset = queryset.filter(
                Q(company_name__icontains=q) |
                Q(details__icontains=q)
            )

        # ---- Category Filter ----
        if category_id:
            queryset = queryset.filter(
                service_category__id=category_id
            )

        # ---- Rating Filter ----
        if min_rating:
            queryset = queryset.filter(
                rating__gte=float(min_rating)
            )
        
        # ---- Availability ----
        if availability:
            queryset = queryset.filter(
                availability_status=availability
            )

        # ---- Budget ----
        if budget:
            queryset = queryset.filter(
                hourly_rate__lte=float(budget)
            )

        # ---- Distance Calculation (ALWAYS attach) ----
        helpers = []
        for helper in queryset:
            office = helper.office_location
            if not office or not office.lat or not office.lng:
                continue
            distance = self.haversine(office.lat, office.lng)
            # distance = self.get_map_distance(office.lat, office.lng)
            helper.distance_km = distance

            # ---- Distance Radius Filter ----
            if distance_radius:
                if distance <= float(distance_radius):
                    helpers.append(helper)
            else:
                helpers.append(helper)
        return helpers
    
    def get_queryset(self):
        user = self.request.user
        address = Address.objects.filter(user=user, is_default=True).first()
        if not address:
            return User.objects.none()
        self.user_lat = address.lat
        self.user_lng = address.lng

        helper_list = ServiceProviderProfile.objects.select_related(
            "user", "office_location"
        ).prefetch_related(
            "service_category"
        ).exclude(
            user=user
        ).filter(
            availability_status=True
        )
        return helper_list
    
    def get_sorting_queryset(self, queryset, sort_by):
        if sort_by == "rating":
            queryset.sort(key=lambda x: x.rating, reverse=True)
        elif sort_by == "price":
            queryset.sort(key=lambda x: x.hourly_rate or 0)
        elif sort_by == "distance" or not sort_by:
            queryset.sort(key=lambda x: x.distance_km)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        helpers = self.get_filter_data(queryset)
        sort_by = request.query_params.get("sort_by")
        helpers = self.get_sorting_queryset(helpers, sort_by)

        page = self.paginate_queryset(helpers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(helpers, many=True)
        return Response({
            "status": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
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

        office = instance.office_location
        if office or office.lat or office.lng:
            # self.get_map_distance(office.lat, office.lng) # use For Google API Destination
            instance.distance_km = self.haversine(office.lat, office.lng)
        serializer = self.get_serializer(instance)
        return self.perform_retrieve(serializer)

# ----------------------------------------------------------

