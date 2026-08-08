"""
Qwen2.5VL-Tools 诊断节点：接收 Playwright 失败产物（日志/截图/DOM），
输出结构化诊断报告（JSON），供 GLM 修复节点使用。
"""
import os
import base64
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from openai import OpenAI
from src.config import settings


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


DIAG_PROMPT = """你是 Odoo 19 前端自动化测试诊断专家。以下是 Playwright E2E 测试失败的产物，
请结合【控制台日志】和【截图】分析根因，输出严格 JSON（不要输出任何其他文字）。

失败日志：
{logs}

控制台输出：
{console}

页面错误：
{errors}

输出格式：
{{
  "root_cause": "一句话根因描述",
  "category": "selector_missing | timeout | login_failed | element_hidden | layout_issue | js_error | unknown",
  "evidence": "从日志/截图中观察到的关键证据",
  "confidence": 0.0-1.0,
  "fix_suggestion": "给修复 Agent 的具体修改建议",
  "affected_selectors": ["#id 或 .class"]
}}
"""


class Diagnostician:
    def __init__(self):
        self.client = OpenAI(
            base_url=settings.QWEN_BASE_URL,
            api_key=settings.QWEN_API_KEY,
        )
        self.model = settings.QWEN_MODEL

    def diagnose(self, test_result: dict) -> dict:
        logs = "\n".join(test_result.get("logs", []))[:4000]
        console = "\n".join(test_result.get("console", []))[:3000]
        errors = "\n".join(test_result.get("errors", []))[:3000]

        content: list = [{
            "type": "text",
            "text": DIAG_PROMPT.format(logs=logs, console=console, errors=errors),
        }]

        shot = test_result.get("screenshot")
        if shot and os.path.exists(shot):
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encode_image(shot)}"},
            })

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
            max_tokens=2048,
        )
        raw = resp.choices[0].message.content
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            return json.loads(raw[start:end + 1])
        except Exception:
            return {
                "root_cause": raw[:500],
                "category": "unknown",
                "evidence": "无法解析模型 JSON 输出",
                "confidence": 0.0,
                "fix_suggestion": "请人工检查测试失败日志",
                "affected_selectors": [],
            }


if __name__ == "__main__":
    import time
    result = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else {
        "logs": ["login failed"], "console": [], "errors": ["TIMEOUT: #login not found"]
    }
    d = Diagnostician().diagnose(result)
    print(json.dumps(d, ensure_ascii=False, indent=2))
