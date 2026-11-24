# AI 学习知识工作台 — 产品需求文档（PRD）

**文档版本**：v0.2  
**创建日期**：2026-10-09  
**最后更新**：2026-10-09  
**状态**：模拟面试答辩 + Cursor 实现基线  

> **给 Cursor 的执行说明**：实现时必须遵循本文 **§16 实现顺序**、**§15 技术栈锁定** 与 **§17 黄金演示路径**；不得引入未列技术；Out of Scope 功能不得实现。

---

## 变更标注说明

- 章节标题带 **`【v0.2 新增】`**：v0.1 中不存在的新章节。  
- 章节标题带 **`【v0.2 修订】`**：v0.1 有对应内容，本版已改写或扩充。  
- 无标注章节：v0.1 原文保留（仅做格式或措辞微调时会在 §20 变更明细中列出）。  
- 完整逐条变更见文档末尾 **§20 修订记录与变更明细**。

---

## 1. 文档说明 【v0.2 修订】

本文档描述将 **知识库问答**、**图像对话**、**研究智能体**、**课程内容生成（讲解视频）** 融合于同一平台的目标、范围、架构与验收标准。

| 维度 | v0.1 | v0.2 |
|------|------|------|
| 主要用途 | 立项草案 | **模拟面试答辩** + **Cursor 自动化实现** 的唯一需求基线 |
| 读者 | 产品/技术评审 | **答辩者**、**Cursor Agent**、面试官（架构与 trade-off） |
| 完成定义 | 方向对齐 | **黄金演示路径可跑通** + 各模块 AC 满足 **§10** |

---

## 2. 产品愿景 【v0.2 修订】

构建面向 **教师、培训从业者、企业知识工作者** 的统一 AI 工作台：在同一套账号、知识库与对话体系中，完成「查资料 → 深度研究 → 多模态答疑 → 结构化产出讲解视频」的闭环。

**一句话定位**：以 **个人/演示级知识库为中枢**，提供多种 AI 能力模式，并将知识 **可溯源地** 转化为讲解内容。

**【v0.2 新增】答辩叙事（Elevator Pitch，30 秒）**  
「这是一个以 RAG 知识库为中心的学习工作台：用户上传资料后可以带引用问答；需要深度整理时走研究 Agent；看图问概念走多模态；最后把同一库里的知识变成可编辑讲稿并渲染成幻灯片讲解视频。四条能力共用一套数据和模型网关，不是四个拼凑的 Demo。」

---

## 3. 目标用户与典型场景

| 用户类型 | 典型场景 |
|----------|----------|
| 教师 / 教研 | 基于教材/讲义库答疑；针对知识点生成讲解稿与幻灯片视频 |
| 企业培训 | 内部制度/产品文档问答；新员工课程批量生成草稿 |
| 知识工作者 | 课题调研报告；将调研结论入库并生成对外培训片段 |
| 学习者（次要） | 对上传资料提问；看图问概念（演示版与创作端同一用户即可） |

**【v0.2 新增】模拟面试默认 persona**  
答辩者扮演产品/全栈负责人，目标用户简化为 **「自备资料备课的单人讲师」**，不做多租户与团队协作，降低 scope。

---

## 4. 产品能力范围

### 4.1 知识库问答（核心基础能力）【v0.2 修订】

**描述**：用户针对已入库文档进行自然语言提问，系统基于 RAG 返回答案，并 **附带引用来源**（文档名、chunk 摘要、定位信息）。

**需求要点**：

- 文档上传、解析、切片、向量化与索引
- 多轮对话，会话历史与 **某一知识库** 绑定
- 回答 **必须** 展示引用片段；UI 上可展开原文上下文
- MVP：**单用户**，无需登录或 **简易本地单用户**（见 §15）

**成功标准**：演示库内 FAQ 类问题回答合理、引用可核对；同步问答 P95 &lt; 30s（演示环境可放宽）。

**【v0.2 新增】验收标准 AC-KB-QA**  
见 §10.1。

---

### 4.2 图像对话（多模态能力）【v0.2 修订】

**描述**：用户上传图片并文字提问；支持 **纯视觉理解** 与 **视觉 + 绑定知识库 RAG** 两种子模式。

**需求要点**：

- 支持 PNG、JPEG、WebP；单会话内多轮图文
- 子模式由用户切换（Toggle），默认可为「纯视觉」
- **与文本问答共用「会话」实体**，通过 `mode` 字段区分（见 §13）

**成功标准**：能对图表/板书类图片给出合理描述；在「视觉+RAG」模式下，涉及库内事实时应返回引用。

**【v0.2 新增】验收标准 AC-VISION**  
见 §10.2。

---

### 4.3 研究智能体（高复杂度能力）【v0.2 修订】

**描述**：用户给出研究主题，Agent 执行 **规划 → 库内检索（必须）→ 综合 → 结构化报告**。

**需求要点**：

- 任务状态可见：步骤列表、当前步骤、最终 Markdown 报告
- **MVP 仅库内检索**，不实现真实外网爬虫；外网步骤 **Mock**（见 §18）
- 步数上限 **≤ 8**，总超时 **≤ 10 分钟**（可配置常量）
- 报告支持 **一键写入知识库** 为 Markdown 文档并触发索引

**成功标准**：对演示库内主题产出 3～5 节报告草稿；超步数或失败时返回已收集内容与明确错误信息。

**【v0.2 新增】验收标准 AC-RESEARCH**  
见 §10.3。

---

### 4.4 课程内容生成器 — 讲解视频（差异化能力）【v0.2 修订】

**产品理解**：用户输入 **知识问题或主题**，系统产出 **讲解型视频**（旁白 + 幻灯片画面 + 字幕）。

**本质定义**：**「AI 编导 + 自动制片」流水线**，非单次文生视频。

**MVP 流水线（必须实现）**：

```
输入（主题 + 绑定知识库 + 可选：目标时长 3/5/8 分钟）
  → 生成 outline + script（Markdown，可编辑）
  → 用户点击「确认并渲染」
  → 异步任务：TTS 按句生成音频 → 幻灯片页与句子对齐 → 烧录字幕 → 合成 mp4
  → 下载 mp4 + 保留 script 副本
```

**需求要点**：

- 讲稿结构：引入 → 要点（≥2）→ 例子 → 小结
- 生成讲稿时 **必须调用 RAG** 拉取片段写入 prompt；UI 展示「参考来源」列表
- **仅 1 种视频模板**：「每句旁白对应 1 张幻灯片卡片（标题+要点 bullets）」
- 渲染异步队列 + 状态：`pending | running | succeeded | failed`

**非 MVP（禁止 Cursor 实现）**：

- 数字人、Manim、文生视频、系列课、PPT 源文件导出

**成功标准**：演示主题下生成 **1～5 分钟** mp4，音画同步，字幕与旁白一致率可肉眼看懂。

**【v0.2 新增】验收标准 AC-VIDEO**  
见 §10.4。

---

## 5. 融合架构原则（产品 + 技术）

1. **一个平台，多种模式**：四种能力为 **模式/技能**，共享知识库、模型网关、审计日志。
2. **知识库为中枢**：问答、研究、课程讲稿均优先检索同一 corpus。
3. **分档 SLA**：问答同步；研究与视频 **异步 Job**。
4. **可编辑工作流**：视频必须 **script 确认后再渲染**。
5. **引用与溯源**：问答、讲稿展示 citations；报告写入库后参与后续 RAG。

**【v0.2 新增】**  
6. **演示优先**：允许 Mock 外网与研究中间数据，但 **RAG 与视频主路径必须真实跑通**。  
7. **单仓库 Monorepo**：前后端同仓，便于 Cursor 连续编辑（见 §15）。

---

## 6. 功能结构（逻辑模块）

```
┌─────────────────────────────────────────────────────────┐
│              演示级单用户 / 本地配置（API Keys）            │
├─────────────────────────────────────────────────────────┤
│  知识库管理  │  会话中心（多模式）  │  异步任务中心          │
├─────────────────────────────────────────────────────────┤
│  模式：chat_qa │ chat_vision │ research │ course_video   │
├─────────────────────────────────────────────────────────┤
│  共用：RAG Pipeline │ LLM Gateway │ Agent Orchestrator     │
├─────────────────────────────────────────────────────────┤
│  视频：Script Gen │ TTS │ Slide Builder │ FFmpeg Compose │
└─────────────────────────────────────────────────────────┘
```

---

## 7. 用户界面 【v0.2 修订】

### 7.1 信息架构

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 工作台首页 | 当前知识库、快捷入口、最近任务 |
| `/kb` | 知识库列表 | 创建/删除库 |
| `/kb/:id` | 知识库详情 | 文档列表、上传、索引状态 |
| `/chat` | 对话 | 模式切换：问答 / 图像 |
| `/research` | 研究任务 | 新建、列表、详情（步骤+报告） |
| `/course` | 课程视频 | 新建、列表、向导（script→渲染→下载） |
| `/settings` | 设置 | API Key、模型名、演示数据初始化 |

### 7.2 统一 UI 元素

- 全局 **知识库选择器**（对话/研究/课程必须显示当前库）
- **引用卡片** CitationCard：文档名、摘录、相似度（可选）
- **Job 进度条**：研究 Agent、视频渲染

**【v0.2 新增】** 具体组件清单见 §14.2。

---

## 8. 非功能需求 【v0.2 修订】

| 类别 | 要求 |
|------|------|
| 安全 | 演示版：API Key 仅存服务端 `.env`；不上传 Key 到前端日志 |
| 隐私 | 无外网研究真实抓取；Mock 数据需要标注 |
| 性能 | 问答同步；研究/视频异步；前端轮询或 SSE 二选一 |
| 可观测 | 后端结构化日志：`request_id`, `job_id`, `kb_id`, 模型名 |
| 合规 | 设置页与关于页固定 **AI 生成内容免责声明** |
| **【v0.2 新增】可部署** | `docker compose up` 或 README 三步启动；提供 `seed` 演示知识库 |
| **【v0.2 新增】可答辩** | README 含架构图（Mermaid）、黄金路径操作步骤 |

---

## 9. MVP 范围与阶段 【v0.2 修订】

**面试交付 = Phase Demo（一条路径）+ Phase Full MVP（四能力均可单独演示）**

| 阶段 | 目标 | 包含 |
|------|------|------|
| **Phase Demo** | 答辩录屏 5 分钟 | 上传 PDF → 问答带引用 → 生成 script → 渲染 mp4 下载 |
| **Phase Full MVP** | 模块齐全 | + 图像对话 + 库内 Research Agent + 报告入库 |
| Phase 3（不做） | — | 外网研究、多视频模板、团队库、计费 |

**【v0.2 新增】Cursor 里程碑**  
以 **§16 实现顺序** 的 Step 编号为准；Phase Demo = Step 1～8；Phase Full = Step 1～12。

---

## 10. 验收标准（Acceptance Criteria）【v0.2 新增】

### 10.1 AC-KB-QA

- [ ] AC-KB-01：可创建知识库并上传至少 PDF、Markdown 各 1 个
- [ ] AC-KB-02：上传后显示 `indexed` 或失败原因；失败可重试索引
- [ ] AC-KB-03：提问后回答含 **≥1 条** 引用，且引用文本来自该库 chunk
- [ ] AC-KB-04：同一会话内可追问，上下文保留 ≥5 轮
- [ ] AC-KB-05：无文档库时问答返回友好提示，不 500

### 10.2 AC-VISION

- [ ] AC-V-01：可上传图片并发送文本问题，得到模型回复
- [ ] AC-V-02：「视觉+RAG」模式下，回复含 citations（当检索命中时）
- [ ] AC-V-03：图片与消息保存在同一会话历史中，刷新后可查看

### 10.3 AC-RESEARCH

- [ ] AC-R-01：创建任务后可见步骤列表（至少：规划、检索×N、撰写报告）
- [ ] AC-R-02：报告为 Markdown，含摘要、≥3 个二级标题、参考来源列表
- [ ] AC-R-03：步数达上限时任务 `failed` 或 `partial`，UI 可查看 partial 报告
- [ ] AC-R-04：「入库」后该 Markdown 出现在知识库文档列表且可被 RAG 检索

### 10.4 AC-VIDEO

- [ ] AC-VID-01：从主题生成 outline + script，可编辑 textarea 后保存
- [ ] AC-VID-02：未确认 script 时「渲染」按钮 disabled 或二次确认
- [ ] AC-VID-03：渲染完成后提供 mp4 下载链接，时长 1～5 分钟（演示可配置加速）
- [ ] AC-VID-04：视频含 burned-in 或软字幕轨（至少一种）；口播与字幕基本一致
- [ ] AC-VID-05：script 生成阶段展示所用 RAG 来源列表

### 10.5 AC-INTEGRATION（黄金路径）

- [ ] AC-INT-01：同一 `kb_id` 完成 §17 全流程无需换库
- [ ] AC-INT-02：端到端耗时在演示环境可接受（视频渲染允许异步等待 UI）

---

## 11. 明确不在范围内（Out of Scope）【v0.2 修订】

- 零编辑一键完美、长时长电影级视频
- 通用文生视频作为整课唯一路径
- 完整 LMS、移动端原生 App
- **【v0.2 新增】** 多租户、OAuth、支付、细粒度 RBAC
- **【v0.2 新增】** 真实外网爬虫/浏览器 Agent（仅 Mock，见 §18）
- **【v0.2 新增】** Word 解析可列为 optional；MVP **至少** PDF + Markdown

---

## 12. 开放问题决议（原开放问题关闭）【v0.2 新增】

| 原问题 | v0.2 默认决议（Cursor 不得另选除非改 PRD） |
|--------|---------------------------------------------|
| B 端 vs C 端 | **演示单用户**，无团队 |
| 视频渲染自建 vs 第三方 | **自建**：TTS API + FFmpeg 本地/容器合成 |
| 语言 | **中文** 讲稿与 TTS；UI 中文 |
| 国产/私有化模型 | **OpenAI 兼容 API**（含 OpenAI / DeepSeek / 通义等），通过 `BASE_URL` + `MODEL` 配置 |
| 课程与研究是否共用项目实体 | **共用 `kb_id` + optional `project_id`**（v0.2 可仅 `kb_id`；`project_id` 作 optional 字段预留） |

---

## 13. 数据模型概要 【v0.2 新增】

### 13.1 实体关系（ER 简述）

- `KnowledgeBase` 1 — N `Document`
- `Document` 1 — N `Chunk`（向量存 Milvus/Qdrant/pgvector 三选一，见 §15）
- `KnowledgeBase` 1 — N `ChatSession`
- `ChatSession` 1 — N `Message`（role: user | assistant | system；可选 `image_url`）
- `KnowledgeBase` 1 — N `ResearchJob`
- `KnowledgeBase` 1 — N `VideoJob`
- `VideoJob` 1 — 1 `Script`（版本随编辑更新）

### 13.2 核心字段（实现时必须包含）

**KnowledgeBase**  
`id`, `name`, `description`, `created_at`

**Document**  
`id`, `kb_id`, `filename`, `mime_type`, `status` (pending|processing|indexed|failed), `storage_path`, `error_message?`

**Chunk**  
`id`, `document_id`, `kb_id`, `text`, `metadata` (page, heading), `embedding_id`

**ChatSession**  
`id`, `kb_id`, `mode` (chat_qa | chat_vision), `title`, `created_at`

**Message**  
`id`, `session_id`, `role`, `content`, `citations` (JSON array), `image_path?`, `created_at`

**ResearchJob**  
`id`, `kb_id`, `topic`, `status`, `steps` (JSON), `report_md?`, `created_at`, `updated_at`

**VideoJob**  
`id`, `kb_id`, `topic`, `target_minutes`, `status`, `script_md`, `script_confirmed` (bool), `output_video_path?`, `citations` (JSON), `error_message?`

### 13.3 Message.citations JSON 形状

```json
[
  {
    "document_id": "uuid",
    "document_name": "example.pdf",
    "chunk_id": "uuid",
    " excerpt": "引用片段..."
  }
]
```

---

## 14. API 概要 【v0.2 新增】

**约定**：REST + JSON；前缀 `/api/v1`；错误体 `{ "error": { "code", "message" } }`。

### 14.1 知识库与文档

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge-bases` | 列表 |
| POST | `/knowledge-bases` | 创建 |
| GET | `/knowledge-bases/:id` | 详情 |
| DELETE | `/knowledge-bases/:id` | 删除 |
| POST | `/knowledge-bases/:id/documents` | multipart 上传 |
| GET | `/knowledge-bases/:id/documents` | 文档列表 |
| POST | `/documents/:id/reindex` | 重新索引 |

### 14.2 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/sessions` | body: `{ kb_id, mode }` |
| GET | `/chat/sessions` | 列表 |
| GET | `/chat/sessions/:id/messages` | 历史 |
| POST | `/chat/sessions/:id/messages` | 提问；vision 时 multipart（text + image） |
| POST | `/chat/sessions/:id/messages/stream` | **可选** SSE 流式；MVP 可用非流式 |

### 14.3 研究

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/research/jobs` | body: `{ kb_id, topic }` → 返回 job_id |
| GET | `/research/jobs/:id` | 状态、步骤、报告 |
| POST | `/research/jobs/:id/ingest` | 报告入库为 Document |

### 14.4 视频

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/video/jobs` | body: `{ kb_id, topic, target_minutes }` → 生成 script |
| PATCH | `/video/jobs/:id/script` | 更新 script_md |
| POST | `/video/jobs/:id/confirm` | `script_confirmed=true` 并入队渲染 |
| GET | `/video/jobs/:id` | 状态与下载 URL |
| GET | `/video/jobs/:id/download` | mp4 文件流 |

### 14.5 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/dev/seed` | 仅 dev：初始化演示 KB（答辩用） |
| GET | `/health` | 健康检查 |

### 14.6 前端页面 ↔ API 映射（Cursor 实现清单）

- `KnowledgeBaseList` → GET/POST `/knowledge-bases`
- `DocumentUpload` → POST documents
- `ChatPanel` → sessions + messages
- `ResearchPanel` → research jobs
- `CourseWizard` → video jobs 状态机
- `CitationCard` → 消费 message.citations / video citations

---

## 15. 技术栈锁定 【v0.2 新增】

| 层 | 选型 | 备注 |
|----|------|------|
| 前端 | **Next.js 14+ (App Router)** + TypeScript + Tailwind | 中文 UI |
| 后端 | **Python 3.11+ FastAPI** | 同仓 `apps/web` + `apps/api` 或 `frontend/` + `backend/` |
| 向量库 | **Qdrant**（Docker）或 **pgvector**（若已用 Postgres） | 二选一，PRD 默认 **Qdrant** |
| 元数据 DB | **SQLite**（演示）或 Postgres | 默认 SQLite 降低搭建成本 |
| 队列 | **Redis + RQ** 或 **FastAPI BackgroundTasks + DB job 表** | MVP 可用 **DB job 表 + 后台线程**，Redis 可选 |
| 文档解析 | `pymupdf` (PDF) + 原生 Markdown | |
| Embedding | OpenAI 兼容 `embeddings` API | 模型名 `.env` 配置 |
| LLM | OpenAI 兼容 chat/completions | 支持 vision 的模型用于图像对话 |
| TTS | OpenAI TTS 或 Edge TTS（fallback） | 需中文音色 |
| 视频 | **FFmpeg** + 静态幻灯片（HTML/CSS→PNG 或 Pillow） | 禁止依赖商业成片 SaaS |
| 部署 | `docker-compose.yml`：api + web + qdrant | |

**环境变量（最小集）**  
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBED_MODEL`, `TTS_PROVIDER`, `DATA_DIR`

---

## 16. Cursor 实现顺序 【v0.2 新增】

> 严格按 Step 顺序提交；每 Step 完成应满足对应 AC 子集。

| Step | 内容 | 完成标志 |
|------|------|----------|
| 1 | Monorepo 脚手架、docker-compose、health | `/health` 200 |
| 2 | KB/Document 模型 + 上传 + PDF/MD 解析 | AC-KB-01 |
| 3 | 切片 + Embedding + Qdrant 检索 | AC-KB-02 |
| 4 | Chat 会话 + RAG 问答 + citations | AC-KB-03,04,05 |
| 5 | VideoJob：script 生成（RAG）+ 编辑 + citations 展示 | AC-VID-01,05 |
| 6 | TTS + 幻灯片生成 + FFmpeg 合成 mp4 | AC-VID-03,04 |
| 7 | script 确认门控 + 下载 | AC-VID-02 + AC-INT |
| 8 | `/dev/seed` + README 黄金路径 | §17 可录屏 |
| 9 | Vision 上传 + 双模式 | AC-V-* |
| 10 | ResearchJob 状态机 + 库内工具 + 报告 | AC-R-01,02,03 |
| 11 | 报告 ingest 再 RAG | AC-R-04 |
| 12 | 设置页、免责声明、Mermaid 架构 README | §8 可答辩 |

---

## 17. 黄金演示路径（答辩 5 分钟）【v0.2 新增】

1. 启动系统，运行 seed（或手动创建库「高中物理-力学」+ 上传演示 PDF）。
2. **问答**：提问「什么是牛顿第一定律？」→ 展示 **引用卡片**。
3. **图像**（若 Phase Full）：上传力的示意图 → 问「图中受力如何分析？」→ 切换视觉+RAG。
4. **研究**（若 Phase Full）：主题「牛顿定律应用」→ 查看步骤与报告 → **一键入库**。
5. **课程**：主题「牛顿第一定律讲解」→ 生成讲稿 → 改一句 → **确认渲染** → 等待 Job 完成 → **下载 mp4**。
6. 收尾：同一知识库内再提问，验证入库报告或讲稿关联知识可被检索（可选）。

**答辩话术要点**：强调 **中枢库**、**引用**、**异步视频**、**Agent 步数上限**、**外网 Mock 而非真实爬虫**。

---

## 18. Mock 与降级策略 【v0.2 新增】

| 能力 | 真实实现 | Mock/降级 |
|------|----------|-----------|
| RAG | 必须真实 | 检索空时 LLM 回答须带「未在库中找到」提示 |
| 研究-外网 | 不实现 | 步骤 UI 可显示「外网检索（演示跳过）」占位 |
| 研究-规划/检索 | 必须真实调用 LLM + 库内检索工具 | — |
| TTS 失败 | — | 降级 Edge TTS 或返回错误并保留 script |
| FFmpeg 失败 | — | Job `failed` + 日志；可下载 script 作为兜底 |

---

## 19. 答辩附录 — 预期追问与 trade-off 【v0.2 新增】

### 19.1 为何不用一个模型端到端生成视频？

**答**：可控性、可编辑性、成本、错误不被视频固化；幻灯片+TTS 管线可审查 script。

### 19.2 切片策略？

**答**：默认按段落/固定 token 窗 + overlap；PDF 带 page metadata；答辩可提后续 heading-aware 切片。

### 19.3 Agent 如何防止死循环？

**答**：硬编码 `MAX_STEPS`、总超时、工具白名单（仅 `search_kb`）；状态持久化便于 UI 展示。

### 19.4 图像+RAG 如何编排？

**答**：先 vision 描述/提取关键词 → 再 RAG → 再融合生成；或并行检索以用户问题+图片描述为 query。

### 19.5 已知局限（主动交代加分）

- 演示单用户、SQLite、中文为主  
- 视频模板单一  
- 无真实外网研究  
- 未做复杂权限与内容审核  

---

## 20. 修订记录与变更明细

### 20.1 版本摘要

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-10-09 | 初始需求，融合产品讨论结论 |
| v0.2 | 2026-10-09 | **模拟面试 + Cursor 可执行 PRD** 全面扩充 |

### 20.2 v0.2 相对 v0.1 变更明细（逐条标注）

| 编号 | 类型 | 章节 | 变更内容 |
|------|------|------|----------|
| C-01 | 修订 | §1 | 增加文档用途：模拟面试答辩、Cursor 实现基线；增加给 Cursor 的执行说明引用 |
| C-02 | 新增 | 文首 | **变更标注说明**（【v0.2 新增/修订】标记规则） |
| C-03 | 修订 | §2 | 增加 30 秒 Elevator Pitch |
| C-04 | 新增 | §3 | 模拟面试默认 persona（单人讲师） |
| C-05 | 修订 | §4.1～4.4 | 各能力绑定 **AC 引用**；权限改为单用户；研究外网改为库内+Mock；视频禁止项写死 |
| C-06 | 新增 | §5 | 原则 6～7：演示优先、Monorepo |
| C-07 | 修订 | §6 | 模块图更新（Job 中心、模式枚举名） |
| C-08 | 修订 | §7 | 路由级 IA、组件引用 §14.2 |
| C-09 | 修订 | §8 | 增加 docker 部署、README、免责声明 |
| C-10 | 修订 | §9 | Phase 重定义为 Demo / Full MVP；对齐 §16 Step |
| C-11 | 新增 | §10 | **全套验收标准 AC-KB/ V/ R/ VID/ INT** |
| C-12 | 修订 | §11 | Out of Scope 扩充（多租户、外网、Word optional） |
| C-13 | 新增 | §12 | **关闭 v0.1 开放问题** 为默认技术决议 |
| C-14 | 新增 | §13 | **数据模型** 实体、字段、citations JSON |
| C-15 | 新增 | §14 | **REST API 清单** 与前端组件映射 |
| C-16 | 新增 | §15 | **技术栈锁定** 与环境变量 |
| C-17 | 新增 | §16 | **Cursor 实现顺序** Step 1～12 |
| C-18 | 新增 | §17 | **黄金演示路径**（5 分钟录屏脚本） |
| C-19 | 新增 | §18 | **Mock 与降级策略** |
| C-20 | 新增 | §19 | **答辩追问与 trade-off** |
| C-21 | 修订 | §20 | 原 §14 修订记录扩展为 **变更明细表 C-01～C-21** |
| C-22 | 删除 | 原脚注 | 删除 v0.1 末尾「后续应补充…」脚注（内容已纳入 v0.2） |

---

## 21. 术语表

| 术语 | 含义 |
|------|------|
| RAG | 检索增强生成，基于向量检索从知识库取片段再生成回答 |
| 研究智能体 | 多步骤规划与工具调用的调研任务（MVP 仅库内工具） |
| 讲解视频流水线 | 讲稿 → 配音 → 幻灯片 → FFmpeg 合成 |
| 模式 | `chat_qa` / `chat_vision` / research / course_video |
| 黄金路径 | §17 答辩必须跑通的端到端流程 |
| Job | 异步任务：ResearchJob 或 VideoJob |

---

*文档结束。下次修订请递增版本号（v0.3…），并在 §20.2 追加变更行（C-23…），且在本文章节标题标注【v0.x 新增/修订】。*
