"""State computed from a normalized report: numbering, failures, attention items."""

from dataclasses import dataclass, field
import re

EVIDENCE_LIMIT = 2000
COUNTED_STEP_KINDS = ("edit", "run", "other")


@dataclass
class AttentionItem:
    kind: str  # "run", "step", "refuted", "unverified", "deleted", "truncated"
    label: str
    anchor: str


@dataclass
class Derived:
    runs: dict[str, int]
    steps: dict[str, int]
    asserted: int
    countable: int
    all_asserted: bool
    files: int | None
    lines_added: int | None
    lines_removed: int | None
    commands: int | None
    contradictions: list[AttentionItem] = field(default_factory=list)
    attention: list[AttentionItem] = field(default_factory=list)
    cited_by: dict[str, list[str]] = field(default_factory=dict)
    all_steps: list[dict] = field(default_factory=list)


def slug(text: str) -> str:
    value = re.sub(r"[\W_]+", "-", text.lower()).strip("-")
    return value or "item"


class _Anchors:
    def __init__(self):
        self.used: set[str] = set()

    def make(self, prefix: str, text: str) -> str:
        base = f"{prefix}-{slug(text)}"
        anchor, index = base, 2
        while anchor in self.used:
            anchor, index = f"{base}-{index}", index + 1
        self.used.add(anchor)
        return anchor


def run_failure(run: dict) -> str:
    failed = (run["exit"] != 0) != run.get("expect_fail", False)
    if not failed:
        return "expected" if run.get("expect_fail") else "ok"
    return "resolved" if run.get("resolved") else "unresolved"


def derive(report: dict) -> Derived:
    """Annotate report items in place and compute the page's derived state."""
    anchors = _Anchors()
    all_steps, runs, claims, files = [], [], [], []
    types = set()
    for index, module in enumerate(report["modules"], 1):
        module["anchor"] = f"module-{index}"
        types.add(module["type"])
        if module["type"] == "timeline":
            phases: dict[str, str] = {}
            for step in module["steps"]:
                all_steps.append(step)
                step["n"] = len(all_steps)
                step["anchor"] = f"step-{step['n']}"
                if step["status"] in ("fail", "warn"):
                    step["failure"] = "resolved" if step.get("resolved") else "unresolved"
                else:
                    step["failure"] = "ok"
                if "phase" in step:
                    if step["phase"] not in phases:
                        phases[step["phase"]] = anchors.make("phase", step["phase"])
                    step["phase_anchor"] = phases[step["phase"]]
        elif module["type"] == "runs":
            for run in module["runs"]:
                runs.append(run)
                run["n"] = len(runs)
                run["anchor"] = f"run-{run['n']}"
                run["failure"] = run_failure(run)
        elif module["type"] == "claims":
            for claim in module["claims"]:
                claims.append(claim)
                claim["n"] = len(claims)
                claim["anchor"] = f"claim-{claim['n']}"
        elif module["type"] == "files":
            for item in module["files"]:
                files.append(item)
                item["anchor"] = anchors.make("file", item["path"])

    countable = runs + claims + files + [s for s in all_steps if s["kind"] in COUNTED_STEP_KINDS]
    asserted = sum(1 for item in countable if item["source"] == "asserted")
    derived = Derived(
        runs={key: sum(1 for r in runs if r["failure"] == key) for key in ("unresolved", "resolved", "expected")},
        steps={key: sum(1 for s in all_steps if s["failure"] == key) for key in ("unresolved", "resolved")},
        asserted=asserted,
        countable=len(countable),
        all_asserted=bool(countable) and asserted == len(countable),
        files=len(files) if "files" in types else None,
        lines_added=sum(f["added"] for f in files) if "files" in types else None,
        lines_removed=sum(f["removed"] for f in files) if "files" in types else None,
        commands=len(runs) if "runs" in types else None,
        all_steps=all_steps,
    )

    failed_runs = [AttentionItem("run", r["command"], r["anchor"]) for r in runs if r["failure"] == "unresolved"]
    failed_steps = [AttentionItem("step", s["label"], s["anchor"]) for s in all_steps if s["failure"] == "unresolved"]
    refuted = [AttentionItem("refuted", c["claim"], c["anchor"]) for c in claims if c["status"] == "refuted"]
    unverified = [AttentionItem("unverified", c["claim"], c["anchor"]) for c in claims if c["status"] == "unverified"]
    deleted = [AttentionItem("deleted", f["path"], f["anchor"]) for f in files if f["change"] == "deleted"]
    truncated = [AttentionItem("truncated", _label(item), item["anchor"])
                 for item in all_steps + runs + claims + files
                 if len(item.get("evidence", "")) > EVIDENCE_LIMIT]
    derived.attention = failed_runs + failed_steps + refuted + unverified + deleted + truncated
    if report["outcome"] == "pass":
        derived.contradictions = failed_runs + failed_steps + refuted + unverified

    by_number = {"steps": all_steps, "runs": runs}
    by_path = {f["path"]: f for f in files}
    for claim in claims:
        refs = claim.get("refs", {})
        targets = [by_number[key][n - 1]["anchor"] for key in ("steps", "runs") for n in refs.get(key, [])]
        targets += [by_path[path]["anchor"] for path in refs.get("files", [])]
        for target in dict.fromkeys(targets):
            derived.cited_by.setdefault(target, []).append(claim["anchor"])
    return derived


def _label(item: dict) -> str:
    for key in ("label", "command", "claim", "path"):
        if key in item:
            return item[key]
    return item["anchor"]
