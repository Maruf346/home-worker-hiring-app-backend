from rest_framework import status
from django.utils.translation import gettext as _
from .serializers import ChatRoomSerializer, ChatMessageSerializer, MessageAttachmentSerializer, RoomStartSerializer, NotificationSerializer, ChatMessageSpecialSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404, redirect
from .models import ChatMessage, ChatRoom, Attachment, Notification
from find_worker_config.utils import UpdateModelViewSet
from rest_framework.viewsets import GenericViewSet
from find_worker_config.model_choice import UserDefault
from django.db import transaction
from rest_framework.exceptions import ValidationError, PermissionDenied


class ChatRoomViewsets(GenericViewSet):
    queryset = ChatRoom.objects.all()
    serializer_class = ChatRoomSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "user"

    def get_user(self) -> object:
        return self.request.user
    
    def get_customer(self) -> object:
        return self.get_user().customer_profile
    
    def get_provider(self) -> object:
        return self.get_user().service_provider_profile

    def get_room_by_uuid(self, uuid):
        return ChatRoom.objects.get(uuid=uuid)

    @action(detail=False, methods=["post"], url_path="start-chat")
    def start_chat(self, request, *args, **kwargs):
        try:
            serializer = RoomStartSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                {
                    "status": True,
                    "room": serializer.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "status": False,
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=["get"], url_path="customer")
    def get_customer_room(self, request, *args, **kwargs):
        uuid = request.query_params.get("uuid")        
        if uuid:
            room = ChatRoom.objects.select_related(
                "customer", "provider"
            ).get(uuid=uuid, customer=self.get_customer())
            serializer = self.get_serializer(room, context={"profile": UserDefault.CUSTOMER, "request": request})
            return Response({
                "status": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        print("---------")
        rooms = ChatRoom.objects.filter(
            customer=self.get_customer()
        ).select_related("customer", "provider")
        
        serializer = self.get_serializer(rooms, many=True)
        return Response({
            "status": True,
            "count": len(serializer.data),
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="provider")
    def get_provider_room(self, request, *args, **kwargs):
        uuid = request.query_params.get("uuid")
        if uuid:
            room = ChatRoom.objects.select_related(
                "customer", "provider"
            ).get(uuid=uuid, provider=self.get_provider())
            serializer = self.get_serializer(room, context={"profile": UserDefault.PROVIDER, "request": request})
            return Response({
                "status": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        
        room = ChatRoom.objects.filter(
            provider=self.get_provider()
        ).select_related("customer","provider")
        serializer = self.get_serializer(room, many=True)
        return Response(
            {
                'status': True,
                'count': len(serializer.data),
                'data': serializer.data
            }, status=status.HTTP_200_OK
        )

class ChatRoomMessageViewsets(UpdateModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_user_profile(self):
        profile = self.kwargs.get("room_user", "").upper()
        if profile not in UserDefault.values:
            raise ValueError(_("Profile Type Invalid."))
        return self.kwargs.get("room_user")

    def get_room(self):
        uuid = self.request.query_params.get("uuid")
        room = ChatRoom.objects.get(uuid=uuid)
        if uuid and room:
            return room
        else:
            return Response(
                {
                    "status": False,
                    "message": _("Conversation ID Missing.")
                }, status=status.HTTP_400_BAD_REQUEST
            )

    def get_queryset(self):
        room = self.get_room()
        return ChatMessage.objects.select_related("room").filter(room=room)
    
    def list(self, request, *args, **kwargs):
        messages = self.get_queryset()
        return Response(
            {
                "status": True,
                "data": ChatMessageSpecialSerializer(messages, many=True).data
            }, status=status.HTTP_200_OK
        )
    
    def retrieve(self, request, *args, **kwargs):
        return Response(
            {
                "status": True,
                "data": ChatMessageSpecialSerializer(self.get_object()).data
            }, status=status.HTTP_200_OK
        )
    
    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.save(room=self.get_room(), sender=self.get_user_profile().upper())
                return Response(
                    {
                        'status': True,
                        'data': serializer.data
                    }, status=status.HTTP_201_CREATED
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
        except PermissionDenied as e:
            return Response(
                {
                    'status': False,
                    'message': str(e),
                }, status=status.HTTP_400_BAD_REQUEST
            )

class NotificationViewsets(UpdateModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    delete_message = _("Notification Deleted.")

    def get_queryset(self):
        return Notification.objects.filter(received=self.request.user)
    
    def perform_retrieve(self, serializer):
        serializer.instance.is_read = True
        serializer.instance.save(update_fields={"is_read": True})
        return super().perform_retrieve(serializer)
    
    def create(self, request, *args, **kwargs):
        return Response(
            {
                "status": False,
                "message": _("Notification direct create not allow.")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def update(self, request, *args, **kwargs):
        return Response(
            {
                "status": False,
                "message": _("Notification direct create not allow.")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

