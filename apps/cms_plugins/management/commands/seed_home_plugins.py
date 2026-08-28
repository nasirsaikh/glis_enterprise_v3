from cms.api import add_plugin
from cms.models import Page
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = "Seed GLIS Home django CMS plugins for English and Arabic"

    REQUIRED_SLOTS = ["hero_content", "hero_image", "partners", "about_image", "about_content", "services_header", "services", "features_header", "features", "process_header", "process", "statistics", "testimonials_header", "testimonials", "faq_header", "faq", "call_to_action"]

    def handle(self, *args, **options):
        page = Page.objects.filter(is_home=True).first()
        if not page:
            raise CommandError("Home page not found.")
        self.stdout.write(self.style.SUCCESS(f"Home page found: {page.pk}"))
        self.seed_language(page, "en")
        self.seed_language(page, "ar")
        self.stdout.write(self.style.SUCCESS("GLIS Home plugins seeded successfully."))

    def get_page_content(self, page, language):
        content = page.get_admin_content(language)
        if not content:
            raise CommandError(f"No PageContent found for language '{language}'.")
        if content.template != "cms/glis_home.html":
            raise CommandError(f"Home page '{language}' is using template '{content.template}' instead of 'cms/glis_home.html'.")
        return content

    def validate_placeholders(self, page, language):
        content = self.get_page_content(page, language)
        available_slots = set(content.get_placeholders().values_list("slot", flat=True))
        missing_slots = [slot for slot in self.REQUIRED_SLOTS if slot not in available_slots]
        self.stdout.write(f"{language}: template = {content.template}")
        self.stdout.write(f"{language}: placeholders = {', '.join(sorted(available_slots)) if available_slots else 'NONE'}")
        if missing_slots:
            raise CommandError(f"Missing placeholders for '{language}': {', '.join(missing_slots)}")
        return content

    def get_placeholder(self, page, language, slot):
        content = self.get_page_content(page, language)
        placeholder = content.get_placeholders().filter(slot=slot).first()
        if not placeholder:
            raise CommandError(f"Placeholder '{slot}' not found for language '{language}'.")
        return placeholder

    def clear_placeholder(self, page, language, slot):
        placeholder = self.get_placeholder(page, language, slot)
        plugins = placeholder.get_plugins(language)
        count = plugins.count()
        if count:
            plugins.delete()
            self.stdout.write(f"{language}: cleared {count} plugin(s) from {slot}")

    def add(self, page, language, slot, plugin_type, **data):
        placeholder = self.get_placeholder(page, language, slot)
        plugin = add_plugin(placeholder=placeholder, plugin_type=plugin_type, language=language, position="last-child", **data)
        self.stdout.write(self.style.SUCCESS(f"{language}: {slot} -> {plugin_type}"))
        return plugin

    def seed_language(self, page, language):
        self.stdout.write(self.style.WARNING(f"Seeding language: {language}"))
        self.validate_placeholders(page, language)
        for slot in self.REQUIRED_SLOTS:
            self.clear_placeholder(page, language, slot)
        if language == "en":
            self.seed_english(page, language)
        elif language == "ar":
            self.seed_arabic(page, language)

    def seed_english(self, page, language):
        self.add(page, language, "hero_content", "HomeHeroCMSPlugin", eyebrow="Insurance Service Coordination", title="Insurance Services Made Simple", subtitle="A secure digital platform connecting customers, providers and insurance teams for faster service coordination.", primary_button_text="Create Request", primary_button_url="/portal/tickets/create/1/", secondary_button_text="Explore Services", secondary_button_url="#services")

        self.add(page, language, "about_content", "HomeContentCMSPlugin", eyebrow="About GLIS", title="Insurance Service Coordination Built Around You", content="GLIS provides a secure and efficient platform for coordinating insurance service requests between customers, providers and internal teams.", button_text="Learn More", button_url="/about/")

        self.add(page, language, "services_header", "HomeSectionHeaderCMSPlugin", eyebrow="Our Services", title="Everything You Need in One Platform", description="Access insurance service coordination through a secure and easy-to-use digital platform.", alignment="center")
        self.add(page, language, "services", "HomeServiceCMSPlugin", icon="bi-headset", title="Customer Support", summary="Submit and track insurance service requests with clear status visibility.", button_text="Create Request", button_url="/portal/tickets/create/1/", featured=True)
        self.add(page, language, "services", "HomeServiceCMSPlugin", icon="bi-file-earmark-medical", title="Claims Support", summary="Coordinate claim-related enquiries and service requirements efficiently.", button_text="Learn More", button_url="#", featured=False)
        self.add(page, language, "services", "HomeServiceCMSPlugin", icon="bi-shield-check", title="Policy Services", summary="Access support for policy servicing and related insurance requirements.", button_text="Learn More", button_url="#", featured=False)

        self.add(page, language, "features_header", "HomeSectionHeaderCMSPlugin", eyebrow="Why GLIS", title="Designed for Secure Insurance Operations", description="A modern platform focused on service quality, transparency and secure coordination.", alignment="center")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-shield-lock", title="Secure", description="Designed with security and controlled access across the platform.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-lightning-charge", title="Fast", description="Streamlined workflows help service requests move faster.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-translate", title="Bilingual", description="Full English and Arabic experience for users and administrators.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-eye", title="Transparent", description="Track service requests and their latest status from one place.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-people", title="Collaborative", description="Connect customers, service providers and internal teams.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-bar-chart", title="Measurable", description="Structured workflows provide better operational visibility.")

        self.add(page, language, "process_header", "HomeSectionHeaderCMSPlugin", eyebrow="How It Works", title="Simple Request Process", description="Submit your request and follow its progress through a clear workflow.", alignment="center")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=1, icon="bi-pencil-square", title="Create Request", description="Submit your insurance service request through the portal.")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=2, icon="bi-diagram-3", title="Assignment", description="The request is automatically routed to the appropriate team.")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=3, icon="bi-gear", title="Processing", description="The responsible team reviews and processes your request.")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=4, icon="bi-check-circle", title="Completion", description="Receive the final update once your request is completed.")

        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-people", value="10", suffix="K+", label="Customers Served")
        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-check-circle", value="25", suffix="K+", label="Requests Completed")
        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-building", value="50", suffix="+", label="Service Partners")
        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-clock-history", value="24", suffix="/7", label="Digital Access")

        self.add(page, language, "testimonials_header", "HomeSectionHeaderCMSPlugin", eyebrow="Customer Experience", title="What Our Customers Say", description="Feedback from customers using our insurance service platform.", alignment="center")
        self.add(page, language, "testimonials", "HomeTestimonialCMSPlugin", name="Ahmed", role="Customer", quote="The service request process was simple and I could easily follow the status.", rating=5)
        self.add(page, language, "testimonials", "HomeTestimonialCMSPlugin", name="Fatma", role="Customer", quote="A convenient platform for communicating and tracking insurance service requests.", rating=5)
        self.add(page, language, "testimonials", "HomeTestimonialCMSPlugin", name="Mohammed", role="Customer", quote="The platform provides clear information and makes follow-up much easier.", rating=4)

        self.add(page, language, "faq_header", "HomeSectionHeaderCMSPlugin", eyebrow="Frequently Asked Questions", title="How Can We Help?", description="Find answers to common questions about using GLIS.", alignment="center")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="How do I create a service request?", answer="Select Create Request, complete the required information and submit the request.")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="Can I track my request?", answer="Yes. Sign in to the portal to view your requests and their latest status.")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="Can I upload documents?", answer="Yes. Supported documents can be attached when creating or updating a request.")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="Is the portal available in Arabic?", answer="Yes. The public website and portal support both English and Arabic.")

        self.add(page, language, "call_to_action", "HomeCTACMSPlugin", eyebrow="Need Assistance?", title="Start Your Insurance Service Request", content="Create a request through our secure portal and keep track of its progress.", button_text="Create Request", button_url="/portal/tickets/create/1/")

    def seed_arabic(self, page, language):
        self.add(page, language, "hero_content", "HomeHeroCMSPlugin", eyebrow="تنسيق خدمات التأمين", title="خدمات التأمين أصبحت أسهل", subtitle="منصة رقمية آمنة تربط العملاء ومقدمي الخدمات وفرق التأمين لتوفير خدمة أسرع وأكثر كفاءة.", primary_button_text="إنشاء طلب", primary_button_url="/ar/portal/tickets/create/1/", secondary_button_text="استكشف الخدمات", secondary_button_url="#services")

        self.add(page, language, "about_content", "HomeContentCMSPlugin", eyebrow="عن GLIS", title="تنسيق خدمات التأمين المصمم من أجلك", content="توفر GLIS منصة آمنة وفعالة لتنسيق طلبات خدمات التأمين بين العملاء ومقدمي الخدمات والفرق الداخلية.", button_text="اعرف المزيد", button_url="/ar/about/")

        self.add(page, language, "services_header", "HomeSectionHeaderCMSPlugin", eyebrow="خدماتنا", title="كل ما تحتاجه في منصة واحدة", description="الوصول إلى خدمات التأمين من خلال منصة رقمية آمنة وسهلة الاستخدام.", alignment="center")
        self.add(page, language, "services", "HomeServiceCMSPlugin", icon="bi-headset", title="دعم العملاء", summary="تقديم ومتابعة طلبات خدمات التأمين مع رؤية واضحة لحالة الطلب.", button_text="إنشاء طلب", button_url="/ar/portal/tickets/create/1/", featured=True)
        self.add(page, language, "services", "HomeServiceCMSPlugin", icon="bi-file-earmark-medical", title="دعم المطالبات", summary="تنسيق الاستفسارات والمتطلبات المتعلقة بالمطالبات بكفاءة.", button_text="اعرف المزيد", button_url="#", featured=False)
        self.add(page, language, "services", "HomeServiceCMSPlugin", icon="bi-shield-check", title="خدمات الوثائق", summary="الحصول على الدعم المتعلق بخدمات وثائق التأمين والمتطلبات ذات الصلة.", button_text="اعرف المزيد", button_url="#", featured=False)

        self.add(page, language, "features_header", "HomeSectionHeaderCMSPlugin", eyebrow="لماذا GLIS", title="مصممة لعمليات تأمين آمنة", description="منصة حديثة تركز على جودة الخدمة والشفافية والتنسيق الآمن.", alignment="center")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-shield-lock", title="آمنة", description="مصممة مع ضوابط أمنية وصلاحيات وصول مناسبة.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-lightning-charge", title="سريعة", description="تساعد إجراءات العمل المبسطة على معالجة الطلبات بشكل أسرع.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-translate", title="ثنائية اللغة", description="تجربة كاملة باللغة العربية والإنجليزية.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-eye", title="شفافة", description="متابعة الطلبات ومعرفة آخر حالة من مكان واحد.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-people", title="تعاونية", description="ربط العملاء ومقدمي الخدمات والفرق الداخلية.")
        self.add(page, language, "features", "HomeFeatureCMSPlugin", icon="bi-bar-chart", title="قابلة للقياس", description="توفر إجراءات العمل المنظمة رؤية تشغيلية أفضل.")

        self.add(page, language, "process_header", "HomeSectionHeaderCMSPlugin", eyebrow="كيف تعمل", title="عملية طلب بسيطة", description="قم بإرسال الطلب ومتابعة تقدمه من خلال خطوات واضحة.", alignment="center")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=1, icon="bi-pencil-square", title="إنشاء الطلب", description="قم بإرسال طلب خدمة التأمين من خلال البوابة.")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=2, icon="bi-diagram-3", title="التعيين", description="يتم توجيه الطلب إلى الفريق المختص.")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=3, icon="bi-gear", title="المعالجة", description="يقوم الفريق المسؤول بمراجعة الطلب ومعالجته.")
        self.add(page, language, "process", "HomeProcessCMSPlugin", step_number=4, icon="bi-check-circle", title="الإكمال", description="ستتلقى التحديث النهائي عند اكتمال الطلب.")

        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-people", value="10", suffix="K+", label="عميل")
        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-check-circle", value="25", suffix="K+", label="طلب مكتمل")
        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-building", value="50", suffix="+", label="شريك خدمة")
        self.add(page, language, "statistics", "HomeStatisticCMSPlugin", icon="bi-clock-history", value="24", suffix="/7", label="وصول رقمي")

        self.add(page, language, "testimonials_header", "HomeSectionHeaderCMSPlugin", eyebrow="تجربة العملاء", title="ماذا يقول عملاؤنا", description="آراء العملاء الذين يستخدمون منصة خدمات التأمين.", alignment="center")
        self.add(page, language, "testimonials", "HomeTestimonialCMSPlugin", name="أحمد", role="عميل", quote="كانت عملية تقديم الطلب بسيطة وتمكنت من متابعة حالة الطلب بسهولة.", rating=5)
        self.add(page, language, "testimonials", "HomeTestimonialCMSPlugin", name="فاطمة", role="عميلة", quote="منصة مريحة للتواصل ومتابعة طلبات خدمات التأمين.", rating=5)
        self.add(page, language, "testimonials", "HomeTestimonialCMSPlugin", name="محمد", role="عميل", quote="توفر المنصة معلومات واضحة وتجعل المتابعة أسهل بكثير.", rating=4)

        self.add(page, language, "faq_header", "HomeSectionHeaderCMSPlugin", eyebrow="الأسئلة الشائعة", title="كيف يمكننا مساعدتك؟", description="إجابات على الأسئلة الشائعة حول استخدام GLIS.", alignment="center")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="كيف يمكنني إنشاء طلب خدمة؟", answer="اختر إنشاء طلب، وأدخل البيانات المطلوبة ثم قم بإرسال الطلب.")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="هل يمكنني متابعة طلبي؟", answer="نعم. قم بتسجيل الدخول إلى البوابة لعرض طلباتك وآخر حالة لها.")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="هل يمكنني رفع المستندات؟", answer="نعم. يمكن إرفاق المستندات المدعومة عند إنشاء الطلب أو تحديثه.")
        self.add(page, language, "faq", "HomeFAQCMSPlugin", question="هل البوابة متوفرة باللغة العربية؟", answer="نعم. الموقع العام والبوابة يدعمان اللغتين العربية والإنجليزية.")

        self.add(page, language, "call_to_action", "HomeCTACMSPlugin", eyebrow="هل تحتاج إلى مساعدة؟", title="ابدأ طلب خدمة التأمين", content="أنشئ طلبك من خلال بوابتنا الآمنة وتابع تقدمه بسهولة.", button_text="إنشاء طلب", button_url="/ar/portal/tickets/create/1/")