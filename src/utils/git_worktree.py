"""
Git Worktree 管理：让 GLM 的修复在独立 worktree 分支中进行，
测试通过后合并回主分支，避免污染主工作区。
"""
import os
import re
import subprocess
import datetime


class GitWorktree:
    def __init__(self, repo_dir: str):
        self.repo = repo_dir
        self.worktrees: list[str] = []

    def _git(self, *args: str) -> str:
        cmd = ["git", "-C", self.repo, *args]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    def _git_ok(self, *args: str) -> bool:
        cmd = ["git", "-C", self.repo, *args]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode == 0

    def baseline_commit(self) -> str:
        """返回当前主分支 HEAD（修复前基线）"""
        return self._git("rev-parse", "HEAD")

    def create_worktree(self, base_dir: str, label: str) -> str:
        """创建独立 worktree，返回其路径"""
        safe = re.sub(r"[^0-9a-zA-Z_-]", "_", label)
        branch = f"fix/{safe}_{datetime.datetime.now().strftime('%H%M%S')}"
        path = os.path.join(base_dir, f"wt_{safe}")
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
        self._git("worktree", "add", "-b", branch, path)
        self.worktrees.append(path)
        return path

    def reset_worktree(self, path: str):
        """重置 worktree 到基线（丢弃 GLM 修改）"""
        self._git_ok("worktree", "prune")
        subprocess.run(["git", "-C", path, "reset", "--hard", "HEAD"], capture_output=True)
        subprocess.run(["git", "-C", path, "clean", "-fd"], capture_output=True)

    def commit_worktree(self, path: str, message: str):
        """在 worktree 中提交修复"""
        subprocess.run(["git", "-C", path, "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", path, "commit", "-m", message], capture_output=True)

    def worktree_branch(self, path: str) -> str:
        """获取 worktree 当前分支名"""
        r = subprocess.run(["git", "-C", path, "branch", "--show-current"], capture_output=True, text=True)
        return r.stdout.strip()

    def merge_to_main(self, path: str) -> str:
        """把 worktree 分支合并回主分支，返回合并后的 commit"""
        branch = self.worktree_branch(path)
        self._git("checkout", self.main_branch())
        self._git("merge", "--no-edit", branch)
        commit = self._git("rev-parse", "HEAD")
        self.remove_worktree(path)
        return commit

    def main_branch(self) -> str:
        r = subprocess.run(["git", "-C", self.repo, "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True)
        return r.stdout.strip()

    def remove_worktree(self, path: str):
        subprocess.run(["git", "-C", self.repo, "worktree", "remove", "--force", path], capture_output=True)
        if path in self.worktrees:
            self.worktrees.remove(path)

    def is_dirty(self, path: str) -> bool:
        r = subprocess.run(["git", "-C", path, "status", "--porcelain"], capture_output=True, text=True)
        return bool(r.stdout.strip())

    def cleanup_all(self):
        for path in list(self.worktrees):
            self.remove_worktree(path)
        self._git_ok("worktree", "prune")

    def log(self, n: int = 10) -> list[str]:
        return self._git("log", "--oneline", f"-{n}").splitlines()


import shutil
