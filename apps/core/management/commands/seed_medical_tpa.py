from django.core.management.base import BaseCommand

from apps.core.models import (
    ManagementMember,
    InsurancePartner,
    ProviderType,
    Governorate,
    City,
    MedicalSpecialty,
    NetworkProvider,
    TPAService,
    MedicalProcessStep,
    MedicalContact,
)


class Command(BaseCommand):
    help = "Seed sample Medical TPA data"

    def handle(self, *args, **options):

        self.stdout.write(
            self.style.WARNING(
                "Seeding Medical TPA sample data..."
            )
        )

        # ====================================================
        # GOVERNORATES
        # ====================================================

        muscat, _ = Governorate.objects.get_or_create(
            name_en="Muscat",
            defaults={
                "name_ar": "مسقط",
                "code": "MUSCAT",
                "is_active": True,
            }
        )

        dhofar, _ = Governorate.objects.get_or_create(
            name_en="Dhofar",
            defaults={
                "name_ar": "ظفار",
                "code": "DHOFAR",
                "is_active": True,
            }
        )

        north_batinah, _ = Governorate.objects.get_or_create(
            name_en="North Al Batinah",
            defaults={
                "name_ar": "شمال الباطنة",
                "code": "N_BATINAH",
                "is_active": True,
            }
        )

        # ====================================================
        # CITIES
        # ====================================================

        muscat_city, _ = City.objects.get_or_create(
            governorate=muscat,
            name_en="Muscat",
            defaults={
                "name_ar": "مسقط",
                "is_active": True,
            }
        )

        seeb_city, _ = City.objects.get_or_create(
            governorate=muscat,
            name_en="Seeb",
            defaults={
                "name_ar": "السيب",
                "is_active": True,
            }
        )

        bowshar_city, _ = City.objects.get_or_create(
            governorate=muscat,
            name_en="Bawshar",
            defaults={
                "name_ar": "بوشر",
                "is_active": True,
            }
        )

        salalah_city, _ = City.objects.get_or_create(
            governorate=dhofar,
            name_en="Salalah",
            defaults={
                "name_ar": "صلالة",
                "is_active": True,
            }
        )

        sohar_city, _ = City.objects.get_or_create(
            governorate=north_batinah,
            name_en="Sohar",
            defaults={
                "name_ar": "صحار",
                "is_active": True,
            }
        )

        # ====================================================
        # PROVIDER TYPES
        # ====================================================

        provider_types_data = [
            (
                "Hospital",
                "مستشفى",
                "bi-hospital"
            ),
            (
                "Clinic",
                "عيادة",
                "bi-building"
            ),
            (
                "Medical Centre",
                "مركز طبي",
                "bi-heart-pulse"
            ),
            (
                "Pharmacy",
                "صيدلية",
                "bi-capsule"
            ),
            (
                "Dental Clinic",
                "عيادة أسنان",
                "bi-emoji-smile"
            ),
            (
                "Optical Centre",
                "مركز بصريات",
                "bi-eyeglasses"
            ),
            (
                "Diagnostic Centre",
                "مركز تشخيص",
                "bi-activity"
            ),
            (
                "Laboratory",
                "مختبر",
                "bi-droplet"
            ),
            (
                "Physiotherapy Centre",
                "مركز علاج طبيعي",
                "bi-person-walking"
            ),
        ]

        provider_types = {}

        for index, (
            name_en,
            name_ar,
            icon
        ) in enumerate(
            provider_types_data,
            start=1
        ):
            obj, _ = ProviderType.objects.update_or_create(
                name_en=name_en,
                defaults={
                    "name_ar": name_ar,
                    "icon": icon,
                    "sort_order": index,
                    "is_active": True,
                }
            )

            provider_types[name_en] = obj

        # ====================================================
        # MEDICAL SPECIALTIES
        # ====================================================

        specialties_data = [
            (
                "General Medicine",
                "الطب العام",
                "bi-heart-pulse"
            ),
            (
                "Cardiology",
                "أمراض القلب",
                "bi-heart"
            ),
            (
                "Pediatrics",
                "طب الأطفال",
                "bi-person"
            ),
            (
                "Orthopedics",
                "جراحة العظام",
                "bi-person-arms-up"
            ),
            (
                "Dermatology",
                "الأمراض الجلدية",
                "bi-bandaid"
            ),
            (
                "ENT",
                "الأنف والأذن والحنجرة",
                "bi-ear"
            ),
            (
                "Ophthalmology",
                "طب العيون",
                "bi-eye"
            ),
            (
                "Gynecology",
                "أمراض النساء",
                "bi-gender-female"
            ),
            (
                "Dentistry",
                "طب الأسنان",
                "bi-emoji-smile"
            ),
            (
                "Physiotherapy",
                "العلاج الطبيعي",
                "bi-person-walking"
            ),
            (
                "Radiology",
                "الأشعة",
                "bi-activity"
            ),
            (
                "Laboratory",
                "المختبر",
                "bi-droplet"
            ),
        ]

        specialties = {}

        for index, (
            name_en,
            name_ar,
            icon
        ) in enumerate(
            specialties_data,
            start=1
        ):

            obj, _ = MedicalSpecialty.objects.update_or_create(
                name_en=name_en,
                defaults={
                    "name_ar": name_ar,
                    "icon": icon,
                    "sort_order": index,
                    "is_active": True,
                }
            )

            specialties[name_en] = obj

        # ====================================================
        # INSURANCE PARTNERS
        # ====================================================

        insurance_partners_data = [
            {
                "name_en": "Takaful Insurance Partner",
                "name_ar": "شريك تأمين تكافلي",
                "short_name": "TIP",
                "description_en":
                    "Health insurance partner providing comprehensive medical coverage.",
                "description_ar":
                    "شريك تأمين صحي يقدم تغطية طبية شاملة.",
                "sort_order": 1,
                "is_featured": True,
            },
            {
                "name_en": "Corporate Health Insurance",
                "name_ar": "التأمين الصحي للشركات",
                "short_name": "CHI",
                "description_en":
                    "Corporate healthcare coverage and medical benefits partner.",
                "description_ar":
                    "شريك في التغطية الصحية ومزايا الرعاية الطبية للشركات.",
                "sort_order": 2,
                "is_featured": True,
            },
            {
                "name_en": "Premium Medical Insurance",
                "name_ar": "التأمين الطبي المميز",
                "short_name": "PMI",
                "description_en":
                    "Premium medical insurance solutions for individuals and groups.",
                "description_ar":
                    "حلول تأمين طبي مميزة للأفراد والمجموعات.",
                "sort_order": 3,
                "is_featured": True,
            },
        ]

        insurance_partners = []

        for item in insurance_partners_data:

            partner, _ = InsurancePartner.objects.update_or_create(
                name_en=item["name_en"],
                defaults=item
            )

            insurance_partners.append(partner)

        # ====================================================
        # MANAGEMENT TEAM
        # ====================================================

        management_data = [
            {
                "name_en": "Chief Executive Officer",
                "name_ar": "الرئيس التنفيذي",
                "designation_en": "Chief Executive Officer",
                "designation_ar": "الرئيس التنفيذي",
                "department_en": "Executive Management",
                "department_ar": "الإدارة التنفيذية",
                "profile_en":
                    "Responsible for overall strategy, healthcare partnerships and operational governance.",
                "profile_ar":
                    "مسؤول عن الاستراتيجية العامة والشراكات الصحية والحوكمة التشغيلية.",
                "experience_years": 20,
                "sort_order": 1,
                "is_active": True,
            },
            {
                "name_en": "Head of Medical Operations",
                "name_ar": "رئيس العمليات الطبية",
                "designation_en": "Head of Medical Operations",
                "designation_ar": "رئيس العمليات الطبية",
                "department_en": "Medical Operations",
                "department_ar": "العمليات الطبية",
                "profile_en":
                    "Leads medical approvals, claims administration and clinical governance.",
                "profile_ar":
                    "يقود الموافقات الطبية وإدارة المطالبات والحوكمة السريرية.",
                "experience_years": 15,
                "sort_order": 2,
                "is_active": True,
            },
            {
                "name_en": "Head of Provider Relations",
                "name_ar": "رئيس علاقات مقدمي الخدمات",
                "designation_en": "Head of Provider Relations",
                "designation_ar": "رئيس علاقات مقدمي الخدمات",
                "department_en": "Provider Network",
                "department_ar": "شبكة مقدمي الخدمات",
                "profile_en":
                    "Manages healthcare provider contracting, network quality and provider engagement.",
                "profile_ar":
                    "يدير التعاقد مع مقدمي الرعاية الصحية وجودة الشبكة والعلاقات مع مقدمي الخدمات.",
                "experience_years": 12,
                "sort_order": 3,
                "is_active": True,
            },
            {
                "name_en": "Head of Claims",
                "name_ar": "رئيس المطالبات",
                "designation_en": "Head of Medical Claims",
                "designation_ar": "رئيس المطالبات الطبية",
                "department_en": "Claims",
                "department_ar": "المطالبات",
                "profile_en":
                    "Responsible for claim assessment, adjudication quality and settlement operations.",
                "profile_ar":
                    "مسؤول عن تقييم المطالبات وجودة التسوية وعمليات الدفع.",
                "experience_years": 14,
                "sort_order": 4,
                "is_active": True,
            },
        ]

        for item in management_data:

            ManagementMember.objects.update_or_create(
                name_en=item["name_en"],
                defaults=item
            )

        # ====================================================
        # TPA SERVICES
        # ====================================================

        tpa_services_data = [
            {
                "title_en": "Medical Claims Management",
                "title_ar": "إدارة المطالبات الطبية",
                "short_description_en":
                    "End-to-end medical claim validation, adjudication and settlement support.",
                "short_description_ar":
                    "إدارة متكاملة للتحقق من المطالبات الطبية وتسويتها.",
                "icon": "bi-file-medical",
                "sort_order": 1,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "Pre-Authorization",
                "title_ar": "الموافقة المسبقة",
                "short_description_en":
                    "Fast and controlled approval workflows for planned medical treatment.",
                "short_description_ar":
                    "إجراءات سريعة ومنظمة للموافقة على العلاج الطبي المخطط.",
                "icon": "bi-clipboard2-check",
                "sort_order": 2,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "Provider Network Management",
                "title_ar": "إدارة شبكة مقدمي الخدمات",
                "short_description_en":
                    "Healthcare provider onboarding, contracting, credentialing and network monitoring.",
                "short_description_ar":
                    "إدارة تسجيل واعتماد وتعاقد ومراقبة مقدمي الرعاية الصحية.",
                "icon": "bi-hospital",
                "sort_order": 3,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "Member Eligibility",
                "title_ar": "أهلية الأعضاء",
                "short_description_en":
                    "Real-time member eligibility and benefit verification.",
                "short_description_ar":
                    "التحقق من أهلية الأعضاء والمزايا التأمينية.",
                "icon": "bi-person-check",
                "sort_order": 4,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "Medical Case Management",
                "title_ar": "إدارة الحالات الطبية",
                "short_description_en":
                    "Clinical coordination and monitoring for complex medical cases.",
                "short_description_ar":
                    "التنسيق السريري ومراقبة الحالات الطبية المعقدة.",
                "icon": "bi-heart-pulse",
                "sort_order": 5,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "Fraud, Waste & Abuse Control",
                "title_ar": "مكافحة الاحتيال والهدر وإساءة الاستخدام",
                "short_description_en":
                    "Analytics and controls for detecting unusual claim and provider activity.",
                "short_description_ar":
                    "تحليلات وضوابط للكشف عن الأنشطة غير المعتادة في المطالبات.",
                "icon": "bi-shield-check",
                "sort_order": 6,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "Reimbursement Management",
                "title_ar": "إدارة الاسترداد",
                "short_description_en":
                    "Member reimbursement review and processing with structured documentation.",
                "short_description_ar":
                    "مراجعة ومعالجة طلبات استرداد الأعضاء بطريقة منظمة.",
                "icon": "bi-receipt",
                "sort_order": 7,
                "is_featured": True,
                "is_active": True,
            },
            {
                "title_en": "24/7 Member Support",
                "title_ar": "دعم الأعضاء على مدار الساعة",
                "short_description_en":
                    "Support for members requiring assistance with network access and medical services.",
                "short_description_ar":
                    "دعم الأعضاء في الوصول إلى الشبكة والخدمات الطبية.",
                "icon": "bi-headset",
                "sort_order": 8,
                "is_featured": True,
                "is_active": True,
            },
        ]

        for item in tpa_services_data:

            TPAService.objects.update_or_create(
                title_en=item["title_en"],
                defaults=item
            )

        # ====================================================
        # MEDICAL PROCESS
        # ====================================================

        medical_steps = [
            {
                "process_type": "PREAUTH",
                "step_number": 1,
                "title_en": "Member Eligibility Verification",
                "title_ar": "التحقق من أهلية العضو",
                "description_en":
                    "The healthcare provider verifies the member's active insurance coverage and available benefits.",
                "description_ar":
                    "يقوم مقدم الخدمة بالتحقق من التغطية التأمينية الفعالة ومزايا العضو.",
                "icon": "bi-person-check",
                "is_active": True,
            },
            {
                "process_type": "PREAUTH",
                "step_number": 2,
                "title_en": "Medical Request Submission",
                "title_ar": "تقديم الطلب الطبي",
                "description_en":
                    "The provider submits diagnosis, treatment details and required clinical documents.",
                "description_ar":
                    "يقوم مقدم الخدمة بتقديم التشخيص وتفاصيل العلاج والمستندات الطبية المطلوبة.",
                "icon": "bi-send",
                "is_active": True,
            },
            {
                "process_type": "PREAUTH",
                "step_number": 3,
                "title_en": "Medical Review",
                "title_ar": "المراجعة الطبية",
                "description_en":
                    "The TPA medical team reviews the request against policy benefits and medical necessity.",
                "description_ar":
                    "يقوم الفريق الطبي بمراجعة الطلب وفقاً للمزايا التأمينية والضرورة الطبية.",
                "icon": "bi-clipboard2-pulse",
                "is_active": True,
            },
            {
                "process_type": "PREAUTH",
                "step_number": 4,
                "title_en": "Authorization Decision",
                "title_ar": "قرار الموافقة",
                "description_en":
                    "Approval, partial approval or additional information request is communicated to the provider.",
                "description_ar":
                    "يتم إرسال قرار الموافقة أو الموافقة الجزئية أو طلب معلومات إضافية إلى مقدم الخدمة.",
                "icon": "bi-check2-circle",
                "is_active": True,
            },
            {
                "process_type": "CLAIM",
                "step_number": 1,
                "title_en": "Claim Submission",
                "title_ar": "تقديم المطالبة",
                "description_en":
                    "The healthcare provider submits the medical claim with required supporting documents.",
                "description_ar":
                    "يقوم مقدم الخدمة بتقديم المطالبة الطبية والمستندات المطلوبة.",
                "icon": "bi-file-medical",
                "is_active": True,
            },
            {
                "process_type": "CLAIM",
                "step_number": 2,
                "title_en": "Claim Validation",
                "title_ar": "التحقق من المطالبة",
                "description_en":
                    "Eligibility, coding, benefit limits and required documentation are validated.",
                "description_ar":
                    "يتم التحقق من الأهلية والترميز وحدود المزايا والمستندات المطلوبة.",
                "icon": "bi-search",
                "is_active": True,
            },
            {
                "process_type": "CLAIM",
                "step_number": 3,
                "title_en": "Claim Adjudication",
                "title_ar": "تسوية المطالبة",
                "description_en":
                    "The claim is assessed according to policy terms, medical rules and agreed provider tariffs.",
                "description_ar":
                    "يتم تقييم المطالبة وفقاً لشروط الوثيقة والقواعد الطبية والتعرفة المتفق عليها.",
                "icon": "bi-calculator",
                "is_active": True,
            },
            {
                "process_type": "CLAIM",
                "step_number": 4,
                "title_en": "Settlement",
                "title_ar": "التسوية",
                "description_en":
                    "Approved amounts are finalized for provider settlement or member reimbursement.",
                "description_ar":
                    "يتم اعتماد المبالغ النهائية لتسوية مقدم الخدمة أو استرداد العضو.",
                "icon": "bi-cash-coin",
                "is_active": True,
            },
        ]

        for item in medical_steps:

            MedicalProcessStep.objects.update_or_create(
                process_type=item["process_type"],
                step_number=item["step_number"],
                defaults=item
            )

        # ====================================================
        # CONTACTS
        # ====================================================

        contacts_data = [
            {
                "contact_type": "CUSTOMER",
                "title_en": "Member Support",
                "title_ar": "دعم الأعضاء",
                "phone": "+968 2400 0000",
                "whatsapp": "96824000000",
                "email": "members@example.com",
                "description_en":
                    "General assistance for members and policy services.",
                "description_ar":
                    "الدعم العام للأعضاء وخدمات الوثائق.",
                "icon": "bi-headset",
                "is_24_hours": True,
                "sort_order": 1,
                "is_active": True,
            },
            {
                "contact_type": "PREAUTH",
                "title_en": "Pre-Authorization",
                "title_ar": "الموافقة المسبقة",
                "phone": "+968 2400 0001",
                "email": "preauth@example.com",
                "description_en":
                    "Support for medical approvals and authorization requests.",
                "description_ar":
                    "الدعم المتعلق بالموافقات الطبية.",
                "icon": "bi-clipboard2-check",
                "is_24_hours": True,
                "sort_order": 2,
                "is_active": True,
            },
            {
                "contact_type": "CLAIM",
                "title_en": "Medical Claims",
                "title_ar": "المطالبات الطبية",
                "phone": "+968 2400 0002",
                "email": "claims@example.com",
                "description_en":
                    "Support for claim submissions, status and reimbursement.",
                "description_ar":
                    "الدعم الخاص بالمطالبات وحالتها والاسترداد.",
                "icon": "bi-file-medical",
                "sort_order": 3,
                "is_active": True,
            },
            {
                "contact_type": "PROVIDER",
                "title_en": "Provider Relations",
                "title_ar": "علاقات مقدمي الخدمات",
                "phone": "+968 2400 0003",
                "email": "providers@example.com",
                "description_en":
                    "Support for healthcare provider onboarding, contracts and network matters.",
                "description_ar":
                    "دعم مقدمي الخدمات فيما يتعلق بالتسجيل والتعاقد والشبكة.",
                "icon": "bi-hospital",
                "sort_order": 4,
                "is_active": True,
            },
            {
                "contact_type": "EMERGENCY",
                "title_en": "Emergency Assistance",
                "title_ar": "المساعدة الطارئة",
                "phone": "+968 2400 0004",
                "description_en":
                    "Emergency assistance and provider guidance.",
                "description_ar":
                    "المساعدة في الحالات الطارئة وإرشادات مقدمي الخدمات.",
                "icon": "bi-life-preserver",
                "is_24_hours": True,
                "sort_order": 5,
                "is_active": True,
            },
        ]

        for item in contacts_data:

            MedicalContact.objects.update_or_create(
                contact_type=item["contact_type"],
                title_en=item["title_en"],
                defaults=item
            )

        # ====================================================
        # NETWORK PROVIDERS
        # ====================================================

        network_provider_data = [
            {
                "provider_code": "OM-MCT-001",
                "name_en": "Muscat Medical Hospital",
                "name_ar": "مستشفى مسقط الطبي",
                "provider_type": provider_types["Hospital"],
                "address_en": "Al Khuwair, Muscat, Oman",
                "address_ar": "الخوير، مسقط، سلطنة عمان",
                "governorate": muscat,
                "city": muscat_city,
                "area_en": "Al Khuwair",
                "area_ar": "الخوير",
                "phone": "+968 2401 1000",
                "emergency_phone": "+968 2401 1111",
                "latitude": 23.5945,
                "longitude": 58.4207,
                "working_hours_en": "24 Hours",
                "working_hours_ar": "24 ساعة",
                "is_24_hours": True,
                "has_emergency": True,
                "has_pharmacy": True,
                "has_dental": False,
                "has_optical": False,
                "is_featured": True,
                "sort_order": 1,
                "is_active": True,
            },
            {
                "provider_code": "OM-MCT-002",
                "name_en": "Bawshar Specialist Clinic",
                "name_ar": "عيادة بوشر التخصصية",
                "provider_type": provider_types["Clinic"],
                "address_en": "Bawshar, Muscat, Oman",
                "address_ar": "بوشر، مسقط، سلطنة عمان",
                "governorate": muscat,
                "city": bowshar_city,
                "area_en": "Bawshar",
                "area_ar": "بوشر",
                "phone": "+968 2402 2000",
                "latitude": 23.5657,
                "longitude": 58.4059,
                "working_hours_en": "8:00 AM - 10:00 PM",
                "working_hours_ar": "8 صباحاً - 10 مساءً",
                "is_24_hours": False,
                "has_emergency": False,
                "has_pharmacy": False,
                "has_dental": True,
                "has_optical": False,
                "is_featured": True,
                "sort_order": 2,
                "is_active": True,
            },
            {
                "provider_code": "OM-SEEB-001",
                "name_en": "Seeb Family Medical Centre",
                "name_ar": "مركز السيب الطبي العائلي",
                "provider_type": provider_types["Medical Centre"],
                "address_en": "Al Hail, Seeb, Oman",
                "address_ar": "الحيل، السيب، سلطنة عمان",
                "governorate": muscat,
                "city": seeb_city,
                "area_en": "Al Hail",
                "area_ar": "الحيل",
                "phone": "+968 2403 3000",
                "latitude": 23.6314,
                "longitude": 58.1881,
                "working_hours_en": "7:00 AM - 11:00 PM",
                "working_hours_ar": "7 صباحاً - 11 مساءً",
                "is_24_hours": False,
                "has_emergency": False,
                "has_pharmacy": True,
                "has_dental": True,
                "has_optical": False,
                "is_featured": True,
                "sort_order": 3,
                "is_active": True,
            },
            {
                "provider_code": "OM-SLL-001",
                "name_en": "Salalah Medical Hospital",
                "name_ar": "مستشفى صلالة الطبي",
                "provider_type": provider_types["Hospital"],
                "address_en": "Salalah, Dhofar, Oman",
                "address_ar": "صلالة، ظفار، سلطنة عمان",
                "governorate": dhofar,
                "city": salalah_city,
                "area_en": "Central Salalah",
                "area_ar": "وسط صلالة",
                "phone": "+968 2404 4000",
                "emergency_phone": "+968 2404 4111",
                "latitude": 17.0194,
                "longitude": 54.0897,
                "working_hours_en": "24 Hours",
                "working_hours_ar": "24 ساعة",
                "is_24_hours": True,
                "has_emergency": True,
                "has_pharmacy": True,
                "has_dental": True,
                "has_optical": True,
                "is_featured": True,
                "sort_order": 4,
                "is_active": True,
            },
            {
                "provider_code": "OM-SOH-001",
                "name_en": "Sohar Healthcare Centre",
                "name_ar": "مركز صحار للرعاية الصحية",
                "provider_type": provider_types["Medical Centre"],
                "address_en": "Sohar, North Al Batinah, Oman",
                "address_ar": "صحار، شمال الباطنة، سلطنة عمان",
                "governorate": north_batinah,
                "city": sohar_city,
                "area_en": "Sohar",
                "area_ar": "صحار",
                "phone": "+968 2405 5000",
                "latitude": 24.3470,
                "longitude": 56.7094,
                "working_hours_en": "8:00 AM - 11:00 PM",
                "working_hours_ar": "8 صباحاً - 11 مساءً",
                "is_24_hours": False,
                "has_emergency": False,
                "has_pharmacy": True,
                "has_dental": False,
                "has_optical": False,
                "is_featured": True,
                "sort_order": 5,
                "is_active": True,
            },
            {
                "provider_code": "OM-MCT-PH01",
                "name_en": "Green Care Pharmacy",
                "name_ar": "صيدلية جرين كير",
                "provider_type": provider_types["Pharmacy"],
                "address_en": "Qurum, Muscat, Oman",
                "address_ar": "القرم، مسقط، سلطنة عمان",
                "governorate": muscat,
                "city": muscat_city,
                "area_en": "Qurum",
                "area_ar": "القرم",
                "phone": "+968 2406 6000",
                "latitude": 23.6159,
                "longitude": 58.5031,
                "working_hours_en": "24 Hours",
                "working_hours_ar": "24 ساعة",
                "is_24_hours": True,
                "has_pharmacy": True,
                "is_featured": True,
                "sort_order": 6,
                "is_active": True,
            },
        ]

        created_providers = {}

        for item in network_provider_data:

            provider, _ = NetworkProvider.objects.update_or_create(
                provider_code=item["provider_code"],
                defaults=item
            )

            created_providers[item["provider_code"]] = provider

            provider.insurance_partners.set(
                insurance_partners
            )

        # ====================================================
        # PROVIDER SPECIALTIES
        # ====================================================

        created_providers["OM-MCT-001"].specialties.set([
            specialties["General Medicine"],
            specialties["Cardiology"],
            specialties["Pediatrics"],
            specialties["Orthopedics"],
            specialties["Radiology"],
            specialties["Laboratory"],
        ])

        created_providers["OM-MCT-002"].specialties.set([
            specialties["Dermatology"],
            specialties["ENT"],
            specialties["Dentistry"],
        ])

        created_providers["OM-SEEB-001"].specialties.set([
            specialties["General Medicine"],
            specialties["Pediatrics"],
            specialties["Dentistry"],
        ])

        created_providers["OM-SLL-001"].specialties.set([
            specialties["General Medicine"],
            specialties["Cardiology"],
            specialties["Pediatrics"],
            specialties["Orthopedics"],
            specialties["Ophthalmology"],
            specialties["Radiology"],
            specialties["Laboratory"],
        ])

        created_providers["OM-SOH-001"].specialties.set([
            specialties["General Medicine"],
            specialties["Pediatrics"],
            specialties["Physiotherapy"],
        ])

        # ====================================================
        # DONE
        # ====================================================

        self.stdout.write(
            self.style.SUCCESS(
                "Medical TPA sample data seeded successfully."
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Network Providers: {NetworkProvider.objects.count()}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Insurance Partners: {InsurancePartner.objects.count()}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Medical Specialties: {MedicalSpecialty.objects.count()}"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"TPA Services: {TPAService.objects.count()}"
            )
        )