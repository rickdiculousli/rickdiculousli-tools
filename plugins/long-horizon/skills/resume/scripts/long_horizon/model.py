from dataclasses import asdict, dataclass
import hashlib
import json


class Invalid(ValueError):
    """Invalid policy, invocation or environment."""


class Blocked(Invalid):
    """Valid inspection/recording blocked by missing or stale acceptance."""


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    remedy: str
    path: str = ''
    line: int = 0

    def json(self):
        return asdict(self)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def finding(code, message, remedy, severity='error', path='', line=0):
    return Finding(severity, code, message, remedy, str(path), line)
