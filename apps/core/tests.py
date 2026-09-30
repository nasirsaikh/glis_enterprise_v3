from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from cms.api import create_page
from cms.models import PageContent
from djangocms_versioning.models import Version

from .models import SiteSettings


@override_settings(CMS_PAGE_CACHE=False, CMS_PLACEHOLDER_CACHE=False, CMS_PLUGIN_CACHE=False)
class PublicLocaleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_superuser('cms-publisher', 'cms@example.com', 'test')
        page = create_page('Arabic homepage', 'cms/glis_home.html', 'ar', created_by=user)
        page.set_as_homepage(user)
        content = PageContent.admin_manager.get(page=page, language='ar')
        Version.objects.get_for_content(content).publish(user)
        site = SiteSettings.load()
        site.hero_title_en = 'English health insurance homepage'
        site.save()

    def setUp(self):
        cache.clear()
        translation.activate('en')

    def tearDown(self):
        cache.clear()
        translation.activate('en')

    def test_anonymous_english_home_with_only_arabic_cms_content(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="en" dir="ltr"')
        self.assertEqual(response['Content-Language'], 'en')
        self.assertContains(response, 'hx-get="/api/v1/home-content/"')
        self.assertContains(response, 'name="language" type="hidden" value="ar"')

    def test_anonymous_switch_to_english_survives_cms_fallback(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'ar'
        self.assertContains(self.client.get('/ar/'), '<html lang="ar" dir="rtl"')
        response = self.client.post(reverse('switch_language'), {'language': 'en', 'next': '/ar/'}, follow=True)
        self.assertEqual(response.redirect_chain, [('/', 302)])
        self.assertContains(response, '<html lang="en" dir="ltr"')
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')
        fragment = self.client.get('/api/v1/home-content/', HTTP_HX_REQUEST='true')
        self.assertContains(fragment, 'English health insurance homepage')
        self.assertContains(fragment, 'hx-get="/api/v1/home/partials/management/"')

    def test_anonymous_switch_back_to_arabic_keeps_localized_home_link(self):
        response = self.client.post(reverse('switch_language'), {'language': 'ar', 'next': '/'}, follow=True)
        self.assertEqual(response.redirect_chain, [('/ar/', 302)])
        self.assertContains(response, '<html lang="ar" dir="rtl"')
        self.assertContains(response, 'class="gl-footer-brand" href="/ar/"')
        self.assertContains(response, 'hx-get="/ar/api/v1/home-content/"')
        self.assertContains(response, 'name="language" type="hidden" value="en"')

    @override_settings(CMS_PAGE_CACHE=True)
    def test_cached_public_home_keeps_each_requested_locale(self):
        for path, language in [('/', 'en'), ('/ar/', 'ar'), ('/', 'en'), ('/ar/', 'ar')]:
            self.assertContains(self.client.get(path), f'<html lang="{language}"')
