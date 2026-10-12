from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify


class WalletProfile(models.Model):
    wallet_address = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.wallet_address


class Listing(models.Model):
    class SurfaceType(models.TextChoices):
        PHYSICAL = "Physical", "Physical"
        DIGITAL = "Digital", "Digital"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        SOLD = "sold", "Sold"

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    owner_account = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="owned_surfaces")
    title = models.CharField(max_length=140)
    owner = models.CharField(max_length=80, default="@owner")
    surface_type = models.CharField(
        max_length=16,
        choices=SurfaceType.choices,
        default=SurfaceType.PHYSICAL,
    )
    duration = models.CharField(max_length=100)
    price_sol = models.DecimalField(
        max_digits=18,
        decimal_places=9,
        default=Decimal("0.1"),
    )
    emoji = models.CharField(max_length=16, default="✨")
    tagline = models.CharField(max_length=240, blank=True)
    accent = models.CharField(
        max_length=180,
        default="from-violet-500/30 to-fuchsia-500/5",
    )
    seller_wallet = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    buyer_wallet = models.CharField(max_length=64, blank=True)
    tx_signature = models.CharField(max_length=128, blank=True)
    mint_address = models.CharField(max_length=64, blank=True)
    reserved_by = models.CharField(max_length=64, blank=True)
    reserved_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="api_listing_status_created_idx"),
            models.Index(fields=["seller_wallet"], name="api_listing_seller_idx"),
        ]

    def release_expired_reservation(self):
        if (
            self.status == self.Status.RESERVED
            and self.reserved_until
            and self.reserved_until <= timezone.now()
        ):
            self.status = self.Status.AVAILABLE
            self.reserved_by = ""
            self.reserved_until = None
            self.save(
                update_fields=[
                    "status",
                    "reserved_by",
                    "reserved_until",
                    "updated_at",
                ]
            )

    def __str__(self):
        return f"{self.title} #{self.pk}"


class Purchase(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    listing = models.ForeignKey(
        Listing,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    buyer_wallet = models.CharField(max_length=64)
    seller_wallet = models.CharField(max_length=64)
    price_sol = models.DecimalField(max_digits=18, decimal_places=9)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    cluster = models.CharField(max_length=16, default="devnet")
    verification_version = models.PositiveSmallIntegerField(default=1)
    tx_signature = models.CharField(max_length=128, unique=True, null=True, blank=True)
    mint_address = models.CharField(max_length=64, blank=True)
    verification_message = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer_wallet", "status"], name="api_purchase_buyer_status_idx"),
            models.Index(fields=["seller_wallet", "status"], name="api_purchase_seller_status_idx"),
        ]

    def __str__(self):
        return f"Purchase #{self.pk} for listing #{self.listing_id}"


class AdRight(models.Model):
    listing = models.OneToOneField(
        Listing,
        on_delete=models.PROTECT,
        related_name="ad_right",
    )
    purchase = models.OneToOneField(
        Purchase,
        on_delete=models.PROTECT,
        related_name="ad_right",
    )
    owner_wallet = models.CharField(max_length=64)
    mint_address = models.CharField(max_length=64, unique=True)
    transaction_signature = models.CharField(max_length=128, unique=True)
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acquired_at"]

    def __str__(self):
        return f"AdRight {self.mint_address}"


class ListingDetails(models.Model):
    listing = models.OneToOneField(Listing, on_delete=models.CASCADE, related_name="details")
    description = models.TextField(blank=True, max_length=3000)
    location = models.CharField(max_length=160, blank=True)
    dimensions = models.CharField(max_length=160, blank=True)
    audience = models.CharField(max_length=240, blank=True)
    available_from = models.DateField(null=True, blank=True)
    available_until = models.DateField(null=True, blank=True)
    terms = models.TextField(blank=True, max_length=2000)
    photo = models.BinaryField(null=True, blank=True)

class SavedListing(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "listing"], name="unique_saved_listing")]

class ListingReport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE)
    reason = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

class Order(models.Model):
    purchase = models.OneToOneField(Purchase, on_delete=models.PROTECT, related_name="order")
    status = models.CharField(max_length=30, default="awaiting_creative")
    brief = models.TextField(blank=True, max_length=3000)
    creative = models.BinaryField(null=True, blank=True)
    proof = models.BinaryField(null=True, blank=True)
    issue = models.TextField(blank=True, max_length=2000)
    paused_status = models.CharField(max_length=30, blank=True)
    resolution = models.TextField(blank=True, max_length=2000)
    updated_at = models.DateTimeField(auto_now=True)

class OrderMessage(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_range")]

class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    previous_status = models.CharField(max_length=30)
    status = models.CharField(max_length=30)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
