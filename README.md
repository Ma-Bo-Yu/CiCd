# AI 学习知识工作台

**唯一使用入口**：http://127.0.0.1:8000（FastAPI + Jinja2 + HTMX，静态资源本地化，不依赖外网 CDN）

| 能力 | 路径 |
|------|------|
| 登录 / 注册 | `/login` · `/register` |
| 知识库 | `/kb` |
| 知识库问答（RAG + 引用） | `/chat` |
| AI 对话（文字 + 粘贴/📎 识图） | `/chat/ai` |
| 研究 Agent | `/research` |
| 讲解视频 | `/video` |
| 套餐与用量 | `/billing` |
| 设置 | `/settings` |

- **元数据**：MySQL 库 `ai`（也可用 SQLite）
- **向量**：Chroma 目录 `./chroma`
- **多用户**：本地注册/登录；知识库按 `owner_id` 隔离
- **套餐**：免费版 / 专业版（模拟开通，无真支付）；超额创建会引导至 `/billing`

商业假设见：[AI学习知识工作台-商业与市场假设.md](./AI学习知识工作台-商业与市场假设.md)

## 1. MySQL

1. 启动 **MySQL 8**（如小皮/phpStudy）
2. 确认库 **`ai`** 存在
3. `.env` 中配置连接串，例如：

```env
DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/ai?charset=utf8mb4
```

首次启动后端会自动建表，并创建演示账号 **`admin` / `admin123`**（默认 **专业版**，避免演示被配额打断）。

## 2. 账号与套餐

- 打开站点后先 **登录** 或 **注册**（新用户默认 **免费版**）
- 默认管理员：`admin` / `admin123`
- 在 **套餐** 页可查看用量，并「模拟开通专业版（30 天）」或恢复免费版

| 项 | 免费 | 专业（模拟 ¥29/月） |
|----|------|---------------------|
| 知识库 | 2 | 20 |
| 文档 | 10 | 200 |
| 本月视频 | 2 | 30 |
| 本月研究 | 3 | 50 |

## 3. 演示资料（理论题）

```env
SEED_DOCS_DIR=C:/Users/admin/Desktop/理论题
SEED_DOC_FILES=复盘(1).md,面试题整理_含回答思路.md,AI相关面试题整理.md
```

登录后在首页/设置点击 **导入理论题示例资料**（占用当前用户配额）。

## 4. 启动

```powershell
cd "c:\Users\admin\Desktop\个人项目2"
.\scripts\run-all.ps1
# 或
.\scripts\run-backend.ps1
```

若 **8000** 被占用：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## 5. 环境变量（`.env`）

- **LLM / Embedding**：未配置时问答为演示降级
- **TTS**：`TTS_PROVIDER=dashscope` + `DASHSCOPE_API_KEY`
- **FFmpeg**：项目内 `tools/ffmpeg/bin`；或将 `FFMPEG_BIN_DIR` 指到正确 bin（勿用旧目录 `个人2`）
- **SESSION_SECRET** / **BOOTSTRAP_ADMIN_***：会话与管理员

## 6. 阿里云部署与 CI/CD

- **线上**：http://47.114.54.192:8000/（ECS 上 Docker Compose）
- **手动部署**：`.\scripts\deploy-aliyun.ps1`
- **自动部署**：push 到 `master`/`main` 后由 GitHub Actions 同步并重建；一次性配置见 [docs/CI-CD.md](./docs/CI-CD.md)

## 7. 交付前自测

```powershell
$env:PYTHONPATH="c:\Users\admin\Desktop\个人项目2"
python scripts\smoke_pages.py
```

手工走一遍：

1. 未登录跳转登录；顶栏有用户名与 **套餐**
2. 免费用户超额创建 → 跳转 `/billing`
3. 模拟开通后限额放大
4. 知识库上传 → indexed；问答有引用
5. 研究 / 视频黄金路径可跑通（admin 默认为 pro）
