from delegation_support import isolate_xdg, state_payload
from pathlib import Path
import tempfile
import unittest

from delegation_support import configure_git, git, git_repo, run_cli

from delegation_check import DelegationError
from delegation_check.tree import repo_root, state_dir, tree_hash


class TreeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        isolate_xdg(self, Path(tmp.name))
        self.tmp = Path(tmp.name)
        self.root = git_repo(self.tmp / "repo")

    def test_stable_when_nothing_changes(self):
        self.assertEqual(tree_hash(self.root), tree_hash(self.root))

    def test_changes_on_edit_untracked_and_extra_input(self):
        t0 = tree_hash(self.root)
        (self.root / "a.txt").write_text("b\n")
        t1 = tree_hash(self.root)
        (self.root / "new.txt").write_text("n\n")
        t2 = tree_hash(self.root)
        self.assertEqual(len({t0, t1, t2}), 3)
        (self.root / ".gitignore").write_text("golden/\n")
        (self.root / "golden").mkdir()
        (self.root / "golden/t.bin").write_bytes(b"1")
        e1 = tree_hash(self.root, ["golden"])
        (self.root / "golden/t.bin").write_bytes(b"2")
        self.assertNotEqual(e1, tree_hash(self.root, ["golden"]))
        self.assertEqual(len(e1), 64)
        self.assertEqual(len(tree_hash(self.root)), 40)

    def test_missing_extra_input_is_distinct_from_present(self):
        missing = tree_hash(self.root, ["nope.bin"])
        (self.root / "nope.bin").write_bytes(b"")
        self.assertNotEqual(missing, tree_hash(self.root, ["nope.bin"]))

    def test_ignored_file_does_not_change_tree(self):
        (self.root / ".gitignore").write_text("build/\n")
        t0 = tree_hash(self.root)
        (self.root / "build").mkdir()
        (self.root / "build/out.o").write_bytes(b"x")
        self.assertEqual(t0, tree_hash(self.root))

    def test_never_touches_real_index(self):
        (self.root / "a.txt").write_text("staged\n")
        git(self.root, "add", "a.txt")
        (self.root / "a.txt").write_text("worktree\n")
        index = self.root / ".git" / "index"
        before = (index.read_bytes(), git(self.root, "diff", "--cached", "--name-only").stdout)
        tree_hash(self.root)
        after = (index.read_bytes(), git(self.root, "diff", "--cached", "--name-only").stdout)
        self.assertEqual(before, after)
        self.assertFalse((self.root / ".git" / "index.lock").exists())

    def test_state_dir_does_not_change_tree(self):
        t0 = tree_hash(self.root)
        (state_payload(self.root) / "ledger.jsonl").write_text("{}\n")
        self.assertEqual(t0, tree_hash(self.root))
        self.assertEqual(list(state_dir(self.root).glob("tmp-index-*")), [])
        self.assertFalse((self.root / ".delegation").exists())

    def test_repo_without_commits(self):
        root = self.tmp / "empty"
        root.mkdir()
        git(root, "init", "-q")
        configure_git(root)
        (root / "f.txt").write_text("x\n")
        self.assertRegex(tree_hash(root), r"\A[0-9a-f]{40}\Z")

    def test_linked_worktree(self):
        wt = self.tmp / "wt"
        git(self.root, "worktree", "add", "-q", str(wt))
        before = {p.name for p in wt.iterdir()}
        self.assertRegex(tree_hash(wt), r"\A[0-9a-f]{40}\Z")
        self.assertEqual(before, {p.name for p in wt.iterdir()})
        self.assertFalse((wt / ".delegation").exists())
        self.assertFalse((self.root / ".agents").exists())
        self.assertEqual(repo_root(wt).resolve(), wt.resolve())

    def snapshot(self, git_dir):
        return {
            str(p.relative_to(git_dir)): p.read_bytes()
            for p in git_dir.rglob("*")
            if p.is_file()
        }

    def test_clean_tree_matches_git_write_tree(self):
        self.assertEqual(tree_hash(self.root), git(self.root, "write-tree").stdout.strip())

    def test_writes_nothing_under_git_main_checkout(self):
        (self.root / "a.txt").write_text("edited\n")
        (self.root / "untracked.txt").write_text("u\n")
        git_dir = self.root / ".git"
        before = self.snapshot(git_dir)
        tree_hash(self.root)
        self.assertEqual(before, self.snapshot(git_dir))
        self.assertEqual(list((self.root / ".delegation").glob("tmp-*")), [])

    def test_writes_nothing_under_git_linked_worktree(self):
        wt = self.tmp / "wt"
        git(self.root, "worktree", "add", "-q", str(wt))
        (wt / "a.txt").write_text("edited\n")
        (wt / "untracked.txt").write_text("u\n")
        git_dir = self.root / ".git"
        before = self.snapshot(git_dir)
        tree_hash(wt)
        self.assertEqual(before, self.snapshot(git_dir))
        self.assertEqual(list((wt / ".delegation").glob("tmp-*")), [])

    def test_relative_root(self):
        import os
        old = os.getcwd()
        os.chdir(self.root.parent)
        self.addCleanup(os.chdir, old)
        self.assertEqual(tree_hash(Path("repo")), tree_hash(self.root))

    def test_repo_root_from_subdirectory(self):
        (self.root / "sub").mkdir()
        self.assertEqual(repo_root(self.root / "sub").resolve(), self.root.resolve())

    def test_not_a_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        with self.assertRaises(DelegationError):
            repo_root(plain)
        self.assertEqual(run_cli(plain, "tree").returncode, 2)

    def test_cli_tree_prints_hash(self):
        self.assertRegex(run_cli(self.root, "tree").stdout.strip(), r"\A[0-9a-f]{40}\Z")


if __name__ == "__main__":
    unittest.main()
