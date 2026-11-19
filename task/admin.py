from django.contrib import admin
from .models import ServiceCategory, ServiceSubCategory, Order, ReviewAndRating, PaymentTransaction, OrderRefundRequest, OrderChangesRequest, OrderAttachment
from unfold.admin import ModelAdmin


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(ModelAdmin):
    list_display = (
        "id",
        "title",
        "is_active",
        "created_at",
    )

    search_fields = ("title",)
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at")

@admin.register(ServiceSubCategory)
class ServiceSubCategoryAdmin(ModelAdmin):
    list_display = (
        "id",
        "title",
        "category",
        "is_active",
    )

    search_fields = ("title",)
    list_filter = ("is_active", "category")



@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        "id",
        "title",
        "customer_name",
        "provider_name",
        "status",
        "payment_status",
        "amount",
        "created_at",
    )

    search_fields = (
        "title",
        "customer__user__username",
        "provider__user__username",
    )

    list_filter = (
        "status",
        "payment_status",
        "order_change_action",
        "category",
    )

    readonly_fields = (
        "confirmation_OTP",
        "created_at",
        "updated_at",
        "accepted_at",
        "started_at",
        "completed_at",
    )

    date_hierarchy = "created_at"

    fieldsets = (
        ("Order Info", {
            "fields": (
                "title",
                "description",
                "category",
                "customer",
                "provider",
                "status",
                "payment_status",
                "order_change_action",
            )
        }),

        ("Schedule", {
            "fields": (
                "working_date",
                "working_start_time",
                "working_hour",
            )
        }),

        ("Financial", {
            "fields": (
                "amount",
            )
        }),

        ("Location", {
            "fields": (
                "area",
                "lat",
                "lng",
            )
        }),

        ("System", {
            "fields": (
                "confirmation_OTP",
                "created_at",
                "updated_at",
            )
        }),
    )

    def customer_name(self, obj):
        return obj.customer.user.username if obj.customer else "-"

    def provider_name(self, obj):
        return obj.provider.user.username if obj.provider else "-"

@admin.register(OrderAttachment)
class OrderAttachmentAdmin(ModelAdmin):
    list_display = (
        "id",
        "order",
        "created_at",
    )

    list_filter = ("created_at",)
    readonly_fields = ("created_at",)

@admin.register(OrderChangesRequest)
class OrderChangesRequestAdmin(ModelAdmin):
    list_display = (
        "id",
        "order",
        "request_by",
        "status",
        "changes_type",
        "created_at",
    )

    list_filter = (
        "status",
        "changes_type",
    )

    readonly_fields = ("created_at", "updated_at")

@admin.register(ReviewAndRating)
class ReviewAdmin(ModelAdmin):
    list_display = (
        "id",
        "order",
        "rating",
        "attachment",
        "send_by",
        "is_approved",
        "created_at",
    )

    list_filter = (
        "rating",
        "is_approved",
    )

    search_fields = ("review",)

@admin.register(OrderRefundRequest)
class RefundAdmin(ModelAdmin):
    list_display = (
        "id",
        "order",
        "status",
        "refund_amount",
        "processed_by",
        "created_at",
    )

    list_filter = ("status",)

    readonly_fields = (
        "order_amount",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Refund Info", {
            "fields": (
                "order",
                "customer",
                "reason",
                "status",
            )
        }),

        ("Financial", {
            "fields": (
                "order_amount",
                "refund_amount",
            )
        }),

        ("Admin Action", {
            "fields": (
                "admin_note",
                "processed_by",
                "processed_at",
            )
        }),
    )

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(ModelAdmin):
    list_display = (
        "payment_id",
        "amount",
        "currency",
        "type",
        "action",
        "user",
        "order",
        "created_at",
    )

    search_fields = (
        "payment_id",
        "transaction_id",
        "user__username",
    )

    list_filter = (
        "type",
        "action",
        "currency",
    )

    readonly_fields = (
        "payment_id",
        "transaction_id",
        "created_at",
        "update_at",
    )

    fieldsets = (
        ("Transaction Info", {
            "fields": (
                "payment_id",
                "transaction_id",
                "user",
                "profile",
                "order",
            )
        }),

        ("Financial", {
            "fields": (
                "amount",
                "currency",
            )
        }),

        ("Type Info", {
            "fields": (
                "type",
                "action",
                "reference",
            )
        }),

        ("System", {
            "fields": (
                "created_at",
                "update_at",
            )
        }),
    )



