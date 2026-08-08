"""
自动编程 + 自动测试流水线（v2 - worktree 隔离版）
流程：
  E2E 测试 → (通过则结束)
  → 失败 → 创建 Git worktree 分支
  → Qwen 诊断 → GLM 在 worktree 中修复
  → SFTP 推送 + 重启 Odoo → 重新测试
  → 通过则合并回主分支；连续失败则重置 worktree 重试
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.config import settings
from src.nodes.diagnostician import Diagnostician
from src.nodes.coder import GLMCoder
from src.utils.sftp_tool import SftpSync, LOCAL_MODULE
from src.utils.git_worktree import GitWorktree

settings.validate()

WT_BASE = os.path.join(settings.WORKSPACE, "worktrees")
os.makedirs(WT_BASE, exist_ok=True)


def list_module_files(root: str) -> dict:
    """读取模块所有源码文件（供 GLM 上下文）"""
    files = {}
    for r, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for name in names:
            if not name.endswith((".py", ".xml", ".csv", ".js")):
                continue
            path = os.path.join(r, name)
            rel = os.path.relpath(path, root)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    files[rel] = f.read()
            except Exception:
                pass
    return files


def push_module(module_dir: str) -> bool:
    """将指定目录（主工作区或 worktree）推送到远程 Ubuntu"""
    sftp = SftpSync()
    try:
        pushed = []
        for r, dirs, names in os.walk(module_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for name in names:
                if not name.endswith((".py", ".xml", ".csv", ".js", ".md", ".png", ".svg")):
                    continue
                lpath = os.path.join(r, name)
                rel = os.path.relpath(lpath, module_dir)
                rpath = f"{sftp.REMOTE_MODULE}/{rel.replace(os.sep, '/')}"
                if not _remote_dir_exists(sftp, os.path.dirname(rpath)):
                    _remote_mkdirs(sftp, os.path.dirname(rpath))
                sftp.sftp.put(lpath, rpath)
                pushed.append(rel)
        print(f"    [push] {len(pushed)} files -> {sftp.REMOTE_MODULE}")
        return True
    except Exception as e:
        print(f"    [push] FAILED: {e}")
        return False
    finally:
        sftp.close()


def _remote_dir_exists(sftp, path: str) -> bool:
    try:
        sftp.sftp.stat(path)
        return True
    except Exception:
        return False


def _remote_mkdirs(sftp, path: str):
    parts = []
    cur = path
    while cur and cur != "/":
        parts.append(cur)
        cur = os.path.dirname(cur)
    for p in reversed(parts):
        try:
            sftp.sftp.mkdir(p)
        except Exception:
            pass


def restart_odoo() -> str:
    sftp = SftpSync()
    try:
        return sftp.restart_odoo()
    finally:
        sftp.close()


def apply_change(change: dict, module_dir: str):
    rel = change.get("file", "")
    action = change.get("action", "replace")
    lpath = os.path.join(module_dir, rel.replace("/", os.sep))
    if action == "replace":
        old, new = change.get("old_string", ""), change.get("new_string", "")
        if not os.path.exists(lpath):
            print(f"    !! file not found: {rel}")
            return
        with open(lpath, "r", encoding="utf-8") as f:
            content = f.read()
        if old in content:
            content = content.replace(old, new, 1)
            with open(lpath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"    applied: {rel} (replace)")
        else:
            print(f"    !! old_string not found in {rel}")
    elif action == "append":
        os.makedirs(os.path.dirname(lpath), exist_ok=True)
        with open(lpath, "a", encoding="utf-8") as f:
            f.write("\n" + change.get("new_string", ""))
        print(f"    applied: {rel} (append)")


def main():
    max_retries = settings.MAX_RETRIES
    wt = GitWorktree(LOCAL_MODULE)
    active_wt: str | None = None
    diagnosis = None
    test_result = None

    print(f"{'='*60}")
    print(f"Odoo19 Auto Coder+Test Loop (v2 worktree) | target={settings.ODOO_URL} | max_retries={max_retries}")
    print(f"module: {LOCAL_MODULE}")
    print(f"{'='*60}")

    for task_round in range(1, max_retries + 2):  # 首轮测试 + max_retries 次修复
        print(f"\n--- Round {task_round} ---")

        # 1. E2E 测试
        from tests.e2e_odoo import run_e2e
        print("[1/3] Running Playwright E2E ...")
        test_result = run_e2e()

        if test_result.get("passed"):
            print("\n[TESTS PASSED]")
            if active_wt:
                print("    merging worktree to main ...")
                try:
                    commit = wt.merge_to_main(active_wt)
                    print(f"    merged: {commit}")
                    active_wt = None
                except Exception as e:
                    print(f"    merge failed (keeping worktree): {e}")
            report = {
                "passed": True,
                "round": task_round,
                "result": test_result,
                "diagnosis": diagnosis,
                "worktree_merged": active_wt is None,
            }
            with open(os.path.join(settings.REPORTS, "final_report.json"), "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            return 0

        print(f"[TESTS FAILED (round {task_round})]")
        if task_round > max_retries:
            print("Max retries reached. Saving failure artifacts.")
            with open(os.path.join(settings.REPORTS, "final_report.json"), "w", encoding="utf-8") as f:
                json.dump({"passed": False, "round": task_round, "result": test_result,
                           "diagnosis": diagnosis}, f, ensure_ascii=False, indent=2)
            return 1

        # 2. Qwen 诊断
        print("[2/3] Qwen diagnosing ...")
        diagnosis = Diagnostician().diagnose(test_result)
        print(f"    root_cause: {diagnosis.get('root_cause')}")
        print(f"    category:   {diagnosis.get('category')} (conf={diagnosis.get('confidence')})")

        # 3. 准备 worktree
        if active_wt is None:
            print("[3/3] creating fix worktree ...")
            active_wt = wt.create_worktree(WT_BASE, f"round{task_round}")
            print(f"    worktree: {active_wt}")
        else:
            print("[3/3] resetting worktree to baseline ...")
            wt.reset_worktree(active_wt)

        # 4. GLM 修复（作用于 worktree）
        module_dir = active_wt
        files = list_module_files(module_dir)
        fix = GLMCoder().fix(test_result, diagnosis, files)
        changes = fix.get("changes", [])

        if not changes:
            print("    GLM produced no code changes; note:", fix.get("note", "")[:300])
            time.sleep(3)
            continue

        for c in changes:
            apply_change(c, module_dir)
        print(f"    applied {len(changes)} changes in worktree")

        # 5. 提交 worktree + 推送远程 + 重启 Odoo
        wt.commit_worktree(module_dir, f"auto-fix round {task_round}")
        print("    pushing worktree to Ubuntu & restarting odoo ...")
        if push_module(module_dir):
            out = restart_odoo()
            print(f"    odoo restart: {out[-80:]}")
        time.sleep(8)

    print("\nLoop finished.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
