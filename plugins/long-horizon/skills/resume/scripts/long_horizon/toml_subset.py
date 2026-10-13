"""Parser for the TOML subset the long-horizon lanes file uses.

Supported: comments, bare and quoted keys, dotted keys, ``[a.b]`` tables, basic and
literal strings, integers, simple decimal floats, booleans and (nested, multi-line) arrays.
Everything else raises ``Invalid`` naming the line. On Python 3.11+ ``load_text`` defers to
``tomllib``; on inputs within the subset both readers return the same value, and
``lanes.normalize`` rejects values (dates, times) that only ``tomllib`` would accept.
"""
from .model import Invalid

try:
    import tomllib
    USING_TOMLLIB = True
except ImportError:  # Python 3.10
    tomllib = None
    USING_TOMLLIB = False

BARE_KEY = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-')
ESCAPES = {'\\': '\\', '"': '"', 'n': '\n', 't': '\t', 'r': '\r'}
HEX = frozenset('0123456789abcdefABCDEF')
SPACE = ' \t'


def load_text(text):
    return tomllib.loads(text) if USING_TOMLLIB else loads(text)


def loads(text):
    return _Parser(text.replace('\r\n', '\n')).parse()


def _digits(text):
    return (bool(text) and text[0] != '_' and text[-1] != '_' and '__' not in text
            and all(c in '0123456789_' for c in text))


class _Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.root = {}
        self.table = self.root
        self.prefix = ()
        self.explicit = set()  # paths defined by a [header]
        self.dotted = set()    # paths created by dotted key/value keys

    def fail(self, message, pos=None):
        pos = self.pos if pos is None else pos
        raise Invalid('TOML line %d: %s' % (self.text.count('\n', 0, pos) + 1, message))

    def peek(self, n=1):
        return self.text[self.pos:self.pos + n]

    def skip(self, newlines=False):
        """Skip spaces and comments (and line breaks when inside an array)."""
        while self.pos < len(self.text):
            c = self.text[self.pos]
            if c in SPACE or (newlines and c == '\n'):
                self.pos += 1
            elif c == '#':
                while self.pos < len(self.text) and self.text[self.pos] != '\n':
                    self.pos += 1
            else:
                return

    def parse(self):
        while True:
            self.skip(newlines=True)
            if self.pos >= len(self.text):
                return self.root
            if self.peek() == '[':
                self.header()
            else:
                self.pair()
            self.skip()
            if self.pos < len(self.text) and self.peek() != '\n':
                self.fail('unexpected text after value')

    def key(self):
        self.skip()
        c = self.peek()
        if c in ('"', "'"):
            return self.string()
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] in BARE_KEY:
            self.pos += 1
        if start == self.pos:
            self.fail('expected a key')
        return self.text[start:self.pos]

    def dotted_key(self):
        keys = [self.key()]
        self.skip()
        while self.peek() == '.':
            self.pos += 1
            keys.append(self.key())
            self.skip()
        return keys

    def header(self):
        if self.peek(2) == '[[':
            self.fail('array of tables is not supported')
        self.pos += 1
        keys = self.dotted_key()
        if self.peek() != ']':
            self.fail('expected ] after table name')
        self.pos += 1
        node, path = self.root, ()
        for key in keys:
            path += (key,)
            child = node.setdefault(key, {})
            if not isinstance(child, dict) or (path in self.dotted):
                self.fail('table %s conflicts with an existing key' % '.'.join(keys))
            node = child
        if path in self.explicit:
            self.fail('table %s defined twice' % '.'.join(keys))
        self.explicit.add(path)
        self.table, self.prefix = node, path

    def pair(self):
        keys = self.dotted_key()
        if self.peek() != '=':
            self.fail('expected = after key')
        self.pos += 1
        self.skip()
        node, path = self.table, self.prefix
        for key in keys[:-1]:
            path += (key,)
            child = node.setdefault(key, {})
            if not isinstance(child, dict) or (path in self.explicit):
                self.fail('key %s conflicts with an existing key' % '.'.join(keys))
            self.dotted.add(path)
            node = child
        if keys[-1] in node:
            self.fail('duplicate key %s' % '.'.join(keys))
        node[keys[-1]] = self.value()

    def value(self):
        c = self.peek()
        if c in ('"', "'"):
            return self.string()
        if c == '[':
            return self.array()
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in ' \t\n,]#':
            self.pos += 1
        return self.scalar(self.text[start:self.pos], start)

    def scalar(self, token, start):
        if token in ('true', 'false'):
            return token == 'true'
        body = token[1:] if token[:1] in '+-' else token
        whole, dot, fraction = body.partition('.')
        if _digits(whole) and (whole == '0' or whole[0] != '0') and (not dot or _digits(fraction)):
            clean = token.replace('_', '')
            return float(clean) if dot else int(clean)
        self.fail('unsupported value %r' % token, start)

    def array(self):
        self.pos += 1
        items = []
        while True:
            self.skip(newlines=True)
            if self.pos >= len(self.text):
                self.fail('unterminated array')
            if self.peek() == ']':
                self.pos += 1
                return items
            items.append(self.value())
            self.skip(newlines=True)
            if self.peek() == ',':
                self.pos += 1
            elif self.peek() != ']':
                self.fail('expected , or ] in array')

    def string(self):
        quote = self.peek()
        if self.peek(3) == quote * 3:
            self.fail('multi-line strings are not supported')
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(self.text) or self.text[self.pos] == '\n':
                self.fail('unterminated string')
            c = self.text[self.pos]
            self.pos += 1
            if c == quote:
                return ''.join(out)
            if ord(c) < 32 and c != '\t' or c == '\x7f':
                self.fail('control character in string')
            out.append(self.escape() if c == '\\' and quote == '"' else c)

    def escape(self):
        kind = self.peek()
        self.pos += 1
        if kind in ESCAPES:
            return ESCAPES[kind]
        digits = self.peek(4)
        if kind == 'u' and len(digits) == 4 and all(c in HEX for c in digits):
            code = int(digits, 16)
            if not 0xD800 <= code <= 0xDFFF:
                self.pos += 4
                return chr(code)
        self.fail('invalid escape \\%s' % kind)
