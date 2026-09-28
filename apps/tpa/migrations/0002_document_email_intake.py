from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ai","0003_tpa_document_intelligence"),
        ("tickets","0007_category_allowed_groups"),
        ("tpa","0001_initial"),
    ]
    operations=[
        migrations.CreateModel(
            name="SourceDocument",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("original_name",models.CharField(max_length=255)),("document_kind",models.CharField(blank=True,max_length=50)),
                ("extraction_method",models.CharField(blank=True,max_length=50)),("processed",models.BooleanField(default=False)),
                ("processing_error",models.TextField(blank=True)),("extracted_payload",models.JSONField(blank=True,default=dict)),
                ("extraction_confidence",models.DecimalField(blank=True,decimal_places=2,max_digits=5,null=True)),
                ("source_hash",models.CharField(blank=True,db_index=True,max_length=64)),
                ("ai_profile",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to="ai.aiextractionprofile")),
                ("ticket_attachment",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="tpa_source_documents",to="tickets.ticketattachment")),
                ("transaction",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="source_documents",to="tpa.membertransaction")),
                ("uploaded_by",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="InboundEmail",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("provider",models.CharField(blank=True,max_length=40)),("provider_message_id",models.CharField(max_length=255)),
                ("sender",models.EmailField(max_length=254)),("recipient",models.EmailField(max_length=254)),("subject",models.CharField(blank=True,max_length=500)),
                ("received_at",models.DateTimeField()),("body_text",models.TextField(blank=True)),("attachment_metadata",models.JSONField(blank=True,default=list)),
                ("processing_state",models.CharField(choices=[("RECEIVED","Received"),("PROCESSING","Processing"),("REVIEW","Needs review"),("PROCESSED","Processed"),("FAILED","Failed")],db_index=True,default="RECEIVED",max_length=20)),
                ("processing_error",models.TextField(blank=True)),
                ("transaction",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="source_emails",to="tpa.membertransaction")),
            ],
        ),
        migrations.AddConstraint(model_name="inboundemail",constraint=models.UniqueConstraint(fields=("provider","provider_message_id"),name="tpa_unique_inbound_email")),
    ]
