from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    vision_model: str = "gpt-4o-mini"

    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"

    tts_provider: str = "edge"
    dashscope_api_key: str = ""
    dashscope_tts_model: str = "cosyvoice-v3-flash"
    dashscope_tts_voice: str = "longanyang"

    ffmpeg_bin_dir: str = ""

    data_dir: Path = Path("./data")
    chroma_dir: Path = Path("./chroma")
    database_url: str = "mysql+pymysql://root:root@127.0.0.1:3306/ai?charset=utf8mb4"

    seed_docs_dir: Path = Path(r"C:/Users/admin/Desktop/理论题")
    seed_doc_files: str = (
        "复盘(1).md,面试题整理_含回答思路.md,AI相关面试题整理.md"
    )

    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    # 会话签名密钥（生产务必修改）；本地演示可用默认值
    session_secret: str = "dev-session-secret-change-me"
    # 启动时若无用户，创建演示管理员账号
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"

    rag_top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 100
    # 知识库问答：False=仅 MySQL/Chroma 检索 + 摘录，不调用 DeepSeek 归纳
    rag_kb_use_llm: bool = False

    max_agent_steps: int = 8
    agent_timeout_seconds: int = 600
    rag_history_rounds: int = 5
    max_image_bytes: int = 10 * 1024 * 1024

    # 趣味视频测试：True=渐变/emoji/动效（非满屏文字）；说「测试结束」改回 False
    video_fun_test: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
