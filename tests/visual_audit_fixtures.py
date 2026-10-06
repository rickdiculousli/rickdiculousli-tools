"""Generated reports for scale and all-pass rendering checks."""

PHASES = ("Explore", "Plan", "Build", "Test", "Fix", "Verify")
KINDS = ("read", "read", "search", "read", "edit", "run", "think", "edit")
DIRECTORIES = ("src/core", "src/ui", "src/api", "tests", "tests/fixtures", "docs", "scripts", "config", "assets")


def large_report() -> dict:
    steps = []
    for index in range(300):
        step = {"kind": KINDS[index % len(KINDS)], "label": f"Step {index + 1}: {KINDS[index % len(KINDS)]} work item",
                "phase": PHASES[index * len(PHASES) // 300]}
        if index in (41, 88, 203):
            step.update(kind="run", status="fail", detail="assertion failed in a generated test")
        elif index in (120, 260):
            step.update(status="warn", detail="slow")
        steps.append(step)
    files = []
    for index in range(80):
        directory = DIRECTORIES[index % len(DIRECTORIES)]
        change = "deleted" if index == 7 else "modified" if index % 3 else "added"
        files.append({"path": f"{directory}/file_{index:02d}.py", "change": change,
                      "added": 0 if change == "deleted" else (index * 37) % 400 + 1, "removed": (index * 11) % 90,
                      "hunks": [f"@@ -{index},3 +{index},4 @@\n-old {index}\n+new {index}\n+more {index}"]})
    runs = [{"command": f"pytest tests/test_{index:02d}.py", "exit": 1 if index in (5, 12) else 0,
             "duration_ms": 900 + index * 37, "resolved": index == 5 or None}
            for index in range(20)]
    for run in runs:
        if run["resolved"] is None:
            del run["resolved"]
    return {"version": 1, "title": "Large refactor of the ingestion pipeline", "goal": "Split ingestion into stages",
            "outcome": "partial", "blockers": ["tests/test_12.py still fails on CI data"],
            "next_steps": ["Reproduce CI data locally", "Re-run lifecycle verification"],
            "modules": [{"type": "timeline", "steps": steps}, {"type": "files", "files": files},
                        {"type": "runs", "runs": runs}]}


def all_pass_report() -> dict:
    return {"version": 1, "title": "Fix typo in README", "goal": "Correct the install command", "outcome": "pass",
            "modules": [
                {"type": "timeline", "steps": [
                    {"kind": "read", "label": "Read README.md"},
                    {"kind": "edit", "label": "Fix install command", "source": "observed",
                     "evidence": "-claude plugin instal\n+claude plugin install"},
                    {"kind": "run", "label": "Run tests", "source": "observed", "evidence": "OK"}]},
                {"type": "files", "files": [{"path": "README.md", "change": "modified", "added": 1, "removed": 1,
                                             "source": "observed", "evidence": "1\t1\tREADME.md"}]},
                {"type": "runs", "runs": [{"command": "python3 -m unittest discover -s tests", "exit": 0,
                                           "source": "observed", "evidence": "Ran 12 tests\nOK"}]},
                {"type": "claims", "claims": [{"claim": "README install command is correct", "status": "verified",
                                               "source": "observed", "evidence": "claude plugin install hello-world@…",
                                               "refs": {"files": ["README.md"]}}]}]}
