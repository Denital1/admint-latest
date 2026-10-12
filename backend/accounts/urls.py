from django.urls import path
from . import views
urlpatterns = [
    path("session/", views.session), path("signup/", views.signup),
    path("login/", views.password_login), path("logout/", views.signout),
    path("wallet/challenge/", views.wallet_challenge), path("wallet/verify/", views.wallet_verify),
    path("google/start/", views.google_start), path("google/callback/", views.google_callback),
]
