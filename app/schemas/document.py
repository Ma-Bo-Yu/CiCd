from datetime import datetime

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: str
    kb_id: str
    filename: str
    mime_type: str
    status: str
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
