from django.contrib import admin
from .models import Identity, LoginEvent
@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "subject", "created_at")
    readonly_fields = ("user", "provider", "subject", "created_at")
    def has_add_permission(self, request): return False
@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "created_at")
    readonly_fields = ("user", "provider", "created_at")
    def has_add_permission(self, request): return False
