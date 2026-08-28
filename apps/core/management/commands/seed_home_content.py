from django.core.management.base import BaseCommand

from apps.core.models import (
    HeroSection,
    HomeSection,
    ServiceCategory,
    Service,
    Feature,
    Statistic,
    ProcessStep,
    Testimonial,
    FAQ,
    Partner,
)


class Command(BaseCommand):
    help = "Seed GLIS public home page content"

    def handle(self, *args, **options):
        self.stdout.write("Seeding GLIS home content...")

        self.seed_hero()
        self.seed_sections()
        self.seed_services()
        self.seed_features()
        self.seed_statistics()
        self.seed_process()
        self.seed_testimonials()
        self.seed_faqs()
        self.seed_partners()

        self.stdout.write(
            self.style.SUCCESS("GLIS home content seeded successfully.")
        )

    def seed_hero(self):
        hero = HeroSection.load()

        hero.eyebrow_en = "Insurance service orchestration"
        hero.eyebrow_ar = "تنسيق خدمات التأمين"

        hero.title_en = "One clear path through every insurance request"
        hero.title_ar = "مسار واضح لكل طلب تأميني"

        hero.subtitle_en = (
            "Submit, track and resolve insurance service requests through "
            "one secure digital platform connecting customers, providers "
            "and insurance teams."
        )

        hero.subtitle_ar = (
            "قدّم طلبات خدمات التأمين وتابعها وأنجزها من خلال منصة رقمية "
            "آمنة تربط العملاء ومقدمي الخدمة وفرق التأمين."
        )

        hero.primary_cta_en = "Submit a request"
        hero.primary_cta_ar = "تقديم طلب"

        hero.secondary_cta_en = "Explore services"
        hero.secondary_cta_ar = "استكشف الخدمات"

        hero.secondary_cta_url = "#services"

        hero.save()

    def seed_sections(self):
        sections = [
            {
                "section": "about",
                "eyebrow_en": "About GLIS",
                "eyebrow_ar": "عن جرين لاين",
                "title_en": "Insurance services designed around clarity and convenience",
                "title_ar": "خدمات تأمين مصممة للوضوح والسهولة",
                "content_en": (
                    "Greenline Insurance Services provides a unified digital "
                    "experience for submitting, tracking and managing insurance "
                    "service requests. Our platform helps customers, providers "
                    "and internal teams collaborate efficiently."
                ),
                "content_ar": (
                    "توفر جرين لاين لخدمات التأمين تجربة رقمية موحدة لتقديم "
                    "طلبات خدمات التأمين ومتابعتها وإدارتها، بما يساعد العملاء "
                    "ومقدمي الخدمة والفرق الداخلية على التعاون بكفاءة."
                ),
            },
            {
                "section": "services",
                "eyebrow_en": "Our Services",
                "eyebrow_ar": "خدماتنا",
                "title_en": "Insurance services in one place",
                "title_ar": "خدمات التأمين في مكان واحد",
                "content_en": (
                    "Access key insurance services through a secure and "
                    "structured digital workflow."
                ),
                "content_ar": (
                    "استفد من خدمات التأمين الرئيسية من خلال مسار رقمي آمن ومنظم."
                ),
            },
            {
                "section": "features",
                "eyebrow_en": "Why GLIS",
                "eyebrow_ar": "لماذا جرين لاين",
                "title_en": "A simpler way to manage insurance requests",
                "title_ar": "طريقة أبسط لإدارة طلبات التأمين",
                "content_en": (
                    "Built to improve visibility, communication and service "
                    "delivery across the insurance journey."
                ),
                "content_ar": (
                    "منصة مصممة لتحسين الرؤية والتواصل وجودة تقديم الخدمة "
                    "عبر رحلة التأمين."
                ),
            },
            {
                "section": "process",
                "eyebrow_en": "How It Works",
                "eyebrow_ar": "كيف تعمل الخدمة",
                "title_en": "From request to resolution",
                "title_ar": "من تقديم الطلب حتى الإنجاز",
                "content_en": (
                    "A clear workflow keeps every request organized and visible."
                ),
                "content_ar": (
                    "مسار عمل واضح يحافظ على تنظيم كل طلب وإمكانية متابعته."
                ),
            },
            {
                "section": "testimonials",
                "eyebrow_en": "Customer Experience",
                "eyebrow_ar": "تجربة العملاء",
                "title_en": "What our customers say",
                "title_ar": "ماذا يقول عملاؤنا",
                "content_en": (
                    "Feedback from customers and service partners using GLIS."
                ),
                "content_ar": (
                    "آراء العملاء وشركاء الخدمة الذين يستخدمون جرين لاين."
                ),
            },
            {
                "section": "faq",
                "eyebrow_en": "Frequently Asked Questions",
                "eyebrow_ar": "الأسئلة الشائعة",
                "title_en": "How can we help?",
                "title_ar": "كيف يمكننا مساعدتك؟",
                "content_en": (
                    "Find answers to common questions about using the platform."
                ),
                "content_ar": (
                    "تعرّف على إجابات أكثر الأسئلة شيوعاً حول استخدام المنصة."
                ),
            },
            {
                "section": "cta",
                "eyebrow_en": "Need Assistance?",
                "eyebrow_ar": "هل تحتاج إلى مساعدة؟",
                "title_en": "Start your insurance service request today",
                "title_ar": "ابدأ طلب خدمة التأمين اليوم",
                "content_en": (
                    "Submit your request securely and track its progress online."
                ),
                "content_ar": (
                    "قدّم طلبك بأمان وتابع حالته إلكترونياً."
                ),
                "button_text_en": "Create request",
                "button_text_ar": "تقديم طلب",
                "button_url": "/portal/tickets/create/1/",
            },
        ]

        for data in sections:
            HomeSection.objects.update_or_create(
                section=data["section"],
                defaults={
                    **data,
                    "is_active": True,
                },
            )

    def seed_services(self):
        motor, _ = ServiceCategory.objects.update_or_create(
            name_en="Motor Insurance",
            defaults={
                "name_ar": "تأمين المركبات",
                "icon": "bi-car-front",
                "order": 1,
                "is_active": True,
            },
        )

        claims, _ = ServiceCategory.objects.update_or_create(
            name_en="Claims Services",
            defaults={
                "name_ar": "خدمات المطالبات",
                "icon": "bi-clipboard2-check",
                "order": 2,
                "is_active": True,
            },
        )

        support, _ = ServiceCategory.objects.update_or_create(
            name_en="Customer Support",
            defaults={
                "name_ar": "دعم العملاء",
                "icon": "bi-headset",
                "order": 3,
                "is_active": True,
            },
        )

        services = [
            {
                "category": motor,
                "title_en": "Motor Insurance Services",
                "title_ar": "خدمات تأمين المركبات",
                "summary_en": (
                    "Submit and manage motor-related insurance service requests."
                ),
                "summary_ar": (
                    "قدّم وأدر طلبات خدمات التأمين المتعلقة بالمركبات."
                ),
                "icon": "bi-car-front",
                "link": "/portal/tickets/create/1/",
                "button_text_en": "Start request",
                "button_text_ar": "ابدأ الطلب",
                "order": 1,
            },
            {
                "category": claims,
                "title_en": "Claims Support",
                "title_ar": "دعم المطالبات",
                "summary_en": (
                    "Raise claim-related requests and follow their progress."
                ),
                "summary_ar": (
                    "قدّم طلبات متعلقة بالمطالبات وتابع تقدمها."
                ),
                "icon": "bi-clipboard2-check",
                "link": "/portal/tickets/create/1/",
                "button_text_en": "Submit request",
                "button_text_ar": "تقديم طلب",
                "order": 2,
            },
            {
                "category": support,
                "title_en": "Customer Assistance",
                "title_ar": "مساعدة العملاء",
                "summary_en": (
                    "Get help with policies, requests, documents and service enquiries."
                ),
                "summary_ar": (
                    "احصل على المساعدة بشأن الوثائق والطلبات والمستندات والاستفسارات."
                ),
                "icon": "bi-headset",
                "link": "/portal/tickets/create/1/",
                "button_text_en": "Get support",
                "button_text_ar": "احصل على الدعم",
                "order": 3,
            },
        ]

        for data in services:
            Service.objects.update_or_create(
                title_en=data["title_en"],
                defaults={
                    **data,
                    "is_featured": True,
                    "is_active": True,
                },
            )

    def seed_features(self):
        items = [
            {
                "title_en": "Secure by design",
                "title_ar": "أمان مدمج",
                "description_en": (
                    "Secure access and controlled workflows help protect "
                    "customer and insurance information."
                ),
                "description_ar": (
                    "يساعد الوصول الآمن ومسارات العمل المنظمة على حماية "
                    "بيانات العملاء والتأمين."
                ),
                "icon": "bi-shield-lock",
                "order": 1,
            },
            {
                "title_en": "Real-time visibility",
                "title_ar": "متابعة واضحة",
                "description_en": (
                    "Track the status and progress of your requests from one place."
                ),
                "description_ar": (
                    "تابع حالة طلباتك وتقدمها من مكان واحد."
                ),
                "icon": "bi-eye",
                "order": 2,
            },
            {
                "title_en": "Centralized communication",
                "title_ar": "تواصل مركزي",
                "description_en": (
                    "Keep service discussions, documents and updates connected "
                    "to the relevant request."
                ),
                "description_ar": (
                    "احتفظ بالمناقشات والمستندات والتحديثات مرتبطة بالطلب المعني."
                ),
                "icon": "bi-chat-dots",
                "order": 3,
            },
            {
                "title_en": "Faster service coordination",
                "title_ar": "تنسيق أسرع للخدمات",
                "description_en": (
                    "Structured workflows help teams respond and resolve requests efficiently."
                ),
                "description_ar": (
                    "تساعد مسارات العمل المنظمة الفرق على الاستجابة وإنجاز الطلبات بكفاءة."
                ),
                "icon": "bi-lightning-charge",
                "order": 4,
            },
            {
                "title_en": "Bilingual experience",
                "title_ar": "تجربة ثنائية اللغة",
                "description_en": (
                    "Use the platform in English or Arabic based on your preference."
                ),
                "description_ar": (
                    "استخدم المنصة باللغة الإنجليزية أو العربية حسب تفضيلك."
                ),
                "icon": "bi-translate",
                "order": 5,
            },
            {
                "title_en": "Digital request history",
                "title_ar": "سجل رقمي للطلبات",
                "description_en": (
                    "Maintain a clear history of requests, actions and communications."
                ),
                "description_ar": (
                    "احتفظ بسجل واضح للطلبات والإجراءات والمراسلات."
                ),
                "icon": "bi-clock-history",
                "order": 6,
            },
        ]

        for data in items:
            Feature.objects.update_or_create(
                title_en=data["title_en"],
                defaults={
                    **data,
                    "is_active": True,
                },
            )

    def seed_statistics(self):
        items = [
            {
                "value": "24",
                "suffix": "/7",
                "label_en": "Digital access",
                "label_ar": "وصول رقمي",
                "icon": "bi-clock",
                "order": 1,
            },
            {
                "value": "100",
                "suffix": "%",
                "label_en": "Online request tracking",
                "label_ar": "متابعة إلكترونية للطلبات",
                "icon": "bi-graph-up-arrow",
                "order": 2,
            },
            {
                "value": "2",
                "suffix": "",
                "label_en": "Supported languages",
                "label_ar": "لغتان مدعومتان",
                "icon": "bi-translate",
                "order": 3,
            },
            {
                "value": "1",
                "suffix": "",
                "label_en": "Unified service platform",
                "label_ar": "منصة خدمات موحدة",
                "icon": "bi-grid-1x2",
                "order": 4,
            },
        ]

        for data in items:
            Statistic.objects.update_or_create(
                label_en=data["label_en"],
                defaults={
                    **data,
                    "is_active": True,
                },
            )

    def seed_process(self):
        items = [
            {
                "step_number": 1,
                "title_en": "Submit",
                "title_ar": "قدّم",
                "description_en": (
                    "Choose the required service and submit your request."
                ),
                "description_ar": (
                    "اختر الخدمة المطلوبة وقدّم طلبك."
                ),
                "icon": "bi-send",
                "order": 1,
            },
            {
                "step_number": 2,
                "title_en": "Review",
                "title_ar": "المراجعة",
                "description_en": (
                    "The relevant team reviews your request and supporting information."
                ),
                "description_ar": (
                    "يقوم الفريق المختص بمراجعة طلبك والمعلومات الداعمة."
                ),
                "icon": "bi-search",
                "order": 2,
            },
            {
                "step_number": 3,
                "title_en": "Track",
                "title_ar": "تابع",
                "description_en": (
                    "Follow status updates and communicate through the portal."
                ),
                "description_ar": (
                    "تابع تحديثات الحالة وتواصل من خلال البوابة."
                ),
                "icon": "bi-activity",
                "order": 3,
            },
            {
                "step_number": 4,
                "title_en": "Resolve",
                "title_ar": "الإنجاز",
                "description_en": (
                    "Receive the final response or service resolution digitally."
                ),
                "description_ar": (
                    "استلم الرد النهائي أو نتيجة الخدمة إلكترونياً."
                ),
                "icon": "bi-check-circle",
                "order": 4,
            },
        ]

        for data in items:
            ProcessStep.objects.update_or_create(
                step_number=data["step_number"],
                defaults={
                    **data,
                    "is_active": True,
                },
            )

    def seed_testimonials(self):
        items = [
            {
                "name": "Ahmed Al Harthy",
                "role_en": "Customer",
                "role_ar": "عميل",
                "quote_en": (
                    "The request process was simple and I could follow every "
                    "update without calling multiple departments."
                ),
                "quote_ar": (
                    "كانت عملية تقديم الطلب سهلة وتمكنت من متابعة جميع "
                    "التحديثات دون الحاجة للتواصل مع عدة أقسام."
                ),
                "rating": 5,
                "order": 1,
            },
            {
                "name": "Fatma Al Balushi",
                "role_en": "Customer",
                "role_ar": "عميلة",
                "quote_en": (
                    "The portal makes it much easier to submit documents and "
                    "check the status of service requests."
                ),
                "quote_ar": (
                    "تجعل البوابة تقديم المستندات ومتابعة حالة طلبات الخدمة أسهل بكثير."
                ),
                "rating": 5,
                "order": 2,
            },
            {
                "name": "Service Partner",
                "role_en": "Provider",
                "role_ar": "مقدم خدمة",
                "quote_en": (
                    "A structured workflow gives us better visibility and "
                    "reduces unnecessary follow-up."
                ),
                "quote_ar": (
                    "يساعد مسار العمل المنظم على تحسين الرؤية وتقليل المتابعات غير الضرورية."
                ),
                "rating": 5,
                "order": 3,
            },
        ]

        for data in items:
            Testimonial.objects.update_or_create(
                name=data["name"],
                defaults={
                    **data,
                    "is_active": True,
                },
            )

    def seed_faqs(self):
        items = [
            {
                "question_en": "How do I submit a service request?",
                "question_ar": "كيف يمكنني تقديم طلب خدمة؟",
                "answer_en": (
                    "Sign in to the portal, select the required service and "
                    "complete the request form with the necessary information."
                ),
                "answer_ar": (
                    "سجّل الدخول إلى البوابة، واختر الخدمة المطلوبة، ثم أكمل "
                    "نموذج الطلب بالمعلومات اللازمة."
                ),
                "order": 1,
            },
            {
                "question_en": "Can I track my request online?",
                "question_ar": "هل يمكنني متابعة طلبي إلكترونياً؟",
                "answer_en": (
                    "Yes. Once submitted, you can monitor the request status "
                    "and related updates from your portal."
                ),
                "answer_ar": (
                    "نعم. بعد تقديم الطلب يمكنك متابعة حالته والتحديثات المرتبطة "
                    "به من خلال البوابة."
                ),
                "order": 2,
            },
            {
                "question_en": "Can I upload supporting documents?",
                "question_ar": "هل يمكنني إرفاق المستندات الداعمة؟",
                "answer_en": (
                    "Yes. Supported requests allow you to upload the required "
                    "documents securely."
                ),
                "answer_ar": (
                    "نعم. تتيح الطلبات المدعومة إرفاق المستندات المطلوبة بشكل آمن."
                ),
                "order": 3,
            },
            {
                "question_en": "Is the platform available in Arabic?",
                "question_ar": "هل المنصة متاحة باللغة العربية؟",
                "answer_en": (
                    "Yes. GLIS supports both English and Arabic."
                ),
                "answer_ar": (
                    "نعم. تدعم منصة جرين لاين اللغتين الإنجليزية والعربية."
                ),
                "order": 4,
            },
            {
                "question_en": "Who can use the portal?",
                "question_ar": "من يمكنه استخدام البوابة؟",
                "answer_en": (
                    "The portal can support customers, providers and authorized "
                    "insurance service teams depending on configured access."
                ),
                "answer_ar": (
                    "يمكن للعملاء ومقدمي الخدمة وفرق خدمات التأمين المصرح لهم "
                    "استخدام البوابة حسب صلاحيات الوصول المحددة."
                ),
                "order": 5,
            },
        ]

        for data in items:
            FAQ.objects.update_or_create(
                question_en=data["question_en"],
                defaults={
                    **data,
                    "is_active": True,
                },
            )

    def seed_partners(self):
        # We do not create fake logos because Partner.logo is required.
        # Create partner records manually from admin after uploading real logos.
        self.stdout.write(
            self.style.WARNING(
                "Partners skipped because Partner.logo requires an uploaded image."
            )
        )