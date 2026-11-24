# CI/CD：改代码 → 自动上线阿里云

流程：**本机 push → GitHub Actions → SCP 到 ECS → `docker compose build && up -d`**

Docker 装在 ECS 上负责跑容器；GitHub 负责「一改代码就触发部署」。`.env.production`、数据库、Chroma 数据**不会**被覆盖。

## 一次性准备

### 1. 把项目推到 GitHub

在 GitHub 新建空仓库（不要勾选自动生成 README），本机执行：

```powershell
cd "c:\Users\admin\Desktop\个人项目2"
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin master
```

### 2. 准备部署用 SSH 密钥

建议单独一把只用于 CI（不要用登录密码）：

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\github_actions_ecs -N '""'
```

把**公钥**写进 ECS：

```powershell
type $env:USERPROFILE\.ssh\github_actions_ecs.pub
# 在服务器执行：追加到 /root/.ssh/authorized_keys
```

本机验证：

```powershell
ssh -i $env:USERPROFILE\.ssh\github_actions_ecs root@47.114.54.192 "echo ok"
```

### 3. 配置 GitHub Secrets

仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**：

| Name | 值 |
|------|-----|
| `ECS_HOST` | `47.114.54.192` |
| `ECS_USER` | `root` |
| `ECS_SSH_KEY` | `github_actions_ecs` **私钥**全文（含 `BEGIN`/`END`） |

### 4. 确认服务器已有运行环境

`/opt/ai-workbench` 里已有 Docker、`.env.production`、数据卷（你当前已部署过即可）。

## 日常用法

改完代码：

```powershell
git add .
git commit -m "说明改了什么"
git push
```

到 GitHub → **Actions** 看 **Deploy to Aliyun ECS** 是否绿勾。成功后打开：

http://47.114.54.192:8000/

也可在 Actions 里点 **Run workflow** 手动部署。

## 注意

- 首次流水线可能要 **10～20 分钟**（远端构建镜像）。
- 只改 `.env.production`：在服务器手改后执行 `docker compose up -d`，不要指望 Git 同步密钥。
- 安全组需继续放行 **TCP 8000**。
