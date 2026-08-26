import uuid
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel


class DataSource(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)
    engine = models.CharField(max_length=30, default="mssql", choices=[("mssql", "SQL Server"), ("postgresql", "PostgreSQL"), ("mysql", "MySQL"), ("oracle", "Oracle"), ("sqlite", "SQLite")])
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(null=True, blank=True)
    database_name = models.CharField(max_length=160, blank=True)
    credential_env_prefix = models.CharField(max_length=80, blank=True, help_text="Environment variable prefix only; never store passwords here.")
    connection_options = models.JSONField(default=dict, blank=True)
    is_read_only = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class AIDomain(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    data_sources = models.ManyToManyField(DataSource, related_name="domains")
    allowed_groups = models.ManyToManyField("auth.Group", related_name="ai_domains", blank=True)
    collection_name = models.CharField(max_length=160, blank=True)
    schema_context = models.TextField(blank=True)
    allowed_tables = models.JSONField(default=list, blank=True)
    max_rows = models.PositiveIntegerField(default=1000)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class BusinessRule(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="business_rules", on_delete=models.CASCADE)
    name = models.CharField(max_length=180)
    rule_text = models.TextField()
    sql_guidance = models.TextField(blank=True)
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("priority", "name")

    def __str__(self):
        return self.name


class TablePolicy(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="table_policies", on_delete=models.CASCADE)
    table_name = models.CharField(max_length=180)
    access = models.CharField(max_length=20, default="allow", choices=[("allow", "Allow"), ("deny", "Deny")])
    allowed_roles = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["domain", "table_name"], name="unique_domain_table_policy")]


class ColumnPolicy(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="column_policies", on_delete=models.CASCADE)
    table_name = models.CharField(max_length=180)
    column_name = models.CharField(max_length=180)
    sensitivity = models.CharField(max_length=20, default="normal", choices=[("normal", "Normal"), ("personal", "Personal"), ("sensitive", "Sensitive"), ("restricted", "Restricted")])
    default_access = models.CharField(max_length=20, default="allow", choices=[("allow", "Allow"), ("mask", "Mask"), ("deny", "Deny")])
    mask_pattern = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["domain", "table_name", "column_name"], name="unique_domain_column_policy")]


class ColumnRolePolicy(TimeStampedModel):
    column_policy = models.ForeignKey(ColumnPolicy, related_name="role_overrides", on_delete=models.CASCADE)
    role = models.CharField(max_length=40)
    access = models.CharField(max_length=20, choices=[("allow", "Allow"), ("mask", "Mask"), ("deny", "Deny")])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["column_policy", "role"], name="unique_column_role_policy")]


class RowAccessPolicy(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="row_policies", on_delete=models.CASCADE)
    name = models.CharField(max_length=180)
    table_name = models.CharField(max_length=180)
    predicate_template = models.TextField(help_text="Reviewed parameterized predicate template, e.g. POLH_DEPT_CODE = {department_code}.")
    allowed_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)


class SuggestedPrompt(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="suggested_prompts", on_delete=models.CASCADE)
    text_en = models.CharField(max_length=500)
    text_ar = models.CharField(max_length=500, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("order", "text_en")


class TrainingPrompt(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="training_prompts", null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=180)
    prompt_type = models.CharField(max_length=30, choices=[("system", "System"), ("sql_generation", "SQL generation"), ("summary", "Summary"), ("chart", "Chart")])
    content = models.TextField()
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)


class TrainingCandidate(TimeStampedModel):
    domain = models.ForeignKey(AIDomain, related_name="training_candidates", on_delete=models.CASCADE)
    kind = models.CharField(max_length=30, choices=[("ddl", "DDL"), ("documentation", "Documentation"), ("question_sql", "Question + SQL"), ("feedback", "Corrected feedback")])
    question = models.TextField(blank=True)
    sql = models.TextField(blank=True)
    content = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="draft", choices=[("draft", "Draft"), ("approved", "Approved"), ("trained", "Trained"), ("rejected", "Rejected")])
    external_training_id = models.CharField(max_length=180, blank=True)
    validation_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class AnalysisSession(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="vanna_sessions", on_delete=models.CASCADE)
    domain = models.ForeignKey(AIDomain, related_name="analysis_sessions", on_delete=models.PROTECT)
    title = models.CharField(max_length=240, blank=True)
    context = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return self.title or str(self.pk)


class QueryAudit(TimeStampedModel):
    session = models.ForeignKey(AnalysisSession, related_name="queries", on_delete=models.CASCADE)
    question = models.TextField()
    generated_sql = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    result_preview = models.JSONField(default=list, blank=True)
    chart_spec = models.JSONField(default=dict, blank=True)
    response_metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="completed", choices=[("pending", "Pending"), ("completed", "Completed"), ("blocked", "Blocked"), ("failed", "Failed")])
    row_count = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ("created_at", "pk")


class VannaSettings(TimeStampedModel):
    provider = models.CharField(
        max_length=30,
        default="demo",
        choices=[
            ("demo", "Safe demo adapter"),
            ("ollama_vanna", "Vanna 2.0 + Ollama + ChromaDB (local)"),
            ("vanna_gateway", "Vanna 2.0 gateway"),
        ],
    )
    endpoint = models.URLField(
        blank=True,
        help_text=(
            "Ollama host for the local provider (for example http://127.0.0.1:11434) "
            "or the HTTPS endpoint for a Vanna gateway."
        ),
    )
    api_key_env = models.CharField(max_length=80, blank=True, help_text="Name of an environment variable containing the gateway secret.")
    timeout_seconds = models.PositiveSmallIntegerField(default=120)
    system_prompt = models.TextField(default="You are an insurance analytics assistant. Enforce all table, column and row policies before using tools.")
    training_prompt = models.TextField(default="Learn only from approved DDL, business documentation, reviewed question-SQL pairs and confirmed corrections.")
    allow_sql_execution = models.BooleanField(default=False)
    require_human_review_for_training = models.BooleanField(default=True)
    chroma_top_k = models.PositiveSmallIntegerField(
        default=8,
        help_text="Relevant ChromaDB training memories supplied to Ollama per question.",
    )
    chroma_auto_train_successful_queries = models.BooleanField(
        default=True,
        help_text="Store successful governed question/SQL pairs in the domain collection.",
    )
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Vanna settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
