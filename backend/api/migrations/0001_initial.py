from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Listing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=140)),
                ("owner", models.CharField(default="@owner", max_length=80)),
                ("surface_type", models.CharField(choices=[("Physical", "Physical"), ("Digital", "Digital")], default="Physical", max_length=16)),
                ("duration", models.CharField(max_length=100)),
                ("price_sol", models.DecimalField(decimal_places=9, default=Decimal("0.1"), max_digits=18)),
                ("emoji", models.CharField(default="✨", max_length=16)),
                ("tagline", models.CharField(blank=True, max_length=240)),
                ("accent", models.CharField(default="from-violet-500/30 to-fuchsia-500/5", max_length=180)),
                ("seller_wallet", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("available", "Available"), ("reserved", "Reserved"), ("sold", "Sold")], default="available", max_length=16)),
                ("buyer_wallet", models.CharField(blank=True, max_length=64)),
                ("tx_signature", models.CharField(blank=True, max_length=128)),
                ("mint_address", models.CharField(blank=True, max_length=64)),
                ("reserved_by", models.CharField(blank=True, max_length=64)),
                ("reserved_until", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="WalletProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("wallet_address", models.CharField(max_length=64, unique=True)),
                ("display_name", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("buyer_wallet", models.CharField(max_length=64)),
                ("seller_wallet", models.CharField(max_length=64)),
                ("price_sol", models.DecimalField(decimal_places=9, max_digits=18)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("confirmed", "Confirmed"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="pending", max_length=16)),
                ("tx_signature", models.CharField(blank=True, max_length=128, null=True, unique=True)),
                ("mint_address", models.CharField(blank=True, max_length=64)),
                ("verification_message", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("listing", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchases", to="api.listing")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AdRight",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_wallet", models.CharField(max_length=64)),
                ("mint_address", models.CharField(max_length=64, unique=True)),
                ("transaction_signature", models.CharField(max_length=128, unique=True)),
                ("acquired_at", models.DateTimeField(auto_now_add=True)),
                ("listing", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="ad_right", to="api.listing")),
                ("purchase", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="ad_right", to="api.purchase")),
            ],
            options={
                "ordering": ["-acquired_at"],
            },
        ),
        migrations.AddIndex(
            model_name="listing",
            index=models.Index(fields=["status", "created_at"], name="api_listing_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="listing",
            index=models.Index(fields=["seller_wallet"], name="api_listing_seller_idx"),
        ),
        migrations.AddIndex(
            model_name="purchase",
            index=models.Index(fields=["buyer_wallet", "status"], name="api_purchase_buyer_status_idx"),
        ),
        migrations.AddIndex(
            model_name="purchase",
            index=models.Index(fields=["seller_wallet", "status"], name="api_purchase_seller_status_idx"),
        ),
    ]
