from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from .models import HomeCTAPlugin, HomeContentPlugin, HomeFAQPlugin, HomeFeaturePlugin, HomeHeroPlugin, HomeImagePlugin, HomePartnerPlugin, HomeProcessPlugin, HomeSectionHeaderPlugin, HomeServicePlugin, HomeStatisticPlugin, HomeTestimonialPlugin,CustomWebSection
from .forms import CustomWebSectionForm

@plugin_pool.register_plugin
class HomeHeroCMSPlugin(CMSPluginBase):
    model = HomeHeroPlugin
    name = "Hero"
    module = "GLIS Home"
    render_template = "cms/plugins/home/hero.html"
    cache = False

@plugin_pool.register_plugin
class HomeImageCMSPlugin(CMSPluginBase):
    model = HomeImagePlugin
    name = "Image"
    module = "GLIS Home"
    render_template = "cms/plugins/home/image.html"
    cache = False

@plugin_pool.register_plugin
class HomeSectionHeaderCMSPlugin(CMSPluginBase):
    model = HomeSectionHeaderPlugin
    name = "Section Header"
    module = "GLIS Home"
    render_template = "cms/plugins/home/section_header.html"
    cache = False

@plugin_pool.register_plugin
class HomeContentCMSPlugin(CMSPluginBase):
    model = HomeContentPlugin
    name = "Content"
    module = "GLIS Home"
    render_template = "cms/plugins/home/content.html"
    cache = False

@plugin_pool.register_plugin
class HomeServiceCMSPlugin(CMSPluginBase):
    model = HomeServicePlugin
    name = "Service Card"
    module = "GLIS Home"
    render_template = "cms/plugins/home/service.html"
    cache = False

@plugin_pool.register_plugin
class HomeFeatureCMSPlugin(CMSPluginBase):
    model = HomeFeaturePlugin
    name = "Feature Card"
    module = "GLIS Home"
    render_template = "cms/plugins/home/feature.html"
    cache = False

@plugin_pool.register_plugin
class HomeProcessCMSPlugin(CMSPluginBase):
    model = HomeProcessPlugin
    name = "Process Step"
    module = "GLIS Home"
    render_template = "cms/plugins/home/process.html"
    cache = False

@plugin_pool.register_plugin
class HomeStatisticCMSPlugin(CMSPluginBase):
    model = HomeStatisticPlugin
    name = "Statistic"
    module = "GLIS Home"
    render_template = "cms/plugins/home/statistic.html"
    cache = False

@plugin_pool.register_plugin
class HomeTestimonialCMSPlugin(CMSPluginBase):
    model = HomeTestimonialPlugin
    name = "Testimonial"
    module = "GLIS Home"
    render_template = "cms/plugins/home/testimonial.html"
    cache = False

@plugin_pool.register_plugin
class HomeFAQCMSPlugin(CMSPluginBase):
    model = HomeFAQPlugin
    name = "FAQ"
    module = "GLIS Home"
    render_template = "cms/plugins/home/faq.html"
    cache = False

@plugin_pool.register_plugin
class HomePartnerCMSPlugin(CMSPluginBase):
    model = HomePartnerPlugin
    name = "Partner"
    module = "GLIS Home"
    render_template = "cms/plugins/home/partner.html"
    cache = False

@plugin_pool.register_plugin
class HomeCTACMSPlugin(CMSPluginBase):
    model = HomeCTAPlugin
    name = "Call To Action"
    module = "GLIS Home"
    render_template = "cms/plugins/home/cta.html"
    cache = False


@plugin_pool.register_plugin
class CustomWebSectionPlugin(CMSPluginBase):
    model = CustomWebSection
    name = "Custom Web Section"
    module = "GLIS Content"
    form = CustomWebSectionForm
    render_template = "cms/plugins/custom_web_section.html"
    cache = False
    fieldsets = (
        (
            "General",
            {
                "fields": (
                    "title",
                    "is_active",
                )
            },
        ),

        (
            "Content - WYSIWYG / HTML",
            {
                "fields": (
                    "html_content",
                )
            },
        ),

        (
            "Custom CSS",
            {
                "fields": (
                    "css_content",
                ),

                "classes": (
                    "collapse",
                ),
            },
        ),

        (
            "Custom JavaScript",
            {
                "fields": (
                    "javascript_content",
                ),

                "classes": (
                    "collapse",
                ),
            },
        ),
    )