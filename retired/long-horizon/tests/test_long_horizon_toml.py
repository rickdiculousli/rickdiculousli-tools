import unittest

import long_horizon_support  # noqa: F401  (puts the long_horizon package on sys.path)
from long_horizon import toml_subset
from long_horizon.model import Invalid
from long_horizon.toml_subset import loads

DOCUMENT = '''# Lanes for the example project
[run]
name = "example"      # trailing comment
retries = 3
branch = 'main'

[shared]
paths = ["docs", "tools"]
levels = [1, 2, 3,]

[rules]
forbidden = [
    "has # hash",   # comment after item
    'say "hi"',
    "escaped \\" quote",
]

[lanes.core]
owns = ["crates/app-core"]
validators = ["unit", "lint"]
host = "linux"

[lanes.ui]
owns = ["web"]
validators = ["unit"]
host = "linux"

[lanes.native]
owns = ["native", "crates/app-core/ffi"]
validators = []
host = "macos"
'''

EXPECTED = {
    'run': {'name': 'example', 'retries': 3, 'branch': 'main'},
    'shared': {'paths': ['docs', 'tools'], 'levels': [1, 2, 3]},
    'rules': {'forbidden': ['has # hash', 'say "hi"', 'escaped " quote']},
    'lanes': {
        'core': {'owns': ['crates/app-core'], 'validators': ['unit', 'lint'], 'host': 'linux'},
        'ui': {'owns': ['web'], 'validators': ['unit'], 'host': 'linux'},
        'native': {'owns': ['native', 'crates/app-core/ffi'], 'validators': [], 'host': 'macos'},
    },
}


class TomlSubsetTests(unittest.TestCase):
    def test_document_matches_tomllib(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest('tomllib needs Python 3.11')
        self.assertEqual(loads(DOCUMENT), tomllib.loads(DOCUMENT))

    def test_document_expected_value(self):
        self.assertEqual(loads(DOCUMENT), EXPECTED)
        self.assertEqual(toml_subset.load_text(DOCUMENT), EXPECTED)
        self.assertIsInstance(toml_subset.USING_TOMLLIB, bool)

    def test_rejected_forms(self):
        for text in [
            'a = {b = 1}', '[[x]]\na = 1', 'a = """x"""', "a = '''x'''",
            'a = 1979-05-27', 'a = 07:32:00', 'a = 1\na = 2', '[t]\n[t]',
            '[t]\na = 1\n[t.u]\n[t]', 'a = [1, 2', 'a = [[1], 2', 'a = [1]]',
            'a = "open', "a = 'open", 'a = bare', 'a =', '= 1', 'a = 1 b = 2',
            'a = 0x10', 'a = 01', 'a = 1__0', 'a = _1', 'a = 1e3', 'a = inf',
            'a = "\\q"', 'a = "\\u12"', 'a = "\\ud800"', 'a = [1 2]', 'a.b = 1\n[a]',
            'a = 1\n[a]', '[a]\nb = 1\n[a.b]', 'a.b = 1\na.b.c = 2', '[a b]', '[a',
        ]:
            with self.subTest(text=text):
                with self.assertRaises(Invalid):
                    loads(text)

    def test_error_names_line(self):
        with self.assertRaises(Invalid) as caught:
            loads('a = 1\nb = 2\nc = bare\n')
        self.assertIn('line 3', str(caught.exception))

    def test_scalars_and_escapes(self):
        text = (
            's = "a\\\\b\\"c\\nd\\te\\rf\\u00e9"\n'
            "lit = 'C:\\path\\n'\n"
            'neg = -42\npos = +7\nbig = 1_000_000\nzero = 0\n'
            'pi = 3.14\nneg_float = -0.5\nsplit = 1_0.2_5\n'
            't = true\nf = false\n'
            '"quoted key" = 1\n"" = 2\n'
        )
        self.assertEqual(loads(text), {
            's': 'a\\b"c\nd\te\rf\u00e9', 'lit': 'C:\\path\\n',
            'neg': -42, 'pos': 7, 'big': 1000000, 'zero': 0,
            'pi': 3.14, 'neg_float': -0.5, 'split': 10.25,
            't': True, 'f': False, 'quoted key': 1, '': 2,
        })

    def test_arrays_comments_and_dotted_keys(self):
        text = (
            'nested = [[1, 2], ["a"], []]  # note\n'
            'mixed = [1, "a", true, 1.5,]\n'
            'multi = [ # first\n  1,\n  # between\n  2\n]\n'
            'a.b = 1\na . c = "x"\n'
            '[t.u.v]\nk = 1\n[t]\nj = 2\n'
            '[ "q.r" . s ]\nz = 0 # end\n'
            '[w]\nd.e.f = [1]\n'
        )
        expected = {
            'nested': [[1, 2], ['a'], []], 'mixed': [1, 'a', True, 1.5], 'multi': [1, 2],
            'a': {'b': 1, 'c': 'x'}, 't': {'u': {'v': {'k': 1}}, 'j': 2},
            'q.r': {'s': {'z': 0}}, 'w': {'d': {'e': {'f': [1]}}},
        }
        self.assertEqual(loads(text), expected)
        self.assertEqual(loads(text.replace('\n', '\r\n')), expected)
        try:
            import tomllib
        except ImportError:
            return
        self.assertEqual(loads(text), tomllib.loads(text))


if __name__ == '__main__':
    unittest.main()
