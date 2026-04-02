"""tests/test_domain_provider_map.py — FD-00006 域名推断单元测试"""

import unittest


class TestDomainProviderMap(unittest.TestCase):
    def test_infer_gmail(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@gmail.com"), "gmail")
        self.assertEqual(infer_provider_from_email("user@googlemail.com"), "gmail")

    def test_infer_qq(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@qq.com"), "qq")
        self.assertEqual(infer_provider_from_email("user@foxmail.com"), "qq")

    def test_infer_163(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@163.com"), "163")

    def test_infer_126(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@126.com"), "126")

    def test_infer_yahoo(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@yahoo.com"), "yahoo")
        self.assertEqual(infer_provider_from_email("user@yahoo.co.jp"), "yahoo")

    def test_infer_aliyun(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@aliyun.com"), "aliyun")
        self.assertEqual(infer_provider_from_email("user@alimail.com"), "aliyun")

    def test_infer_outlook(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertEqual(infer_provider_from_email("user@outlook.com"), "outlook")
        self.assertEqual(infer_provider_from_email("user@hotmail.com"), "outlook")
        self.assertEqual(infer_provider_from_email("user@live.com"), "outlook")
        self.assertEqual(infer_provider_from_email("user@live.cn"), "outlook")

    def test_infer_unknown_domain(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertIsNone(infer_provider_from_email("user@unknown.org"))
        self.assertIsNone(infer_provider_from_email("user@company.co"))

    def test_infer_invalid_input(self):
        from outlook_web.services.providers import infer_provider_from_email

        self.assertIsNone(infer_provider_from_email(""))
        self.assertIsNone(infer_provider_from_email(None))
        self.assertIsNone(infer_provider_from_email("no-at-sign"))

    def test_extract_and_normalize_email_domain(self):
        from outlook_web.services.providers import extract_email_domain, normalize_email_domain

        self.assertEqual(extract_email_domain("User@HotMail.COM"), "hotmail.com")
        self.assertEqual(normalize_email_domain(" HotMail.COM "), "hotmail.com")
        self.assertEqual(normalize_email_domain("user@live.com"), "live.com")

    def test_provider_supports_email_domain(self):
        from outlook_web.services.providers import provider_supports_email_domain

        self.assertTrue(provider_supports_email_domain("outlook", "hotmail.com"))
        self.assertTrue(provider_supports_email_domain("outlook", "HotMail.COM"))
        self.assertFalse(provider_supports_email_domain("gmail", "hotmail.com"))

    def test_known_provider_keys(self):
        from outlook_web.services.providers import KNOWN_PROVIDER_KEYS, MAIL_PROVIDERS

        self.assertEqual(KNOWN_PROVIDER_KEYS, set(MAIL_PROVIDERS.keys()))
        self.assertIn("outlook", KNOWN_PROVIDER_KEYS)
        self.assertIn("gmail", KNOWN_PROVIDER_KEYS)
        self.assertIn("custom", KNOWN_PROVIDER_KEYS)

    def test_provider_group_name(self):
        from outlook_web.services.providers import PROVIDER_GROUP_NAME

        self.assertEqual(PROVIDER_GROUP_NAME["outlook"], "Outlook")
        self.assertEqual(PROVIDER_GROUP_NAME["gptmail"], "临时邮箱")

    def test_get_provider_list_has_auto_first(self):
        from outlook_web.services.providers import get_provider_list

        providers = get_provider_list()
        self.assertGreater(len(providers), 0)
        self.assertEqual(providers[0]["key"], "auto")
        self.assertEqual(providers[0]["account_type"], "mixed")
        # auto 不应出现在第二个及以后的位置
        keys = [p["key"] for p in providers]
        self.assertEqual(keys.count("auto"), 1)


if __name__ == "__main__":
    unittest.main()
