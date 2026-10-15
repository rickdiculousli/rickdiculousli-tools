import unittest
from tiny import tiny


class TinyTests(unittest.TestCase):
    def test_bounded_behavior(self):
        self.assertEqual(tiny(), 2)
