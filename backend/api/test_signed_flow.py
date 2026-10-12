import base64
from io import BytesIO
from unittest.mock import patch
import base58
from PIL import Image
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.utils import timezone
from .models import Purchase, Listing, AdRight, Order, Review
from .test_deep_audit import TOKEN, SYSTEM, token_instruction

class SignedMarketplaceFlowTests(TestCase):
    def post(self,client,path,data):
        csrf=client.get("/api/auth/session/").json()["csrfToken"]
        return client.post(path,data,content_type="application/json",HTTP_X_CSRFTOKEN=csrf)

    def sign_in(self,key):
        client=Client(enforce_csrf_checks=True)
        wallet=base58.b58encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
        challenge=self.post(client,"/api/auth/wallet/challenge/",{"wallet":wallet}).json()
        signature=base64.b64encode(key.sign(challenge["message"].encode())).decode()
        result=self.post(client,"/api/auth/wallet/verify/",{"challenge":challenge["challenge"],"signature":signature})
        self.assertEqual(result.status_code,200,result.content)
        return client,wallet

    def form(self,client,path,data):
        csrf=client.get("/api/auth/session/").json()["csrfToken"]
        return client.post(path,data,HTTP_X_CSRFTOKEN=csrf)

    def image(self):
        out=BytesIO();Image.new("RGB",(30,30)).save(out,"PNG")
        return SimpleUploadedFile("evidence.png",out.getvalue(),content_type="image/png")

    def test_signed_accounts_purchase_chat_delivery_review_and_refresh(self):
        cache.clear()
        seller_key=Ed25519PrivateKey.generate();buyer_key=Ed25519PrivateKey.generate()
        seller,seller_wallet=self.sign_in(seller_key)
        buyer,buyer_wallet=self.sign_in(buyer_key)
        created=self.post(seller,"/api/listings/",{"title":"Signed E2E surface","duration":"7 days","surfaceType":"Physical","priceSol":"0.25","seller_wallet":seller_wallet})
        self.assertEqual(created.status_code,201,created.content)
        listing_id=created.json()["id"]
        self.assertEqual(self.form(seller,f"/api/listings/{listing_id}/details/",{"description":"Placement agreement","location":"Test studio","photo":self.image()}).status_code,200)
        prepared=self.post(buyer,"/api/purchases/prepare/",{"listing_id":listing_id,"buyer_wallet":buyer_wallet})
        self.assertEqual(prepared.status_code,201,prepared.content)
        purchase_id=prepared.json()["id"]
        tx={"blockTime":int(timezone.now().timestamp()),"meta":{"err":None,"preTokenBalances":[],"postTokenBalances":[{"accountIndex":1,"mint":"test-mint","owner":buyer_wallet,"programId":TOKEN,"uiTokenAmount":{"amount":"1","decimals":0}}]},"transaction":{"message":{"accountKeys":[{"pubkey":buyer_wallet,"signer":True},{"pubkey":"test-token-account","signer":False}],"instructions":[
            {"program":"system","programId":SYSTEM,"parsed":{"type":"transfer","info":{"source":buyer_wallet,"destination":seller_wallet,"lamports":250000000}}},
            token_instruction("initializeMint",mint="test-mint",decimals=0,mintAuthority=buyer_wallet,freezeAuthority=None),
            token_instruction("mintTo",mint="test-mint",account="test-token-account",amount="1",mintAuthority=buyer_wallet),
            token_instruction("setAuthority",account="test-mint",authorityType="mintTokens",authority=buyer_wallet,newAuthority=None),
        ]}}}
        tx["transaction"]["message"]["instructions"].append({"programId":"MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr","parsed":f"AdMint purchase:{purchase_id}"})
        confirm_path=f"/api/purchases/{purchase_id}/confirm/"
        payload={"tx_signature":"test-chain-signature","mint_address":"test-mint","cluster":"devnet"}
        with patch("api.solana._rpc_call",side_effect=TimeoutError()):
            self.assertEqual(self.post(buyer,confirm_path,payload).status_code,503)
        self.assertEqual(Purchase.objects.get(pk=purchase_id).status,"pending")
        def rpc(cluster,method,params):
            return {"result":{"value":[{"err":None,"confirmationStatus":"finalized"}]}} if method=="getSignatureStatuses" else {"result":tx}
        with patch("api.solana._rpc_call",side_effect=rpc):
            self.assertEqual(self.post(buyer,confirm_path,payload).status_code,200)
        self.assertEqual(AdRight.objects.count(),1)
        self.assertEqual(Listing.objects.get(pk=listing_id).status,"sold")
        self.assertEqual(self.form(seller,f"/api/listings/{listing_id}/details/",{"description":"Change paid terms"}).status_code,409)
        order_path=f"/api/orders/{purchase_id}/"
        self.assertEqual(self.form(buyer,order_path,{"action":"creative","brief":"Use the agreed logo","file":self.image()}).status_code,200)
        self.assertEqual(self.post(buyer,order_path+"messages/",{"text":"Our campaign brief"}).status_code,200)
        self.assertEqual(self.post(seller,order_path+"messages/",{"text":"Brief received"}).status_code,200)
        self.assertEqual(self.form(seller,order_path,{"action":"accept"}).status_code,200)
        self.assertEqual(self.form(seller,order_path,{"action":"deliver","file":self.image()}).status_code,200)
        self.assertEqual(self.form(buyer,order_path,{"action":"complete"}).status_code,200)
        self.assertEqual(self.post(buyer,order_path+"review/",{"rating":5,"text":"Placement completed"}).status_code,200)
        fresh,fresh_wallet=self.sign_in(buyer_key)
        order=fresh.get(order_path).json()
        self.assertEqual(order["status"],"completed")
        self.assertTrue(order["reviewed"])
        self.assertEqual(len(order["messages"]),2)
        self.assertEqual(fresh.get(order["creative"]).status_code,200)
        self.assertEqual(fresh.get(order["proof"]).status_code,200)
        self.assertEqual(fresh.get("/api/ad-rights/",{"wallet":fresh_wallet}).json()[0]["listing"],listing_id)
        self.assertEqual(Review.objects.count(),1)
        self.assertEqual(Order.objects.count(),1)
