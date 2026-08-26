from django.contrib import admin
from .models import AIInteraction, AISettings


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    exclude = ()

    def has_add_permission(self, request):
        return not AISettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AIInteraction)
class AIInteractionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "purpose", "provider", "confidence", "succeeded")
    list_filter = ("purpose", "provider", "succeeded")
    readonly_fields = [field.name for field in AIInteraction._meta.fields]
