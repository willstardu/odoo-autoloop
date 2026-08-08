"""
SFTP 工具：与 Ubuntu (192.168.108.134) 交换 baselife_stock 模块源码。
支持拉取模块到本地、应用修复补丁回远程。
"""
import os
import sys
import json
import stat as stat_mod

import paramiko

REMOTE_HOST = "192.168.108.134"
REMOTE_USER = "root"
REMOTE_PASS = "Bp20220726;"
REMOTE_MODULE = "/opt/custom-addons/baselife_stock"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_MODULE = os.path.join(PROJECT_ROOT, "workspace", "baselife_stock")

# 需要同步的文件白名单（排除 pycache / 备份）
SYNC_WHITELIST = (".py", ".xml", ".csv", ".js", ".scss", ".css", ".ts", ".png", ".svg", ".md", ".rst", ".pot", ".po", ".toml", ".json", ".cfg", ".txt")
EXCLUDE_DIRS = ("__pycache__", ".git", "static/description", "i18n", "tests")


class SftpSync:
    def __init__(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(REMOTE_HOST, 22, REMOTE_USER, REMOTE_PASS, timeout=20)
        self.sftp = self.client.open_sftp()

    def close(self):
        self.sftp.close()
        self.client.close()

    # ---------- pull: Ubuntu -> local ----------
    def pull_module(self):
        os.makedirs(LOCAL_MODULE, exist_ok=True)
        pulled = []
        self._walk_pull(REMOTE_MODULE, LOCAL_MODULE, pulled)
        return pulled

    def _walk_pull(self, remote_dir, local_dir, pulled):
        for entry in self.sftp.listdir_attr(remote_dir):
            name = entry.filename
            rpath = f"{remote_dir}/{name}"
            lpath = os.path.join(local_dir, name)
            is_dir = stat_mod.S_ISDIR(entry.st_mode)
            if is_dir:  # dir
                if name in EXCLUDE_DIRS:
                    continue
                os.makedirs(lpath, exist_ok=True)
                self._walk_pull(rpath, lpath, pulled)
            else:
                if not name.endswith(SYNC_WHITELIST):
                    continue
                self.sftp.get(rpath, lpath)
                pulled.append(name)

    # ---------- apply patch -> Ubuntu ----------
    def apply_changes(self, changes: list):
        """应用 JSON diff。每条: {file, action, old_string, new_string}"""
        results = []
        for change in changes:
            file = change.get("file", "")
            action = change.get("action", "replace")
            rpath = f"{REMOTE_MODULE}/{file.lstrip('/')}"
            try:
                with self.sftp.open(rpath, "r") as f:
                    content = f.read().decode("utf-8", "replace")
            except FileNotFoundError:
                content = ""
                if action == "replace":
                    results.append({"file": file, "status": "fail", "msg": "remote file not found"})
                    continue

            if action == "replace":
                old = change.get("old_string", "")
                new = change.get("new_string", "")
                if old and old in content:
                    content = content.replace(old, new, 1)
                else:
                    results.append({"file": file, "status": "fail", "msg": "old_string not found in remote file"})
                    continue
            elif action == "append":
                content += "\n" + change.get("new_string", "")
            elif action == "delete":
                old = change.get("old_string", "")
                if old and old in content:
                    content = content.replace(old, "", 1)
                else:
                    results.append({"file": file, "status": "fail", "msg": "old_string not found"})
                    continue

            with self.sftp.open(rpath, "w") as f:
                f.write(content.encode("utf-8"))
            results.append({"file": file, "status": "ok"})
        return results

    # ---------- restart odoo ----------
    def restart_odoo(self) -> str:
        _, stdout, stderr = self.client.exec_command("systemctl restart odoo19.service && echo RESTART_OK", timeout=120)
        out = stdout.read().decode()
        err = stderr.read().decode()
        return (out + err).strip()


if __name__ == "__main__":
    s = SftpSync()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "pull":
            pulled = s.pull_module()
            print(json.dumps({"pulled": len(pulled), "files": pulled}, ensure_ascii=False, indent=2))
        else:
            s.close()
            print("usage: python sftp_tool.py pull")
    finally:
        s.close()
