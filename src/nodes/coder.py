"""
GLM-5.2 修复节点：接收 Qwen 诊断结果，对 baselife_stock 模块源码生成修复。
当前 v1 采用"生成修复补丁（JSON diff）"模式，由编排器通过 SFTP 应用回 Ubuntu。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from openai import OpenAI
from src.config import settings

FIX_PROMPT = """你是 Odoo 19 后端/前端修复专家。以下是自动化测试失败诊断，请修复 baselife_stock 模块代码。

--- 测试失败信息 ---
{test_summary}

--- Qwen 诊断 ---
{diagnosis}

--- 涉及文件及内容 ---
{files}

要求：
1. 只修复与诊断相关的 bug，不要重构无关代码。
2. 用 JSON 数组输出修改，格式:
[
  {{
    "file": "models/stock_picking.py",
    "action": "replace" | "append" | "delete",
    "old_string": "要替换的原文（精确匹配）",
    "new_string": "替换后的内容"
  }}
]
3. file 路径相对于 baselife_stock/ 模块根目录。
4. 如果无法定位根因或无需修改代码，输出 [] 并在 "note" 字段说明。
5. 只输出 JSON，不要输出其他文字。
"""


class GLMCoder:
    def __init__(self):
        self.client = OpenAI(
            base_url=settings.GLM_BASE_URL,
            api_key=settings.GLM_API_KEY,
        )
        self.model = settings.GLM_MODEL

    def fix(self, test_result: dict, diagnosis: dict, files: dict) -> dict:
        test_summary = {
            "logs": test_result.get("logs", [])[-10:],
            "errors": test_result.get("errors", []),
            "console": test_result.get("console", [])[-10:],
        }
        files_text = "\n\n".join(
            f"### {name}\n```\n{content[:8000]}\n```"
            for name, content in files.items()
        )
        prompt = FIX_PROMPT.format(
            test_summary=json.dumps(test_summary, ensure_ascii=False, indent=2),
            diagnosis=json.dumps(diagnosis, ensure_ascii=False, indent=2),
            files=files_text[:60000],
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        try:
            start = raw.find("[")
            end = raw.rfind("]")
            changes = json.loads(raw[start:end + 1])
            return {"changes": changes, "note": ""}
        except Exception:
            return {"changes": [], "note": raw[:1000]}


if __name__ == "__main__":
    d = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else {"root_cause": "test", "fix_suggestion": "x"}
    r = GLMCoder().fix({"logs": [], "errors": [], "console": []}, d, {})
    print(json.dumps(r, ensure_ascii=False, indent=2))
