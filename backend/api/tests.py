from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Listing, Purchase


class AdMintApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.seller = "Seller111111111111111111111111111111111111"
        self.buyer = "Buyer2222222222222222222222222222222222222"
        from django.contrib.auth import get_user_model
        from accounts.models import Identity
        self.user = get_user_model().objects.create_user(username="api-test")
        Identity.objects.create(user=self.user, provider="phantom", subject=self.buyer)
        self.seller_user = get_user_model().objects.create_user(username="seller-test")
        Identity.objects.create(user=self.seller_user, provider="phantom", subject=self.seller)
        self.client.force_login(self.user)

    def test_health(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_readiness_reports_dependency_failures_without_internal_details(self):
        from unittest.mock import patch
        self.assertEqual(self.client.get("/api/ready/").status_code,200)
        for target in ["api.views.cache.get", "api.views.connection.cursor"]:
            with patch(target,side_effect=RuntimeError("private backend credentials")):
                response=self.client.get("/api/ready/")
            self.assertEqual(response.status_code,503)
            self.assertFalse(response.json()["ok"])
            self.assertNotIn("private",response.content.decode())
            self.assertIn("no-store",response["Cache-Control"])

    def test_create_and_list_listing(self):
        self.client.force_login(self.seller_user)
        response = self.client.post(
            "/api/listings/",
            {
                "title": "Test Laptop",
                "owner": "@seller",
                "surfaceType": "Physical",
                "duration": "7 days",
                "priceSol": "0.25",
                "emoji": "💻",
                "tagline": "Test surface",
                "accent": "from-violet-500/30 to-fuchsia-500/5",
                "seller_wallet": self.seller,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["price"], "0.25 SOL")

        listing = self.client.get("/api/listings/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)

    def test_prepare_and_cancel_purchase(self):
        listing = Listing.objects.create(
            title="Test Surface",
            owner="@seller",
            surface_type="Physical",
            duration="7 days",
            price_sol=Decimal("0.25"),
            emoji="💻",
            tagline="Test",
            accent="from-violet-500/30 to-fuchsia-500/5",
            seller_wallet=self.seller,
        )

        response = self.client.post(
            "/api/purchases/prepare/",
            {"listing_id": listing.id, "buyer_wallet": self.buyer},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.RESERVED)
        purchase_id = response.json()["id"]

        response = self.client.post(f"/api/purchases/{purchase_id}/cancel/")
        self.assertEqual(response.status_code, 200)
        listing.refresh_from_db()
        purchase = Purchase.objects.get(pk=purchase_id)
        self.assertEqual(listing.status, Listing.Status.AVAILABLE)
        self.assertEqual(purchase.status, Purchase.Status.CANCELLED)

    def test_expired_reservation_is_released(self):
        listing = Listing.objects.create(
            title="Expired Surface",
            owner="@seller",
            surface_type="Digital",
            duration="1 day",
            price_sol=Decimal("0.10"),
            emoji="𝕏",
            tagline="Test",
            accent="from-sky-500/25 to-cyan-500/5",
            seller_wallet=self.seller,
            status=Listing.Status.RESERVED,
            reserved_by=self.buyer,
            reserved_until=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get("/api/listings/")
        self.assertEqual(response.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.AVAILABLE)


class SolanaVerificationTests(TestCase):
    def test_rpc_mint_authority_and_invalid_purchase_details(self):
        from copy import deepcopy
        from unittest.mock import patch
        from .solana import verify_purchase_transaction

        transaction = {
            "meta": {"err": None, "preTokenBalances": [], "postTokenBalances": [{"accountIndex": 1, "mint": "mint", "owner": "buyer", "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "uiTokenAmount": {"amount": "1", "decimals": 0}}]},
            "transaction": {"message": {
                "accountKeys": [{"pubkey": "buyer", "signer": True}, {"pubkey": "buyer-token", "signer": False}],
                "instructions": [
                    {"program": "system", "programId": "11111111111111111111111111111111", "parsed": {"type": "transfer", "info": {
                        "source": "buyer", "destination": "seller", "lamports": 30000000,
                    }}},
                    {"program": "spl-token", "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "parsed": {"type": "mintTo", "info": {
                        "mint": "mint", "account": "buyer-token", "amount": "1", "mintAuthority": "buyer",
                    }}},
                    {"program": "spl-token", "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "parsed": {"type": "initializeMint", "info": {"mint": "mint", "decimals": 0, "mintAuthority": "buyer", "freezeAuthority": None}}},
                    {"program": "spl-token", "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "parsed": {"type": "setAuthority", "info": {"account": "mint", "authorityType": "mintTokens", "authority": "buyer", "newAuthority": None}}},
                ],
            }},
        }
        cases = [("valid", None, None, True),
                 ("wrong authority", "mintAuthority", "other", False),
                 ("wrong mint", "mint", "other", False),
                 ("wrong amount", "amount", "2", False),
                 ("wrong payment", "lamports", 1, False),
                 ("unsigned buyer", "signer", False, False)]
        for name, field, value, expected in cases:
            with self.subTest(name=name):
                result = deepcopy(transaction)
                message = result["transaction"]["message"]
                if field == "signer":
                    message["accountKeys"][0][field] = value
                elif field == "lamports":
                    message["instructions"][0]["parsed"]["info"][field] = value
                elif field:
                    message["instructions"][1]["parsed"]["info"][field] = value
                with patch("api.solana.get_signature_status", return_value={
                    "ok": True, "confirmed": True, "confirmation_status": "finalized",
                }), patch("api.solana._rpc_call", return_value={"result": result}):
                    verification = verify_purchase_transaction(
                        signature="signature", cluster="devnet", buyer_wallet="buyer",
                        seller_wallet="seller", price_sol=Decimal("0.03"), mint_address="mint",
                    )
                self.assertEqual(verification["confirmed"], expected)

class AccountSelfPurchaseTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import Identity
        self.owner=get_user_model().objects.create_user(username="surface-owner")
        self.other=get_user_model().objects.create_user(username="surface-buyer")
        Identity.objects.create(user=self.owner,provider="phantom",subject="seller-wallet")
        Identity.objects.create(user=self.owner,provider="phantom",subject="second-owner-wallet")
        Identity.objects.create(user=self.other,provider="phantom",subject="unrelated-wallet")
        self.listing=Listing.objects.create(title="Own surface",seller_wallet="seller-wallet",owner_account=self.owner,price_sol=Decimal("0.25"),duration="7 days")
        self.client=APIClient()

    def test_different_wallet_on_same_account_is_blocked(self):
        self.client.force_login(self.owner)
        r=self.client.post("/api/purchases/prepare/",{"listing_id":self.listing.pk,"buyer_wallet":"second-owner-wallet"},format="json")
        self.assertEqual(r.status_code,400)
        self.assertEqual(Purchase.objects.count(),0)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status,"available")

    def test_legacy_listing_is_blocked_by_linked_seller_wallet(self):
        self.listing.owner_account=None
        self.listing.save()
        self.test_different_wallet_on_same_account_is_blocked()

    def test_persisted_owner_blocks_without_seller_wallet_identity(self):
        from accounts.models import Identity
        Identity.objects.filter(subject="seller-wallet").delete()
        self.test_different_wallet_on_same_account_is_blocked()

    def test_other_account_can_buy(self):
        self.client.force_login(self.other)
        r=self.client.post("/api/purchases/prepare/",{"listing_id":self.listing.pk,"buyer_wallet":"unrelated-wallet"},format="json")
        self.assertEqual(r.status_code,201)

    def test_confirmation_cannot_bypass_owner_check(self):
        from unittest.mock import patch
        p=Purchase.objects.create(listing=self.listing,buyer_wallet="second-owner-wallet",seller_wallet="seller-wallet",price_sol=Decimal("0.25"))
        self.client.force_login(self.owner)
        with patch("api.views.verify_purchase_transaction") as verify:
            r=self.client.post(f"/api/purchases/{p.pk}/confirm/",{"tx_signature":"signature","mint_address":"mint","cluster":"devnet"},format="json")
            self.assertEqual(r.status_code,400)
            verify.assert_not_called()

    def test_listing_creation_saves_account_owner(self):
        self.client.force_login(self.owner)
        r=self.client.post("/api/listings/",{"title":"New surface","owner":"me","surfaceType":"Physical","duration":"1 day","priceSol":"0.25","seller_wallet":"second-owner-wallet","emoji":"X","tagline":"","accent":"from-violet-500/30"},format="json")
        self.assertEqual(r.status_code,201)
        self.assertEqual(Listing.objects.get(pk=r.json()["id"]).owner_account_id,self.owner.pk)
        self.assertEqual(r.json()["ownerAccountId"],self.owner.pk)
