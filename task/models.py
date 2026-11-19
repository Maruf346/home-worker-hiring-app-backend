from datetime import datetime, timedelta

from django.db import models
from account.models import User, CustomerProfile, ServiceProviderProfile
from find_worker_config.model_choice import ChangesRequestType, OrderChangesRequestStatus, OrderStatus, ReviewRatingChoice, OrderPaymentStatus, PaymentCurrencyType, PaymentTransactionType, PaymentAction, RefundStatus, UserDefault, OrderChangeRequestAction
from django.db import transaction
from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import secrets
import string
from rest_framework.exceptions import ValidationError
from django.db.models import Avg, Q

# ============================================================
# Category Models Section ===================
class ServiceCategory(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ServiceSubCategory(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name="subcategory")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} of {self.category.title}"

# Category Models Section ===================
# ============================================================


# ============================================================
# Order Models Section ===================
class Order(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, related_name="orders", blank=True, null=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.SET_NULL, related_name="orders_as_customer", blank=True, null=True)
    provider = models.ForeignKey(ServiceProviderProfile, on_delete=models.SET_NULL, related_name="orders_as_provider", blank=True, null=True)
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    area = models.CharField(max_length=255)
    lat = models.DecimalField(max_digits=25, decimal_places=20, blank=True, null=True)
    lng = models.DecimalField(max_digits=25, decimal_places=20, blank=True, null=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    payment_status = models.CharField(max_length=20, choices=OrderPaymentStatus.choices, default=OrderPaymentStatus.UNPAID)
    order_change_action = models.CharField(max_length=40, choices=OrderChangeRequestAction.choices, default=OrderChangeRequestAction.NO_ACTION)
    working_date = models.DateField(blank=True, null=True)
    working_start_time = models.TimeField(blank=True, null=True)
    working_hour = models.PositiveIntegerField(default=1)
    confirmation_OTP = models.CharField(max_length=6, blank=True, null=True)
    
    accepted_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    cancel_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def end_time(self):
        return (datetime.combine(self.working_date, self.working_start_time) + timedelta(hours=self.working_hour)).time()
    
    @property
    def end_datetime(self):
        return datetime.combine(self.working_date, self.working_start_time) + timedelta(hours=self.working_hour)

    @property
    def is_provider_review(self):
        return self.order_review.filter(send_by=UserDefault.PROVIDER).exists()
    
    @property
    def is_customer_review(self):
        return self.order_review.filter(send_by=UserDefault.CUSTOMER).exists()
    
    @property
    def is_cancel_request(self):
        return self.changes_requests.filter(
            changes_type=ChangesRequestType.CANCEL, status__in=[
                OrderChangesRequestStatus.ACCEPT, OrderChangesRequestStatus.NO_RESPONSE
            ]
        ).exists()
        
    @property
    def cancel_request_by(self):
        request = self.changes_requests.filter(
            changes_type=ChangesRequestType.CANCEL,
            status__in=[
                OrderChangesRequestStatus.NO_RESPONSE,
            ]
        ).first()
        if request:
            return request.request_by
        return None
    
    @property
    def cancel_request_accept_by(self):
        accept_by = self.changes_requests.filter(changes_type=ChangesRequestType.CANCEL).first().perform_by
        if accept_by:
            return accept_by or None
        return None
    
    @property
    def changes_request_pending(self):
        change_request = OrderChangesRequest.objects.filter(
            order=self, status=OrderChangesRequestStatus.NO_RESPONSE
        ).first()
        if change_request:
            return {
                "id": change_request.id,
                "request_by": change_request.request_by,
                "status": change_request.status,
                "changes_type": change_request.changes_type,
                "changes_data": change_request.changes_data,
                "created_at": change_request.created_at,
                "updated_at": change_request.updated_at
            }
        else:
            return None

    def save(self, *args, **kwargs):
        is_status_changed = False
        if self.pk:
            old_status = Order.objects.get(pk=self.pk).status
            is_status_changed = old_status != self.status
        if self.payment_status == OrderPaymentStatus.PAID and self.status in [OrderStatus.ACCEPT, OrderStatus.PENDING]:
            self.status = OrderStatus.CONFIRM
        return super().save(*args, **kwargs)

class OrderAttachment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_attachments")
    file = models.FileField(upload_to="order/file/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

class OrderChangesRequest(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="changes_requests")
    request_by = models.CharField(max_length=20, default=UserDefault.CUSTOMER, choices=UserDefault.choices)
    perform_by = models.CharField(max_length=20, choices=UserDefault.choices, blank=True, null=True)
    status = models.CharField(max_length=20, choices=OrderChangesRequestStatus.choices, default=OrderChangesRequestStatus.NO_RESPONSE)
    changes_type = models.CharField(max_length=30, choices=ChangesRequestType.choices, default=ChangesRequestType.AMOUNT)
    changes_data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# Order Models Section ===================
# ============================================================



class ReviewAndRating(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_review")
    customer = models.ForeignKey(CustomerProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name="customer_reviews")
    provider = models.ForeignKey(ServiceProviderProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name="provider_reviews")
    send_by = models.CharField(max_length=20, default=UserDefault.CUSTOMER, choices=UserDefault.choices)

    rating = models.IntegerField(choices=ReviewRatingChoice.choices, default=ReviewRatingChoice.FIVE)
    review = models.CharField(max_length=255, blank=True, null=True)
    attachment = models.FileField(upload_to="review/attachments/", blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def image(self):
        return self.attachment
    
    def save(self, *args, **kwargs):
        if self.send_by == UserDefault.CUSTOMER:
            provider = self.provider
            avg_rating = ReviewAndRating.objects.filter(
                provider=provider, send_by=UserDefault.CUSTOMER
            ).aggregate(
                avg=Avg("rating")
            )["avg"] or 0
            provider.rating = avg_rating
            provider.save()
        elif self.send_by == UserDefault.PROVIDER:
            customer = self.customer
            avg_rating = ReviewAndRating.objects.filter(
                customer=customer, send_by=UserDefault.CUSTOMER
            ).aggregate(
                avg=Avg("rating")
            )["avg"] or 0
            customer.rating = avg_rating
            customer.save()
        return super().save(*args, **kwargs)

class OrderRefundRequest(models.Model):
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, related_name="refund_request", blank=True, null=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.SET_NULL, related_name="refund_requests", blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    order_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    admin_note = models.TextField(blank=True, null=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="processed_refunds")
    processed_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save_order_data(self):
        if not self.customer:
            self.customer = self.order.customer
        if not self.refund_amount:
            self.refund_amount = self.order.amount
        return True

    def save(self, *args, **kwargs):
        if not self.pk:
            self.save_order_data()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Refund for Order {self.order.id} | {self.status}"


# ==========================================================================================
# ============= Payment transaction & Wallet Section Start=============================


class PaymentTransaction(models.Model):
    # related object fields
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="payment_transactions")
    profile = models.CharField(max_length=15, choices=UserDefault.choices, blank=True, null=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, blank=True, null=True, related_name="payment_transactions")

    # payment and transaction fields
    payment_id = models.CharField(max_length=50, blank=True, null=True, unique=True, editable=False)
    transaction_id = models.CharField(max_length=50, blank=True, null=True, unique=True, editable=False)
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    currency = models.CharField(max_length=20, choices=PaymentCurrencyType.choices, default=PaymentCurrencyType.CA)
    payment_information = models.JSONField(blank=True, null=True)

    # object related fields------
    type = models.CharField(max_length=20, choices=PaymentTransactionType.choices)
    action = models.CharField(max_length=50, choices=PaymentAction.choices, blank=True, null=True)
    reference = models.CharField(max_length=255, blank=True, null=True)

    # reference object------
    entity_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, blank=True, null=True)
    entity_id = models.PositiveBigIntegerField(blank=True, null=True)
    service = GenericForeignKey('entity_type', 'entity_id')

    created_at = models.DateTimeField(auto_now_add=True)
    update_at = models.DateTimeField(auto_now=True)

    def generate_payment_id(self):
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(6))
            generate_id = f"PAY-{code}"
            if not PaymentTransaction.objects.filter(payment_id=generate_id).exists():
                return generate_id
            

    def save(self, *args, **kwargs):
        if not self.payment_id:
            self.payment_id = self.generate_payment_id()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.payment_id} | {self.amount} | {self.action}"

# ============= Payment transaction & Wallet Section End=============================
# ==========================================================================================


