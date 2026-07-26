from django.utils.translation import gettext as _
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from account.models import ActivityLog
from chat_notify.models import Notification
from django.db import transaction
from chat_notify.utils import push_notification, push_notify_role
from chat_notify.models import Notification


def handle_log_engine(request, action, status, message, entity=None, perform_user=None, perform_user_type=None, logify=True, notify=False, role=None, send_to=None, send_to_type=None, notification_message=None):
    log_data = {
        "action": action,
        "status": status,
        "message": message,
        "entity": entity,
        "request": request
    }
    log_engine = LogActivityEngine(log_data)
    if logify:
        log_engine.create_log(perform_user, perform_user_type)
    if notify:
        log_engine.send_notification(role, receiver=send_to or perform_user or request.user, profile=send_to_type or perform_user_type or None, notification_message=notification_message or None)

class LogActivityEngine:
    def get_confirm_data(self, field, field_name):
        if not field:
            raise Exception(_("{} is missing.").format(field_name))
        return field
    
    def __init__(self, data: dict):
        self.action = self.get_confirm_data(data.get("action"), "Action")
        self.status = self.get_confirm_data(data.get("status"), "Status")
        self.entity = data.get("entity")
        self.request = self.get_confirm_data(data.get("request"), "Request")
        self.message = self.get_confirm_data(data.get("message"), "Message")
    
    def get_entity_type(self):
        if self.entity is None:
            return None
        elif not hasattr(self.entity, "_meta"):
            raise Exception(_("Entity must be a Django model instance."))
        else:
            return ContentType.objects.get_for_model(self.entity)

    def get_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0]
        return request.META.get("REMOTE_ADDR")

    def get_data(self, user, user_type):
        dict_data = {
            "user": user,
            "user_type": user_type,
            "action": self.action,
            "message": self.message,
            "status": self.status,
            "ip_address": self.get_ip(self.request)
        }
        if self.entity:
            dict_data["entity_type"] = self.get_entity_type()
            dict_data["entity_id"] = self.entity.id
        return dict_data

    def create_log(self, user=None, user_type=None):
        try:
            with transaction.atomic():
                log = ActivityLog.objects.create(
                    **self.get_data(user, user_type)
                )
                return log
        except Exception as e:
            print("error: ", e)
            raise Exception(_("Someting wrong for create log!"))


    def get_notification_data(self, notification_for, receiver, profile, notification_message=None):
        dict_data = {
            "notification_for": notification_for,
            "receiver": receiver,
            "profile": profile,
            "action": self.action,
            "message": notification_message or self.message
        }
        if self.entity:
            dict_data["entity_type"] = self.get_entity_type()
            dict_data["entity_id"] = self.entity.id
        return dict_data

    def send_notification(self, notification_for, receiver=None, profile=None, notification_message=None):
        receiver = receiver
        profile = profile
        notification_for = self.get_confirm_data(notification_for, "Notification send to")
        try:
            with transaction.atomic():
                notification = Notification.objects.create(
                    **self.get_notification_data(notification_for, receiver, profile, notification_message)
                )
                # Need Logic For Dynamic Set
                if receiver:
                    push_notification(
                        user_id=notification.receiver.id,
                        data={
                            "notify_text": notification.notify_text,
                            "entity_type": notification.entity_type.model if notification.entity_type else None,
                            "entity": notification.entity_id,
                            "is_read": notification.is_read
                        }
                    )
                elif notification_for:
                    push_notify_role(
                        role=notification_for,
                        data={
                            "notify_text": notification.notify_text,
                            "entity_type": notification.entity_type.model if notification.entity_type else None,
                            "entity": notification.entity_id,
                            "is_read": notification.is_read
                        }
                    )
                return notification
        except Exception as e:
            print("error: ", e)
            raise Exception(_("Someting wrong for create log!"))

