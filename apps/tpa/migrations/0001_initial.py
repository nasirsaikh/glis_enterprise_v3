from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tickets","0007_category_allowed_groups"),
    ]
    operations = [
        migrations.CreateModel(
            name="TPAOrganization",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("code",models.CharField(max_length=40,unique=True)),("name_en",models.CharField(max_length=180)),("name_ar",models.CharField(blank=True,max_length=180)),
                ("organization_type",models.CharField(choices=[("INDIVIDUAL","Individual"),("CORPORATE","Corporate / Sponsor"),("INSURER","Insurance Company"),("TPA","TPA"),("BROKER","Broker"),("AGENT","Agent"),("OTHER","Other")],max_length=20)),
                ("commercial_registration",models.CharField(blank=True,max_length=80)),("contact_name",models.CharField(blank=True,max_length=160)),
                ("contact_email",models.EmailField(blank=True,max_length=254)),("contact_phone",models.CharField(blank=True,max_length=60)),("is_active",models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name="Policy",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("policy_number",models.CharField(db_index=True,max_length=80,unique=True)),("policy_name",models.CharField(blank=True,max_length=180)),("start_date",models.DateField()),("expiry_date",models.DateField()),
                ("status",models.CharField(choices=[("draft","Draft"),("active","Active"),("suspended","Suspended"),("expired","Expired"),("cancelled","Cancelled")],db_index=True,default="draft",max_length=20)),
                ("product_type",models.CharField(default="MEDICAL",max_length=80)),("insurer_reference",models.CharField(blank=True,max_length=100)),("tpa_reference",models.CharField(blank=True,max_length=100)),
                ("cancellation_effective_date",models.DateField(blank=True,null=True)),("currency",models.CharField(default="OMR",max_length=3)),("stp_enabled",models.BooleanField(default=False)),
                ("premium_calculation_enabled",models.BooleanField(default=True)),("allowed_backdating_days",models.PositiveSmallIntegerField(default=30)),("validation_bypass_allowed",models.BooleanField(default=False)),
                ("configuration",models.JSONField(blank=True,default=dict)),("notes",models.TextField(blank=True)),
                ("insurance_company",models.ForeignKey(limit_choices_to={"organization_type":"INSURER"},on_delete=django.db.models.deletion.PROTECT,related_name="insured_policies",to="tpa.tpaorganization")),
                ("sponsor",models.ForeignKey(limit_choices_to={"organization_type":"CORPORATE"},on_delete=django.db.models.deletion.PROTECT,related_name="sponsored_policies",to="tpa.tpaorganization")),
            ],
        ),
        migrations.CreateModel(
            name="BenefitPlan",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("code",models.CharField(max_length=50)),("name",models.CharField(max_length=160)),("description",models.TextField(blank=True)),
                ("annual_premium",models.DecimalField(decimal_places=3,default=Decimal("0"),max_digits=14)),("default_sum_insured",models.DecimalField(blank=True,decimal_places=3,max_digits=16,null=True)),
                ("premium_configuration",models.JSONField(blank=True,default=dict)),("is_active",models.BooleanField(default=True)),
                ("policy",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="plans",to="tpa.policy")),
            ],
        ),
        migrations.AddConstraint(model_name="benefitplan",constraint=models.UniqueConstraint(fields=("policy","code"),name="tpa_unique_policy_plan")),
        migrations.CreateModel(
            name="Member",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("tpa_member_id",models.CharField(blank=True,editable=False,max_length=40,null=True,unique=True)),("employee_id",models.CharField(blank=True,db_index=True,max_length=80)),
                ("first_name",models.CharField(max_length=100)),("middle_name",models.CharField(blank=True,max_length=100)),("last_name",models.CharField(max_length=100)),("date_of_birth",models.DateField()),
                ("gender",models.CharField(max_length=20)),("relationship",models.CharField(choices=[("PRINCIPAL","Principal"),("SPOUSE","Spouse"),("CHILD","Child"),("OTHER","Other")],max_length=20)),
                ("national_id",models.CharField(blank=True,db_index=True,max_length=80)),("passport_number",models.CharField(blank=True,db_index=True,max_length=80)),
                ("status",models.CharField(choices=[("active","Active"),("terminated","Terminated"),("voided","Deleted / Voided"),("cancelled","Cancelled")],db_index=True,default="active",max_length=20)),
                ("principal",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name="dependents",to="tpa.member")),
                ("sponsor",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="members",to="tpa.tpaorganization")),
            ],
        ),
        migrations.CreateModel(
            name="MemberPolicyEnrollment",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("coverage_start_date",models.DateField()),("coverage_end_date",models.DateField(blank=True,null=True)),
                ("enrollment_status",models.CharField(choices=[("pending","Pending"),("active","Active"),("terminated","Terminated"),("voided","Voided"),("cancelled","Cancelled")],db_index=True,default="pending",max_length=20)),
                ("premium_amount",models.DecimalField(decimal_places=3,default=Decimal("0"),max_digits=14)),("premium_calculation_basis",models.JSONField(blank=True,default=dict)),
                ("termination_reason",models.TextField(blank=True)),("termination_date",models.DateField(blank=True,null=True)),("voided_at",models.DateTimeField(blank=True,null=True)),("cancellation_date",models.DateField(blank=True,null=True)),
                ("benefit_plan",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="enrollments",to="tpa.benefitplan")),
                ("member",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="enrollments",to="tpa.member")),
                ("policy",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="enrollments",to="tpa.policy")),
            ],
        ),
        migrations.CreateModel(
            name="MemberTransaction",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("reference",models.CharField(blank=True,editable=False,max_length=40,null=True,unique=True)),
                ("transaction_type",models.CharField(choices=[("NEW_POLICY_ENROLLMENT","New Policy Enrollment"),("MEMBER_ADD","Member Addition"),("MEMBER_TERMINATE","Member Termination"),("MEMBER_DELETE","Member Deletion / Void"),("POLICY_CANCEL","Policy Cancellation")],db_index=True,max_length=30)),
                ("source",models.CharField(choices=[("PORTAL","Portal"),("EMAIL","Email"),("API","API"),("ADMIN","Admin"),("IMPORT","Import")],default="PORTAL",max_length=20)),
                ("request_date",models.DateTimeField(auto_now_add=True)),("effective_date",models.DateField()),
                ("status",models.CharField(choices=[("draft","Draft"),("extracting","Extracting"),("pending_validation","Pending Validation"),("needs_information","Needs Information"),("validation_failed","Validation Failed"),("pending_approval","Pending Approval"),("approved","Approved"),("auto_approved","Auto Approved"),("processing","Processing"),("processed","Processed"),("rejected","Rejected"),("failed","Failed"),("cancelled","Cancelled")],db_index=True,default="draft",max_length=30)),
                ("premium_before",models.DecimalField(decimal_places=3,default=Decimal("0"),max_digits=16)),("premium_adjustment",models.DecimalField(decimal_places=3,default=Decimal("0"),max_digits=16)),("premium_after",models.DecimalField(decimal_places=3,default=Decimal("0"),max_digits=16)),
                ("currency",models.CharField(default="OMR",max_length=3)),("validation_score",models.DecimalField(decimal_places=2,default=Decimal("0"),max_digits=5)),
                ("stp_eligible",models.BooleanField(default=False)),("stp_blockers",models.JSONField(blank=True,default=list)),("ai_summary",models.TextField(blank=True)),("ai_extraction_status",models.CharField(blank=True,max_length=30)),
                ("validation_bypassed",models.BooleanField(default=False)),("validation_bypass_reason",models.TextField(blank=True)),("validation_bypassed_at",models.DateTimeField(blank=True,null=True)),
                ("remarks",models.TextField(blank=True)),("submitted_at",models.DateTimeField(blank=True,null=True)),("processed_at",models.DateTimeField(blank=True,null=True)),("approved_at",models.DateTimeField(blank=True,null=True)),("rejection_reason",models.TextField(blank=True)),("metadata",models.JSONField(blank=True,default=dict)),
                ("approved_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="approved_tpa_transactions",to=settings.AUTH_USER_MODEL)),
                ("insurer",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="insurer_transactions",to="tpa.tpaorganization")),
                ("policy",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="transactions",to="tpa.policy")),
                ("requester",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="tpa_transactions",to=settings.AUTH_USER_MODEL)),
                ("requester_organization",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="requested_transactions",to="tpa.tpaorganization")),
                ("sponsor",models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name="transactions",to="tpa.tpaorganization")),
                ("ticket",models.OneToOneField(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="tpa_transaction",to="tickets.ticket")),
                ("validation_bypassed_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="tpa_validation_bypasses",to=settings.AUTH_USER_MODEL)),
            ],
            options={"permissions":[("view_tpa_dashboard","Can view TPA dashboard"),("create_enrollment","Can create TPA enrollment"),("create_endorsement","Can create TPA endorsement"),("terminate_member","Can terminate TPA member"),("delete_member","Can delete/void TPA member"),("cancel_policy","Can cancel TPA policy"),("approve_endorsement","Can approve TPA endorsement"),("process_endorsement","Can process TPA endorsement"),("bypass_validation","Can bypass TPA validation"),("override_premium","Can override TPA premium"),("view_sensitive_member_data","Can view sensitive TPA member data"),("view_ai_source_data","Can view TPA AI source data"),("configure_tpa","Can configure TPA"),("export_tpa_data","Can export TPA data")]},
        ),
        migrations.CreateModel(
            name="MemberAction",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("action",models.CharField(max_length=30)),("row_number",models.PositiveIntegerField(blank=True,null=True)),("submitted_data",models.JSONField(blank=True,default=dict)),("extracted_data",models.JSONField(blank=True,default=dict)),("corrected_data",models.JSONField(blank=True,default=dict)),
                ("before_data",models.JSONField(blank=True,default=dict)),("after_data",models.JSONField(blank=True,default=dict)),("extraction_confidence",models.DecimalField(blank=True,decimal_places=2,max_digits=5,null=True)),
                ("validation_status",models.CharField(choices=[("VALID","Valid"),("WARNING","Warning"),("ERROR","Error"),("BYPASSED","Bypassed")],default="ERROR",max_length=12)),("validation_errors",models.JSONField(blank=True,default=list)),("warnings",models.JSONField(blank=True,default=list)),
                ("calculated_premium",models.DecimalField(decimal_places=3,default=Decimal("0"),max_digits=14)),("calculation_snapshot",models.JSONField(blank=True,default=dict)),("processing_status",models.CharField(blank=True,max_length=30)),("processing_message",models.TextField(blank=True)),("processed_at",models.DateTimeField(blank=True,null=True)),
                ("member",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name="transaction_actions",to="tpa.member")),
                ("transaction",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="member_actions",to="tpa.membertransaction")),
            ],
        ),
        migrations.CreateModel(
            name="PolicyAccess",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("can_view",models.BooleanField(default=True)),("can_view_members",models.BooleanField(default=False)),("can_create_enrollment",models.BooleanField(default=False)),("can_create_endorsement",models.BooleanField(default=False)),
                ("can_view_premium",models.BooleanField(default=False)),("can_approve",models.BooleanField(default=False)),("can_process",models.BooleanField(default=False)),("active",models.BooleanField(default=True)),
                ("organization",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="policy_access",to="tpa.tpaorganization")),
                ("policy",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="access_entries",to="tpa.policy")),
                ("user",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.CASCADE,related_name="tpa_policy_access",to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="policyaccess",constraint=models.UniqueConstraint(fields=("organization","policy","user"),name="tpa_unique_policy_access")),
        migrations.CreateModel(
            name="TransactionEvent",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("event_type",models.CharField(db_index=True,max_length=50)),("summary",models.CharField(max_length=255)),("details",models.JSONField(blank=True,default=dict)),
                ("actor",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),
                ("transaction",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="events",to="tpa.membertransaction")),
            ],
            options={"ordering":["created_at"]},
        ),
    ]
