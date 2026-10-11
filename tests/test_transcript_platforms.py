"""Check the script's dependency selection without downloading model packages."""

import ast
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/yt-transcript/skills/yt-transcript/scripts/yt_transcript.py"


class DependencySelectionTest(unittest.TestCase):
    def test_every_supported_platform_selects_one_whisper_backend(self):
        header = SCRIPT.read_text(encoding="utf-8").split("# /// script\n", 1)[1].split("# ///", 1)[0]
        metadata = "\n".join(line.removeprefix("# ") for line in header.splitlines())
        assignments = ast.parse("dependencies =" + metadata.split("dependencies =", 1)[1]).body
        dependencies = next(ast.literal_eval(item.value) for item in assignments
                            if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name)
                            and item.targets[0].id == "dependencies")
        for system, machine, expected in (
            ("darwin", "arm64", {"mlx-whisper"}),
            ("darwin", "x86_64", {"faster-whisper"}),
            ("linux", "x86_64", {"faster-whisper"}),
            ("linux", "aarch64", {"faster-whisper"}),
        ):
            with self.subTest(system=system, machine=machine):
                selected = set()
                for requirement in dependencies:
                    package, separator, marker = requirement.partition(";")
                    # This header uses the PEP 508 subset shared with Python:
                    # string comparisons, parentheses, and boolean operators.
                    if not separator or eval(marker.strip(), {"__builtins__": {}}, {
                        "sys_platform": system, "platform_machine": machine,
                    }):
                        selected.add(package.strip().split("<", 1)[0])
                self.assertEqual(selected & {"mlx-whisper", "faster-whisper"}, expected)
                if expected == {"faster-whisper"}:
                    self.assertIn("av", selected)
