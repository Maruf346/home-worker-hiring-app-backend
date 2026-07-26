
from rest_framework import status, exceptions
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from find_worker_config.model_choice import PaymentCurrencyType, PaymentTransactionType, ServiceChargeType, PaymentAction
from task.models import PaymentTransaction
from core.models import AdminWallet
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from account.models import ActivityLog
from chat_notify.models import Notification
from ipware import get_client_ip
from django.db import transaction
from chat_notify.utils import push_notification
from chat_notify.models import Notification


class UpdateModelViewSet(ModelViewSet):
    delete_message = _("Object successfully deleted.")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.perform_retrieve(serializer)
    
    def perform_retrieve(self, serializer):
        return Response(
            {
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK
        )
    
    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
            return Response(
                {
                    'status': True,
                    'count': len(response.data),
                    'data': response.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'messgae': str(e),
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                return Response(
                    {
                        'status': True,
                        'data': serializer.data
                    }, status=status.HTTP_201_CREATED
                )
        except exceptions.ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    'status': False,
                    'message': error,
                },status=status.HTTP_400_BAD_REQUEST
            )
        except exceptions.PermissionDenied as e:
            return Response(
                {
                    'status': False,
                    'message': str(e),
                }, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'message': str(e),
                }, status=status.HTTP_400_BAD_REQUEST
            )
    
    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                object = self.get_object()
                serializer = self.get_serializer(object, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                return Response(
                    {
                        'status': True,
                        'data': serializer.data
                    },
                    status=status.HTTP_200_OK
                )
        except exceptions.ValidationError:
            error = {key: str(value[0]) for key, value in serializer.errors.items()}
            return Response(
                {
                    'status': False,
                    'message': error
                },
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            super().destroy(request, *args, **kwargs)
            return Response(
                {
                    'status': True,
                    'message': self.delete_message,
                }, status=status.HTTP_200_OK
            )

class UpdateReadOnlyModelViewSet(ReadOnlyModelViewSet):
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.perform_retrieve(serializer)
    
    def perform_retrieve(self, serializer):
        return Response(
            {
                'status': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK
        )
    
    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
            return Response(
                {
                    'status': True,
                    'count': len(response.data),
                    'data': response.data
                }, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    'status': False,
                    'messgae': str(e),
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentTransactionModule:
    def __init__(self, user, order, amount, reference_object, type, action, payment_information: dict={}, transaction_id=None, reference=None, currency=None, profile=None, service_charge: dict={}):
        self.user = user
        self.profile = profile
        self.order = order
        self.amount = amount
        self.payment_information = payment_information
        self.reference_object = reference_object
        self.type = type
        self.action = action
        self.reference = reference
        self.currency = currency or PaymentCurrencyType.CA
        self.service_charge = service_charge
        self.transaction_id = transaction_id
    
    def get_wallet(self):
        wallet, _ = AdminWallet.objects.get_or_create()
        return wallet
    
    def get_service_charge_amount(self, amount):
        charge_type = self.service_charge.get("type")
        charge_number = self.service_charge.get("number")
        if charge_type == ServiceChargeType.FLAT:
            charge = charge_number
        elif charge_type == ServiceChargeType.PERCENTAGE:
            charge = (amount * charge_number) / 100
        else:
            charge = (amount * 10) / 100
        payable_amount = amount-charge
        return charge, payable_amount
    
    def update_wallet(self, transaction):
        wallet = self.get_wallet()
        amount = transaction.amount
        if self.type == PaymentTransactionType.CREDIT:
            wallet.payment_balance += amount
        elif self.type == PaymentTransactionType.HOLD:
            wallet.payment_balance -= amount
            wallet.hold_balance += amount
        elif self.type == PaymentTransactionType.DEBIT:
            if transaction.action == PaymentAction.SEND_PROVIDER:
                charge_amount, payable_amount = self.get_service_charge_amount(amount)
                transaction.amount = payable_amount
                transaction.save(update_fields=["amount"])
                wallet.hold_balance -= amount
                wallet.total_withdraw += payable_amount
                wallet.current_balance += charge_amount
            elif transaction.action == PaymentAction.REFUND_CUSTOMER:
                wallet.payment_balance -= transaction.amount

        wallet.save(update_fields=[
            "payment_balance",
            "hold_balance",
            "total_withdraw",
            "current_balance",
        ])
        return True

    def payment_transaction(self):
        entity_type = ContentType.objects.get_for_model(self.reference_object)
        with transaction.atomic():
            payment_transaction = PaymentTransaction.objects.create(
                user=self.user,
                amount=self.amount,
                profile=self.profile,
                order=self.order,
                transaction_id=self.transaction_id,
                payment_information=self.payment_information or {},
                entity_type=entity_type,
                entity_id=self.reference_object.id,
                type=self.type,
                action=self.action,
                reference=self.reference,
                currency=self.currency or PaymentCurrencyType.CA
            )
            self.update_wallet(payment_transaction)
            return True
        raise Exception(_("Payment transaction failed to update."))






