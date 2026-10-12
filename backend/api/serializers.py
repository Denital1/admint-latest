from decimal import Decimal
from rest_framework import serializers

from .models import AdRight, Listing, Purchase, WalletProfile


class ListingSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source="details.location", read_only=True, default="")
    photo = serializers.SerializerMethodField()
    def get_photo(self, obj):
        details = getattr(obj, "details", None)
        return f"/api/listings/{obj.pk}/photo/" if details and details.photo else None

    ownerAccountId = serializers.IntegerField(source="owner_account_id", read_only=True)
    sellerAddress = serializers.CharField(source="seller_wallet", read_only=True)
    buyerAddress = serializers.CharField(source="buyer_wallet", read_only=True)
    txSignature = serializers.CharField(source="tx_signature", read_only=True)
    mintAddress = serializers.CharField(source="mint_address", read_only=True)
    surfaceType = serializers.ChoiceField(source="surface_type", choices=Listing.SurfaceType.choices)
    price = serializers.SerializerMethodField()
    price_sol = serializers.DecimalField(read_only=True, max_digits=18, decimal_places=9)
    priceSol = serializers.DecimalField(
        source="price_sol",
        max_digits=18,
        decimal_places=9,
        min_value=Decimal("0.000000001"),
        write_only=True,
        required=True,
    )
    seller_wallet = serializers.CharField(max_length=64, write_only=True, required=True)

    class Meta:
        model = Listing
        fields = [
            "id",
            "title",
            "location",
            "photo",
            "owner",
            "surfaceType",
            "duration",
            "price",
            "price_sol",
            "priceSol",
            "seller_wallet",
            "emoji",
            "tagline",
            "accent",
            "ownerAccountId",
            "sellerAddress",
            "status",
            "buyerAddress",
            "txSignature",
            "mintAddress",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "price",
            "ownerAccountId",
            "sellerAddress",
            "status",
            "buyerAddress",
            "txSignature",
            "mintAddress",
            "created_at",
        ]

    def get_price(self, obj):
        return f"{obj.price_sol.normalize()} SOL"

    def create(self, validated_data):
        seller_wallet = validated_data["seller_wallet"].strip()
        if not seller_wallet:
            raise serializers.ValidationError({"seller_wallet": "Wallet address is required."})
        WalletProfile.objects.get_or_create(wallet_address=seller_wallet)
        return super().create(validated_data)


class PurchasePrepareSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField()
    cluster = serializers.ChoiceField(choices=["devnet", "testnet", "mainnet", "localnet"], default="devnet")
    buyer_wallet = serializers.CharField(max_length=64)


class PurchaseConfirmSerializer(serializers.Serializer):
    tx_signature = serializers.CharField(max_length=128)
    mint_address = serializers.CharField(max_length=64)
    cluster = serializers.ChoiceField(
        choices=["devnet", "testnet", "mainnet", "localnet"],
        default="devnet",
    )


class PurchaseSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = Purchase
        fields = [
            "id",
            "listing",
            "listing_title",
            "cluster",
            "buyer_wallet",
            "seller_wallet",
            "price_sol",
            "status",
            "tx_signature",
            "mint_address",
            "verification_message",
            "created_at",
            "confirmed_at",
        ]


class AdRightSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = AdRight
        fields = [
            "id",
            "listing",
            "listing_title",
            "owner_wallet",
            "mint_address",
            "transaction_signature",
            "acquired_at",
        ]
