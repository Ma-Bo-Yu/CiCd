from app.config import get_settings


def trim_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """保留最近 N 轮对话（PRD N=5）。"""
    settings = get_settings()
    rounds = getattr(settings, "rag_history_rounds", 5)
    max_messages = rounds * 2
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]
