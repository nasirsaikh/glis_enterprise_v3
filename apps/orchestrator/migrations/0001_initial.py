import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="DataSource", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=160, unique=True)), ("engine", models.CharField(choices=[("mssql", "SQL Server"), ("postgresql", "PostgreSQL"), ("mysql", "MySQL"), ("oracle", "Oracle"), ("sqlite", "SQLite")], default="mssql", max_length=30)),
            ("host", models.CharField(blank=True, max_length=255)), ("port", models.PositiveIntegerField(blank=True, null=True)), ("database_name", models.CharField(blank=True, max_length=160)),
            ("credential_env_prefix", models.CharField(blank=True, help_text="Environment variable prefix only; never store passwords here.", max_length=80)), ("connection_options", models.JSONField(blank=True, default=dict)), ("is_read_only", models.BooleanField(default=True)), ("is_active", models.BooleanField(default=True)),
        ]),
        migrations.CreateModel(name="VannaSettings", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("provider", models.CharField(choices=[("demo", "Safe demo adapter"), ("vanna_gateway", "Vanna 2.0 gateway")], default="demo", max_length=30)), ("endpoint", models.URLField(blank=True)),
            ("api_key_env", models.CharField(blank=True, help_text="Name of an environment variable containing the gateway secret.", max_length=80)), ("timeout_seconds", models.PositiveSmallIntegerField(default=120)),
            ("system_prompt", models.TextField(default="You are an insurance analytics assistant. Enforce all table, column and row policies before using tools.")),
            ("training_prompt", models.TextField(default="Learn only from approved DDL, business documentation, reviewed question-SQL pairs and confirmed corrections.")),
            ("allow_sql_execution", models.BooleanField(default=False)), ("require_human_review_for_training", models.BooleanField(default=True)), ("is_enabled", models.BooleanField(default=True)),
        ], options={"verbose_name_plural": "Vanna settings"}),
        migrations.CreateModel(name="AIDomain", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=160, unique=True)), ("slug", models.SlugField(unique=True)), ("description", models.TextField(blank=True)), ("collection_name", models.CharField(blank=True, max_length=160)),
            ("schema_context", models.TextField(blank=True)), ("allowed_tables", models.JSONField(blank=True, default=list)), ("max_rows", models.PositiveIntegerField(default=1000)), ("is_active", models.BooleanField(default=True)),
            ("allowed_groups", models.ManyToManyField(blank=True, related_name="ai_domains", to="auth.group")), ("data_sources", models.ManyToManyField(related_name="domains", to="orchestrator.datasource")),
        ]),
        migrations.CreateModel(name="BusinessRule", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=180)), ("rule_text", models.TextField()), ("sql_guidance", models.TextField(blank=True)), ("priority", models.PositiveSmallIntegerField(default=100)), ("is_active", models.BooleanField(default=True)),
            ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="business_rules", to="orchestrator.aidomain")),
        ], options={"ordering": ("priority", "name")}),
        migrations.CreateModel(name="TablePolicy", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("table_name", models.CharField(max_length=180)), ("access", models.CharField(choices=[("allow", "Allow"), ("deny", "Deny")], default="allow", max_length=20)), ("allowed_roles", models.JSONField(blank=True, default=list)), ("description", models.TextField(blank=True)),
            ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="table_policies", to="orchestrator.aidomain")),
        ]),
        migrations.CreateModel(name="ColumnPolicy", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("table_name", models.CharField(max_length=180)), ("column_name", models.CharField(max_length=180)), ("sensitivity", models.CharField(choices=[("normal", "Normal"), ("personal", "Personal"), ("sensitive", "Sensitive"), ("restricted", "Restricted")], default="normal", max_length=20)),
            ("default_access", models.CharField(choices=[("allow", "Allow"), ("mask", "Mask"), ("deny", "Deny")], default="allow", max_length=20)), ("mask_pattern", models.CharField(blank=True, max_length=120)),
            ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="column_policies", to="orchestrator.aidomain")),
        ]),
        migrations.CreateModel(name="ColumnRolePolicy", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("role", models.CharField(max_length=40)), ("access", models.CharField(choices=[("allow", "Allow"), ("mask", "Mask"), ("deny", "Deny")], max_length=20)),
            ("column_policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="role_overrides", to="orchestrator.columnpolicy")),
        ]),
        migrations.CreateModel(name="RowAccessPolicy", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=180)), ("table_name", models.CharField(max_length=180)), ("predicate_template", models.TextField(help_text="Reviewed parameterized predicate template, e.g. POLH_DEPT_CODE = {department_code}.")), ("allowed_roles", models.JSONField(blank=True, default=list)), ("is_active", models.BooleanField(default=True)),
            ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="row_policies", to="orchestrator.aidomain")),
        ]),
        migrations.CreateModel(name="SuggestedPrompt", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("text_en", models.CharField(max_length=500)), ("text_ar", models.CharField(blank=True, max_length=500)), ("order", models.PositiveSmallIntegerField(default=0)), ("is_active", models.BooleanField(default=True)),
            ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="suggested_prompts", to="orchestrator.aidomain")),
        ], options={"ordering": ("order", "text_en")}),
        migrations.CreateModel(name="TrainingPrompt", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("name", models.CharField(max_length=180)), ("prompt_type", models.CharField(choices=[("system", "System"), ("sql_generation", "SQL generation"), ("summary", "Summary"), ("chart", "Chart")], max_length=30)), ("content", models.TextField()), ("version", models.PositiveIntegerField(default=1)), ("is_active", models.BooleanField(default=True)),
            ("domain", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="training_prompts", to="orchestrator.aidomain")),
        ]),
        migrations.CreateModel(name="TrainingCandidate", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("kind", models.CharField(choices=[("ddl", "DDL"), ("documentation", "Documentation"), ("question_sql", "Question + SQL"), ("feedback", "Corrected feedback")], max_length=30)), ("question", models.TextField(blank=True)), ("sql", models.TextField(blank=True)), ("content", models.TextField(blank=True)),
            ("status", models.CharField(choices=[("draft", "Draft"), ("approved", "Approved"), ("trained", "Trained"), ("rejected", "Rejected")], default="draft", max_length=20)), ("external_training_id", models.CharField(blank=True, max_length=180)), ("validation_notes", models.TextField(blank=True)),
            ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)), ("domain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="training_candidates", to="orchestrator.aidomain")),
        ]),
        migrations.CreateModel(name="AnalysisSession", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("title", models.CharField(blank=True, max_length=240)), ("context", models.JSONField(blank=True, default=dict)), ("is_active", models.BooleanField(default=True)),
            ("domain", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="analysis_sessions", to="orchestrator.aidomain")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vanna_sessions", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="QueryAudit", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("question", models.TextField()), ("generated_sql", models.TextField(blank=True)), ("summary", models.TextField(blank=True)), ("result_preview", models.JSONField(blank=True, default=list)), ("chart_spec", models.JSONField(blank=True, default=dict)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("completed", "Completed"), ("blocked", "Blocked"), ("failed", "Failed")], default="completed", max_length=20)), ("row_count", models.PositiveIntegerField(default=0)), ("duration_ms", models.PositiveIntegerField(default=0)), ("error_code", models.CharField(blank=True, max_length=80)),
            ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="queries", to="orchestrator.analysissession")),
        ]),
        migrations.AddConstraint(model_name="tablepolicy", constraint=models.UniqueConstraint(fields=("domain", "table_name"), name="unique_domain_table_policy")),
        migrations.AddConstraint(model_name="columnpolicy", constraint=models.UniqueConstraint(fields=("domain", "table_name", "column_name"), name="unique_domain_column_policy")),
        migrations.AddConstraint(model_name="columnrolepolicy", constraint=models.UniqueConstraint(fields=("column_policy", "role"), name="unique_column_role_policy")),
    ]
