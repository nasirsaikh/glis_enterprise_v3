"""Keep historical identifiers and attach every domain request to one Ticket."""
import re
from datetime import timedelta
from django.db import migrations, models
import django.db.models.deletion

WORKFLOWS = [('GLIS','Service Tickets','service',''),('POL','Policy Enrollment','policy','NEW_POLICY_ENROLLMENT'),('ADD','Member Addition','endorsement','MEMBER_ADD'),('DEL','Member Deletion','endorsement','MEMBER_DELETE'),('TRM','Member Termination','endorsement','MEMBER_TERMINATE'),('CHG','Member Demographic Change','endorsement','MEMBER_UPDATE'),('SUS','Member Suspension','endorsement','MEMBER_SUSPEND'),('REA','Member Reactivation','endorsement','MEMBER_REACTIVATE'),('CAN','Policy Cancellation','endorsement','POLICY_CANCEL'),('END','General Endorsement','endorsement','GENERAL_ENDORSEMENT'),('CLM','Claim Request','claim','CLAIM')]

def backfill(apps,schema_editor):
    alias=schema_editor.connection.alias
    Project,Product,Category,Ticket,Sequence,Participant,Event,SLA=[apps.get_model('tickets',m) for m in ['Project','Product','Category','Ticket','TicketSequence','TicketOrganization','TicketEvent','SLAPolicy']]
    Policy,Tx=apps.get_model('tpa','Policy'),apps.get_model('tpa','MemberTransaction')
    legacy=Project.objects.using(alias).filter(code='TPA').first()
    legacy_codes={'NEW_POLICY_ENROLLMENT':'new-policy-enrollment','MEMBER_ADD':'member-addition','MEMBER_DELETE':'member-deletion','MEMBER_TERMINATE':'member-termination','MEMBER_UPDATE':'member-demographic-change','MEMBER_SUSPEND':'member-suspension','MEMBER_REACTIVATE':'member-reactivation','POLICY_CANCEL':'policy-cancellation'}
    mapping={}
    for code,name,kind,handler in WORKFLOWS:
        project,_=Project.objects.using(alias).get_or_create(code=code,defaults={'name_en':name})
        project.request_type,project.workflow_type=kind,handler
        project.save(using=alias,update_fields=['request_type','workflow_type'])
        product,_=Product.objects.using(alias).get_or_create(project=project,code='MEDICAL',defaults={'name_en':'Medical'})
        product.policy_types=[{'code':'GROUP_MEDICAL','name':'Group Medical'},{'code':'INDIVIDUAL_MEDICAL','name':'Individual Medical'}]
        product.save(using=alias,update_fields=['policy_types'])
        category,_=Category.objects.using(alias).get_or_create(product=product,code=handler or 'SERVICE',defaults={'name_en':name})
        old=Category.objects.using(alias).filter(product__project=legacy,code=legacy_codes.get(handler,'')).first() if legacy else None
        if old:
            for field in Category._meta.fields:
                if field.name not in {'id','created_at','updated_at','product','code'}:setattr(category,field.attname,getattr(old,field.attname))
            category.save(using=alias)
            category.allowed_groups.set(old.allowed_groups.all());category.default_groups.set(old.default_groups.all())
            project.groups.set(legacy.groups.all());project.members.set(legacy.members.all())
            for old_sla in SLA.objects.using(alias).filter(category=old):
                values={f.attname:getattr(old_sla,f.attname) for f in SLA._meta.fields if f.name not in {'id','created_at','updated_at','project','category'}}
                SLA.objects.using(alias).get_or_create(project=project,category=category,priority=old_sla.priority,defaults=values)
        SLA.objects.using(alias).get_or_create(project=project,category=None,priority='medium',defaults={'name':f'{code} workflow SLA','resolution_minutes':2400})
        if handler:mapping[handler]=project
    for reference in Ticket.objects.using(alias).values_list('reference',flat=True).iterator():
        match=re.fullmatch(r'(.+)-(\d{4})-(\d+)',reference or '')
        if match:
            prefix,year,value=match.groups();seq,_=Sequence.objects.using(alias).get_or_create(prefix=prefix,year=int(year))
            if seq.value<int(value):seq.value=int(value);seq.save(using=alias,update_fields=['value'])
    for policy in Policy.objects.using(alias).all().iterator():
        if policy.tpa_organization_id:policy.workflow_organizations.add(policy.tpa_organization_id)
        product=Product.objects.using(alias).filter(project__code='POL',code=policy.product_type).first()
        if product:Policy.objects.using(alias).filter(pk=policy.pk).update(product_id=product.pk)
    for tx in Tx.objects.using(alias).select_related('policy','ticket').all().iterator():
        project=mapping.get(tx.transaction_type,mapping['GENERAL_ENDORSEMENT'])
        product,_=Product.objects.using(alias).get_or_create(project=project,code=tx.policy.product_type[:30],defaults={'name_en':tx.policy.product_type})
        category,_=Category.objects.using(alias).get_or_create(product=product,code=tx.transaction_type,defaults={'name_en':project.name_en})
        if tx.ticket_id:
            ticket=tx.ticket;ticket.organization_id=tx.organization_id;ticket.policy_id=tx.policy_id
            ticket.project_id,ticket.product_id,ticket.category_id=project.pk,product.pk,category.pk
            ticket.save(using=alias,update_fields=['organization','policy','project','product','category'])
        else:
            seq,_=Sequence.objects.using(alias).get_or_create(prefix=project.code,year=tx.created_at.year)
            seq.value+=1;seq.save(using=alias,update_fields=['value'])
            ticket=Ticket.objects.using(alias).create(reference=f'{project.code}-{tx.created_at.year}-{seq.value:06d}',subject=f'{project.name_en} · {tx.policy.policy_number}',description=tx.remarks or f'Migrated {tx.reference}',requester_id=tx.requester_id,project=project,product=product,category=category,organization_id=tx.organization_id,policy_id=tx.policy_id,is_sensitive=True,status='closed' if tx.status in {'processed','completed','cancelled','rejected'} else 'new',resolved_at=tx.processed_at,closed_at=tx.processed_at)
            Ticket.objects.using(alias).filter(pk=ticket.pk).update(created_at=tx.created_at);ticket.created_at=tx.created_at
            Tx.objects.using(alias).filter(pk=tx.pk).update(ticket_id=ticket.pk)
        if not ticket.sla_policy_id:
            sla=SLA.objects.using(alias).filter(category=category,priority=ticket.priority,is_active=True).first() or SLA.objects.using(alias).filter(project=project,category=None,priority='medium').first()
            Ticket.objects.using(alias).filter(pk=ticket.pk).update(sla_policy_id=sla.pk,first_response_due_at=ticket.created_at+timedelta(minutes=sla.first_response_minutes),resolution_due_at=ticket.created_at+timedelta(minutes=sla.resolution_minutes))
        roles=[(tx.organization_id,'owner',True),(tx.insurer_id,'insurer',False),(tx.requester_organization_id,'requester',False)]+[(i,'processing',False) for i in tx.policy.workflow_organizations.values_list('pk',flat=True)]
        for org,role,primary in roles:Participant.objects.using(alias).get_or_create(ticket=ticket,organization_id=org,relationship_type=role,defaults={'is_primary':primary})
        Event.objects.using(alias).create(ticket=ticket,actor_id=None,event_type='workflow_migrated',summary='Business request consolidated into ticket workflow.',details={'transaction_id':tx.pk,'legacy_reference':tx.reference})
    Email=apps.get_model('tpa','InboundEmail')
    for email in Email.objects.using(alias).filter(transaction__isnull=False).select_related('transaction').iterator():
        Email.objects.using(alias).filter(pk=email.pk).update(ticket_id=email.transaction.ticket_id)
    if Tx.objects.using(alias).filter(ticket__isnull=True).exists():raise RuntimeError('Missing parent Ticket after migration.')

def reverse_routes(apps,schema_editor):
    Policy=apps.get_model('tpa','Policy')
    for policy in Policy.objects.using(schema_editor.connection.alias).all().iterator():
        first=policy.workflow_organizations.order_by('pk').first()
        if first:Policy.objects.using(schema_editor.connection.alias).filter(pk=policy.pk).update(tpa_organization_id=first.pk)

class Migration(migrations.Migration):
    dependencies=[('tpa','0015_alter_member_organization_and_more')]
    operations=[migrations.RunPython(backfill,reverse_routes),migrations.RemoveField(model_name='policy',name='tpa_organization'),migrations.AlterField(model_name='membertransaction',name='ticket',field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='tpa_transaction',to='tickets.ticket'))]
