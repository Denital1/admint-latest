from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, Client
from accounts.models import Identity
from .models import Listing, Purchase, Order

class ReservationConcurrencyTests(TransactionTestCase):
    def test_two_buyers_cannot_reserve_same_surface(self):
        seller=get_user_model().objects.create_user(username="concurrent-seller")
        listing=Listing.objects.create(title="Concurrent",duration="day",owner_account=seller,seller_wallet="seller",price_sol=Decimal("0.25"))
        clients=[]
        for index in range(2):
            buyer=get_user_model().objects.create_user(username=f"concurrent-buyer-{index}")
            wallet=f"buyer-{index}"
            Identity.objects.create(user=buyer,provider="phantom",subject=wallet)
            client=Client();client.force_login(buyer);clients.append((client,wallet))
        barrier=Barrier(2)
        def reserve(pair):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                client,wallet=pair
                return client.post("/api/purchases/prepare/",{"listing_id":listing.pk,"buyer_wallet":wallet},content_type="application/json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(reserve,clients))
        self.assertTrue(all(status in {201,409,503} for status in statuses),statuses)
        self.assertLessEqual(statuses.count(201),1,statuses)
        self.assertEqual(Purchase.objects.count(),statuses.count(201))
        if 201 in statuses:
            listing.refresh_from_db();self.assertEqual(listing.status,"reserved")

    def test_simultaneous_first_order_visits_both_succeed(self):
        if connection.vendor == "sqlite" and "memory" in str(connection.settings_dict["NAME"]):
            self.skipTest("Run with qa/run-file-db-tests.py to exercise real SQLite file locks.")
        buyer=get_user_model().objects.create_user(username="order-concurrent-buyer")
        Identity.objects.create(user=buyer,provider="phantom",subject="order-buyer-wallet")
        listing=Listing.objects.create(title="Concurrent first order",duration="day",seller_wallet="order-seller")
        purchase=Purchase.objects.create(listing=listing,buyer_wallet="order-buyer-wallet",seller_wallet="order-seller",price_sol="0.03",status="confirmed")
        clients=[Client(),Client()]
        for client in clients:client.force_login(buyer)
        barrier=Barrier(2)
        from unittest.mock import patch
        from django.db.models.query import QuerySet
        original_get=QuerySet.get
        def synchronized_get(queryset,*args,**kwargs):
            try:return original_get(queryset,*args,**kwargs)
            except Order.DoesNotExist:
                barrier.wait(timeout=10)
                raise
        def visit(client):
            close_old_connections()
            try:
                response=client.get(f"/api/orders/{purchase.pk}/")
                return response.status_code,response.json()
            finally:close_old_connections()
        # Both requests observe the missing order before either inserts it.
        with patch.object(QuerySet,"get",new=synchronized_get):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(visit,clients))
        self.assertEqual([result[0] for result in results],[200,200],results)
        self.assertTrue(all(result[1]["status"]=="awaiting_creative" for result in results))
        self.assertEqual(Order.objects.filter(purchase=purchase).count(),1)
