from django.contrib import admin
from .models import AIExtractionProfile, AIInteraction, AIProviderConfig, AISettings, AITrainingExample


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


@admin.register(AIProviderConfig)
class AIProviderConfigAdmin(admin.ModelAdmin):
    list_display=("name","provider","model_name","supports_vision","allow_sensitive_data","priority","is_active")
    list_filter=("provider","supports_vision","allow_sensitive_data","is_active")
    search_fields=("name","model_name","endpoint")
    exclude=("secret_reference",)

class AITrainingExampleInline(admin.TabularInline):
    model=AITrainingExample
    extra=0

@admin.register(AIExtractionProfile)
class AIExtractionProfileAdmin(admin.ModelAdmin):
    list_display=("name","task","applicable_product","applicable_transaction_type","priority","is_active")
    list_filter=("task","is_active")
    search_fields=("name","system_prompt","instructions")
    inlines=(AITrainingExampleInline,)

@admin.register(AITrainingExample)
class AITrainingExampleAdmin(admin.ModelAdmin):
    list_display=("name","profile","sort_order","is_active")
    list_filter=("is_active","profile__task")
    search_fields=("name","input_text")
