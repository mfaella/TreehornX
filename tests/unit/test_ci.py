from unittest import TestCase

from ci import ci


class CITestCase(TestCase):
    def test_ci(self):
        self.assertEqual(ci(), "CI")
