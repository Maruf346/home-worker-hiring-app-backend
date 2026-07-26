from account.models import HelperSlotException, Address, User, HelperStrike
from django.utils.translation import gettext as _
from .serializers import ServiceCategorySerializer, ServiceSubCategorySerializer, ReviewAndRatingSerializer, PaymentTransactionSerializer, CompleteSerializer, CounterSerializer, ProposeNewTimeActionSerializer, ProposeNewTimeSerializer, SetHourSerializer, OrderSerializerAll, StartWorkSerializer, ReviewAndRatingSerializer
from find_worker_config.utils import UpdateModelViewSet, PaymentTransactionModule, UpdateReadOnlyModelViewSet
from .models import ServiceCategory, ServiceSubCategory, Order, ReviewAndRating, PaymentTransaction, OrderRefundRequest, OrderChangesRequest
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from find_worker_config.permissions import IsAdminWritePermissionOnly, ForCustomerProfile, ForAdminProfile
from find_worker_config.model_choice import UserRole, OrderStatus, OrderPaymentStatus, PaymentTransactionType, PaymentAction, RefundStatus, UserDefault, LogStatus, HelperSlotExceptionType, OrderChangesRequestStatus, ChangesRequestType, SendMessageType, SendEventType, OrderChangeRequestAction
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.generics import CreateAPIView
from core.services.log_engine import handle_log_engine
from datetime import datetime, timedelta
from core.paginations import DefaultPagination
from math import radians, cos, sin, asin, sqrt
from chat_notify.utils import PushSendMessage
from chat_notify.models import ChatRoom
from core.services.slot_status_engine import SlotStatusEngine
from django.db import transaction
from rest_framework.views import APIView
from account.models import ServiceProviderProfile, HelperWeeklyAvailability
from core.services.slot_status_engine import SlotStatusEngine
from find_worker_config.model_choice import DayStatus

# ============================================================
# Category Views Section ===================
class ServiceCategoryViewSet(UpdateModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAdminWritePermissionOnly]

    def perform_update(self, serializer):
        instance = serializer.save()
        handle_log_engine(
            request=self.request, action="CREATE CATEGORY", status=LogStatus.SUCCESS, message="Create a New Category.", entity=instance,
            perform_user=self.request.user
        )
        return instance

class ServiceSubCategoryViewSet(UpdateModelViewSet):
    queryset = ServiceSubCategory.objects.all()
    serializer_class = ServiceSubCategorySerializer
    permission_classes = [IsAdminWritePermissionOnly]

    def perform_update(self, serializer):
        instance = serializer.save()
        handle_log_engine(
            request=self.request, action="CREATE SUB-CATEGORY", status=LogStatus.SUCCESS, message="Create a New Sub-Category.", entity=instance,
            perform_user=self.request.user
        )
        return instance

# Category Views Section ===================
# ============================================================


# ============================================================
# ========Order Views Section===================

# -----------Custom Offer Order Start-------------
class GetHelperDateAvailablity(APIView):
    def get_date_available_slot(self, provider, date_obj, slot_duration=60):
        day_start = datetime.combine(date_obj, datetime.min.time())
        day_end = datetime.combine(date_obj + timedelta(days=1), datetime.min.time())
        
        slots = []
        current_time = day_start
        while current_time + timedelta(minutes=slot_duration) <= day_end:
            slot_start = current_time
            slot_end = current_time + timedelta(minutes=slot_duration)
            slot_status = self.get_slot_check(provider, date_obj, slot_start, slot_end)
            if slot_status == DayStatus.AVAILABLE:
                slots.append({
                    "slot": f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}",
                    "start_time": slot_start.strftime("%I:%M %p"),
                    "end_time": slot_end.strftime("%I:%M %p"),
                    "status": slot_status
                })
            current_time += timedelta(minutes=slot_duration)
        
        return slots
    
    def get_slot_check(self, provider, date, slot_start_dt, slot_end_dt):
        slot_engine = SlotStatusEngine()
        slot_status = slot_engine.get_status(
            provider=provider,
            date_obj=date,
            slot_start=slot_start_dt,
            slot_end=slot_end_dt
        )
        return slot_status
    
    def check_by_working_hour(self, provider, date, time, working_hour):
        if not date and not time:
            raise ValidationError(_("Date or time must be provided."))

        # Convert string to date
        if isinstance(date, str):
            date = datetime.strptime(date, "%d-%m-%Y").date()
        # Convert string to time
        if isinstance(time, str):
            try:
                time = datetime.strptime(time, "%I:%M %p").time()
            except ValueError:
                time = datetime.strptime(time, "%H:%M").time()
        working_hour = int(working_hour)

        slot_start_dt = datetime.combine(date, time)
        slot_end_dt = slot_start_dt + timedelta(hours=working_hour)

        if self.get_slot_check(provider, date, slot_start_dt, slot_end_dt) != HelperSlotExceptionType.AVAILABLE:
            return Response(
                {
                    "status": False,
                    "is_available": False,
                    "message": _("For {} hour, Slot is unavailable!").format(working_hour),
                    "available_slot": self.get_date_available_slot(provider, date)
                }, status=status.HTTP_200_OK
            )
        return Response(
                {
                    "stauts": True,
                    "is_availasble": True,
                    "message": _("For {} hour, Slot is available!").format(working_hour),
                    "slot": f"{slot_start_dt.strftime('%I:%M %p')} - {slot_end_dt.strftime('%I:%M %p')}"
                }, status=status.HTTP_200_OK
            )
    
    def get(self, request, provider_id, date):
        working_hour = self.request.query_params.get("working_hour", None)
        if working_hour:
            start_time = self.request.query_params.get("start_time")
            return self.check_by_working_hour(
                ServiceProviderProfile.objects.get(id=provider_id),
                date, start_time, working_hour,
            )
        try:
            provider = ServiceProviderProfile.objects.get(id=provider_id)
            date_obj = datetime.strptime(date, "%d-%m-%Y").date()
            weekday = date_obj.strftime("%a")

            # Load Weekly Availability and show "No available slots for this date." if no availability for this date
            availability = HelperWeeklyAvailability.objects.filter(provider=provider, day=weekday).first()
            slot_duration = 60
            # slot_duration = availability.slot_duration_minutes if availability else 60
            slots = self.get_date_available_slot(provider, date_obj, slot_duration)
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

class CustomerOrderCreateViews(CreateAPIView):
    serializer_class = OrderSerializerAll
    permission_classes = [IsAuthenticated]

    def convert_to_24h(self, time_str):
        try:
            return datetime.strptime(time_str, "%I:%M %p").time()
        except ValueError:
            raise ValidationError(_("Invalid time format. Expected format like '09:00 AM'"))
    
    def get_room(self, order):
        customer = order.customer
        provider = order.provider
        room, _ = ChatRoom.objects.get_or_create(
            customer=customer,
            provider=provider
        )
        return room
    
    def slot_engine_call(self, provider, date, slot_start_dt, slot_end_dt):
        slot_engine = SlotStatusEngine()
        slot_status = slot_engine.get_status(
            provider=provider,
            date_obj=date,
            slot_start=slot_start_dt,
            slot_end=slot_end_dt
        )
        if slot_status != HelperSlotExceptionType.AVAILABLE:
            status_map = {
                "BOOKED": _("Already booked"),
                "UNAVAILABLE": _("Provider unavailable"),
                "FREEZED": _("Temporarily locked"),
            }
            raise ValidationError({
                "slot": status_map.get(slot_status, _("Not available"))
            })
    
    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                instance = serializer.instance
                
                room = self.get_room(instance)
                sendMessage = PushSendMessage(request, room)
                sendMessage.order_chat_message(UserDefault.CUSTOMER, instance, message_type=SendMessageType.EVENT, event_type=SendEventType.ORDER_CREATED)
                sendMessage.send_message()
                
                handle_log_engine(
                    request=request, action="CUSTOM OFFER CREATED", status=LogStatus.SUCCESS, message="Custom Offer Created by Customer", entity=instance,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                    notify=True, logify=True, 
                    role=UserRole.USER
                )
                handle_log_engine(
                    request=request, action="CUSTOM OFFER CREATED", status=LogStatus.SUCCESS, message="Create a New Custom Order from Client", entity=instance,
                    perform_user=instance.provider.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, logify=False,
                    role=UserRole.USER
                )
                return Response(
                    {
                        'status': True,
                        'message': _('Custom offer created!'),
                        'data': serializer.data
                    }, status=status.HTTP_201_CREATED
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="CUSTOM OFFER CREATED", status=LogStatus.FAILED, message="Failed to Create Custom Offer",
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=False, logify=True
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
        except PermissionDenied as e:
            handle_log_engine(
                request=request, action="CUSTOM OFFER CREATED", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=False, logify=True
            )
            return Response(
                {
                    'status': False,
                    'message': str(e),
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            handle_log_engine(
                request=request, action="CUSTOM OFFER CREATED", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=False, logify=True,
            )
            return Response(
                {
                    'status': False,
                    'message': str(e),
                }, status=status.HTTP_400_BAD_REQUEST
            )

# -----------Custom Offer Order End-------------


class CustomerOrderViewSet(UpdateModelViewSet):
    serializer_class = OrderSerializerAll
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination
    
    def get_room(self, order):
        customer = order.customer
        provider = order.provider
        room, _ = ChatRoom.objects.get_or_create(
            customer=customer,
            provider=provider
        )
        return room

    def get_filter_data(self, queryset):
        # ---- Query Params ----
        status = self.request.query_params.get("status")
        q = self.request.query_params.get("q")
        category_id = self.request.query_params.get("category_id")
        budget = self.request.query_params.get("budget")

        working_date = self.request.query_params.get("working_date")
        created_at = self.request.query_params.get("created_at")

        # ---- Budget ---- confirm/complete/cancel **Important and Only Workable
        if status:
            if status == "confirm":
                queryset = queryset.filter(
                    status__in=[OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS]
                )
            elif status == "complete":
                queryset = queryset.filter(
                    status__in=[OrderStatus.COMPLETED, OrderStatus.IN_PROGRESS]
                )
            elif status == "cancel":
                queryset = queryset.filter(
                    status__in=[OrderStatus.CANCELLED, OrderStatus.REFUND_REQUEST, OrderStatus.REFUND]
                )

        # ---- Search Filter ----
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q)
            )

        # ---- Category Filter ----
        if category_id:
            queryset = queryset.filter(
                category__id=category_id
            )
        
        # ---- Budget ----
        if budget:
            queryset = queryset.filter(
                amount__lte=budget
            )

        # ---- Rating Filter ----
        if working_date:
            queryset = queryset.filter(working_date=working_date)
        
        # ---- Availability ----
        if created_at:
            try:
                date_obj = datetime.strptime(created_at, "%Y-%m-%d")
                next_day = date_obj + timedelta(days=1)
                queryset = queryset.filter(
                    created_at__gte=date_obj,
                    created_at__lt=next_day
                )
            except ValueError:
                pass
        
        return queryset

    def get_serializer_context(self):
        return {"request": self.request, "profile_type": UserDefault.CUSTOMER}

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user.customer_profile).order_by("-created_at")
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            orders = self.get_filter_data(queryset)

            page = self.paginate_queryset(orders)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(orders, many=True)
            return Response({
                "status": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'messgae': str(e),
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def counter(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            serializer = CounterSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(
                order=order, profile_type=UserDefault.CUSTOMER
            )
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.CUSTOMER, order, message_type=SendMessageType.EVENT, event_type=SendEventType.ORDER_COUNTER, changes_object=serializer.get_changes_object()
            )
            sendMessage.send_message()

            handle_log_engine(
                request=request, action="COUNTER OFFER SEND", status=LogStatus.SUCCESS, message="Send Counter Offer from Customer.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER, notification_message="Received Counter Offer from Customer"
            )
            return Response(
                {
                    "status": True,
                    "message": _("Counter Offer Sent")
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}

            handle_log_engine(
                request=request, action="COUNTER OFFER SEND", status=LogStatus.FAILED, message="Failed to Send Counter Offer.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )

    def get_or_create_slot_exception(self, order, exception_type):
        if not (order.provider and order.working_date and order.working_start_time):
            return None
    
        reason=f"{exception_type} via order"
        if HelperSlotException.objects.filter(order=order).exists():
            slot_exception = HelperSlotException.objects.filter(order=order).first()
            slot_exception.type = exception_type
            slot_exception.date = order.working_date
            slot_exception.start_time = order.working_start_time
            slot_exception.end_time = order.end_time
            slot_exception.reason = reason
            slot_exception.save()
        else:
            slot_exception = HelperSlotException.objects.create(
                provider=order.provider,
                order=order,
                
                type=exception_type,
                date=order.working_date,
                start_time=order.working_start_time,
                end_time=order.end_time,
                reason=reason
            )
        return slot_exception

    @action(detail=True, methods=["get"])
    def accept(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status != OrderStatus.PENDING:
            raise ValueError(f"Order already {order.status}.")
        if order.order_change_action != OrderChangeRequestAction.PROVIDER_COUNTER_SEND:
            raise ValueError("You can't accept the order now.")
        with transaction.atomic():
            order.status = OrderStatus.ACCEPT
            order.accepted_at = timezone.localtime(timezone.now())
            order.order_change_action = OrderChangeRequestAction.NO_ACTION
            order.save()

            self.get_or_create_slot_exception(order, HelperSlotExceptionType.FREEZED)
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.CUSTOMER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_STATUS,
                # changes_object=serializer.get_changes_object()
            )
            sendMessage.send_message()

            handle_log_engine(
                request=request, action="ACCEPT OFFER", status=LogStatus.SUCCESS, message="Accept the Custom Offer.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER, notification_message="Accept the Custom Offer by Customer"
            )
            return Response(
                {
                    "status": True,
                    "message": _("Order accept and awaiting for payment.")
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["get"], url_path="pay-and-confirm")
    def pay_and_confirm(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            # Error Handling, Permission and Acceptance For Payment
            if order.payment_transactions.filter(type=PaymentTransactionType.CREDIT, action=PaymentAction.ORDER_PAYMENT).exists():
                return Response(
                    {"status": False, "message": _("Duplicate payment detected.")},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if order.status == OrderStatus.CONFIRM and order.payment_status == OrderPaymentStatus.PAID:
                raise Exception(_("The order is already confirm!"))
            if not (order.status == OrderStatus.ACCEPT and order.payment_status == OrderPaymentStatus.UNPAID):
                return Response(
                    {"status": False, "message": _("Only accept and Unpaid order can payment to confirm!")},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
                # Here Code for Payment Process and Build Logic
                # payment_information = payment information value json
                # \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\

                # Payment Transaction----
                payment = PaymentTransactionModule(
                    user=request.user,
                    profile=UserDefault.CUSTOMER,
                    amount=order.amount,
                    order=order,
                    reference_object=order,
                    type=PaymentTransactionType.CREDIT,
                    action=PaymentAction.ORDER_PAYMENT
                )
                payment.payment_transaction()
                
                # Order update After payment transanction-------
                order.status = OrderStatus.CONFIRM
                order.payment_status = OrderPaymentStatus.PAID
                order.save(update_fields=["status", "payment_status"])

                self.get_or_create_slot_exception(order, HelperSlotExceptionType.BOOKED)
                
                room = self.get_room(order)
                sendMessage = PushSendMessage(request, room)
                sendMessage.order_chat_message(
                    UserDefault.CUSTOMER, order, message_type=SendMessageType.EVENT,
                    event_type=SendEventType.ORDER_STATUS,
                    # changes_object=serializer.get_changes_object()
                )
                sendMessage.send_message()

                handle_log_engine(
                    request=request, action="PAYMENT COMPLETE", status=LogStatus.SUCCESS, message="Payment Complete & Order Confirm", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=self.request.user, send_to_type=UserDefault.CUSTOMER
                )
                handle_log_engine(
                    request=request, action="PAYMENT COMPLETE", status=LogStatus.SUCCESS, message="Payment Complete & Order Confirm", entity=order,
                    notify=True, logify=False,
                    role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER
                )
                return Response(
                    {"status": True, "message": _("Order pay and confirm!")},
                    status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="PAYMENT COMPLETE", status=LogStatus.FAILED, message=str(e),
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )

            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"], url_path="propose-new-time")
    def propose_new_time(self, request, *args, **kwargs):
        order  = self.get_object()
        with transaction.atomic():
            data = request.data
            action = data.pop("action", None)
            if action == "create":
                serializer = ProposeNewTimeSerializer(data=request.data, context={"order": order})
            elif action == "update":
                serializer = ProposeNewTimeActionSerializer(data=request.data)
            else:
                raise Exception(_("Action not mention!"))
            serializer.is_valid(raise_exception=True)
            serializer.save(order=order, profile_type=UserDefault.CUSTOMER)

            self.get_or_create_slot_exception(order, HelperSlotExceptionType.BOOKED)
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.CUSTOMER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_CHANGE_REQUEST,
                changes_object=serializer.get_changes_object()
            )
            sendMessage.send_message()
            
            handle_log_engine(
                request=request, action="PROPOSE NEW TIME", status=LogStatus.SUCCESS, message="Send Propose New Time for Changes Time", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER, notification_message="Received Propose New Time for Changes Time."
            )
            return Response(
                {
                    "status": True,
                    "message": serializer.get_response_message()
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        order = self.get_object()
        changes_object = None
        data = request.data
        message = data.get("message", None)
        if message is None:
            raise ValueError("Cancellation Reason/Message must be needed.")
        
        with transaction.atomic():
            if order.changes_requests.filter(changes_type=ChangesRequestType.CANCEL, status=OrderChangesRequestStatus.NO_RESPONSE).exists():
                return Response(
                    {
                        "status": False,
                        "message": _("Cancellation Request already Send!")
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            
            if order.status in [OrderStatus.PENDING, OrderStatus.ACCEPT] and order.payment_status == OrderPaymentStatus.UNPAID:
                order.status = OrderStatus.CANCELLED
                order.payment_status = OrderPaymentStatus.CANCELLED
                order.cancel_at = timezone.now()
                changes_object = OrderChangesRequest.objects.create(
                    order=order,
                    request_by=UserDefault.CUSTOMER,
                    perform_by=UserDefault.CUSTOMER,
                    status=OrderChangesRequestStatus.ACCEPT,
                    changes_type=ChangesRequestType.CANCEL,
                    changes_data={
                        "message": message
                    }
                )
                response_message = "Order Cancelled"
            elif order.status in [OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS] and order.payment_status == OrderPaymentStatus.PAID:
                order.order_change_action = OrderChangeRequestAction.CUSTOMER_CANCEL_REQUEST_SEND
                order.status = OrderStatus.CANCELLATION_REQUEST
                changes_object = OrderChangesRequest.objects.create(
                    order=order,
                    request_by=UserDefault.CUSTOMER,
                    status=OrderChangesRequestStatus.NO_RESPONSE,
                    changes_type=ChangesRequestType.CANCEL,
                    changes_data={
                        "message": message
                    }
                )
                response_message = "Order Cancellation Request Send!"
            else:
                return Response(
                    {
                        "status": False,
                        "message": _("Order already {}").format(order.status)
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            order.save()

            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.CUSTOMER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_CANCEL,
                changes_object=changes_object
            )
            sendMessage.send_message()
            
            handle_log_engine(
                request=request, action="ORDER CANCELLATION REQUEST", status=LogStatus.SUCCESS, message="Send Cancel Request for Cancel This Order", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    "status": True,
                    "message": response_message
                }, status=status.HTTP_200_OK
            )
    
    @action(detail=True, methods=["post"], url_path="cancel-accept")
    def cancellation_accept(self, request, *args, **kwargs):
        # data----
        order = self.get_object()
        provider = order.provider
        data = request.data
        request_id = data.get("changes_request_id", None)
        action = data.get("action", None)

        # data validation----
        if request_id is None:
            raise ValueError("Changes Request must be needed!")
        elif action is None:
            raise ValueError("Changes action must be needed!")
        elif not OrderChangesRequest.objects.filter(pk=request_id).exists():
            raise ValueError("Wrong Request ID.")
        
        # get refund amount----
        def get_refund_amount(order):
            return order.amount
        
        # user validation----
        changes_request = OrderChangesRequest.objects.get(pk=request_id)
        if changes_request.request_by == UserDefault.CUSTOMER:
            raise Exception(_("You can't perform this action"))
        if changes_request.status not in [OrderChangesRequestStatus.NO_RESPONSE]:
            raise Exception(_("Order Request Already Perform!"))
        
        pending_cancel_request = OrderChangesRequest.objects.filter(
            order=order, status=OrderChangesRequestStatus.NO_RESPONSE
        ).first()
        if pending_cancel_request != changes_request:
            raise Exception(_("Wrong Request ID"))

        # use logic---
        with transaction.atomic():
            if action.upper() == OrderChangesRequestStatus.ACCEPT:
                changes_request.status = OrderChangesRequestStatus.ACCEPT
                changes_request.perform_by = UserDefault.CUSTOMER
                changes_request.save()

                Order.objects.filter(pk=order.id).update(
                    status=OrderStatus.REFUND_REQUEST,
                    payment_status=OrderPaymentStatus.REFUND,
                    cancel_at=timezone.now(),
                    order_change_action=OrderChangeRequestAction.NO_ACTION
                )
                refund, create = OrderRefundRequest.objects.get_or_create(
                    order=order,
                    defaults={
                        "customer":order.customer,
                        "reason":changes_request.changes_data.get("message", None),
                        "order_amount":order.amount,
                        "refund_amount":get_refund_amount(order)
                    }
                )

                HelperStrike.objects.create(
                    provider=provider,
                    order=order,
                    related_object=changes_request,
                    reason=f"For Confirm Order Cancellation.",
                    is_active=True,
                    expired_at = timezone.now() + timedelta(days=90)
                )
                
                HelperSlotException.objects.filter(order=order).update(is_active=False)
                response_message = "Order Cancelled Confirm & Refund Processing!"

                handle_log_engine(
                    request=request, action="CANCELLATION CONFIRM", status=LogStatus.SUCCESS, message="Order Cencellation Request Confirm By Customer.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER, notification_message="Order Cencellation Request Confirm By Customer."
                )
            elif action.upper() in [OrderChangesRequestStatus.DECLINED, "REJECT"]:
                changes_request.status = OrderChangesRequestStatus.DECLINED
                changes_request.save()
                response_message = "Order Cancellation Declined!"

                Order.objects.filter(pk=order.id).update(
                    status=OrderStatus.CONFIRM,
                    order_change_action=OrderChangeRequestAction.NO_ACTION
                )

                handle_log_engine(
                    request=request, action="CANCELLATION REJECTED", status=LogStatus.SUCCESS, message="Order Cencellation Request Rejected By Customer.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER, notification_message="Order Cencellation Request Rejected By Customer."
                )
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.CUSTOMER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_CANCEL,
                changes_object=changes_request
            )
            sendMessage.send_message()
            
            return Response(
                {
                    "status": True,
                    "message": response_message
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["post"], url_path="give-feedback")
    def give_feedback(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            with transaction.atomic():
                serializer = ReviewAndRatingSerializer(data=request.data, context={"order": order, "send_by": UserDefault.CUSTOMER, "request": request})
                serializer.is_valid(raise_exception=True)
                serializer.save()
                
                handle_log_engine(
                    request=request, action="SEND FEEDBACK", status=LogStatus.SUCCESS, message="Send Feedback with this Order.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.provider.user, send_to_type=UserDefault.PROVIDER, notification_message="Received Feedback with this Order."
                )
                return Response(
                    {
                        "status": True,
                        "message": _("Thanks for your feedback!")
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="SEND FEEDBACK", status=LogStatus.FAILED, message="Failed to Send Feedback with this Order.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )

    def create(self, request, *args, **kwargs):
        handle_log_engine(
            request=request, action="POST METHOD NOT ALLOWED", status=LogStatus.FAILED, message="Post Method perform not allowed.",
            perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
        )
        return Response(
            {
                "status": True,
                "message": _("Create method not allowed!")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def update(self, request, *args, **kwargs):
        handle_log_engine(
            request=request, action="UPDATE METHOD NOT ALLOWED", status=LogStatus.FAILED, message="Update Method perform not allowed.",
            perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
        )
        return Response(
            {
                "status": True,
                "message": _("Update method not allowed!")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def destroy(self, request, *args, **kwargs):
        handle_log_engine(
            request=request, action="DELETE METHOD NOT ALLOWED", status=LogStatus.FAILED, message="Delete Method perform not allowed.",
            perform_user=self.request.user, perform_user_type=UserDefault.CUSTOMER
        )
        return Response(
            {
                "status": True,
                "message": _("Delete method not allowed!")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

class ProviderOrderViewSet(UpdateModelViewSet):
    serializer_class = OrderSerializerAll
    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination
    
    def get_room(self, order):
        customer = order.customer
        provider = order.provider
        room, _ = ChatRoom.objects.get_or_create(
            customer=customer,
            provider=provider
        )
        return room

    def get_filter_data(self, queryset):
        # ---- Query Params ----
        status = self.request.query_params.get("status")
        q = self.request.query_params.get("q")
        category_id = self.request.query_params.get("category_id")
        budget = self.request.query_params.get("budget")

        working_date = self.request.query_params.get("working_date")
        created_at = self.request.query_params.get("created_at")

        # ---- Budget ---- confirm/complete/cancel **Important and Only Workable
        if status:
            if status == "confirm":
                queryset = queryset.filter(
                    status__in=[OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS]
                )
            elif status == "complete":
                queryset = queryset.filter(
                    status__in=[OrderStatus.COMPLETED, OrderStatus.IN_PROGRESS]
                )
            elif status == "cancel":
                queryset = queryset.filter(
                    status__in=[OrderStatus.CANCELLED, OrderStatus.REFUND_REQUEST, OrderStatus.REFUND]
                )

        # ---- Search Filter ----
        if q:
            queryset = queryset.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q)
            )

        # ---- Category Filter ----
        if category_id:
            queryset = queryset.filter(
                category__id=category_id
            )
        
        # ---- Budget ----
        if budget:
            queryset = queryset.filter(
                amount__lte=budget
            )

        # ---- Rating Filter ----
        if working_date:
            queryset = queryset.filter(working_date=working_date)
        
        # ---- Availability ----
        if created_at:
            try:
                date_obj = datetime.strptime(created_at, "%Y-%m-%d")
                next_day = date_obj + timedelta(days=1)
                queryset = queryset.filter(
                    created_at__gte=date_obj,
                    created_at__lt=next_day
                )
            except ValueError:
                pass
        
        return queryset

    def get_serializer_context(self):
        return {"request": self.request, "profile_type": UserDefault.PROVIDER}

    def get_queryset(self):
        user = self.request.user
        return Order.objects.filter(provider=user.service_provider_profile).order_by("-created_at")
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            orders = self.get_filter_data(queryset)

            page = self.paginate_queryset(orders)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(orders, many=True)
            return Response({
                "status": True,
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'messgae': str(e),
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"])
    def counter(self, request, *args, **kwargs):
        try:
            serializer = CounterSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            order = self.get_object()
            serializer.save(
                order=order, profile_type=UserDefault.PROVIDER
            )
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_COUNTER,
                changes_object=serializer.get_changes_object()
            )
            sendMessage.send_message()

            handle_log_engine(
                request=request, action="COUNTER OFFER SEND", status=LogStatus.SUCCESS, message="Send Counter Offer from Provider.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER, notification_message="Received Counter Offer from Provider"
            )
            return Response(
                {
                    "status": True,
                    "message": _("Counter Offer Sent")
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="COUNTER OFFER SEND", status=LogStatus.FAILED, message="Failed to Send Counter Offer.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
    
    def get_or_create_slot_exception(self, order, exception_type):
        if not (order.provider and order.working_date and order.working_start_time):
            return None
        reason=f"{exception_type} via order"
        if HelperSlotException.objects.filter(order=order).exists():
            slot_exception = HelperSlotException.objects.filter(order=order).first()
            slot_exception.type = exception_type
            slot_exception.date = order.working_date
            slot_exception.start_time = order.working_start_time
            slot_exception.end_time = order.end_time
            slot_exception.reason = reason
            slot_exception.save()
        else:
            slot_exception = HelperSlotException.objects.create(
                provider=order.provider,
                order=order,
                
                type=exception_type,
                date=order.working_date,
                start_time=order.working_start_time,
                end_time=order.end_time,
                reason=reason
            )
        return slot_exception

    @action(detail=True, methods=["get"])
    def accept(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status != OrderStatus.PENDING:
            raise ValueError(f"Order already {order.status}.")
        if order.order_change_action == OrderChangeRequestAction.PROVIDER_COUNTER_SEND:
            raise ValueError("You can't accept the order now.")
        
        with transaction.atomic():
            order.status = OrderStatus.ACCEPT
            order.accepted_at = timezone.localtime(timezone.now())
            order.order_change_action = OrderChangeRequestAction.NO_ACTION
            order.save()

            self.get_or_create_slot_exception(order, HelperSlotExceptionType.FREEZED)
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_STATUS,
            )
            sendMessage.send_message()

            handle_log_engine(
                request=request, action="ACCEPT OFFER", status=LogStatus.SUCCESS, message="Accept the Custom Offer.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER, notification_message="Accept the Custom Offer by Provider"
            )
            return Response(
                {
                    "status": True,
                    "message": _("Order accept and awaiting for payment.")
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["post"], url_path="set-work-hour")
    def set_work_hour(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            with transaction.atomic():
                serializer = SetHourSerializer(data=request.data, context={"order": order})
                serializer.is_valid(raise_exception=True)
                serializer.save(order=order)

                self.get_or_create_slot_exception(order, HelperSlotExceptionType.BOOKED)
                
                room = self.get_room(order)
                sendMessage = PushSendMessage(request, room)
                sendMessage.order_chat_message(
                    UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                    event_type=SendEventType.ORDER_HOUR_SET,
                    changes_object=serializer.get_changes_object()
                )
                sendMessage.send_message()

                handle_log_engine(
                    request=request, action="SET WORK HOUR", status=LogStatus.SUCCESS, message="Set Work Hour.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
                )
                return Response(
                    {
                        "status": True,
                        "message": _("{} Hour Set for complete the work!").format(serializer.validated_data.get("set_hour"))
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="SET WORK HOUR", status=LogStatus.FAILED, message="Failed to Set Work Hour.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=["post"], url_path="propose-new-time")
    def propose_new_time(self, request, *args, **kwargs):
        order = self.get_object()
        with transaction.atomic():
            data = request.data
            action = data.pop("action", None)
            if action == "create":
                serializer = ProposeNewTimeSerializer(data=request.data, context={"order": order})
            elif action == "update":
                serializer = ProposeNewTimeActionSerializer(data=request.data)
            else:
                raise Exception(_("Action not mention!"))
            serializer.is_valid(raise_exception=True)
            serializer.save(order=order, profile_type=UserDefault.PROVIDER)

            self.get_or_create_slot_exception(order, HelperSlotExceptionType.BOOKED)
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_CHANGE_REQUEST,
                changes_object=serializer.get_changes_object()
            )
            sendMessage.send_message()

            handle_log_engine(
                request=request, action="PROPOSE NEW TIME", status=LogStatus.SUCCESS, message="Send Propose New Time for Changes Time", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER, notification_message="Received Propose New Time for Changes Time."
            )
            return Response(
                {
                    "status": True,
                    "message": serializer.get_response_message()
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        order = self.get_object()
        changes_object = None
        data = request.data
        message = data.get("message", None)
        if message is None:
            raise ValueError("Cancellation Reason/Message must be needed.")
        
        with transaction.atomic():
            if order.changes_requests.filter(changes_type=ChangesRequestType.CANCEL, status=OrderChangesRequestStatus.NO_RESPONSE).exists():
                return Response(
                    {
                        "status": False,
                        "message": _("Cancellation Request already Send!")
                    }, status=status.HTTP_400_BAD_REQUEST
                )

            if order.status in [OrderStatus.PENDING, OrderStatus.ACCEPT] and order.payment_status == OrderPaymentStatus.UNPAID:
                order.status = OrderStatus.CANCELLED
                order.payment_status = OrderPaymentStatus.CANCELLED
                order.cancel_at = timezone.now()
                changes_object = OrderChangesRequest.objects.create(
                    order=order,
                    request_by=UserDefault.PROVIDER,
                    perform_by=UserDefault.PROVIDER,
                    status=OrderChangesRequestStatus.ACCEPT,
                    changes_type=ChangesRequestType.CANCEL,
                    changes_data={
                        "message": message
                    }
                )
                response_message = "Order Cancelled"
            elif order.status in [OrderStatus.CONFIRM, OrderStatus.IN_PROGRESS] and order.payment_status == OrderPaymentStatus.PAID:
                order.order_change_action = OrderChangeRequestAction.PROVIDER_CANCEL_REQUEST_SEND
                order.status = OrderStatus.CANCELLATION_REQUEST
                changes_object = OrderChangesRequest.objects.create(
                    order=order,
                    request_by=UserDefault.PROVIDER,
                    status=OrderChangesRequestStatus.NO_RESPONSE,
                    changes_type=ChangesRequestType.CANCEL,
                    changes_data={
                        "message": message
                    }
                )
                response_message = "Order Cancellation Request Send!"
            else:
                return Response(
                    {
                        "status": False,
                        "message": _("Order already {}").format(order.payment_status)
                    }, status=status.HTTP_400_BAD_REQUEST
                )
            order.save()
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_CANCEL,
                changes_object=changes_object
            )
            sendMessage.send_message()

            handle_log_engine(
                request=request, action="ORDER CANCELLATION REQUEST", status=LogStatus.SUCCESS, message="Send Cancel Request for Cancel This Order", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": True,
                    "message": response_message
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["post"], url_path="cancel-accept")
    def cancellation_accept(self, request, *args, **kwargs):
        # data----
        order = self.get_object()
        data = request.data
        request_id = data.get("changes_request_id", None)
        action = data.get("action", None)

        # data validation----
        if request_id is None:
            raise ValueError("Changes Request must be needed!")
        elif action is None:
            raise ValueError("Changes action must be needed!")
        elif not OrderChangesRequest.objects.filter(pk=request_id).exists():
            raise ValueError("Wrong Request ID.")
        
        # get refund amount----
        def get_refund_amount(order):
            return order.amount
        
        # user validation----
        changes_request = OrderChangesRequest.objects.get(pk=request_id)
        if changes_request.request_by == UserDefault.PROVIDER:
            raise Exception(_("You can't perform this action"))
        if changes_request.status not in [OrderChangesRequestStatus.NO_RESPONSE]:
            raise Exception(_("Order Request Already Perform!"))
        
        pending_cancel_request = OrderChangesRequest.objects.filter(
            order=order, status=OrderChangesRequestStatus.NO_RESPONSE
        ).first()
        if pending_cancel_request != changes_request:
            raise Exception(_("Wrong Request ID"))
        
        # use logic---
        with transaction.atomic():
            if action.upper() == OrderChangesRequestStatus.ACCEPT:
                changes_request.status = OrderChangesRequestStatus.ACCEPT
                changes_request.perform_by = UserDefault.PROVIDER
                changes_request.save()

                Order.objects.filter(pk=order.id).update(
                    status=OrderStatus.REFUND_REQUEST,
                    payment_status=OrderPaymentStatus.REFUND,
                    cancel_at=timezone.now(),
                    order_change_action=OrderChangeRequestAction.NO_ACTION
                )
                OrderRefundRequest.objects.create(
                    order=order,
                    customer=order.customer,
                    reason=changes_request.changes_data.get("message", None),
                    order_amount=order.amount,
                    refund_amount=get_refund_amount(order)
                )
                HelperSlotException.objects.filter(order=order).update(is_active=False)
                response_message = "Order Cancelled Confirm & Refund Processing!"
                handle_log_engine(
                    request=request, action="CANCELLATION CONFIRM", status=LogStatus.SUCCESS, message="Order Cencellation Request Confirm By Provider.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER, notification_message="Order Cencellation Request Confirm By Provider."
                )
            elif action.upper() in [OrderChangesRequestStatus.DECLINED, "REJECT"]:
                changes_request.status = OrderChangesRequestStatus.DECLINED
                changes_request.save()
                response_message = "Order Cancellation Declined!"
                
                Order.objects.filter(pk=order.id).update(
                    status=OrderStatus.CONFIRM,
                    order_change_action=OrderChangeRequestAction.NO_ACTION
                )

                handle_log_engine(
                    request=request, action="CANCELLATION REJECTED", status=LogStatus.SUCCESS, message="Order Cencellation Request Rejected By Provider.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER, notification_message="Order Cencellation Request Rejected By Provider."
                )
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_CANCEL,
                changes_object=changes_request
            )
            sendMessage.send_message()
            
            return Response(
                {
                    "status": True,
                    "message": response_message
                }, status=status.HTTP_200_OK
            )

    @action(detail=True, methods=["post"], url_path="start-work")
    def start_work(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            if order.status != OrderStatus.CONFIRM:
                raise ValueError("Order must be confirmed!")
            serializer = StartWorkSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.work_start(order=order)
            
            room = self.get_room(order)
            sendMessage = PushSendMessage(request, room)
            sendMessage.order_chat_message(
                UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                event_type=SendEventType.ORDER_WORK_START
            )
            sendMessage.send_message()
            
            handle_log_engine(
                request=request, action="START WORK", status=LogStatus.SUCCESS, message="Start work to complete.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                notify=True, logify=True,
                role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER
            )
            return Response(
                {
                    "status": True,
                    "message": _("Work Started!")
                }, status=status.HTTP_200_OK
            )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}

            handle_log_engine(
                request=request, action="START WORK", status=LogStatus.FAILED, message="Failed to Start work to complete.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            with transaction.atomic():
                if self.get_object().status == OrderStatus.COMPLETED:
                    raise ValueError("Order already complete")
                elif self.get_object().status != OrderStatus.IN_PROGRESS:
                    raise ValueError("Order must be in progress!")
                
                serializer = CompleteSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                serializer.complete(order=self.get_object())
                
                # order.update_complete_rate()
                # order.save()
                
                room = self.get_room(order)
                sendMessage = PushSendMessage(request, room)
                sendMessage.order_chat_message(
                    UserDefault.PROVIDER, order, message_type=SendMessageType.EVENT,
                    event_type=SendEventType.ORDER_COMPLETE
                )
                sendMessage.send_message()

                handle_log_engine(
                    request=request, action="COMPLETE ORDER", status=LogStatus.SUCCESS, message="Mark Complete the order by OTP.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER
                )
                return Response(
                    {
                        "status": True,
                        "message": _("Work Complete!")
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="COMPLETE ORDER", status=LogStatus.FAILED, message="Failed to Mark Complete the order.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"], url_path="give-feedback")
    def give_feedback(self, request, *args, **kwargs):
        order = self.get_object()
        try:
            with transaction.atomic():
                serializer = ReviewAndRatingSerializer(data=request.data, context={"order": order, "send_by": UserDefault.PROVIDER, "request": request})
                serializer.is_valid(raise_exception=True)
                serializer.save()                
                handle_log_engine(
                    request=request, action="SEND FEEDBACK", status=LogStatus.SUCCESS, message="Send Feedback with this Order.", entity=order,
                    perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER,
                    notify=True, logify=True,
                    role=UserRole.USER, send_to=order.customer.user, send_to_type=UserDefault.CUSTOMER, notification_message="Received Feedback with this Order."
                )
                return Response(
                    {
                        "status": True,
                        "message": _("Thanks for your feedback!")
                    }, status=status.HTTP_200_OK
                )
        except ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            handle_log_engine(
                request=request, action="SEND FEEDBACK", status=LogStatus.FAILED, message="Failed to Send Feedback with this Order.", entity=order,
                perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
            )
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )

    def create(self, request, *args, **kwargs):
        handle_log_engine(
            request=request, action="POST METHOD NOT ALLOWED", status=LogStatus.FAILED, message="Post Method perform not allowed.",
            perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
        )
        return Response(
            {
                "status": True,
                "message": _("Post method not allowed!")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def update(self, request, *args, **kwargs):
        handle_log_engine(
            request=request, action="UPDATE METHOD NOT ALLOWED", status=LogStatus.FAILED, message="Update Method perform not allowed.",
            perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
        )
        return Response(
            {
                "status": True,
                "message": _("Update method not allowed!")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def destroy(self, request, *args, **kwargs):
        handle_log_engine(
            request=request, action="DELETE METHOD NOT ALLOWED", status=LogStatus.FAILED, message="Delete Method perform not allowed.",
            perform_user=self.request.user, perform_user_type=UserDefault.PROVIDER
        )
        return Response(
            {
                "status": True,
                "message": _("Delete method not allowed!")
            }, status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

# ========Order Views Section===================
# ============================================================




class ReviewAndRatingViewSets(UpdateModelViewSet):
    queryset = ReviewAndRating.objects.all()
    serializer_class = ReviewAndRatingSerializer
    permission_classes = [ForCustomerProfile]



# ==========================================================================================
# =================== Payment transaction Section Start===================================
class PaymentTransactionViewSets(UpdateReadOnlyModelViewSet):
    queryset = PaymentTransaction.objects.all()
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_profile_type(self):
        return self.request.headers.get("profile-type", None)

    def get_queryset(self):
        if self.request.user.role == UserRole.USER:
            pt = PaymentTransaction.objects.filter(
                user=self.request.user
            ).filter(
                Q(type=PaymentTransactionType.CREDIT) | Q(type=PaymentTransactionType.DEBIT)
            )
            if self.get_profile_type() and self.get_profile_type().upper() in UserDefault.values:
                pt.filter(
                    profile=self.get_profile_type().upper()
                )
        elif self.request.user.role == UserRole.ADMIN:
            pt = PaymentTransaction.objects.all()
        else:
            raise Exception(_("Payment transaction not get for the user."))
        return pt

# =================== Payment transaction Section Start===================================
# ==========================================================================================


    
