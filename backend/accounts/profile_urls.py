from django.urls import path
from . import profiles, notifications
urlpatterns = [path("notifications/", notifications.inbox), path("notifications/read/", notifications.mark_read), path("search/", profiles.search), path("update/", profiles.update), path("wallet/<str:address>/", profiles.wallet_profile),
    path("<int:user_id>/", profiles.detail), path("<int:user_id>/avatar/", profiles.avatar),
    path("<int:user_id>/follow/", profiles.follow)]
