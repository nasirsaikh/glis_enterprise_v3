from django.contrib import admin
from .models import (
    AIDomain, AnalysisSession, BusinessRule, ColumnPolicy, ColumnRolePolicy,
    DataSource, QueryAudit, RowAccessPolicy, SuggestedPrompt, TablePolicy,
    TrainingCandidate, TrainingPrompt, VannaSettings,
)


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "engine", "host", "database_name", "is_read_only", "is_active")
    list_filter = ("engine", "is_read_only", "is_active")
    search_fields = ("name", "host", "database_name")


@admin.register(AIDomain)
class AIDomainAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "collection_name", "max_rows", "is_active")
    filter_horizontal = ("data_sources", "allowed_groups")


@admin.register(BusinessRule)
class BusinessRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "priority", "is_active", "updated_at")
    list_filter = ("domain", "is_active")
    list_editable = ("priority", "is_active")
    search_fields = ("name", "rule_text", "sql_guidance")


@admin.register(TablePolicy)
class TablePolicyAdmin(admin.ModelAdmin):
    list_display = ("table_name", "domain", "access", "allowed_roles")
    list_filter = ("domain", "access")


@admin.register(ColumnPolicy)
class ColumnPolicyAdmin(admin.ModelAdmin):
    list_display = ("column_name", "table_name", "domain", "sensitivity", "default_access")
    list_filter = ("domain", "sensitivity", "default_access")


@admin.register(ColumnRolePolicy)
class ColumnRolePolicyAdmin(admin.ModelAdmin):
    list_display = ("column_policy", "role", "access")
    list_filter = ("role", "access")


@admin.register(RowAccessPolicy)
class RowAccessPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "table_name", "is_active")
    list_filter = ("domain", "is_active")


@admin.register(SuggestedPrompt)
class SuggestedPromptAdmin(admin.ModelAdmin):
    list_display = ("text_en", "domain", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(TrainingPrompt)
class TrainingPromptAdmin(admin.ModelAdmin):
    list_display = ("name", "domain", "prompt_type", "version", "is_active")
    list_filter = ("domain", "prompt_type", "is_active")


@admin.register(TrainingCandidate)
class TrainingCandidateAdmin(admin.ModelAdmin):
    list_display = ("id", "domain", "kind", "status", "created_by", "updated_at")
    list_filter = ("domain", "kind", "status")
    search_fields = ("question", "sql", "content", "validation_notes")
    actions = ("approve_selected",)

    @admin.action(description="Approve selected candidates for Vanna training")
    def approve_selected(self, request, queryset):
        queryset.update(status="approved")


@admin.register(AnalysisSession)
class AnalysisSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "domain", "title", "is_active", "updated_at")
    list_filter = ("domain", "is_active")
    search_fields = ("user__email", "title")


@admin.register(QueryAudit)
class QueryAuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "session", "status", "row_count", "duration_ms", "question_excerpt")
    list_filter = ("status", "session__domain")
    readonly_fields = tuple(field.name for field in QueryAudit._meta.fields)

    @admin.display(description="Question")
    def question_excerpt(self, obj):
        return obj.question[:80]

    def has_add_permission(self, request):
        return False


@admin.register(VannaSettings)
class VannaSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Provider",
            {
                "fields": (
                    "provider",
                    "endpoint",
                    "api_key_env",
                    "timeout_seconds",
                    "is_enabled",
                ),
                "description": (
                    "For Vanna 2.0 + Ollama + ChromaDB, set Endpoint to the local Ollama host "
                    "(normally http://127.0.0.1:11434). Models are read from OLLAMA_MODEL "
                    "and OLLAMA_EMBED_MODEL."
                ),
            },
        ),
        ("Prompts", {"fields": ("system_prompt", "training_prompt")}),
        (
            "ChromaDB retrieval",
            {"fields": ("chroma_top_k", "chroma_auto_train_successful_queries")},
        ),
        ("Safety", {"fields": ("allow_sql_execution", "require_human_review_for_training")}),
    )

    def has_add_permission(self, request):
        return not VannaSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
