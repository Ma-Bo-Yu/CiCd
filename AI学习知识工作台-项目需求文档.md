# AI 学习知识工作台 — 全面项目需求文档（PRD）

**文档版本**：v1.0  
**创建日期**：2026-10-09  
**最后更新**：2026-10-11  
**文档状态**：正式基线 — 模拟面试答辩 + Cursor 全自动实现  
**项目名称（仓库名建议）**：`ai-knowledge-workbench`

---

> ## 给 Cursor 的执行指令（最高优先级）
>
> 1. **严格遵循**本文 **§6 技术栈锁定** — 禁止引入 Next.js、React、Vue、Redis、Celery、Qdrant、微服务拆分。  
> 2. **严格按** **§18 实现顺序** Step 1 → 12 逐步实现；每 Step 完成须满足对应 **§16 验收标准**。  
> 3. **必须先完成 P0 黄金路径**（§19），再实现 P1 模块（图像对话、研究 Agent）。  
> 4. **§17 Out of Scope** 所列功能不得实现。  
> 5. 所有 LLM/Embedding/TTS 调用通过 **OpenAI 兼容 HTTP API**（`httpx`），配置来自 `.env`。  
> 6. 代码仓库结构遵循 **§20 目录结构**。

---

## 变更标注说明

| 标记 | 含义 |
|------|------|
| **【v1.0 新增】** | 相对 v0.2 全新章节或内容块 |
| **【v1.0 修订】** | v0.2 有对应内容，本版改写或替换 |
| **【v1.0 继承】** | 自 v0.2 继承，本版未改或仅微调 |
| 无标记 | v1.0 基线正文 |

完整版本间差异见 **§25 修订记录与变更明细**。

---

## 目录

1. [文档说明](#1-文档说明)
2. [项目概述](#2-项目概述)
3. [目标用户与场景](#3-目标用户与场景)
4. [用户故事](#4-用户故事)
5. [系统架构](#5-系统架构)
6. [技术栈锁定](#6-技术栈锁定)
7. [功能规格 — 知识库管理](#7-功能规格--知识库管理)
8. [功能规格 — 知识库问答（RAG）](#8-功能规格--知识库问答rag)
9. [功能规格 — 图像对话](#9-功能规格--图像对话)
10. [功能规格 — 研究智能体](#10-功能规格--研究智能体)
11. [功能规格 — 讲解视频生成](#11-功能规格--讲解视频生成)
12. [融合设计与共享能力](#12-融合设计与共享能力)
13. [用户界面与交互](#13-用户界面与交互)
14. [数据模型](#14-数据模型)
15. [API 规格](#15-api-规格)
16. [验收标准（AC）](#16-验收标准ac)
17. [Out of Scope](#17-out-of-scope)
18. [实现顺序（Cursor Step 1～12）](#18-实现顺序cursor-step-112)
19. [黄金演示路径](#19-黄金演示路径)
20. [项目目录结构](#20-项目目录结构)
21. [环境与依赖](#21-环境与依赖)
22. [非功能需求](#22-非功能需求)
23. [Mock 与降级策略](#23-mock-与降级策略)
24. [答辩附录](#24-答辩附录)
25. [修订记录与变更明细](#25-修订记录与变更明细)
26. [术语表](#26-术语表)

---

## 1. 文档说明

### 1.1 文档目的

本文档是 **AI 学习知识工作台** 项目的唯一需求基线，服务于：

| 受众 | 用途 |
|------|------|
| **答辩者（你）** | 理解全貌、准备架构追问、验收 Cursor 产出 |
| **Cursor Agent** | 按规格自动实现代码，无需猜测技术选型 |
| **模拟面试官** | 评审产品设计、技术 trade-off、完成度 |

### 1.2 项目性质

- **类型**：个人模拟面试答辩项目（非商业上线产品）
- **实现方式**：答辩者主导需求与验收，**Cursor 完成绝大部分编码**
- **成功定义**：
  - P0：**§19 黄金路径** 可录屏演示（约 5 分钟）
  - P1：四大能力模块均可独立演示
  - 答辩者能口述 **§24** 中的架构与 trade-off

### 1.3 优先级定义

| 优先级 | 含义 | 模块 |
|--------|------|------|
| **P0** | 必须完成，答辩底线 | 知识库、RAG 问答、讲解视频（讲稿→mp4） |
| **P1** | 全功能演示，面试加分 | 研究 Agent、图像对话 |
| **P2** | 不做 | 见 §17 |

---

## 2. 项目概述

### 2.1 产品愿景

构建以 **个人知识库为中枢** 的 AI 学习工作台，在同一平台完成：

```
上传资料 → 带引用问答 → 深度研究整理 → 图像答疑 → 生成讲解视频
```

四种能力共享同一知识库与模型网关，形成闭环，而非四个独立 Demo 拼凑。

### 2.2 一句话定位

**「可溯源的知识库 + 多模式 AI 工作台 + 讲稿驱动视频制片流水线。」**

### 2.3 答辩 Elevator Pitch（30 秒）

「这是一个以 RAG 知识库为中心的学习工作台。用户上传 PDF 或 Markdown 后，可以进行带引用来源的问答；需要系统整理时，研究 Agent 会在库内多步检索并生成报告；上传图片可以做多模态答疑；最后把同一知识库里的内容生成可编辑讲稿，确认后自动 TTS 配音、生成幻灯片并合成讲解视频。四条能力共用 FastAPI 后端、Chroma 向量库和同一套 LLM 网关。」

### 2.4 核心设计原则

1. **知识库为中枢**：问答、研究、讲稿生成均优先 RAG 检索同一 corpus。
2. **引用可溯源**：凡事实性回答须展示 citations（文档名 + 摘录）。
3. **可编辑优于一键完美**：视频必须经讲稿确认后再渲染。
4. **同步 vs 异步分档**：问答同步返回；研究、视频走 Job 异步队列。
5. **演示可落地**：技术栈以 **Python / FastAPI 单仓** 为主，降低学习与部署成本。
6. **诚实边界**：外网研究、多模板视频、企业级权限等明确 Out of Scope。

---

## 3. 目标用户与场景

### 3.1 默认 Persona（模拟面试简化）

**「自备资料备课的单人讲师」** — 不上多租户、不做团队协作。

### 3.2 场景矩阵

| 用户 | 场景 | 使用模块 | 优先级 |
|------|------|----------|--------|
| 讲师 | 上传教材 PDF，课堂知识点答疑 | 知识库 + RAG 问答 | P0 |
| 讲师 | 针对「牛顿第一定律」生成 3 分钟讲解视频 | 讲稿 + 视频渲染 | P0 |
| 讲师 | 对讲义插图提问 | 图像对话 | P1 |
| 讲师 | 对「力学章节」做系统梳理报告 | 研究 Agent | P1 |
| 答辩者 | 演示端到端工作流 | 黄金路径 §19 | P0 |

---

## 4. 用户故事 【v1.0 新增】

### 4.1 P0 用户故事

| ID | 故事 | 验收关联 |
|----|------|----------|
| US-01 | 作为讲师，我可以创建知识库并上传 PDF/Markdown，以便后续问答 | AC-KB-01,02 |
| US-02 | 作为讲师，我可以对知识库提问并获得**带引用**的回答，以便核对准确性 | AC-KB-03,04 |
| US-03 | 作为讲师，我可以输入主题让系统基于知识库生成讲稿，并手动修改 | AC-VID-01,05 |
| US-04 | 作为讲师，我确认讲稿后可以异步渲染并下载 mp4 讲解视频 | AC-VID-02,03,04 |
| US-05 | 作为答辩者，我可以用 seed 数据在 5 分钟内完成录屏演示 | AC-INT-01 |

### 4.2 P1 用户故事

| ID | 故事 | 验收关联 |
|----|------|----------|
| US-06 | 作为讲师，我可以上传图片并提问，系统能理解图像内容 | AC-V-01 |
| US-07 | 作为讲师，我可以在图像模式下结合知识库回答并给出引用 | AC-V-02 |
| US-08 | 作为讲师，我可以发起研究任务，看到 Agent 步骤并获取 Markdown 报告 | AC-R-01,02 |
| US-09 | 作为讲师，我可以将研究报告一键入库，供后续问答检索 | AC-R-04 |

---

## 5. 系统架构

### 5.1 逻辑架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                     Browser（Jinja2 + HTMX）                      │
│   知识库页 │ 问答页 │ 图像对话页 │ 研究任务页 │ 视频任务页 │ 设置页   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP (HTML / JSON)
┌────────────────────────────▼─────────────────────────────────────┐
│                      FastAPI Application                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ │
│  │ KB Router   │ │ Chat Router │ │Research Rtr │ │ Video Router│ │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ │
│         │               │               │               │        │
│  ┌──────▼───────────────▼───────────────▼───────────────▼──────┐ │
│  │                      Service Layer                           │ │
│  │  ingest │ rag │ llm │ agent │ tts │ slide │ video_render    │ │
│  └──────┬───────────────┬───────────────┬───────────────┬──────┘ │
│         │               │               │               │        │
│  ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ │
│  │ SQLite ORM  │ │  ChromaDB   │ │ Job Runner  │ │  File Store │ │
│  │ (metadata)  │ │ (vectors)   │ │ (bg tasks)  │ │ data/       │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS
┌────────────────────────────▼─────────────────────────────────────┐
│              External OpenAI-Compatible APIs                        │
│         LLM (chat/vision) │ Embeddings │ TTS                      │
└──────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                    FFmpeg（本地进程，视频合成）                        │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 部署架构（演示环境）

- **单机部署**：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **数据持久化**：`./data/`（上传文件、生成视频）、`./chroma/`（向量）、`./app.db`（SQLite）
- **无需 Docker**（可选提供 `Dockerfile`，非必须）

### 5.3 请求路径分类

| 类型 | 处理方式 | 示例 |
|------|----------|------|
| 同步 | 请求内完成，直接返回 | RAG 问答、讲稿生成 |
| 异步 Job | 写入 Job 表 → BackgroundTasks 执行 → 前端轮询 | 视频渲染、研究 Agent |

---

## 6. 技术栈锁定 【v1.0 修订】

> **v1.0 相对 v0.2 的核心变更**：由 Next.js + Qdrant + Redis 改为 **FastAPI 单仓 Python 栈**。

### 6.1 强制技术选型

| 层级 | 技术 | 版本要求 | 用途 |
|------|------|----------|------|
| 语言 | **Python** | 3.11+ | 全栈后端 + 模板 |
| Web 框架 | **FastAPI** | 0.100+ | API + 页面路由 |
| 模板 | **Jinja2** | 3.x | 服务端渲染 HTML |
| 前端交互 | **HTMX** | 1.9+ | 局部刷新、表单提交 |
| 样式 | **Tailwind CSS**（CDN）或简单自定义 CSS | — | 演示级 UI |
| ORM | **SQLAlchemy** | 2.x | 元数据持久化 |
| 数据库 | **SQLite** | 3 | 演示零配置 |
| 向量库 | **ChromaDB** | 0.4+（嵌入式） | Embedding 存储与检索 |
| HTTP 客户端 | **httpx** | — | 调用 LLM/Embedding/TTS API |
| PDF 解析 | **PyMuPDF** (`fitz`) | — | PDF 文本提取 |
| 图像处理 | **Pillow** | — | 幻灯片图片生成 |
| 视频合成 | **FFmpeg** | 系统安装 | 音画合成、字幕 |
| TTS | OpenAI TTS API 或 **edge-tts**（fallback） | — | 中文旁白 |
| 异步任务 | **FastAPI BackgroundTasks** + Job 表 | — | 禁止 Celery/Redis |
| 配置 | **pydantic-settings** + `.env` | — | 环境变量管理 |

### 6.2 禁止引入的技术

- Next.js、React、Vue、Angular、Svelte
- Qdrant、Milvus、Elasticsearch（向量检索仅用 Chroma）
- Redis、RabbitMQ、Celery
- 微服务拆分、独立前端仓库
- 商业视频成片 SaaS（如 Runway 一键成片作为主路径）
- 真实外网爬虫 / Playwright 浏览器 Agent

### 6.3 外部 API 约定

- 统一 **OpenAI 兼容** 接口格式
- 通过环境变量切换供应商（OpenAI / DeepSeek / 通义 / 其他）
- Vision 能力要求 `LLM_MODEL` 支持图像输入（或单独配置 `VISION_MODEL`）

---

## 7. 功能规格 — 知识库管理

### 7.1 功能描述

用户可创建多个知识库，向库中上传文档，系统完成解析、切片、向量化与索引。

### 7.2 支持的文档格式

| 格式 | MVP | 解析方式 |
|------|-----|----------|
| PDF | **必须** | PyMuPDF 按页提取文本 |
| Markdown (.md) | **必须** | 直接读取 UTF-8 |
| 纯文本 (.txt) | 可选 | 直接读取 |
| Word (.docx) | **不做** | Out of Scope |

### 7.3 文档处理流水线

```
上传文件
  → 保存至 data/uploads/{kb_id}/{doc_id}_{filename}
  → documents.status = processing
  → 解析全文
  → 切片（§7.4）
  → 批量 Embedding
  → 写入 Chroma collection: kb_{kb_id}
  → 写入 chunks 表（文本 + metadata）
  → documents.status = indexed
  → 失败则 status = failed, error_message 记录原因
```

### 7.4 切片策略

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CHUNK_SIZE` | 500 字符（或 ~400 token） | 可配置常量 |
| `CHUNK_OVERLAP` | 100 字符 | 相邻块重叠 |
| PDF metadata | `page`（页码，从 1 开始） | 写入 chunk metadata |
| MD metadata | `heading`（若有） | 可选，从 `#` 标题提取 |

### 7.5 知识库操作

| 操作 | 说明 |
|------|------|
| 创建 | 名称 + 可选描述 |
| 列表 | 显示库名、文档数、创建时间 |
| 详情 | 文档列表及索引状态 |
| 删除 | 删除库、关联文档、Chroma collection、chunks |
| 重新索引 | 对单文档触发 reindex |

---

## 8. 功能规格 — 知识库问答（RAG）

### 8.1 功能描述

用户在选定知识库下进行多轮文本问答，系统通过 RAG 检索相关片段，生成回答并附带引用。

### 8.2 处理流程

```
用户问题 + session_id + kb_id
  → 加载最近 N 轮历史（N=5）
  → query embedding
  → Chroma query top_k=5
  → 若最高相似度 < 阈值（可选 0.3）→ 标记低置信度
  → 拼装 prompt（§8.3）
  → LLM chat completion
  → 解析回答 + 构建 citations[]
  → 持久化 user message + assistant message
  → 返回页面（HTMX 片段或 JSON）
```

### 8.3 System Prompt 模板（必须实现）

```text
你是基于知识库的问答助手。请严格根据以下「参考资料」回答问题。
规则：
1. 仅使用参考资料中的信息；资料不足时明确说「知识库中未找到相关信息」。
2. 不要编造参考资料中不存在的事实。
3. 回答简洁、准确，适合教学场景。

参考资料：
{context_with_indexed_chunks}

请用中文回答。
```

`context_with_indexed_chunks` 格式示例：

```text
[1] 来源: 力学基础.pdf (第3页)
内容: 牛顿第一定律指出...

[2] 来源: 力学基础.pdf (第4页)
内容: ...
```

### 8.4 Citations 构建规则

- 从检索到的 top_k chunks 构建 citations
- 每条含：`document_id`, `document_name`, `chunk_id`, `excerpt`（前 200 字）, `page?`
- UI 以卡片形式展示，可展开 excerpt

### 8.5 会话管理

- `ChatSession.mode = chat_qa`
- 同一会话内保留上下文（最近 5 轮带入 prompt）
- 会话列表可按知识库筛选

---

## 9. 功能规格 — 图像对话

### 9.1 功能描述（P1）

用户上传图片并输入问题，系统支持两种子模式：

| 子模式 | 行为 |
|--------|------|
| `vision_only` | 仅将图片 + 问题送 Vision LLM |
| `vision_rag` | 先用问题（+ 可选图片描述）检索知识库，再融合检索结果与图片送 LLM |

### 9.2 处理流程 — vision_rag

```
图片保存至 data/images/{session_id}/
  → 若需要：Vision LLM 生成图片简短描述
  → query = 用户问题 + 图片描述
  → RAG top_k=5
  → 拼装多模态 prompt（文本部分含参考资料，图片作为 image_url/base64）
  → Vision LLM 回答
  → citations（当 RAG 命中时）
```

### 9.3 支持的图片格式

PNG、JPEG、WebP；单张最大 10MB（可配置）。

### 9.4 会话

- `ChatSession.mode = chat_vision`
- 消息可含 `image_path`；历史展示缩略图 + 文字

---

## 10. 功能规格 — 研究智能体

### 10.1 功能描述（P1）

用户输入研究主题，Agent 在知识库内多步检索与综合，输出结构化 Markdown 报告。

### 10.2 Agent 设计

**类型**：ReAct 风格有限步数循环（非无限自主 Agent）。

**工具白名单**（仅以下工具可调用）：

| 工具名 | 说明 |
|--------|------|
| `search_kb` | 参数 `query`, `top_k`；返回 chunks 列表 |
| `write_section` | 参数 `title`, `content`；追加到报告草稿 |
| `finish` | 结束任务，标记完成 |

**禁止工具**：外网搜索、代码执行、文件系统任意读写。

### 10.3 执行流程

```
创建 ResearchJob (status=pending)
  → BackgroundTasks 启动
  → status=running
  → Step 1: LLM 规划子问题列表（3～5 个）→ 写入 steps
  → Step 2..N: 对每个子问题调用 search_kb → 摘要 → write_section
  → 最终: 生成完整 report_md（摘要 + 章节 + 参考来源）
  → status=succeeded
  → 超 MAX_STEPS(8) 或超时(10min) → status=failed 或 partial
```

### 10.4 报告结构（Markdown）

```markdown
# {topic} 研究报告

## 摘要
...

## 1. {子主题一}
...

## 2. {子主题二}
...

## 参考来源
- [1] 文档名 — 摘录...
```

### 10.5 报告入库

- 接口 `POST /research/jobs/{id}/ingest`
- 将 `report_md` 存为 `{topic}_report.md` 加入原知识库
- 触发标准 ingest 流水线索引

### 10.6 外网步骤（Mock）

- UI 步骤列表可显示「外网检索（演示环境已跳过）」占位 Step
- **不实现真实 HTTP 爬取**

---

## 11. 功能规格 — 讲解视频生成

### 11.1 功能描述（P0）

用户输入主题，系统基于知识库 RAG 生成讲稿，用户确认后异步渲染为 **幻灯片 + 旁白 + 字幕** 的 mp4 视频。

### 11.2 产品定义

**「AI 编导 + 自动制片」流水线** — 非文生视频模型一键出片。

### 11.3 完整流水线

```
Phase A — 讲稿生成（同步）
  输入: kb_id, topic, target_minutes (3|5|8)
  → RAG 检索 top_k=8
  → LLM 生成 script_md（Markdown）
  → 结构: 引入 → 要点(≥2) → 例子 → 小结
  → 保存 VideoJob, script_confirmed=false
  → 返回可编辑讲稿 + citations

Phase B — 用户编辑（同步）
  → 用户在 textarea 修改 script_md
  → PATCH 保存

Phase C — 确认与渲染（异步 Job）
  → 用户点击「确认并渲染」→ script_confirmed=true
  → status=pending → running
  → 1. 解析 script 为 slides[]（每段/每句一张幻灯片）
  → 2. 每段 TTS 生成 audio_i
  → 3. Pillow 生成 slide_i.png（标题 + bullets）
  → 4. FFmpeg: 每张 slide 显示时长 = audio_i 时长
  → 5. 生成 subtitles.srt，烧录或软字幕
  → 6. 合成 output.mp4 → data/videos/{job_id}.mp4
  → status=succeeded
```

### 11.4 幻灯片模板（唯一模板）

- 尺寸：1280×720
- 背景：白色
- 标题：顶部居中，36px 黑体
- 正文：左侧 bullets，24px
- 每「句/段」一张幻灯片（按句号或 Markdown 段落切分）

### 11.5 时长控制

- `target_minutes` 作为 prompt 约束传给 LLM
- 演示环境允许 1～5 分钟实际成片
- 可通过加快 TTS 语速或精简讲稿控制时长

### 11.6 状态机

```
draft → (confirm) → pending → running → succeeded
                              ↘ failed
```

- `draft`：讲稿已生成，未确认
- `pending`：已确认，等待后台
- `running`：渲染中
- `succeeded`：可下载
- `failed`：`error_message` 可查；讲稿仍保留

---

## 12. 融合设计与共享能力

### 12.1 共享组件（代码层）

| 组件 | 路径建议 | 被谁使用 |
|------|----------|----------|
| `LLMService` | `services/llm.py` | 问答、研究、讲稿、图像 |
| `RAGService` | `services/rag.py` | 问答、研究、讲稿、图像+RAG |
| `IngestService` | `services/ingest.py` | 上传、报告入库 |
| `JobService` | `services/jobs.py` | 研究、视频 |
| `CitationBuilder` | `services/citations.py` | 所有返回引用的模块 |

### 12.2 全局 UI 组件

| 组件 | 说明 |
|------|------|
| `KnowledgeBaseSelector` | 顶栏下拉，切换当前 kb_id |
| `CitationCard` | 展示单条引用 |
| `JobProgress` | 轮询展示 Job 状态与进度条 |
| `AlertBanner` | 错误/免责声明 |

### 12.3 模式枚举

```python
class SessionMode(str, Enum):
    CHAT_QA = "chat_qa"
    CHAT_VISION = "chat_vision"

class JobType(str, Enum):
    RESEARCH = "research"
    VIDEO = "video"
```

---

## 13. 用户界面与交互

### 13.1 页面路由

| 路由 | 页面名 | 优先级 | 功能 |
|------|--------|--------|------|
| `/` | 工作台首页 | P0 | 快捷入口、当前库、最近任务 |
| `/kb` | 知识库列表 | P0 | CRUD |
| `/kb/{id}` | 知识库详情 | P0 | 文档列表、上传、状态 |
| `/chat` | 文本问答 | P0 | RAG 对话 |
| `/chat/vision` | 图像对话 | P1 | 上传图+问 |
| `/research` | 研究任务列表 | P1 | 新建、查看 |
| `/research/{id}` | 研究详情 | P1 | 步骤时间线、报告 |
| `/video` | 视频任务列表 | P0 | 新建、查看 |
| `/video/{id}` | 视频向导 | P0 | 讲稿编辑、确认、下载 |
| `/settings` | 设置 | P0 | 模型信息、免责声明、seed |

### 13.2 关键交互说明

**知识库详情页**

- 拖拽或按钮上传 PDF/MD
- 表格列：文件名、大小、状态（processing/indexed/failed）、操作（删除、重新索引）

**问答页**

- 左侧：会话列表（可选）
- 右侧：消息流 + 底部输入框
- Assistant 消息下方渲染 CitationCard 列表

**视频向导页**

- Step 1：输入主题、选择时长 →「生成讲稿」
- Step 2：Markdown textarea 编辑 + 参考来源侧栏
- Step 3：「确认并渲染」（`script_confirmed=false` 时 primary 按钮 disabled）
- Step 4：进度条轮询；完成后显示下载链接

**研究详情页**

- 垂直步骤时间线（planning → searching → writing → done）
- 报告 Markdown 预览（可用简单 CSS 渲染）
- 「入库」按钮

### 13.3 HTMX 约定

- 表单提交使用 `hx-post` + `hx-target` 局部更新消息区
- Job 状态使用 `hx-trigger="every 2s"` 轮询进度片段
- 无复杂 SPA 路由；页面跳转用标准 `<a href>`

---

## 14. 数据模型

### 14.1 ER 关系

```
KnowledgeBase 1──N Document 1──N Chunk
KnowledgeBase 1──N ChatSession 1──N Message
KnowledgeBase 1──N ResearchJob
KnowledgeBase 1──N VideoJob
```

### 14.2 表结构

#### knowledge_bases

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| name | VARCHAR(200) | 必填 |
| description | TEXT | 可选 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

#### documents

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| kb_id | UUID FK | |
| filename | VARCHAR(500) | 原始文件名 |
| mime_type | VARCHAR(100) | |
| storage_path | VARCHAR(1000) | 相对路径 |
| status | ENUM | pending, processing, indexed, failed |
| error_message | TEXT | 可选 |
| created_at | DATETIME | |

#### chunks

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| document_id | UUID FK | |
| kb_id | UUID FK | |
| text | TEXT | |
| metadata_json | TEXT | page, heading 等 |
| chroma_id | VARCHAR(100) | Chroma 中的 id |

#### chat_sessions

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| kb_id | UUID FK | |
| mode | VARCHAR(20) | chat_qa, chat_vision |
| title | VARCHAR(200) | 首条消息摘要或默认 |
| created_at | DATETIME | |

#### messages

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| session_id | UUID FK | |
| role | VARCHAR(20) | user, assistant, system |
| content | TEXT | |
| citations_json | TEXT | JSON 数组，可选 |
| image_path | VARCHAR(1000) | 可选 |
| created_at | DATETIME | |

#### research_jobs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| kb_id | UUID FK | |
| topic | VARCHAR(500) | |
| status | VARCHAR(20) | pending, running, succeeded, failed, partial |
| steps_json | TEXT | 步骤数组 |
| report_md | TEXT | |
| error_message | TEXT | |
| created_at | DATETIME | |
| updated_at | DATETIME | |

#### video_jobs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| kb_id | UUID FK | |
| topic | VARCHAR(500) | |
| target_minutes | INT | 3, 5, 8 |
| status | VARCHAR(20) | draft, pending, running, succeeded, failed |
| script_md | TEXT | |
| script_confirmed | BOOLEAN | default false |
| citations_json | TEXT | |
| output_video_path | VARCHAR(1000) | |
| error_message | TEXT | |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### 14.3 citations_json 结构

```json
[
  {
    "document_id": "uuid",
    "document_name": "力学基础.pdf",
    "chunk_id": "uuid",
    "excerpt": "牛顿第一定律指出……",
    "page": 3
  }
]
```

### 14.4 steps_json 结构（研究任务）

```json
[
  {"step": 1, "name": "规划", "status": "done", "detail": "拆分为3个子问题"},
  {"step": 2, "name": "检索: 牛顿第一定律", "status": "done", "detail": "命中5条"},
  {"step": 3, "name": "撰写报告", "status": "running", "detail": ""}
]
```

---

## 15. API 规格

**约定**：REST + JSON（API 端点）；HTML（页面端点）。前缀 `/api/v1`。错误：`{"error": {"code": "...", "message": "..."}}`。

### 15.1 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/knowledge-bases` | 列表 |
| POST | `/api/v1/knowledge-bases` | body: `{name, description?}` |
| GET | `/api/v1/knowledge-bases/{id}` | 详情 |
| DELETE | `/api/v1/knowledge-bases/{id}` | 删除 |
| POST | `/api/v1/knowledge-bases/{id}/documents` | multipart 上传 |
| GET | `/api/v1/knowledge-bases/{id}/documents` | 文档列表 |
| POST | `/api/v1/documents/{id}/reindex` | 重新索引 |

### 15.2 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat/sessions` | `{kb_id, mode}` |
| GET | `/api/v1/chat/sessions` | 列表，可选 `?kb_id=` |
| GET | `/api/v1/chat/sessions/{id}/messages` | 消息历史 |
| POST | `/api/v1/chat/sessions/{id}/messages` | `{content}` 文本问答 |
| POST | `/api/v1/chat/sessions/{id}/messages/vision` | multipart: `content` + `image` |

### 15.3 研究

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/research/jobs` | `{kb_id, topic}` |
| GET | `/api/v1/research/jobs` | 列表 |
| GET | `/api/v1/research/jobs/{id}` | 详情 |
| POST | `/api/v1/research/jobs/{id}/ingest` | 报告入库 |

### 15.4 视频

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/video/jobs` | `{kb_id, topic, target_minutes}` → 生成讲稿 |
| GET | `/api/v1/video/jobs` | 列表 |
| GET | `/api/v1/video/jobs/{id}` | 详情 |
| PATCH | `/api/v1/video/jobs/{id}/script` | `{script_md}` |
| POST | `/api/v1/video/jobs/{id}/confirm` | 确认并触发渲染 |
| GET | `/api/v1/video/jobs/{id}/download` | mp4 文件流 |

### 15.5 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | `{status: "ok"}` |
| POST | `/api/v1/dev/seed` | 仅开发：初始化演示数据 |

---

## 16. 验收标准（AC）

### 16.1 知识库 AC-KB

- [ ] **AC-KB-01**：可创建知识库，上传 PDF 与 Markdown 各至少 1 个
- [ ] **AC-KB-02**：文档处理完成后状态为 `indexed`；失败显示 `error_message`
- [ ] **AC-KB-03**：可删除知识库及关联数据
- [ ] **AC-KB-04**：可对失败文档执行 reindex

### 16.2 问答 AC-QA

- [ ] **AC-QA-01**：提问后 30s 内返回回答（演示环境）
- [ ] **AC-QA-02**：回答含 ≥1 条 citation，excerpt 来自该库真实 chunk
- [ ] **AC-QA-03**：库内无相关内容时，回答包含「未找到」类提示，不伪造引用
- [ ] **AC-QA-04**：同会话 ≥3 轮追问，上下文连贯
- [ ] **AC-QA-05**：切换知识库后问答仅检索对应库

### 16.3 视频 AC-VID

- [ ] **AC-VID-01**：输入主题可生成含「引入/要点/例子/小结」结构的 script_md
- [ ] **AC-VID-02**：讲稿生成阶段展示 RAG citations 列表
- [ ] **AC-VID-03**：textarea 可编辑并保存 script
- [ ] **AC-VID-04**：`script_confirmed=false` 时无法触发渲染
- [ ] **AC-VID-05**：渲染完成后可下载 mp4，时长 1～5 分钟
- [ ] **AC-VID-06**：视频含字幕，口播与字幕基本一致
- [ ] **AC-VID-07**：渲染失败时 status=failed，讲稿仍保留

### 16.4 图像 AC-V

- [ ] **AC-V-01**：上传 PNG/JPEG 并提问，获得合理回复
- [ ] **AC-V-02**：`vision_rag` 模式下，库有相关内容时回复含 citations
- [ ] **AC-V-03**：图文消息在历史中可回看

### 16.5 研究 AC-R

- [ ] **AC-R-01**：创建任务后可见 ≥3 个步骤的状态变化
- [ ] **AC-R-02**：成功时 report_md 含摘要、≥3 个二级标题、参考来源
- [ ] **AC-R-03**：超步数或失败时有明确 status 与可查看内容
- [ ] **AC-R-04**：入库后新文档出现在知识库且可被 RAG 检索

### 16.6 集成 AC-INT

- [ ] **AC-INT-01**：同一 `kb_id` 完成 §19 全流程无需切换库
- [ ] **AC-INT-02**：`/api/v1/dev/seed` 一键准备演示环境
- [ ] **AC-INT-03**：README 含启动步骤与架构说明

---

## 17. Out of Scope

以下功能 **禁止实现**：

- OAuth、组织级多租户、RBAC（角色权限矩阵）
- ~~用户注册、登录~~ → **已放开**：允许本地用户名密码注册/登录，并以知识库 `owner_id` 做数据隔离
- ~~支付、计费、配额商业化~~ → **部分放开**：允许演示级个人套餐（free/pro）、配额拦截与「模拟开通」；**仍禁止**微信/支付宝等真实支付、发票税务、组织级席位计费
- Word 文档解析（除非 v1.1 单开）
- 真实外网爬虫、浏览器自动化
- 文生视频模型作为整课主路径
- 数字人、Manim、多视频模板
- 系列课程编排、完整 LMS
- 移动端 App
- 微服务、Kubernetes 部署
- Redis、Celery、消息队列中间件
- Next.js / React 前端

---

## 18. 实现顺序（Cursor Step 1～12）

> **严格按序执行。** 每 Step 提交前对照 §16 AC 自检。

| Step | 任务 | 产出 | 验收 |
|------|------|------|------|
| **1** | 项目脚手架 | `app/main.py`, SQLAlchemy, Jinja 首页, `/health` | 服务可启动 |
| **2** | 知识库 CRUD 页面 | KB 模型, 列表/创建/删除 | AC-KB-01,03 |
| **3** | 文档上传与存储 | upload API, documents 表 | 文件可上传 |
| **4** | Ingest 流水线 | 解析, 切片, Chroma, chunks | AC-KB-02 |
| **5** | RAG 问答 | chat 会话, LLM, citations, 问答页 | AC-QA-* |
| **6** | 讲稿生成 | VideoJob, script 生成, 编辑页 | AC-VID-01,02,03 |
| **7** | 视频渲染 | TTS, Pillow slides, FFmpeg, Job 轮询 | AC-VID-04,05,06,07 |
| **8** | Seed + 黄金路径 | `dev/seed`, README | AC-INT-* |
| **9** | 图像对话 | vision 上传, 双模式 | AC-V-* |
| **10** | 研究 Agent | ResearchJob, 工具循环, 报告 | AC-R-01,02,03 |
| **11** | 报告入库 | ingest 报告为文档 | AC-R-04 |
| **12** | 设置页与答辩包装 | 免责声明, Mermaid 架构图 | 可答辩 |

**里程碑**：

- **M1（P0 完成）**：Step 1～8
- **M2（全功能）**：Step 9～12

---

## 19. 黄金演示路径

**目标**：5 分钟内录屏，展示 P0 全流程；P1 模块可剪接或 live 补充。

| 步骤 | 操作 | 解说要点 |
|------|------|----------|
| 1 | 启动 `uvicorn`，访问首页 | 单仓 FastAPI 架构 |
| 2 | 点击「初始化演示数据」或手动建库上传 PDF | 知识库中枢 |
| 3 | 进入问答，问「{演示主题}是什么？」 | **引用卡片** |
| 4 | 进入视频，输入同主题，生成讲稿 | RAG 驱动讲稿 |
| 5 | 修改讲稿一句，点击确认渲染 | 可编辑、防错误固化 |
| 6 | 等待 Job 完成，下载 mp4 播放 | 异步流水线 |
| 7 | （P1）展示研究任务或图像对话 | 多模式融合 |

**演示用主题建议**：「牛顿第一定律」或「机器学习基本概念」（自备 2～3 页 PDF 即可）。

---

## 20. 项目目录结构

```
ai-knowledge-workbench/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app 工厂
│   ├── config.py               # Settings from .env
│   ├── db.py                   # SQLAlchemy engine & session
│   ├── models/
│   │   ├── __init__.py
│   │   ├── knowledge_base.py
│   │   ├── document.py
│   │   ├── chunk.py
│   │   ├── chat.py
│   │   ├── research.py
│   │   └── video.py
│   ├── schemas/                # Pydantic 请求/响应
│   ├── routers/
│   │   ├── pages.py            # HTML 页面路由
│   │   ├── kb.py
│   │   ├── chat.py
│   │   ├── research.py
│   │   ├── video.py
│   │   └── dev.py
│   ├── services/
│   │   ├── ingest.py
│   │   ├── rag.py
│   │   ├── llm.py
│   │   ├── citations.py
│   │   ├── agent.py
│   │   ├── tts.py
│   │   ├── slides.py
│   │   └── video_render.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── kb/
│   │   ├── chat/
│   │   ├── research/
│   │   └── video/
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── scripts/
│   └── seed.py
├── data/                       # gitignore
├── chroma/                     # gitignore
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 21. 环境与依赖

### 21.1 系统依赖

- Python 3.11+
- **FFmpeg**（必须，`ffmpeg -version` 可用）

### 21.2 requirements.txt

```text
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
sqlalchemy>=2.0.0
python-multipart>=0.0.6
jinja2>=3.1.0
httpx>=0.24.0
pymupdf>=1.23.0
chromadb>=0.4.0
python-dotenv>=1.0.0
pydantic-settings>=2.0.0
pillow>=10.0.0
edge-tts>=6.1.0
```

### 21.3 .env.example

```env
# LLM（OpenAI 兼容）
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o-mini

# Embedding
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=sk-xxx
EMBED_MODEL=text-embedding-3-small

# TTS: openai | edge
TTS_PROVIDER=edge

# 数据目录
DATA_DIR=./data
CHROMA_DIR=./chroma
DATABASE_URL=sqlite:///./app.db

# RAG
RAG_TOP_K=5
CHUNK_SIZE=500
CHUNK_OVERLAP=100

# Agent
MAX_AGENT_STEPS=8
AGENT_TIMEOUT_SECONDS=600
```

### 21.4 启动命令

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 API Key
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 22. 非功能需求

| 类别 | 要求 |
|------|------|
| 安全 | API Key 仅存 `.env`，不得硬编码或写入前端 |
| 隐私 | 演示数据本地存储；无外网爬取 |
| 性能 | 问答 P95 &lt; 30s；视频/研究异步 |
| 可靠性 | Job 失败可重试；保留中间产物（讲稿、报告） |
| 可维护 | 模块分层清晰；关键服务可单元测试 |
| 可答辩 | README 含架构图、启动步骤、黄金路径 |
| 合规 | 设置页展示 AI 生成内容免责声明 |

---

## 23. Mock 与降级策略

| 场景 | 策略 |
|------|------|
| RAG 无命中 | LLM 明确提示「库中未找到」，不返回假 citations |
| TTS API 失败 | 降级 `edge-tts`；仍失败则 Job failed，保留 script |
| FFmpeg 失败 | Job failed + `error_message`；日志记录完整命令 |
| Vision 模型不可用 | 图像对话返回友好错误，建议检查 `VISION_MODEL` |
| Agent 超步数 | status=`partial` 或 `failed`，保留已生成章节 |
| 外网研究 | UI 占位步骤，不发起真实请求 |

---

## 24. 答辩附录

### 24.1 架构口述（2 分钟版）

1. **问题**：讲师备课工具分散，知识难溯源，难以快速产出讲解视频。  
2. **方案**：以知识库为中心，FastAPI 统一编排 RAG、Agent、多模态与视频 Job。  
3. **关键设计**：Citations 贯穿问答与讲稿；视频走确定性 FFmpeg 管线；Agent 工具有限步数。  
4. **局限**：单用户演示、一种视频模板、无真实外网研究。

### 24.2 预期追问与参考答案

**Q：为什么不用 Next.js 前后端分离？**  
A：模拟面试 + 个人实现成本；Jinja+HTMX 足够演示；生产可拆前端。

**Q：为什么用 Chroma 不用 Qdrant？**  
A：嵌入式、零运维、演示规模足够；上万文档级可迁 Qdrant/pgvector。

**Q：RAG 如何降低幻觉？**  
A：强制基于检索片段；无命中显式提示；问答与讲稿均展示 citations。

**Q：Agent 如何防止死循环？**  
A：`MAX_STEPS=8`、超时、工具白名单仅 `search_kb`/`write_section`/`finish`。

**Q：为什么不用文生视频？**  
A：可控性、可编辑讲稿、成本、错误不被视频固化。

**Q：视频渲染为什么用 FFmpeg 不用云服务？**  
A：演示可本地复现、流水线透明、便于答辩讲解合成步骤。

**Q：BackgroundTasks 重启丢任务怎么办？**  
A：演示环境可接受；Job 状态持久化在 DB，可扩展为启动时恢复 pending 任务；生产换 Celery。

### 24.3 已知局限（主动交代）

- 单用户、SQLite、中文为主
- 视频模板单一
- 无权限与审计
- PDF 扫描件 OCR 未做
- Agent 仅库内检索

### 24.4 升级路线图（若被问「生产化」）

1. SQLite → PostgreSQL  
2. Chroma → Qdrant 集群  
3. BackgroundTasks → Redis + Celery  
4. Jinja → 独立 React 前端  
5. 增加 OAuth、团队库、用量统计

---

## 25. 修订记录与变更明细

### 25.1 版本摘要

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-10-09 | 初始产品构想 |
| v0.2 | 2026-10-09 | 模拟面试 + Cursor 基线；技术栈为 Next+Qdrant |
| **v1.0** | **2026-10-11** | **全面 PRD；技术栈改为 FastAPI 单仓；补全用户故事、流水线规格、目录结构** |

### 25.2 v1.0 相对 v0.2 变更明细

| 编号 | 类型 | 章节 | 变更内容 |
|------|------|------|----------|
| C-101 | 修订 | 全文 | 文档升级为 v1.0 全面基线；文件名建议 `AI学习知识工作台-项目需求文档.md` |
| C-102 | 修订 | §6 | **技术栈由 Next+Qdrant+Redis 改为 FastAPI+Jinja+HTMX+SQLite+Chroma** |
| C-103 | 新增 | §4 | 用户故事 US-01～US-09 |
| C-104 | 修订 | §5 | 架构图改为 FastAPI 单仓 + Chroma + FFmpeg |
| C-105 | 新增 | §7～11 | 各模块详细流水线、参数、Prompt 模板、状态机 |
| C-106 | 修订 | §13 | 路由改为 Jinja 页面；增加 HTMX 约定 |
| C-107 | 修订 | §14 | 补全字段类型与 JSON 结构 |
| C-108 | 继承 | §15 | API 清单继承 v0.2，路径微调 |
| C-109 | 修订 | §16 | AC 拆分为 KB/QA/VID/V/R/INT |
| C-110 | 修订 | §18 | 实现顺序对齐 FastAPI 单仓 12 Step |
| C-111 | 新增 | §20 | 完整项目目录结构 |
| C-112 | 新增 | §21 | requirements.txt 与 .env.example 全文 |
| C-113 | 修订 | §24 | 答辩追问适配新栈（Chroma、HTMX、FFmpeg） |
| C-114 | 删除 | — | 移除 v0.2 中 Docker/Qdrant/Next 相关强制要求 |

### 25.3 后续修订规范

- 版本号递增：v1.1, v1.2…  
- 在 §25.2 追加 C-1xx 行  
- 修改章节标题标注 **【v1.x 修订】** 或 **【v1.x 新增】**

---

## 26. 术语表

| 术语 | 定义 |
|------|------|
| RAG | Retrieval-Augmented Generation；检索增强生成 |
| Chunk | 文档切片后的文本块 |
| Citation | 回答或讲稿引用的知识库片段及来源信息 |
| Job | 异步任务（ResearchJob 或 VideoJob） |
| 黄金路径 | §19 答辩必须演示的端到端流程 |
| OpenAI 兼容 API | 遵循 OpenAI SDK/HTTP 格式的第三方模型接口 |
| HTMX | 通过 HTML 属性实现局部刷新的轻量前端库 |
| 讲稿流水线 | script 生成 → 用户确认 → TTS + 幻灯片 + FFmpeg 合成 |

---

**文档结束**

*下一步：将本 PRD 交给 Cursor，指令为「严格按 PRD v1.0 从 Step 1 开始实现」。*
