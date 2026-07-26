from rest_framework import serializers
from django.utils.translation import gettext as _
from .models import ChatMessage, ChatRoom, Attachment, Notification, ChatEvent
from task.models import Order, OrderChangesRequest
from account.models import ServiceProviderProfile, User
from find_worker_config.model_choice import UserRole, UserDefault, SendMessageType
import os
import mimetypes


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "photo", "role"]

class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = "__all__"

class MessageChatEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatEvent
        fields = "__all__"

class ChatMessageSerializer(serializers.ModelSerializer):
    attachments = MessageAttachmentSerializer(many=True, required=False)
    event = MessageChatEventSerializer(required=False)
    sender_data = serializers.SerializerMethodField()
    sender = serializers.ChoiceField(required=False, choices=UserDefault.choices)
    class Meta:
        model = ChatMessage
        fields = ["id", "sender", "sender_data", "message_type", "content", "timestamp", "is_read", "attachments", "event"]
    
    def to_representation(self, instance):
        payload = {
            "id": instance.id,
            "message_type": instance.message_type,
            "content": instance.content,
            "timestamp": instance.timestamp.isoformat(),
            "is_read": instance.is_read,
            
            "attachments": [],
            "event": [],
            
            "sender": instance.sender,
            "sender_data": self.get_sender_data(instance)
        }
        if instance.message_type == SendMessageType.EVENT and instance.event:
            payload["event"] = instance.event.payload
        # if attachment:
        #     payload["attachments"] = str(attachment)
        return payload

    def get_sender_data(self, obj):
        user = None
        if obj.sender == UserDefault.CUSTOMER:
            user = obj.room.customer.user
        elif obj.sender == UserDefault.PROVIDER:
            user = obj.room.provider.user
        else:
            raise Exception(_("Invalid User!"))
        return UserMiniSerializer(user).data if user else None
    
    def get_message_type_from_mime(self, mime: str):
        if not mime:
            return SendMessageType.FILE
        elif mime.startswith("image/"):
            return SendMessageType.IMAGE
        elif mime.startswith("video/"):
            return SendMessageType.VIDEO
        elif mime.startswith("audio/"):
            return SendMessageType.AUDIO
        return SendMessageType.FILE
    
    def create(self, validated_data):
        attachments_files = self.context['request'].FILES.getlist('attachments')
        event_data = validated_data.pop("event", {})

        message = ChatMessage.objects.create(**validated_data)
        message_type = SendMessageType.TEXT

        for file in attachments_files:
            mime, _ = mimetypes.guess_type(file.name)
            Attachment.objects.create(
                message=message,
                file=file,
                mime=mime or "",
                name=file.name,
                size=file.size
            )

            message_type = self.get_message_type_from_mime(mime)
        message.message_type = message_type
        message.save(update_fields=["message_type"])
        return message

class ChatRoomSerializer(serializers.ModelSerializer):
    other_user = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    class Meta:
        model = ChatRoom
        fields = ["uuid", "other_user", "unread_count", "last_message"]
    
    def get_last_message(self, obj):
        msg = obj.messages.order_by("-timestamp").only("id","content","message_type","timestamp", "is_read").first()
        if not msg: return None
        return {"id": msg.id, "message_type": msg.message_type, "content": msg.content, "timestamp": msg.timestamp}
    
    def get_other_user(self, obj):
        u = self.context["request"].user
        other = obj.provider if obj.customer.user == u else obj.customer
        return UserMiniSerializer(other.user).data
    
    def get_unread_count(self, obj):
        profile = self.context.get("profile")
        unread_message = obj.messages.filter(is_read=False).exclude(sender=profile)
        print("unread_message", unread_message)
        
        if profile == UserDefault.CUSTOMER:
            return obj.messages.filter(is_read=False).exclude(sender=profile).count()

        return obj.messages.filter(is_read=False).exclude(sender=profile).count()

class RoomStartSerializer(serializers.Serializer):
    provider_id = serializers.IntegerField(required=True)

    def validate(self, attrs):
        request = self.context["request"]
        provider_id = attrs["provider_id"]
        me_customer = request.user.customer_profile
        other_provider = ServiceProviderProfile.objects.get(id=provider_id)
        print("other_provider: :", other_provider)
        if me_customer == other_provider:
            raise Exception(_("Same user cannot chat each other!"))
        self.customer = me_customer
        self.provider = other_provider
        return super().validate(attrs)

    def create(self, validated):
        request = self.context["request"]
        room, created = ChatRoom.objects.get_or_create(
            customer=self.customer,
            provider=self.provider
        )
        return room
    
    def to_representation(self, instance):
        return ChatRoomSerializer(instance, context=self.context).data





class NotificationSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    class Meta:
        model = Notification
        fields = "__all__"









# ============================================================================================
# =========================Special Serializer for Get Message Object=========================
class AttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ("id", "file_url", "mime", "name", "size", )

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return None
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

class ChatOrderSerializer(serializers.ModelSerializer):
    end_time = serializers.SerializerMethodField()
    end_datetime = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ("id", "title", "description", "area", "amount", "status", "payment_status", "working_date", "working_start_time", "working_hour", "end_time", "end_datetime", "created_at", "is_provider_review", "is_customer_review", "is_cancel_request", "cancel_request_by", "cancel_request_accept_by")
    
    def get_end_time(self, obj):
        if obj.end_time:
            return obj.end_time.strftime("%H:%M:%S")
        return None

    def get_end_datetime(self, obj):
        if obj.end_datetime:
            return obj.end_datetime.isoformat()
        return None

class OrderChangesRequestSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderChangesRequest
        fields = ("id", "request_by", "status", "changes_type", "changes_data", "created_at", "updated_at", )

class ChatEventSerializer(serializers.ModelSerializer):
    order_object = ChatOrderSerializer(read_only=True)
    reference_object = OrderChangesRequestSerializer(read_only=True)

    class Meta:
        model = ChatEvent
        fields = ("id", "event_type", "payload", "order_object", "reference_object", "created_at", "updated_at",)

class ChatMessageSpecialSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True,read_only=True)
    event = ChatEventSerializer(read_only=True)
    is_event_message = serializers.SerializerMethodField()
    sender_data = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ("id","sender", "sender_data", "message_type","content","timestamp","is_read", "is_event_message", "attachments","event",)

    def get_is_event_message(self, obj):
        return hasattr(obj, "event")
    
    def get_sender_data(self, obj):
        if obj.sender == UserDefault.PROVIDER:
            user = obj.room.provider.user
        elif obj.sender == UserDefault.CUSTOMER:
            user = obj.room.customer.user
        else:
            raise Exception(_("Invalid User!"))
        return UserMiniSerializer(user).data

# messages = (
#     ChatMessage.objects
#     .filter(room=room)
#     .select_related(
#         "event",
#         "event__order_object",
#         "event__reference_object",
#     )
#     .prefetch_related(
#         "attachments"
#     )
# )
# =========================Special Serializer for Get Message Object=========================
# ============================================================================================







