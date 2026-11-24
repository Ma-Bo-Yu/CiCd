from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.chroma_store import get_or_create_collection
from app.services.citations import build_citation, format_context_for_prompt
from app.services.llm import LLMService
from app.services.text_utils import KB_MISS_REPLY, plain_text_from_chunk, strip_html

RAG_SYSTEM_TEMPLATE = """你是基于知识库的问答助手。请严格根据以下「参考资料」回答问题。
规则：
1. 仅使用参考资料中的信息；资料不足时明确说「知识库中未找到相关信息」。
2. 不要编造参考资料中不存在的事实。
3. 只输出直接答案，不要写「根据资料」「来源如下」、不要列编号、不要复述参考资料标题。

参考资料：
{context_with_indexed_chunks}

请用中文简洁回答。"""


class RetrievedChunk:
    def __init__(
        self,
        chunk: Chunk,
        document: Document,
        metadata: dict,
        distance: float,
        score: int = 0,
    ):
        self.chunk = chunk
        self.document = document
        self.metadata = metadata
        self.distance = distance
        self.score = score


def _query_terms(query: str) -> list[str]:
    q = query.strip()
    terms: list[str] = []
    terms.extend(re.findall(r"[A-Za-z0-9_]{2,}", q))
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", q))
    if q and not terms:
        terms.append(q)
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            out.append(t)
    return out


_GENERIC_QUERY_TERMS = frozenset(
    {
        "rag",
        "pdf",
        "知识库",
        "文档",
        "如何",
        "进行",
        "什么",
        "怎么",
        "为什么",
        "是否",
        "哪些",
        "等",
    }
)


def _question_anchors(question: str) -> list[str]:
    q = question.strip()
    anchors: list[str] = []
    if "入库" in q:
        anchors.extend(
            [
                "是怎么进行入库",
                "如何进行入库",
                "入库的？",
                "入库层",
                "解析层",
                "分块层",
                "入库 pipeline",
            ]
        )
    for t in _query_terms(q):
        if len(t) >= 4 and t.lower() not in _GENERIC_QUERY_TERMS:
            anchors.append(t)
    q_compact = re.sub(r"[\s？?，,。.!！\"\"'']", "", q)
    if len(q_compact) >= 10:
        anchors.append(q_compact[:24])
        anchors.append(q_compact.replace("是如何", "是怎么")[:24])
    seen: set[str] = set()
    out: list[str] = []
    for a in anchors:
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


class RAGService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm or LLMService()
        self.settings = get_settings()

    def retrieve_keyword(self, kb_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        terms = _query_terms(query)
        if not terms:
            return []

        chunks = self.db.scalars(select(Chunk).where(Chunk.kb_id == kb_id)).all()
        if not chunks:
            return []

        doc_ids = {c.document_id for c in chunks}
        docs = self.db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
        doc_map = {d.id: d for d in docs}

        min_score = max(1, len(terms) // 3)
        scored: list[tuple[int, Chunk]] = []
        for chunk in chunks:
            raw = chunk.text
            plain = strip_html(raw).lower()
            score = 0
            matched = 0
            for term in terms:
                tl = term.lower()
                if tl in _GENERIC_QUERY_TERMS and len(term) <= 4:
                    weight = 1
                elif len(term) >= 4:
                    weight = 4
                else:
                    weight = 2
                if tl in plain or term in raw:
                    matched += 1
                    score += (plain.count(tl) + raw.count(term)) * weight
            for anchor in _question_anchors(query):
                if anchor in raw:
                    score += 12
            if matched >= 1 and score >= min_score:
                scored.append((score, chunk))

        scored.sort(key=lambda x: (-x[0], len(x[1].text)))
        retrieved: list[RetrievedChunk] = []
        for score, chunk in scored[:top_k]:
            doc = doc_map.get(chunk.document_id)
            if doc is None:
                continue
            meta = json.loads(chunk.metadata_json or "{}")
            retrieved.append(
                RetrievedChunk(
                    chunk=chunk,
                    document=doc,
                    metadata=meta,
                    distance=1.0 / (score + 1),
                    score=score,
                )
            )
        return retrieved

    async def retrieve(self, kb_id: str, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or self.settings.rag_top_k

        if self.llm.embed_demo:
            kw = self.retrieve_keyword(kb_id, query, top_k=top_k)
            return self._inject_extractive_chunk(kb_id, query, kw, top_k)

        query_vec = (await self.llm.embed_texts([query]))[0]
        collection = get_or_create_collection(kb_id)
        try:
            result = collection.query(
                query_embeddings=[query_vec],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            kw = self.retrieve_keyword(kb_id, query, top_k=top_k)
            return self._inject_extractive_chunk(kb_id, query, kw, top_k)

        ids = result.get("ids", [[]])[0]
        if not ids:
            kw = self.retrieve_keyword(kb_id, query, top_k=top_k)
            return self._inject_extractive_chunk(kb_id, query, kw, top_k)

        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        chunks = self.db.scalars(select(Chunk).where(Chunk.chroma_id.in_(ids))).all()
        chunk_by_chroma = {c.chroma_id: c for c in chunks}
        doc_ids = {c.document_id for c in chunks}
        docs = self.db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
        doc_map = {d.id: d for d in docs}

        retrieved: list[RetrievedChunk] = []
        for chroma_id, dist, meta in zip(ids, distances, metadatas):
            chunk = chunk_by_chroma.get(chroma_id)
            if chunk is None:
                continue
            doc = doc_map.get(chunk.document_id)
            if doc is None:
                continue
            meta_dict = meta or json.loads(chunk.metadata_json or "{}")
            retrieved.append(
                RetrievedChunk(
                    chunk=chunk, document=doc, metadata=meta_dict, distance=dist, score=1
                )
            )
        if not retrieved:
            kw = self.retrieve_keyword(kb_id, query, top_k=top_k)
            return self._inject_extractive_chunk(kb_id, query, kw, top_k)
        retrieved = self._inject_extractive_chunk(kb_id, query, retrieved, top_k)
        return retrieved

    def _score_chunk_extractive(self, chunk: Chunk, question: str) -> int:
        raw = chunk.text or ""
        plain = plain_text_from_chunk(raw, single_line=True)
        score = 0
        for anchor in _question_anchors(question):
            if anchor in raw or anchor in plain:
                score += 10
        q_pat = re.compile(
            r"\d+\.\s+[^<\n]{4,120}?(?:入库|分割|metadata|召回|chunk)[^<\n]{0,80}[？?]"
        )
        for m in q_pat.finditer(raw):
            line = m.group(0)
            if sum(1 for t in _query_terms(question) if t in line) >= 2:
                score += 18
        if "入库" in question and "解析层" in raw and "入库层" in raw:
            score += 25
        if "入库" in question and "是怎么进行入库" in raw:
            score += 30
        qn = re.sub(r"[\s？?，,]+", "", question)
        pn = re.sub(r"[\s？?，,]+", "", plain)
        if len(qn) >= 8 and qn[:12] in pn.replace("是如何", "是怎么"):
            score += 20
        return score

    def _find_best_extractive_chunk(
        self, kb_id: str, question: str, doc_ids: set[str] | None = None
    ) -> tuple[int, RetrievedChunk] | None:
        chunks = self.db.scalars(select(Chunk).where(Chunk.kb_id == kb_id)).all()
        if not chunks:
            return None
        doc_id_set = doc_ids or {c.document_id for c in chunks}
        docs = self.db.scalars(
            select(Document).where(Document.id.in_(doc_id_set))
        ).all()
        doc_map = {d.id: d for d in docs}

        def pick(pool: list[Chunk]) -> tuple[int, RetrievedChunk] | None:
            best_score = 0
            best_rc: RetrievedChunk | None = None
            for chunk in pool:
                sc = self._score_chunk_extractive(chunk, question)
                if sc > best_score:
                    doc = doc_map.get(chunk.document_id)
                    if doc is None:
                        continue
                    meta = json.loads(chunk.metadata_json or "{}")
                    best_score = sc
                    best_rc = RetrievedChunk(
                        chunk, doc, meta, distance=0.05, score=sc
                    )
            if best_rc is None or best_score <= 0:
                return None
            return best_score, best_rc

        scoped = [c for c in chunks if c.document_id in doc_id_set]
        hit = pick(scoped)
        if hit and hit[0] >= 15:
            return hit
        return pick(chunks)

    def _inject_extractive_chunk(
        self,
        kb_id: str,
        question: str,
        retrieved: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        doc_ids = {r.document.id for r in retrieved}
        hit = self._find_best_extractive_chunk(kb_id, question, doc_ids)
        if hit is None:
            return retrieved
        score, rc = hit
        if score < 15:
            return retrieved
        if any(r.chunk.id == rc.chunk.id for r in retrieved):
            return retrieved
        return [rc] + retrieved[: max(1, top_k - 1)]

    def _answer_plausible(self, question: str, block: str) -> bool:
        if len(block.strip()) < 50:
            return False
        if "color:" in block or '="' in block or ">  <span" in block:
            return False
        if "先说结论" not in block and not re.search(
            r"第[一二三四五][，、,]", block
        ):
            return False
        if "入库" in question and not (
            "解析层" in block or "入库层" in block
        ):
            return False
        m1 = re.search(r"第一[，、,]", block)
        m3 = re.search(r"第三[，、,]", block)
        if m1 and m3 and m1.start() >= m3.start():
            return False
        return True

    def _extract_conclusion_from_raw(self, question: str, raw: str) -> str:
        m = re.search(
            r"先说结论[\s\S]*?(?=</span>\s*\*\*<span|\*\*<span\s+style=\"color:#1565C0\">\s*\d+\.|$)",
            raw,
        )
        segment = m.group(0) if m else raw
        return self._extract_answer_block(question, segment)

    def low_confidence(self, retrieved: list[RetrievedChunk], threshold: float = 0.3) -> bool:
        if not retrieved:
            return True
        if self.llm.embed_demo:
            return False
        best = min(r.distance for r in retrieved)
        return best > threshold

    def _normalize_compare_text(self, s: str) -> str:
        s = strip_html(s)
        s = re.sub(r"[\s\d\.\*\#>`\-_|]+", "", s)
        return s.lower()

    def _line_echoes_question(self, line: str, question: str) -> bool:
        line = line.strip()
        if len(line) < 6:
            return True
        ql = self._normalize_compare_text(question)
        ll = self._normalize_compare_text(line)
        if not ql or not ll:
            return False
        if ll == ql or (ql in ll and len(ll) <= len(ql) + 8):
            return True
        if line.rstrip().endswith("？") and len(line) < 100:
            if "答" not in line and "思路" not in line and "解析" not in line:
                return True
        return False

    def _chunk_doc_index(self, chunk: Chunk) -> int:
        m = re.search(r"_(\d+)$", chunk.chroma_id or "")
        return int(m.group(1)) if m else 0

    _CN_ORDINAL = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}

    def _sort_cn_numbered_body(self, text: str) -> str:
        """面试稿里「第一/第二/第三」在同段或切片乱序时，按序号排回正序。"""
        parts = re.split(r"(第[一二三四五][，、,\s]+)", text)
        if len(parts) < 3:
            return text
        prefix = parts[0].rstrip()
        sections: list[tuple[int, str]] = []
        i = 1
        while i + 1 < len(parts):
            label = parts[i]
            body = parts[i + 1]
            m = re.search(r"第([一二三四五])", label)
            if not m:
                i += 2
                continue
            order = self._CN_ORDINAL.get(m.group(1), 99)
            sections.append((order, (label + body).strip()))
            i += 2
        if len(sections) < 2 or any(o > 5 for o, _ in sections):
            return text
        sections.sort(key=lambda x: x[0])
        body = "\n\n".join(s for _, s in sections)
        return f"{prefix}\n\n{body}".strip() if prefix else body

    def _score_chunk_for_question(self, rc: RetrievedChunk, question: str) -> int:
        plain = plain_text_from_chunk(rc.chunk.text, single_line=True).lower()
        terms = _query_terms(question)
        score = sum(3 if t.lower() in plain else 0 for t in terms)
        q_norm = re.sub(r"[\s？?，,。.!！]", "", question).lower()
        p_norm = re.sub(r"[\s？?，,。.!！]", "", plain)
        if len(q_norm) >= 8 and q_norm[:12] in p_norm:
            score += 15
        if "？" in rc.chunk.text or "?" in rc.chunk.text:
            head = plain[:180]
            if sum(1 for t in terms if t.lower() in head) >= max(2, len(terms) // 2):
                score += 12
        return score

    def _filter_retrieved_for_question(
        self, retrieved: list[RetrievedChunk], question: str
    ) -> list[RetrievedChunk]:
        if not retrieved:
            return retrieved
        scored = [(self._score_chunk_for_question(rc, question), rc) for rc in retrieved]
        scored.sort(key=lambda x: (-x[0], x[1].distance))
        best = scored[0][0]
        if best <= 0:
            return retrieved
        keep = max(2, best // 2)
        filtered = [rc for s, rc in scored if s >= keep]
        return filtered or [scored[0][1]]

    def _expand_retrieved_chunks(self, retrieved: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """同一文档补相邻切片，避免只命中「第三」等尾段。"""
        by_chunk_id: dict[str, RetrievedChunk] = {rc.chunk.id: rc for rc in retrieved}
        doc_map = {rc.document.id: rc.document for rc in retrieved}
        for rc in list(retrieved):
            doc_id = rc.document.id
            idx = self._chunk_doc_index(rc.chunk)
            for delta in (-2, -1, 1, 2):
                cid = f"{doc_id}_{idx + delta}"
                if any(c.chunk.chroma_id == cid for c in by_chunk_id.values()):
                    continue
                chunk = self.db.scalars(select(Chunk).where(Chunk.chroma_id == cid)).first()
                if chunk is None:
                    continue
                doc = doc_map.get(chunk.document_id) or rc.document
                meta = json.loads(chunk.metadata_json or "{}")
                by_chunk_id[chunk.id] = RetrievedChunk(
                    chunk, doc, meta, rc.distance + 0.05, score=max(1, rc.score // 2)
                )
        return list(by_chunk_id.values())

    def _load_document_plain(self, doc_id: str) -> str:
        chunks = self.db.scalars(select(Chunk).where(Chunk.document_id == doc_id)).all()
        if not chunks:
            return ""
        ordered = sorted(chunks, key=self._chunk_doc_index)
        parts = [plain_text_from_chunk(c.text) for c in ordered if c.text]
        return "\n\n".join(p for p in parts if p)

    def _find_qa_block(self, plain: str, question: str) -> str:
        """在面试稿合并正文中定位与用户问题最匹配的一题（单题边界）。"""
        if not plain.strip():
            return plain
        terms = _query_terms(question)
        q_pat = re.compile(r"\d+\.\s+[^\n？?]{4,140}[？?]")
        matches = list(q_pat.finditer(plain))
        if not matches:
            return plain
        best_score = -1
        best_span = (0, min(len(plain), 4000))
        for i, m in enumerate(matches):
            qline = m.group(0)
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(plain)
            score = sum(6 for t in terms if t.lower() in qline.lower())
            qn = re.sub(r"[\s\d\.\*\#>`\-_|？?，,]+", "", question).lower()
            ln = re.sub(r"[\s\d\.\*\#>`\-_|？?，,]+", "", qline).lower()
            if len(qn) >= 6 and qn[:10] in ln:
                score += 20
            if score > best_score:
                best_score = score
                best_span = (start, end)
        if best_score >= max(6, len(terms) * 3):
            return plain[best_span[0] : best_span[1]].strip()
        return plain

    @staticmethod
    def _dedupe_citations(citations: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for c in citations:
            key = str(c.get("document_id") or c.get("chunk_id") or id(c))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _extract_answer_block(self, question: str, chunk_text: str) -> str:
        """从合并后的正文取「题干之后」完整答案，按阅读顺序。"""
        plain = (
            chunk_text
            if "\n" in chunk_text or not re.search(r"[<>*`]", chunk_text)
            else plain_text_from_chunk(chunk_text)
        )
        if not plain:
            return ""
        plain = self._find_qa_block(plain, question)

        start_markers = ("先说结论", "答案", "答：", "答:", "参考回答", "第一，", "第一,", "第一、")
        start_at = len(plain)
        for m in start_markers:
            p = plain.find(m)
            if p >= 0:
                start_at = min(start_at, p)
        if start_at < len(plain):
            text = plain[start_at:]
        else:
            lines = plain.split("\n")
            out: list[str] = []
            started = False
            for line in lines:
                s = line.strip()
                if not s:
                    if started:
                        out.append("")
                    continue
                if not started:
                    if self._line_echoes_question(s, question):
                        continue
                    if re.match(r"^\d+\.\s*", s) and "？" in s and len(s) < 120:
                        continue
                    started = True
                    out.append(s)
                    continue
                if re.match(r"^\d+\.\s+[^\n]{4,80}？\s*$", s):
                    break
                out.append(s)
            text = "\n".join(out).strip() or plain

        next_q = re.search(r"\n\s*\d+\.\s+[^\n]+[？?]\s*(?:\n|$)", text)
        if next_q:
            text = text[: next_q.start()].strip()
        proj = re.search(r"\*\*项目里可以这样说", text)
        if proj:
            text = text[: proj.end()].strip()
            tail = re.search(r"项目里可以这样说[^*]*", text)
            if tail:
                text = text[: tail.end()].strip()
        if text.count("先说结论") > 1:
            idx = text.find("先说结论")
            rest = text[idx + 4 :]
            nxt = rest.find("先说结论")
            if nxt > 0:
                text = text[: idx + 4 + nxt].strip()
        if re.search(r"第[一二三][，、,]", text):
            text = self._sort_cn_numbered_body(text)
        text = re.sub(r"\*\*\s*\"", "\"", text)
        return text[:2800]

    def _merge_retrieved_document_text(self, retrieved: list[RetrievedChunk]) -> str:
        """同一文档的多条切片按入库序号拼接，避免只命中尾段导致「倒序/缺段」。"""
        by_doc: dict[str, list[RetrievedChunk]] = {}
        for rc in retrieved:
            by_doc.setdefault(rc.document.id, []).append(rc)

        def doc_weight(doc_id: str) -> float:
            items = by_doc[doc_id]
            return sum(r.score for r in items) + len(items) * 0.5

        best_doc = max(by_doc.keys(), key=doc_weight)
        ordered = sorted(
            by_doc[best_doc],
            key=lambda r: self._chunk_doc_index(r.chunk),
        )
        parts: list[str] = []
        last_idx = -1
        for rc in ordered:
            idx = self._chunk_doc_index(rc.chunk)
            plain = plain_text_from_chunk(rc.chunk.text)
            if not plain:
                continue
            if idx <= last_idx and parts:
                parts[-1] = f"{parts[-1]}\n{plain}"
            else:
                parts.append(plain)
                last_idx = idx
        return "\n\n".join(parts)

    def _extractive_answer(self, question: str, retrieved: list[RetrievedChunk]) -> str:
        """从 MySQL 切片摘录：锚点定位题目切片，再取「先说结论」段。"""
        if not retrieved:
            return ""
        kb_id = retrieved[0].chunk.kb_id
        doc_ids = {r.document.id for r in retrieved}
        anchor_hit = self._find_best_extractive_chunk(kb_id, question, doc_ids)
        if anchor_hit and anchor_hit[0] >= 15:
            _, anchor_rc = anchor_hit
            block = self._extract_conclusion_from_raw(question, anchor_rc.chunk.text)
            if self._answer_plausible(question, block):
                return block
            expanded = self._expand_retrieved_chunks([anchor_rc])
            merged = self._merge_retrieved_document_text(expanded)
            block = self._extract_conclusion_from_raw(question, merged)
            if self._answer_plausible(question, block):
                return block

        expanded = self._expand_retrieved_chunks(retrieved)
        focused = self._filter_retrieved_for_question(expanded, question)
        merged = self._merge_retrieved_document_text(focused)
        block = self._extract_answer_block(question, merged)
        if self._answer_plausible(question, block):
            return block
        best = max(
            focused,
            key=lambda r: (
                self._score_chunk_extractive(r.chunk, question),
                self._score_chunk_for_question(r, question),
            ),
        )
        block = self._extract_conclusion_from_raw(question, best.chunk.text)
        if self._answer_plausible(question, block):
            return block
        return block or plain_text_from_chunk(best.chunk.text)[:2200]

    async def answer(
        self,
        kb_id: str,
        question: str,
        history: list[dict[str, str]] | None = None,
        top_k: int | None = None,
        kb_strict: bool = False,
    ) -> tuple[str, list[dict]]:
        retrieved = await self.retrieve(kb_id, question, top_k=top_k)

        if not retrieved or self.low_confidence(retrieved):
            if kb_strict:
                return KB_MISS_REPLY, []
            if not retrieved:
                return "知识库中未找到相关信息。", []
            context = "（无匹配参考资料）"
            citations: list[dict] = []
        else:
            chunks = [r.chunk for r in retrieved]
            docs = {r.document.id: r.document for r in retrieved}
            metas = [r.metadata for r in retrieved]
            context = format_context_for_prompt(chunks, docs, metas)
            citations = self._dedupe_citations(
                [
                    build_citation(r.chunk, r.document, r.metadata) for r in retrieved
                ]
            )

        if kb_strict:
            if not citations:
                return KB_MISS_REPLY, []
            if self.llm.llm_demo or not self.settings.rag_kb_use_llm:
                return self._extractive_answer(question, retrieved), citations
            system = RAG_SYSTEM_TEMPLATE.format(context_with_indexed_chunks=context)
            messages: list[dict] = [{"role": "system", "content": system}]
            for msg in history or []:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": question})
            try:
                answer = await self.llm.chat_completion(messages)
            except Exception:
                return self._extractive_answer(question, retrieved), citations
            if not citations:
                return KB_MISS_REPLY, []
            return answer, citations

        if self.llm.llm_demo:
            if citations:
                return self._extractive_answer(question, retrieved), citations
            return "知识库中未找到相关信息。", []

        system = RAG_SYSTEM_TEMPLATE.format(context_with_indexed_chunks=context)
        messages: list[dict] = [{"role": "system", "content": system}]
        for msg in history or []:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})

        try:
            answer = await self.llm.chat_completion(messages)
        except Exception:
            if citations:
                return self._extractive_answer(question, retrieved), citations
            return "知识库中未找到相关信息。", []

        if answer.startswith("（演示模式）") or "未配置有效" in answer:
            if citations:
                return self._extractive_answer(question, retrieved), citations

        if not citations and "未找到" not in answer:
            answer = "知识库中未找到相关信息。" if not retrieved else answer
        return answer, citations

    async def iter_answer_stream(
        self,
        kb_id: str,
        question: str,
        history: list[dict[str, str]] | None = None,
        top_k: int | None = None,
        kb_strict: bool = False,
    ) -> AsyncIterator[tuple[str, object]]:
        """Yield ('token', str) then ('done', citations | None)."""
        retrieved = await self.retrieve(kb_id, question, top_k=top_k)

        if not retrieved or self.low_confidence(retrieved):
            if kb_strict:
                async for item in self._stream_plain(KB_MISS_REPLY, []):
                    yield item
                return
            if not retrieved:
                async for item in self._stream_plain("知识库中未找到相关信息。", []):
                    yield item
                return
            context = "（无匹配参考资料）"
            citations: list[dict] = []
        else:
            chunks = [r.chunk for r in retrieved]
            docs = {r.document.id: r.document for r in retrieved}
            metas = [r.metadata for r in retrieved]
            context = format_context_for_prompt(chunks, docs, metas)
            citations = self._dedupe_citations(
                [
                    build_citation(r.chunk, r.document, r.metadata) for r in retrieved
                ]
            )

        if kb_strict:
            if not citations:
                async for item in self._stream_plain(KB_MISS_REPLY, []):
                    yield item
                return
            if self.llm.llm_demo or not self.settings.rag_kb_use_llm:
                answer = self._extractive_answer(question, retrieved)
                async for item in self._stream_plain(answer, citations):
                    yield item
                return
            system = RAG_SYSTEM_TEMPLATE.format(context_with_indexed_chunks=context)
            messages: list[dict] = [{"role": "system", "content": system}]
            for msg in history or []:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": question})
            try:
                async with asyncio.timeout(20.0):
                    async for piece in self.llm.chat_completion_stream(
                        messages, on_http_error="raise"
                    ):
                        yield "token", piece
            except Exception:
                answer = self._extractive_answer(question, retrieved)
                async for item in self._stream_plain(answer, citations):
                    yield item
                return
            yield "done", citations
            return

        answer, citations_out = await self.answer(
            kb_id, question, history=history, top_k=top_k, kb_strict=False
        )
        async for item in self._stream_plain(answer, citations_out or []):
            yield item

    async def iter_extractive_stream(
        self, kb_id: str, question: str
    ) -> AsyncIterator[tuple[str, object]]:
        """知识库问答：仅检索 + 原文摘录（不调用大模型）。用于模型不可用时的降级。"""
        retrieved = await self.retrieve(kb_id, question)
        if not retrieved or self.low_confidence(retrieved):
            async for item in self._stream_plain(KB_MISS_REPLY, []):
                yield item
            return
        citations = self._dedupe_citations(
            [
                build_citation(r.chunk, r.document, r.metadata) for r in retrieved
            ]
        )
        answer = self._extractive_answer(question, retrieved)
        async for item in self._stream_plain(answer, citations):
            yield item

    async def _stream_plain(
        self, text: str, citations: list[dict]
    ) -> AsyncIterator[tuple[str, object]]:
        step = 2
        for i in range(0, len(text), step):
            yield "token", text[i : i + step]
            await asyncio.sleep(0.028)
        yield "done", citations
