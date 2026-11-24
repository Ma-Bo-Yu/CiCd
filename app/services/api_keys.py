"""判断 API Key 是否为有效配置（排除 .env 占位符）。"""


def is_configured_api_key(key: str | None) -> bool:
    if not key:
        return False
    k = key.strip()
    if len(k) < 10:
        return False
    lower = k.lower()
    placeholders = {
        "sk-xxx",
        "sk-xxxx",
        "xxx",
        "your-api-key",
        "your_api_key",
        "changeme",
        "paste-your-key",
    }
    if lower in placeholders:
        return False
    if lower.startswith("sk-") and "xxx" in lower:
        return False
    return True
