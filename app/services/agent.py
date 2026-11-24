from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.research import ResearchJob
from app.services.llm import LLMService, parse_agent_action
from app.services.rag import RAGService

AGENT_SYSTEM = """你是知识库研究 Agent。你只能使用以下工具（JSON 回复，不要其它文字）：
1. search_kb — args: {"query": str, "top_k": int}
2. write_section — args: {"title": str, "content": str}
3. finish — args: {}

每次只返回一个 JSON 对象：{"tool": "...", "args": {...}}
"""


def _save_steps(job: ResearchJob, steps: list[dict[str, Any]], db: Session) -> None:
    job.steps_json = json.dumps(steps, ensure_ascii=False)
    db.commit()


async def _tool_search_kb(rag: RAGService, kb_id: str, args: dict) -> str:
    query = args.get("query") or ""
    top_k = int(args.get("top_k") or 5)
    retrieved = await rag.retrieve(kb_id, query, top_k=top_k)
    if not retrieved:
        return "（无命中）"
    return "\n".join(r.chunk.text[:300] for r in retrieved)


async def run_research_job(job_id: str, db: Session) -> None:
    settings = get_settings()
    job = db.get(ResearchJob, job_id)
    if job is None:
        return

    llm = LLMService()
    rag = RAGService(db, llm)
    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "name": "外网检索（演示环境已跳过）",
            "status": "done",
            "detail": "占位步骤",
        },
        {"step": 2, "name": "规划", "status": "running", "detail": ""},
    ]
    job.status = "running"
    _save_steps(job, steps, db)
    started = time.monotonic()
    sections: list[tuple[str, str]] = []
    refs: list[str] = []
    step_no = 3
    tool_calls = 0

    try:
        plan_raw = await llm.chat_completion(
            [
                {
                    "role": "user",
                    "content": (
                        f"针对研究主题「{job.topic}」，列出 3～5 个需要在知识库内检索的子问题，"
                        "每行一个，不要编号外的多余文字。"
                    ),
                }
            ],
            temperature=0.2,
        )
        sub_questions = [ln.strip("-• \t") for ln in plan_raw.splitlines() if ln.strip()][:5]
        if not sub_questions:
            sub_questions = [job.topic]

        steps[1]["status"] = "done"
        steps[1]["detail"] = f"拆分为 {len(sub_questions)} 个子问题"
        _save_steps(job, steps, db)

        for q in sub_questions:
            if time.monotonic() - started > settings.agent_timeout_seconds:
                job.status = "partial"
                job.error_message = "超过超时时间"
                break
            if tool_calls >= settings.max_agent_steps:
                job.status = "partial"
                job.error_message = "超过最大步数"
                break

            steps.append(
                {
                    "step": step_no,
                    "name": "search_kb",
                    "status": "running",
                    "detail": q[:60],
                }
            )
            _save_steps(job, steps, db)
            tool_calls += 1

            hits_text = await _tool_search_kb(rag, job.kb_id, {"query": q, "top_k": 5})
            retrieved = await rag.retrieve(job.kb_id, q, top_k=5)
            steps[-1]["status"] = "done"
            steps[-1]["detail"] = f"命中 {len(retrieved)} 条"
            step_no += 1

            for r in retrieved:
                refs.append(f"- {r.document.filename} — {r.chunk.text[:120]}…")

            action_raw = await llm.chat_completion(
                [
                    {"role": "system", "content": AGENT_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"主题：{job.topic}\n子问题：{q}\n检索结果：\n{hits_text}\n\n"
                            '请调用 write_section 写入本章，JSON 格式。'
                        ),
                    },
                ],
                temperature=0.2,
            )
            action = parse_agent_action(action_raw) or {
                "tool": "write_section",
                "args": {"title": q[:60], "content": hits_text[:500] or "（无内容）"},
            }

            if action.get("tool") == "write_section":
                args = action.get("args") or {}
                title = str(args.get("title") or q[:60])
                content = str(args.get("content") or "")
                if len(content.strip()) < 50:
                    content = await llm.chat_completion(
                        [
                            {
                                "role": "user",
                                "content": (
                                    f"子问题：{q}\n资料：\n{hits_text}\n"
                                    "写 150～300 字中文章节，仅依据资料。"
                                ),
                            }
                        ],
                        temperature=0.3,
                    )
                sections.append((title, content))
                steps.append(
                    {
                        "step": step_no,
                        "name": "write_section",
                        "status": "done",
                        "detail": title,
                    }
                )
                step_no += 1
                tool_calls += 1

        abstract = await llm.chat_completion(
            [
                {
                    "role": "user",
                    "content": (
                        f"为主题「{job.topic}」写一段 100 字以内的中文摘要：\n"
                        + "\n".join(s[1][:200] for s in sections)
                    ),
                }
            ],
            temperature=0.3,
        )

        body_parts = [f"# {job.topic} 研究报告\n\n## 摘要\n\n{abstract.strip()}\n"]
        for title, content in sections:
            body_parts.append(f"## {title}\n\n{content.strip()}\n")
        body_parts.append("## 参考来源\n" + ("\n".join(dict.fromkeys(refs)) if refs else "（无）"))
        job.report_md = "\n".join(body_parts)

        steps.append({"step": step_no, "name": "finish", "status": "done", "detail": "报告已生成"})
        if job.status not in ("partial", "failed"):
            job.status = "succeeded"
        job.error_message = job.error_message if job.status == "partial" else None
        _save_steps(job, steps, db)
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        steps.append(
            {"step": step_no, "name": "失败", "status": "failed", "detail": str(exc)}
        )
        _save_steps(job, steps, db)
