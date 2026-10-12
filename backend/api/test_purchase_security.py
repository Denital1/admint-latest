from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client
from accounts.models import Identity
from .models import Listing, Purchase, AdRight, Order


class PurchaseSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.buyer = get_user_model().objects.create_user(username="audit-buyer")
        self.seller = get_user_model().objects.create_user(username="audit-seller")
        self.stranger = get_user_model().objects.create_user(username="audit-stranger")
        Identity.objects.create(user=self.buyer, provider="phantom", subject="audit-buyer-wallet")
        Identity.objects.create(user=self.seller, provider="phantom", subject="audit-seller-wallet")
        self.listing = Listing.objects.create(title="Audit surface", duration="7 days", seller_wallet="audit-seller-wallet", owner_account=self.seller, price_sol=Decimal("0.25"))
        self.client.force_login(self.buyer)

    def prepare(self, listing=None):
        response = self.client.post("/api/purchases/prepare/", {"listing_id": (listing or self.listing).pk, "buyer_wallet": "audit-buyer-wallet"}, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        return Purchase.objects.get(pk=response.json()["id"])

    def confirm(self, purchase, signature="audit-signature", mint="audit-mint", result=None):
        with patch("api.views.verify_purchase_transaction", return_value=result or {"confirmed": True, "message": "Verified"}) as verify:
            response = self.client.post(f"/api/purchases/{purchase.pk}/confirm/", {"tx_signature": signature, "mint_address": mint, "cluster": "devnet"}, content_type="application/json")
        return response, verify

    def test_missing_listing_returns_404(self):
        response = self.client.post("/api/purchases/prepare/", {"listing_id": 999999, "buyer_wallet": "audit-buyer-wallet"}, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_cancelled_purchase_cannot_confirm(self):
        purchase = self.prepare()
        self.client.post(f"/api/purchases/{purchase.pk}/cancel/")
        response, verify = self.confirm(purchase)
        self.assertEqual(response.status_code, 409)
        verify.assert_not_called()
        self.assertFalse(AdRight.objects.exists())

    def test_old_purchase_cannot_release_new_reservation(self):
        old = self.prepare()
        self.listing.reserved_until = None
        self.listing.status = "available"
        self.listing.save()
        new = self.prepare()
        self.client.post(f"/api/purchases/{old.pk}/cancel/")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "reserved")
        response, verify = self.confirm(old)
        self.assertEqual(response.status_code, 409)
        verify.assert_not_called()
        new.refresh_from_db()
        self.assertEqual(new.status, "pending")

    def test_reused_transaction_returns_conflict(self):
        first = self.prepare()
        self.assertEqual(self.confirm(first)[0].status_code, 200)
        listing = Listing.objects.create(title="Second", duration="day", seller_wallet="audit-seller-wallet", owner_account=self.seller, price_sol=Decimal("0.25"))
        second = self.prepare(listing)
        response, verify = self.confirm(second, mint="different-mint")
        self.assertEqual(response.status_code, 409)
        verify.assert_not_called()
        self.assertEqual(AdRight.objects.count(), 1)

    def test_reused_mint_returns_conflict(self):
        first = self.prepare()
        self.assertEqual(self.confirm(first)[0].status_code, 200)
        listing = Listing.objects.create(title="Second", duration="day", seller_wallet="audit-seller-wallet", owner_account=self.seller, price_sol=Decimal("0.25"))
        second = self.prepare(listing)
        response, verify = self.confirm(second, signature="different-signature")
        self.assertEqual(response.status_code, 409)
        verify.assert_not_called()

    def test_temporary_rpc_failure_keeps_reservation(self):
        purchase = self.prepare()
        response, _ = self.confirm(purchase, result={"confirmed": False, "retryable": True, "message": "RPC temporarily unavailable"})
        self.assertEqual(response.status_code, 503)
        purchase.refresh_from_db(); self.listing.refresh_from_db()
        self.assertEqual(purchase.status, "pending")
        self.assertEqual(self.listing.status, "reserved")
        self.assertEqual(self.confirm(purchase)[0].status_code, 200)

    def test_duplicate_confirmation_is_idempotent(self):
        purchase = self.prepare()
        self.assertEqual(self.confirm(purchase)[0].status_code, 200)
        response, verify = self.confirm(purchase)
        self.assertEqual(response.status_code, 200)
        verify.assert_not_called()
        self.assertEqual(AdRight.objects.count(), 1)

    def test_foreign_wallet_private_endpoints(self):
        purchase = self.prepare()
        self.assertEqual(self.confirm(purchase)[0].status_code, 200)
        self.client.force_login(self.stranger)
        for path in [f"/api/purchases/{purchase.pk}/cancel/", f"/api/purchases/{purchase.pk}/confirm/"]:
            data = {"tx_signature":"x", "mint_address":"x", "cluster":"devnet"}
            self.assertEqual(self.client.post(path, data, content_type="application/json").status_code, 403)
        for path in ["/api/purchases/?wallet=audit-buyer-wallet", "/api/ad-rights/?wallet=audit-buyer-wallet", f"/api/orders/{purchase.pk}/"]:
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_invalid_surface_type_rejected(self):
        self.client.force_login(self.seller)
        response = self.client.post("/api/listings/", {"title":"Bad", "duration":"day", "surfaceType":"Anything", "priceSol":"0.25", "seller_wallet":"audit-seller-wallet"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_private_order_file_requires_confirmed_payment(self):
        purchase = self.prepare()
        Order.objects.create(purchase=purchase, creative=b"private")
        self.assertEqual(self.client.get(f"/api/orders/{purchase.pk}/file/creative/").status_code, 404)

    def test_csrf_blocks_purchase_and_listing_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.buyer)
        for path in ["/api/purchases/prepare/", "/api/listings/"]:
            self.assertEqual(client.post(path, {}, content_type="application/json").status_code, 403)

    def test_complete_purchase_order_persistence(self):
        purchase = self.prepare()
        self.assertEqual(self.confirm(purchase)[0].status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "sold")
        self.assertEqual(self.client.get("/api/ad-rights/?wallet=audit-buyer-wallet").json()[0]["listing"], self.listing.pk)
        url = f"/api/orders/{purchase.pk}/"
        self.assertEqual(self.client.post(url, {"action":"creative", "brief":"Campaign"}).status_code, 200)
        self.assertEqual(self.client.post(url+"messages/", {"text":"Private brief"}, content_type="application/json").status_code, 200)
        fresh = Client(); fresh.force_login(self.buyer)
        order = fresh.get(url).json()
        self.assertEqual(order["status"], "creative_submitted")
        self.assertEqual(order["brief"], "Campaign")
        self.assertEqual(order["messages"][0]["text"], "Private brief")
        self.assertEqual(fresh.get("/api/listings/").json()[0]["status"], "sold")
