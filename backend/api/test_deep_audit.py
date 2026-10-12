from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch
from datetime import timedelta
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from accounts.models import Identity
from django.contrib.auth import get_user_model
from .models import Listing, Purchase, Order, AdRight
from .solana import verify_purchase_transaction, get_signature_status

TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SYSTEM = "11111111111111111111111111111111"

def token_instruction(kind, **info):
    return {"program":"spl-token", "programId":TOKEN, "parsed":{"type":kind, "info":info}}

def evidence():
    return {"blockTime":int(timezone.now().timestamp()), "meta":{"err":None,"preTokenBalances":[],"postTokenBalances":[{"accountIndex":1,"mint":"mint","owner":"buyer","programId":TOKEN,"uiTokenAmount":{"amount":"1","decimals":0}}]},"transaction":{"message":{"accountKeys":[{"pubkey":"buyer","signer":True},{"pubkey":"buyer-token","signer":False}],"instructions":[
        {"program":"system","programId":SYSTEM,"parsed":{"type":"transfer","info":{"source":"buyer","destination":"seller","lamports":250000000}}},
        token_instruction("initializeMint", mint="mint", decimals=0, mintAuthority="buyer", freezeAuthority=None),
        token_instruction("mintTo", mint="mint", account="buyer-token", amount="1", mintAuthority="buyer"),
        token_instruction("setAuthority", account="mint", authorityType="mintTokens", authority="buyer", newAuthority=None),
    ]}}}

class TokenEvidenceTests(TestCase):
    def verify(self, tx, not_before=None):
        with patch("api.solana.get_signature_status",return_value={"confirmed":True}),patch("api.solana._rpc_call",return_value={"result":tx}):
            return verify_purchase_transaction(signature="signature",cluster="devnet",buyer_wallet="buyer",seller_wallet="seller",price_sol=Decimal("0.25"),mint_address="mint",not_before=not_before)

    def test_full_token_evidence_valid(self):
        self.assertTrue(self.verify(evidence(),timezone.now())["confirmed"])

    def test_adversarial_token_evidence(self):
        mutations = {
            "wrong token recipient":lambda t:t["meta"]["postTokenBalances"][0].update(owner="seller"),
            "wrong token account":lambda t:t["meta"]["postTokenBalances"][0].update(accountIndex=0),
            "no token received":lambda t:t["meta"].update(postTokenBalances=[]),
            "token decimals":lambda t:t["meta"]["postTokenBalances"][0]["uiTokenAmount"].update(decimals=9),
            "token amount":lambda t:t["meta"]["postTokenBalances"][0]["uiTokenAmount"].update(amount="2"),
            "mint existed":lambda t:t["meta"].update(preTokenBalances=[{"mint":"mint"}]),
            "mint authority retained":lambda t:t["transaction"]["message"]["instructions"][3]["parsed"]["info"].update(newAuthority="buyer"),
            "freeze authority":lambda t:t["transaction"]["message"]["instructions"][1]["parsed"]["info"].update(freezeAuthority="buyer"),
            "mint decimals":lambda t:t["transaction"]["message"]["instructions"][1]["parsed"]["info"].update(decimals=9),
            "wrong system program":lambda t:t["transaction"]["message"]["instructions"][0].update(programId="fake"),
            "wrong token program":lambda t:t["transaction"]["message"]["instructions"][2].update(programId="fake"),
            "duplicate mint":lambda t:t["transaction"]["message"]["instructions"].append(deepcopy(t["transaction"]["message"]["instructions"][2])),
            "chain failure":lambda t:t["meta"].update(err={"InstructionError":[1,"Failure"]}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                tx=evidence();mutate(tx)
                self.assertFalse(self.verify(tx)["confirmed"])

    def test_historical_transaction_rejected(self):
        tx=evidence();tx["blockTime"]-=3600
        self.assertFalse(self.verify(tx,timezone.now())["confirmed"])

    def test_missing_transaction_details_retryable(self):
        self.assertTrue(self.verify(None)["retryable"])
        tx=evidence();tx["blockTime"]=None
        self.assertTrue(self.verify(tx,timezone.now())["retryable"])

    def test_rpc_failures_and_processing_are_retryable(self):
        for payload in [{"result":{"value":[None]}},{"result":{"value":[{"err":None,"confirmationStatus":"processed"}]}}]:
            with patch("api.solana._rpc_call",return_value=payload):
                self.assertTrue(get_signature_status("sig","devnet")["retryable"])
        with patch("api.solana._rpc_call",side_effect=TimeoutError("private infrastructure address")):
            result=get_signature_status("sig","devnet")
            self.assertTrue(result["retryable"])
            self.assertNotIn("private infrastructure",result["message"])

class AccessAndRecoveryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.buyer=get_user_model().objects.create_user(username="deep-buyer")
        self.seller=get_user_model().objects.create_user(username="deep-seller")
        self.other=get_user_model().objects.create_user(username="deep-other")
        Identity.objects.create(user=self.buyer,provider="phantom",subject="buyer")
        Identity.objects.create(user=self.seller,provider="phantom",subject="seller")
        self.listing=Listing.objects.create(title="Deep",duration="7 days",owner_account=self.seller,seller_wallet="seller",price_sol=Decimal("0.25"),status="reserved",reserved_by="buyer",reserved_until=timezone.now()-timedelta(minutes=1))
        self.purchase=Purchase.objects.create(listing=self.listing,buyer_wallet="buyer",seller_wallet="seller",price_sol=Decimal("0.25"),tx_signature="sig",mint_address="mint")
        self.url=f"/api/orders/{self.purchase.pk}/"

    def test_submitted_transaction_reservation_not_expired_or_cancelled(self):
        self.client.get("/api/listings/")
        self.listing.refresh_from_db();self.assertEqual(self.listing.status,"reserved")
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(f"/api/purchases/{self.purchase.pk}/cancel/").status_code,409)

    def test_original_signature_required_for_recovery(self):
        self.client.force_login(self.buyer)
        with patch("api.views.verify_purchase_transaction") as verify:
            r=self.client.post(f"/api/purchases/{self.purchase.pk}/confirm/",{"tx_signature":"different","mint_address":"mint","cluster":"devnet"},content_type="application/json")
        self.assertEqual(r.status_code,409);verify.assert_not_called()

    def test_confirmation_uses_real_verifier_and_persists(self):
        self.client.force_login(self.buyer)
        tx=evidence()
        def rpc(cluster, method, params):
            return {"result":{"value":[{"err":None,"confirmationStatus":"finalized"}]}} if method=="getSignatureStatuses" else {"result":tx}
        with patch("api.solana._rpc_call",side_effect=rpc):
            r=self.client.post(f"/api/purchases/{self.purchase.pk}/confirm/",{"tx_signature":"sig","mint_address":"mint","cluster":"devnet"},content_type="application/json")
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(AdRight.objects.get().owner_wallet,"buyer")
        self.purchase.refresh_from_db();self.assertEqual(self.purchase.status,"confirmed")

    def test_all_foreign_order_mutations_denied(self):
        self.purchase.status="confirmed";self.purchase.save()
        Order.objects.create(purchase=self.purchase,status="completed",proof=b"private",creative=b"private")
        self.client.force_login(self.other)
        for action in ["creative","accept","deliver","complete","dispute","refund_request"]:
            with self.subTest(action=action):
                self.assertEqual(self.client.post(self.url,{"action":action,"brief":"Attack","issue":"Attack message"}).status_code,403)
        for path in [self.url,self.url+"file/creative/",self.url+"file/proof/"]:
            self.assertEqual(self.client.get(path).status_code,403)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":5},content_type="application/json").status_code,403)
        self.assertEqual(self.client.post(self.url+"messages/",{"text":"Attack"},content_type="application/json").status_code,403)

    def test_seller_cannot_perform_buyer_actions(self):
        self.purchase.status="confirmed";self.purchase.save()
        order=Order.objects.create(purchase=self.purchase,status="delivered")
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(self.url,{"action":"complete"}).status_code,409)
        self.assertEqual(self.client.post(self.url,{"action":"refund_request","issue":"Request a refund"}).status_code,403)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":5},content_type="application/json").status_code,403)
        order.refresh_from_db();self.assertEqual(order.status,"delivered")

    def test_message_rate_limit(self):
        self.purchase.status="confirmed";self.purchase.save()
        self.client.force_login(self.buyer)
        for _ in range(30):
            self.assertEqual(self.client.post(self.url+"messages/",{"text":"hello"},content_type="application/json").status_code,200)
        self.assertEqual(self.client.post(self.url+"messages/",{"text":"limit"},content_type="application/json").status_code,429)

    def test_malformed_json_safe_errors(self):
        self.purchase.status="confirmed";self.purchase.save()
        Order.objects.create(purchase=self.purchase,status="completed")
        self.client.force_login(self.buyer)
        for path in [self.url+"messages/",self.url+"review/",f"/api/listings/{self.listing.pk}/save/",f"/api/listings/{self.listing.pk}/report/", "/api/profiles/notifications/read/"]:
            for payload in ["{", "[]", "null", "42"]:
                with self.subTest(path=path,payload=payload):
                    self.assertEqual(self.client.post(path,payload,content_type="application/json").status_code,400)

    def test_private_responses_are_not_cached(self):
        self.purchase.status="confirmed";self.purchase.save()
        self.client.force_login(self.buyer)
        for path in ["/api/auth/session/","/api/orders/",self.url,"/api/purchases/?wallet=buyer","/api/ad-rights/?wallet=buyer"]:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertIn("no-store",response["Cache-Control"])

    def test_invalid_review_ratings_and_messages(self):
        self.purchase.status="confirmed";self.purchase.save()
        Order.objects.create(purchase=self.purchase,status="completed")
        self.client.force_login(self.buyer)
        for rating in [True,0,6,"5",None]:
            self.assertEqual(self.client.post(self.url+"review/",{"rating":rating},content_type="application/json").status_code,400)
        for text in [None,[],{},"", " "*10, "x"*2001]:
            self.assertEqual(self.client.post(self.url+"messages/",{"text":text},content_type="application/json").status_code,400)


class PurchaseBindingTests(TestCase):
    def test_memo_binds_transaction_to_exact_purchase(self):
        tx=evidence()
        with patch("api.solana.get_signature_status",return_value={"confirmed":True}),patch("api.solana._rpc_call",return_value={"result":tx}):
            args=dict(signature="sig",cluster="devnet",buyer_wallet="buyer",seller_wallet="seller",price_sol=Decimal("0.25"),mint_address="mint",purchase_id=42)
            self.assertFalse(verify_purchase_transaction(**args)["confirmed"])
            tx["transaction"]["message"]["instructions"].append({"programId":"MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr","parsed":"AdMint purchase:41"})
            self.assertFalse(verify_purchase_transaction(**args)["confirmed"])
            tx["transaction"]["message"]["instructions"][-1]["parsed"]="AdMint purchase:42"
            self.assertTrue(verify_purchase_transaction(**args)["confirmed"])

    def test_real_rpc_authority_field_and_legacy_clock_skew(self):
        tx=evidence();tx["blockTime"]-=65
        info=tx["transaction"]["message"]["instructions"][3]["parsed"]["info"]
        info["mint"]=info.pop("account")
        with patch("api.solana.get_signature_status",return_value={"confirmed":True}),patch("api.solana._rpc_call",return_value={"result":tx}):
            self.assertTrue(verify_purchase_transaction(signature="sig",cluster="devnet",buyer_wallet="buyer",seller_wallet="seller",price_sol=Decimal("0.25"),mint_address="mint",not_before=timezone.now())["confirmed"])

    def test_prepared_purchase_network_cannot_change(self):
        from django.contrib.auth import get_user_model
        user=get_user_model().objects.create_user(username="network-buyer")
        Identity.objects.create(user=user,provider="phantom",subject="buyer")
        self.client.force_login(user)
        listing=Listing.objects.create(title="Network test",seller_wallet="seller",price_sol=Decimal("0.25"))
        response=self.client.post("/api/purchases/prepare/",{"listing_id":listing.pk,"buyer_wallet":"buyer","cluster":"testnet"},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content)
        purchase=Purchase.objects.get(pk=response.json()["id"])
        self.assertEqual(purchase.cluster,"testnet")
        self.assertEqual(purchase.verification_version,2)
        with patch("api.views.verify_purchase_transaction") as verify:
            response=self.client.post(f"/api/purchases/{purchase.pk}/confirm/",{"tx_signature":"sig","mint_address":"mint","cluster":"devnet"},content_type="application/json")
        self.assertEqual(response.status_code,400)
        verify.assert_not_called()
