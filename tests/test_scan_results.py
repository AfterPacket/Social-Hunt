"""Offline classification regressions: python -m unittest discover -s tests."""
import unittest
from types import SimpleNamespace

from social_hunt.providers_yaml import PatternProvider
from social_hunt.types import ResultStatus


class FakeClient:
    def __init__(self, code, text):
        self.response = SimpleNamespace(status_code=code, text=text)

    async def get(self, *args, **kwargs):
        return self.response


class ClassificationTests(unittest.IsolatedAsyncioTestCase):
    async def check_page(self, code, text):
        provider = PatternProvider("github", {
            "url": "https://example.org/{username}",
            "success_patterns": ["profile exists"],
        })
        return await provider.check("testuser", FakeClient(code, text), {})

    async def test_http_errors_override_success_text(self):
        for code, expected in ((401, ResultStatus.BLOCKED),
                               (403, ResultStatus.BLOCKED),
                               (429, ResultStatus.BLOCKED),
                               (404, ResultStatus.NOT_FOUND),
                               (410, ResultStatus.NOT_FOUND),
                               (500, ResultStatus.ERROR)):
            with self.subTest(code=code):
                result = await self.check_page(code, 'users/testuser profile exists <meta property="og:image" content="/error.png">')
                self.assertEqual(result.status, expected)
                self.assertEqual(result.profile, {})
                if expected != ResultStatus.NOT_FOUND:
                    self.assertTrue(result.error)

    async def test_cloudflare_asset_is_not_a_block(self):
        result = await self.check_page(200, 'profile exists <script src="https://static.cloudflareinsights.com/beacon.min.js"></script>')
        self.assertEqual(result.status, ResultStatus.FOUND)

    async def test_challenge_not_overridden_by_username_hint(self):
        result = await self.check_page(200, '<title>Just a moment...</title> users/testuser')
        self.assertEqual(result.status, ResultStatus.BLOCKED)
        self.assertTrue(result.error)
        self.assertEqual(result.profile, {})


if __name__ == "__main__":
    unittest.main()
