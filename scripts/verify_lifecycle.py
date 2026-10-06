#!/usr/bin/env python3
"""Verify both native plugin lifecycles in disposable configuration profiles."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

try:
    from .sync_marketplaces import ROOT, load_catalog, sync
except ImportError:  # Direct script execution.
    from sync_marketplaces import ROOT, load_catalog, sync


def run_command(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, env=env, cwd=cwd, text=True, capture_output=True, timeout=45)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


HOST_DIRECTORIES = (".claude-plugin", ".codex-plugin")
IGNORED_NAMES = ("__pycache__", ".DS_Store")


def tracked_files(root: Path, plugin: Path) -> list[str]:
    """Committed plugin files relative to the plugin directory, excluding generated host manifests."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", plugin.as_posix()],
                            text=True, capture_output=True, check=True).stdout
    files = [Path(name).relative_to(plugin).as_posix() for name in listed.split("\0") if name]
    return sorted(name for name in files if name.split("/")[0] not in HOST_DIRECTORIES)


def compare_tree(expected: list[str], source: Path, installed: Path) -> list[str]:
    """Report expected files missing or changed in the installed copy, and unexpected extra files."""
    problems = []
    for name in expected:
        copied = installed / name
        if not copied.is_file():
            problems.append(f"missing: {name}")
        elif copied.read_bytes() != (source / name).read_bytes():
            problems.append(f"changed: {name}")
    wanted = set(expected)
    for path in installed.rglob("*"):
        relative = path.relative_to(installed)
        if not path.is_file() or relative.parts[0] in HOST_DIRECTORIES:
            continue
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if relative.as_posix() not in wanted:
            problems.append(f"extra: {relative.as_posix()}")
    return sorted(problems)


def plugin_id(item: dict) -> str:
    return item.get("pluginId", item.get("id", ""))


def verify_host(host: str, root: Path, profile: Path) -> dict:
    result = {"host": host, "passed": False, "stages": [], "commands": [], "cleanup_errors": []}
    registered = False
    expected_ids = set()

    def command(stage: str, *args: str) -> str:
        argv = [executable, *args]
        event = {"stage": stage, "command": [host, *args]}
        result["commands"].append(event)
        try:
            completed = run_command(argv, env, work)
        except subprocess.CalledProcessError as error:
            event.update(returncode=error.returncode, stdout=error.stdout, stderr=error.stderr)
            raise RuntimeError(f"{host} {' '.join(args)} failed ({error.returncode}): {error.stderr or error.stdout}") from error
        except Exception as error:
            event["error"] = str(error)
            raise
        event.update(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        return completed.stdout

    def json_command(stage: str, *args: str):
        return json.loads(command(stage, *args))

    def marketplaces(stage: str) -> list[dict]:
        data = json_command(stage, "plugin", "marketplace", "list", "--json")
        return data["marketplaces"] if host == "codex" else data

    def plugins(stage: str) -> dict:
        flags = ["--marketplace", marketplace] if host == "codex" else []
        data = json_command(stage, "plugin", "list", *flags, "--available", "--json")
        require(isinstance(data.get("installed"), list) and isinstance(data.get("available"), list),
                f"{host} returned unsupported plugin list output")
        return data

    def remove_plugin(stage: str, identity: str):
        command(stage, "plugin", "remove" if host == "codex" else "uninstall", identity, "--json")

    try:
        require(host in {"claude", "codex"}, f"Unsupported host: {host}")
        executable = shutil.which(host)
        require(bool(executable), f"Required executable is missing: {host}")
        root, profile = root.resolve(), profile.resolve()
        require(profile.is_dir() and not any(profile.iterdir()), "Verification profile must exist and be empty")
        require(profile not in {Path.home() / ".claude", Path.home() / ".codex"}, "Refusing a normal user configuration directory")
        catalog, entries = load_catalog(root)
        marketplace = catalog["name"]
        expected_ids = {f"{manifest['name']}@{marketplace}" for _, manifest in entries}
        env = os.environ.copy()
        env["CODEX_HOME" if host == "codex" else "CLAUDE_CONFIG_DIR"] = str(profile)
        if host == "codex":
            env["CODEX_SQLITE_HOME"] = str(profile)
        else:
            env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        work = profile / "work"
        work.mkdir()
        result["version"] = command("version", "--version").strip()

        require(sync(root, check=True), "Generated marketplace metadata has drifted")
        if host == "claude":
            command("validation", "plugin", "validate", str(root))
            for path, _ in entries:
                command("validation", "plugin", "validate", str(root / path))
                command("validation", "plugin", "validate", str(root / path / "skills"))
        result["stages"].append("validation")

        require(not marketplaces("isolation"), f"{host} isolation failed: profile already has marketplaces")
        # Use an unfiltered list before any marketplace exists.
        before = json_command("isolation", "plugin", "list", "--available", "--json")
        require(not before["installed"], f"{host} isolation failed: profile already has installed plugins")
        result["stages"].append("empty_profile")

        registered = True  # Also clean up a partially successful registration.
        add_flags = ["--json"] if host == "codex" else []
        command("registration", "plugin", "marketplace", "add", str(root), *add_flags)
        marker = profile / ("config.toml" if host == "codex" else "plugins/known_marketplaces.json")
        require(marker.is_file(), f"{host} did not store marketplace state in its isolated profile")
        listed = marketplaces("registration")
        matching = [item for item in listed if item["name"] == marketplace]
        require(len(matching) == 1, f"Marketplace {marketplace} is missing or duplicated in {host}")
        location = matching[0].get("root", matching[0].get("path", ""))
        require(Path(location).resolve() == root, f"{host} marketplace root differs from the tested repository")
        result["stages"].append("marketplace_registered")

        available = plugins("discovery")
        discovered = {plugin_id(item) for item in available["available"]}
        require(expected_ids <= discovered, f"Missing discoverable plugins: {sorted(expected_ids - discovered)}")
        result["stages"].append("all_plugins_discovered")

        inspections = []
        for path, manifest in entries:
            identity = f"{manifest['name']}@{marketplace}"
            installed = json_command("install", "plugin", "add" if host == "codex" else "install", identity, "--json")
            state = plugins("installed_state")
            matches = [item for item in state["installed"] if plugin_id(item) == identity]
            require(len(matches) == 1 and matches[0].get("enabled") is True,
                    f"Plugin {identity} is not installed and enabled in {host}")
            install_path = installed.get("installedPath") if host == "codex" else matches[0].get("installPath")
            require(bool(install_path), f"No installed path for {identity}")
            cached = Path(install_path).resolve()
            require(cached.is_relative_to(profile), f"Installed {identity} outside isolated profile: {cached}")
            cached_manifest = json.loads((cached / "plugin.json").read_text(encoding="utf-8"))
            require(cached_manifest == manifest, f"Installed portable manifest differs for {identity}")
            problems = compare_tree(tracked_files(root, path), root / path, cached)
            require(not problems, f"Installed files differ from source for {identity}: {', '.join(problems)}")
            skills = [{"name": source.parent.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
                      for source in sorted((root / path / "skills").glob("*/SKILL.md"))]
            if host == "claude":
                inventory = command("skill_inventory", "plugin", "details", manifest["name"])
                require(all(skill["name"] in inventory for skill in skills) and "Skills" in inventory,
                        f"Native skill inventory missing for {identity}")
            inspections.append({"pluginId": identity, "skills": skills, "installedPath": str(cached)})
        result["plugins"] = inspections
        result["stages"].extend(["all_plugins_installed_and_enabled", "installed_files_verified"])

        for identity in sorted(expected_ids):
            remove_plugin("uninstall", identity)
            state = plugins("uninstalled_state")
            require(identity not in {plugin_id(item) for item in state["installed"]},
                    f"Plugin {identity} remains installed in {host}")
        result["stages"].append("all_plugins_uninstalled")

        command("marketplace_removal", "plugin", "marketplace", "remove", marketplace)
        require(marketplace not in {item["name"] for item in marketplaces("removed_state")},
                f"Marketplace {marketplace} remains registered in {host}")
        registered = False
        result["stages"].append("marketplace_removed")
        result["passed"] = True
    except Exception as error:
        result["error"] = str(error)
    finally:
        if registered:
            try:
                leftovers = plugins("cleanup_state")["installed"]
                for item in leftovers:
                    identity = plugin_id(item)
                    if identity in expected_ids:
                        try:
                            remove_plugin("cleanup_plugin", identity)
                        except Exception as error:
                            result["cleanup_errors"].append(str(error))
            except Exception as error:
                result["cleanup_errors"].append(str(error))
            try:
                command("cleanup_marketplace", "plugin", "marketplace", "remove", marketplace)
                require(marketplace not in {item["name"] for item in marketplaces("cleanup_removed_state")},
                        f"Cleanup left marketplace {marketplace} registered")
            except Exception as error:
                result["cleanup_errors"].append(str(error))
        if result["cleanup_errors"]:
            result["passed"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write JSON evidence, including any failures")
    args = parser.parse_args()
    report = {"verifiedAt": datetime.now(timezone.utc).isoformat(), "repository": str(ROOT), "hosts": []}
    with tempfile.TemporaryDirectory(prefix="rickdiculousli-plugin-verification-") as directory:
        for host in ("codex", "claude"):
            print(f"Verifying {host} marketplace and plugin lifecycle…", flush=True)
            profile = Path(directory) / host
            profile.mkdir()
            result = verify_host(host, ROOT, profile)
            report["hosts"].append(result)
            print(f"{host}: {'PASS' if result['passed'] else 'FAIL'} ({result.get('version', 'version unavailable')})", flush=True)
            if not result["passed"]:
                print(result.get("error", "Cleanup failed"), file=sys.stderr)
                for error in result["cleanup_errors"]:
                    print(f"Cleanup: {error}", file=sys.stderr)
    passed = all(host["passed"] for host in report["hosts"])
    report["passed"] = passed
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence: {args.report}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
