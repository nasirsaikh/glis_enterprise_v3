from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import BenefitPlan, Member, MemberTransaction, Policy, TPAOrganization
from .services.pricing import calculate_member_premium

class TPACoreTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username="tpa",password="x")
        self.sponsor=TPAOrganization.objects.create(code="SP1",name_en="Sponsor",organization_type="CORPORATE")
        self.insurer=TPAOrganization.objects.create(code="IN1",name_en="Insurer",organization_type="INSURER")
        self.policy=Policy.objects.create(sponsor=self.sponsor,insurance_company=self.insurer,policy_number="POL-1",start_date=date(2026,1,1),expiry_date=date(2026,12,31),status="active")
        self.plan=BenefitPlan.objects.create(policy=self.policy,code="GOLD",name="Gold",annual_premium="365.000",premium_configuration={"method":"PRORATA","denominator":365})
    def test_prorata_is_decimal_and_snapshotted(self):
        amount,snapshot=calculate_member_premium(self.policy,self.plan,date(2026,7,1))
        self.assertEqual(str(amount),"184.000"); self.assertEqual(snapshot["method"],"PRORATA")
    def test_transaction_reference_generated(self):
        tx=MemberTransaction.objects.create(sponsor=self.sponsor,insurer=self.insurer,policy=self.policy,transaction_type="MEMBER_ADD",effective_date=date(2026,7,1),requester=self.user,requester_organization=self.sponsor)
        self.assertTrue(tx.reference.startswith("TPA-END-2026-"))
