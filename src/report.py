import os
import json
from datetime import datetime
from src.config import settings


class Report:
    def __init__(self, report_dir: str | None = None):
        self.dir = report_dir or settings.REPORTS
        os.makedirs(self.dir, exist_ok=True)
        self.entries: list[dict] = []

    def add(self, stage: str, status: str, detail: str = "", extra: dict | None = None):
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "stage": stage,
            "status": status,
            "detail": detail,
        }
        if extra:
            entry.update(extra)
        self.entries.append(entry)
        icon = "OK" if status == "pass" else ("FAIL" if status == "fail" else "..")
        print(f"[{icon}] {stage}: {detail}")

    def save(self, name: str = "report.json") -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"generated": datetime.now().isoformat(), "runs": self.entries},
                      f, ensure_ascii=False, indent=2)
        return path


report = Report()
