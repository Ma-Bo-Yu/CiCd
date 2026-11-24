from typing import TYPE_CHECKING, Any

from app.config import get_settings

if TYPE_CHECKING:
    import chromadb

_client: Any = None


def get_chroma_client():
    global _client
    if _client is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        settings = get_settings()
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


def get_or_create_collection(kb_id: str):
    client = get_chroma_client()
    return client.get_or_create_collection(name=collection_name(kb_id))


def delete_kb_collection(kb_id: str) -> None:
    client = get_chroma_client()
    name = collection_name(kb_id)
    try:
        client.delete_collection(name)
    except Exception:
        pass
