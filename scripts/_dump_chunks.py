import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db import SessionLocal
from app.models.chunk import Chunk
from app.models.document import Document

out = ROOT / "scripts" / "_chunk_dump.txt"
with SessionLocal() as db:
    d = db.scalars(select(Document).where(Document.filename.like("%口语背诵%"))).first()
    lines = [d.filename, d.id, ""]
    for i in range(0, 12):
        c = db.scalars(select(Chunk).where(Chunk.chroma_id == f"{d.id}_{i}")).first()
        lines.append(f"=== {i} ===")
        lines.append(c.text[:600] if c else "missing")
        lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out)
