from io import BytesIO
from PIL import Image
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import Identity
from .models import Listing, Purchase, Order, Review, OrderMessage

class CommerceTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.seller=U.objects.create_user(username="commerce-seller",first_name="Seller")
        self.buyer=U.objects.create_user(username="commerce-buyer")
        self.other=U.objects.create_user(username="commerce-other")
        Identity.objects.create(user=self.buyer,provider="phantom",subject="buyer-wallet")
        self.listing=Listing.objects.create(title="Studio",owner_account=self.seller,seller_wallet="seller-wallet",duration="7 days")
        self.purchase=Purchase.objects.create(listing=self.listing,buyer_wallet="buyer-wallet",seller_wallet="seller-wallet",price_sol="0.1",status="confirmed")
        self.url=f"/api/orders/{self.purchase.pk}/"
    def image(self):
        b=BytesIO();Image.new("RGB",(50,50)).save(b,"PNG")
        return SimpleUploadedFile("photo.png",b.getvalue(),content_type="image/png")
    def test_order_flow_and_review(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(self.url,{"action":"complete"}).status_code,409)
        self.assertEqual(self.client.post(self.url,{"action":"creative","brief":"Place our logo","file":self.image()}).status_code,200)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(self.url,{"action":"complete"}).status_code,409)
        self.assertEqual(self.client.post(self.url,{"action":"accept"}).json()["status"],"in_progress")
        self.assertEqual(self.client.post(self.url,{"action":"deliver"}).status_code,400)
        self.assertEqual(self.client.post(self.url,{"action":"deliver","file":self.image()}).json()["status"],"delivered")
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":5},content_type="application/json").status_code,409)
        self.assertEqual(self.client.post(self.url,{"action":"complete"}).json()["status"],"completed")
        self.assertEqual(self.client.post(self.url+"review/",{"rating":5,"text":"Great"},content_type="application/json").status_code,200)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":4},content_type="application/json").status_code,409)
        self.assertEqual(Review.objects.count(),1)

    def test_fulfillment_role_and_stage_matrix_preserves_order(self):
        from .models import OrderEvent
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(self.url).status_code,200)
        stages=[
            ("awaiting_creative",self.buyer,{"action":"creative","brief":"Place the test advertisement"},"creative_submitted"),
            ("creative_submitted",self.seller,{"action":"accept"},"in_progress"),
            ("in_progress",self.seller,{"action":"deliver"},"delivered"),
            ("delivered",self.buyer,{"action":"complete"},"completed"),
        ]
        for before,actor,payload,after in stages:
            with self.subTest(stage=before):
                order=Order.objects.get(purchase=self.purchase)
                self.assertEqual(order.status,before)
                event_count=OrderEvent.objects.count()
                # The opposite party cannot perform the valid action for this stage.
                self.client.force_login(self.seller if actor==self.buyer else self.buyer)
                invalid={**payload}
                if payload["action"]=="deliver":invalid["file"]=self.image()
                self.assertEqual(self.client.post(self.url,invalid).status_code,409)
                self.client.force_login(self.other)
                self.assertEqual(self.client.post(self.url,payload).status_code,403)
                self.client.force_login(actor)
                valid={**payload}
                if payload["action"] in {"creative","deliver"}:valid["file"]=self.image()
                self.assertEqual(self.client.post(self.url,valid).json()["status"],after)
                order.refresh_from_db()
                self.assertEqual(order.status,after)
                self.assertEqual(OrderEvent.objects.count(),event_count+1)
                event=OrderEvent.objects.latest("pk")
                self.assertEqual((event.actor_id,event.previous_status,event.status),(actor.pk,before,after))
                if payload["action"] != "creative":
                    self.assertEqual(self.client.post(self.url,payload).status_code,409)
                    self.assertEqual(OrderEvent.objects.count(),event_count+1)
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(self.url,{"action":"creative","brief":"Replace completed campaign","file":self.image()}).status_code,409)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":5},content_type="application/json").status_code,403)
        self.client.force_login(self.buyer)
        for rating in [0,6,True,"5"]:
            self.assertEqual(self.client.post(self.url+"review/",{"rating":rating},content_type="application/json").status_code,400)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":4,"text":"Test advertisement delivered"},content_type="application/json").status_code,200)
        self.assertEqual(self.client.post(self.url+"review/",{"rating":1},content_type="application/json").status_code,409)
        self.assertEqual(Review.objects.count(),1)
        for user in [self.buyer,self.seller]:
            fresh=Client();fresh.force_login(user)
            data=fresh.get(self.url).json()
            self.assertEqual(data["status"],"completed")
            self.assertTrue(data["reviewed"])
            for key in ["creative","proof"]:
                response=fresh.get(data[key])
                self.assertEqual(response.status_code,200)
                self.assertIn("no-store",response["Cache-Control"])
                with Image.open(BytesIO(response.content)) as image:self.assertEqual(image.format,"JPEG")
        self.client.force_login(self.other)
        for kind in ["creative","proof"]:
            self.assertEqual(self.client.get(self.url+f"file/{kind}/").status_code,403)
        self.assertEqual(Order.objects.count(),1)

    def test_invalid_creative_and_proof_never_advance_fulfillment(self):
        from .models import OrderEvent
        self.client.force_login(self.buyer)
        self.client.get(self.url)
        for brief in ["", " "*10, "x"*3001]:
            self.assertEqual(self.client.post(self.url,{"action":"creative","brief":brief,"file":self.image()}).status_code,400)
        self.assertEqual(self.client.post(self.url,{"action":"creative","brief":"Test brief","file":SimpleUploadedFile("invalid.png",b"invalid image")}).status_code,400)
        order=Order.objects.get(purchase=self.purchase)
        self.assertEqual((order.status,order.brief),("awaiting_creative",""))
        self.assertFalse(order.creative)
        self.assertEqual(OrderEvent.objects.count(),0)
        self.client.post(self.url,{"action":"creative","brief":"Test brief","file":self.image()})
        self.client.force_login(self.seller)
        self.client.post(self.url,{"action":"accept"})
        self.assertEqual(self.client.post(self.url,{"action":"deliver"}).status_code,400)
        self.assertEqual(self.client.post(self.url,{"action":"deliver","file":SimpleUploadedFile("invalid.png",b"invalid image")}).status_code,400)
        order.refresh_from_db()
        self.assertEqual(order.status,"in_progress")
        self.assertFalse(order.proof)
        self.assertEqual(OrderEvent.objects.count(),2)
    def test_private_messages_files_and_order(self):
        self.client.force_login(self.buyer)
        self.client.post(self.url,{"action":"creative","brief":"Our campaign","file":self.image()})
        self.assertEqual(self.client.post(self.url+"messages/",{"text":"Hello seller"},content_type="application/json").status_code,200)
        self.client.force_login(self.other)
        for path in [self.url,self.url+"file/creative/"]:
            self.assertEqual(self.client.get(path).status_code,403)
        self.assertEqual(self.client.post(self.url+"messages/",{"text":"Intruder"},content_type="application/json").status_code,403)
        self.assertEqual(self.client.get("/api/orders/").json()["results"],[])
        self.assertEqual(OrderMessage.objects.count(),1)
    def test_listing_edit_photo_dates_saves_and_reports(self):
        url=f"/api/listings/{self.listing.pk}/"
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url+"details/",{"description":"Hijack"}).status_code,403)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(url+"details/",{"available_from":"2026-10-20","available_until":"2026-10-01"}).status_code,400)
        self.assertEqual(self.client.post(url+"details/",{"photo":SimpleUploadedFile("bad.svg",b"<svg/>")}).status_code,400)
        self.assertEqual(self.client.post(url+"details/",{"photo":self.image(),"location":"Tbilisi"}).status_code,200)
        self.assertEqual(self.client.get(url+"photo/")["Content-Type"],"image/jpeg")
        self.listing.status="sold";self.listing.save()
        self.assertEqual(self.client.post(url+"details/",{"description":"Changed terms"}).status_code,409)
        for _ in range(2):self.client.post(url+"save/",{"saved":True},content_type="application/json")
        self.assertEqual(self.client.get("/api/saved/").json()["ids"],[self.listing.pk])
        self.assertEqual(self.client.post(url+"report/",{"reason":"Misleading listing details"},content_type="application/json").status_code,200)
    def test_refund_request_never_marks_payment_refunded(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(self.url,{"action":"refund_request","issue":"Placement was not delivered"}).json()["status"],"refund_requested")
        self.purchase.refresh_from_db();self.assertEqual(self.purchase.status,"confirmed")
    def test_csrf_and_unconfirmed_access(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.buyer)
        self.assertEqual(c.post(self.url+"messages/",{"text":"hello"},content_type="application/json").status_code,403)
        self.purchase.status="pending";self.purchase.save()
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(self.url).status_code,404)

    def test_order_audit_and_staff_resolution(self):
        from .models import OrderEvent
        from .admin import OrderAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from unittest.mock import patch
        self.client.force_login(self.buyer)
        self.client.post(self.url,{"action":"creative","brief":"Campaign"})
        self.client.post(self.url,{"action":"dispute","issue":"Please review this campaign"})
        order=Order.objects.get(purchase=self.purchase)
        self.assertEqual(order.paused_status,"creative_submitted")
        self.assertEqual(OrderEvent.objects.filter(order=order).count(),2)
        request=RequestFactory().post("/admin/");request.user=self.seller
        admin=OrderAdmin(Order,AdminSite())
        with patch.object(admin,"message_user"):
            admin.resolve_issue(request,Order.objects.filter(pk=order.pk))
            order.refresh_from_db();self.assertEqual(order.status,"disputed")
            order.resolution="Both parties agreed to resume delivery.";order.save()
            admin.resolve_issue(request,Order.objects.filter(pk=order.pk))
        order.refresh_from_db();self.assertEqual(order.status,"creative_submitted")
        self.assertEqual(OrderEvent.objects.filter(order=order,action="issue_resolved").count(),1)
