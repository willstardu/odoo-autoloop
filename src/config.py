import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _get(key: str, default: str = "") -> str:
    v = os.getenv(key, default)
    if v is None or v.strip() == "":
        return default
    return v.strip()


class Settings:
    # GLM-5.2 (TokenHub)
    GLM_BASE_URL = _get("GLM_BASE_URL", "https://api.tokenhub.market/v1")
    GLM_API_KEY = _get("GLM_API_KEY")
    GLM_MODEL = _get("GLM_MODEL", "glm-5.2")

    # Qwen (Ollama)
    QWEN_BASE_URL = _get("QWEN_BASE_URL", "http://192.168.108.143:11434/v1")
    QWEN_API_KEY = _get("QWEN_API_KEY", "ollama")
    QWEN_MODEL = _get("QWEN_MODEL", "qwen2.5vl-tools:latest")

    # Odoo
    ODOO_URL = _get("ODOO_URL", "http://192.168.108.134:8069")
    ODOO_DB = _get("ODOO_DB")
    ODOO_USER = _get("ODOO_USER", "admin")
    ODOO_PASSWORD = _get("ODOO_PASSWORD")

    # Orchestration
    MAX_RETRIES = int(_get("MAX_RETRIES", "3"))
    HEADLESS = _get("HEADLESS", "true").lower() in ("1", "true", "yes")

    # Paths
    BASE_DIR = BASE_DIR
    WORKSPACE = os.path.join(BASE_DIR, "workspace")
    ARTIFACTS = os.path.join(BASE_DIR, "artifacts")
    SCREENSHOTS = os.path.join(ARTIFACTS, "screenshots")
    REPORTS = os.path.join(ARTIFACTS, "reports")

    def validate(self):
        missing = []
        if not self.GLM_API_KEY:
            missing.append("GLM_API_KEY")
        if not self.ODOO_PASSWORD:
            missing.append("ODOO_PASSWORD")
        if missing:
            raise RuntimeError(f".env 缺少必要配置: {', '.join(missing)}")
        return self


settings = Settings()
