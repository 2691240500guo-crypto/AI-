# PyCharm 启动说明（智能健康测评系统）

> 适用：在 PyCharm 中手动启动 后端(FastAPI:8000) + 前端(Vue3:5173)
> 前置：本机 MySQL(3306) 与 docker 容器 MinIO/Milvus/Neo4j 已运行

---

## 〇、一键预览（不想手动时）

直接双击项目根目录 `start.bat`（首次会自动装依赖，后续直接起服务）。
但如果你要在 PyCharm 里调试，请按下面步骤走。

---

## 一、启动后端 FastAPI（端口 8000）

### 1. 用 PyCharm 打开 backend

- PyCharm → `File` → `Open` → 选择 `D:\项目阶段\项目实操\智能健康测评\backend`
- 信任项目（Trust Project）

### 2. 配置 Python 解释器（venv）

- `File` → `Settings` → `Project: backend` → `Python Interpreter`
- 点齿轮/`Add Interpreter` → `Add Local Interpreter` → 选 `Virtualenv Environment`
  - 新建位置建议：`D:\项目阶段\项目实操\智能健康测评\backend\venv`
  - Base interpreter：你本机的 Python 3.10+（如 `C:\Python313\python.exe`）
- 等 PyCharm 建好虚拟环境后，在底部 `Terminal` 执行依赖安装：

```bash
# Windows PowerShell / CMD（在 backend 目录下）
pip install -r requirements.txt
```

### 3. 检查配置 backend\.env

```
MYSQL_PASSWORD=123456      ← 改成你本机 MySQL root 密码
SILICONFLOW_API_KEY=sk-... ← 硅基流动 API Key
```
> 其余 MinIO/Minilvus/Neo4j 默认值与你的 docker 容器一致（9000/19530/7687），
> 端口/账号密码如果和你的容器不同，按实际改。

### 4. 启动运行

方式 A（推荐，带热重载）：
```
uvicorn app.main:app --reload --port 8000
```

方式 B（PyCharm Run 配置）：
- 右上角 `Add Configuration` → `+` → `Python`
  - Script path: 选择 `backend\app\main.py`
  - Parameters 填：`--reload --port 8000`（可选）
  - Working directory: `backend`
  - Python interpreter: 选刚建好的 venv
- 点 ▶ 运行

### 5. 验证

浏览器打开 http://127.0.0.1:8000/docs → 能看到 Swagger 接口文档即成功。
启动日志会输出：`✓ MySQL 表结构就绪`、`Neo4j 连接成功/图谱跳过导入` 等。

---

## 二、启动前端 Vue3（端口 5173）

### 1. 用 PyCharm 打开 frontend

- `File` → `Open` → 选择 `D:\项目阶段\项目实操\智能健康测评\frontend`
- 信任项目

### 2. 安装依赖（首次必做）

在 frontend 目录的 Terminal 执行：
```bash
npm install
```
> 若报 node/npm 找不到：先装 Node.js 18+ 并重启 PyCharm。

### 3. 启动运行

方式 A（Terminal）：
```bash
npm run dev
```

方式 B（PyCharm Run 配置）：
- `Add Configuration` → `+` → `npm`
  - package.json: `frontend/package.json`
  - Scripts: `dev`
- 点 ▶

### 4. 验证

浏览器打开 http://127.0.0.1:5173 → 出现顶部导航
「🍎营养风险测评 / 📊可视化总览 / 📚多模态知识库 / 🕸️营养知识图谱」即成功。

> 前端已配置 Vite 代理：页面里的 `/api` 请求会自动转发到 http://127.0.0.1:8000，
> 所以先起后端、再起前端即可，无需手动处理跨域。

---

## 三、常见问题（踩坑清单）

| 现象 | 原因 | 解决 |
|---|---|---|
| 后端起不来，报 `Unknown database` | MySQL 里还没建库 | 手动执行 `backend\sql\init.sql`（或启动后调用 /api/graph/init 等仍提示，先建库） |
| `ModuleNotFoundError: fastapi` | 装到了别的解释器 | 确认 pip install 用的是 backend 的 venv |
| 前端页面 401/网络错误 | 后端没启动 | 先启动后端 8000 |
| 知识库上传失败 | MinIO 容器没跑 | `docker start ai_minio` |
| 图谱页空白/报错 | Neo4j 容器没跑 | `docker start neo4j`，再点「导入预置图谱」 |
| OCR 失败 | SiliconFlow key 无效 | 检查 .env 中 `SILICONFLOW_API_KEY` |
| 前端 npm 报错 vite 版本 | Node 版本过旧 | 升级 Node 到 18+（推荐 20/22 LTS） |
| 端口被占用（8000/5173） | 上次进程没关 | `netstat -ano \| findstr :8000` 找到 PID → `taskkill /F /PID <pid>` |

---

## 四、演示路线（答辩/小组自测）

1. **测评页**：点「高风险患者」示例 → 「开始测评」
   → 看 4 维分项 + 风险等级 + AI 报告 + 图谱命中提示（若填了疾病）
2. **可视化总览**：自动加载历史数据 → 环形/趋势/雷达/柱状图
3. **知识库页**：拖入 `.txt/.pdf/.docx/.png` → 查看解析块数 → 语义检索提问
4. **图谱页**：下拉疾病（如 2型糖尿病）→ 查看关联营养素/食物/建议

---

## 五、目录速查

```
智能健康测评/
├── start.bat               # 一键启动（非 PyCharm 用）
├── README.md               # 全架构说明
├── 本文件 PyCharm启动说明.md
├── backend/
│   ├── .env                # ★ 改 MySQL 密码 / SiliconFlow Key
│   ├── requirements.txt    # ★ pip install -r
│   ├── sql/init.sql        # 建库建表 + 示例数据
│   └── app/main.py         # ★ uvicorn 入口
└── frontend/
    ├── package.json        # ★ npm run dev
    └── src/App.vue         # 页面导航
```
