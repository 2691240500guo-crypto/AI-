# 智能健康测评系统 - NRS2002 营养风险筛查

> 全闭环：**多模态知识库构建 → 营养风险测评 → 数据存储与查询 → 可视化展示**
> 技术：FastAPI + Vue3 + ECharts + MySQL + MinIO + Milvus + Neo4j + SiliconFlow

## 一、功能架构

```
┌─────────────────────────────────────────────────────────────┐
│ 前端 Vue3 (5173)                                            │
│  ├─ 营养风险测评页   （表单→NRS2002评分→AI报告→历史）        │
│  ├─ 可视化总览页     （风险分布/趋势/维度雷达，ECharts）      │
│  ├─ 多模态知识库页   （上传/OCR/向量检索/管理）               │
│  └─ 营养知识图谱页   （Neo4j 食物-营养素-疾病图可视化）       │
└──────────────────────────┬──────────────────────────────────┘
                           │  /api (Vite proxy)
┌──────────────────────────▼──────────────────────────────────┐
│ FastAPI 后端 (8000)                                         │
│  ├─ /api/assessment/*   规则评分 + LLM报告 + 历史 + 统计     │
│  ├─ /api/knowledge/*    上传→解析→向量化→检索 + 元数据       │
│  └─ /api/graph/*        Neo4j 图谱初始化/查询/可视化         │
└───┬──────────┬──────────┬──────────┬──────────┬─────────────┘
    │          │          │          │          │
 MySQL(3306) MinIO(9000) Milvus(19530) Neo4j(7687) SiliconFlow API
 测评记录/     知识原件     bge-m3      营养图谱     DeepSeek-V4-Flash
 文件元数据     存储        向量检索     (neo4j)     报告生成 + OCR
```

## 二、环境依赖（docker 容器）

| 服务 | 地址 | 凭据 | 用途 |
|---|---|---|---|
| MySQL 8 | 127.0.0.1:3306 | root / 123456（可在 .env 改） | 测评记录、知识库元数据 |
| MinIO | 127.0.0.1:9000 | minio / 12345678 | 知识文件对象存储 |
| Milvus | 127.0.0.1:19530 | - | 文本块向量检索 |
| Neo4j | bolt://127.0.0.1:7687 | neo4j / 12345678 | 营养知识图谱 |
| SiliconFlow | API | 你的 key | LLM 报告 + bge-m3 向量 + OCR |

> 你的本机 docker 已运行上述容器（ai_minio / milvus-standalone / neo4j）。
> Neo4j 中可能有其它项目数据（如人才图谱），本系统只用
> `Food/Nutrient/Disease` 三类标签，互不影响。

## 三、启动

### 后端（backend/，端口 8000）
```bash
cd backend
python -m venv venv                 # 首次
venv/Scripts/pip install -r requirements.txt
venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
# 首次建表/示例数据也可执行：
# venv/Scripts/python -c "import pymysql;..." 或直接用 sql/init.sql
```

### 前端（frontend/，端口 5173）
```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173

### 用户端 / 管理端

当前前端提供两个独立开发端口：

```bash
npm run dev:user   # 用户端：http://127.0.0.1:5173
npm run dev:admin  # 管理端：http://127.0.0.1:5174
```

演示账号：用户端 `user / user123`，管理端 `admin / admin123`。两端登录后看到的导航和工作台不同；后端统一通过 `/api/auth/login` 校验角色。

## 四、演示路线（答辩建议顺序）

1. **测评页** → 点「高风险患者」示例 → 开始测评（看 NRS2002 四维评分依据 + AI 报告 + 图谱命中提示）
2. **可视化总览页** → 看风险分布环形图/趋势/雷达
3. **知识库页** → 上传知识文档或图片 → 语义检索提问
4. **图谱页** → 点疾病（如 2型糖尿病）看关联营养素与食物

## 五、接口速查（Swagger: http://127.0.0.1:8000/docs）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/assessment | 执行 NRS2002 测评（含 LLM 报告） |
| GET | /api/assessment/history?user_id=xx | 历史记录 |
| GET | /api/assessment/stats | 统计（图表用） |
| POST | /api/knowledge/upload | 上传文件入库（multipart） |
| GET | /api/knowledge/files | 文件列表 |
| POST | /api/knowledge/search | 向量语义检索 |
| POST | /api/graph/init | 导入预置营养图谱 |
| GET | /api/graph/data | 图谱可视化数据 |
| GET | /api/graph/disease/{name} | 疾病关联查询 |
| GET | /api/graph/assess-hint?disease=xx | 测评关联图谱提示 |

## 六、NRS2002 评分规则（0-7 分，≥3 高风险）

| 维度 | 规则 | 分 |
|---|---|---|
| 营养受损 | BMI < 18.5 | 3 |
| | BMI 18.5~20.5 / 近3月体重降 >5% / 进食减 25-50% | 1 |
| | 近3月体重降 >10% / 进食减 50-75% | 2 |
| 疾病严重度 | 无 | 0 |
| | 轻度（稳定期慢性病） | 1 |
| | 中度（卧床/大手术/肺炎/肿瘤放化疗） | 2 |
| | 重度（ICU/重症） | 3 |
| 年龄 | ≥70 岁 | 1 |

风险分档：0 无风险 / 1 低风险 / 2 中风险 / ≥3 高风险（需营养支持）

## 八、HealthyBot P0 健康助手

当前版本在原有测评、知识库和图谱基础上增加了一个“健康助手”工作台，使用现有 SiliconFlow 配置，不依赖 Dify 或 Ollama：

- `GET/PUT /api/assistant/profile/{user_id}`：用户健康画像
- `POST /api/assistant/chat`：多轮健康对话，按营养/运动/睡眠/健康管理路由
- `POST /api/meals/analyze`：餐照视觉识别，失败时返回可编辑的待确认结果
- `POST /api/meals/confirm`：确认并保存饮食记录
- `GET /api/meals/daily`：每日热量、三大营养素和记录列表

所有助手回复都带有“仅供健康观察和生活方式参考，不能替代医生诊断”的提示。模型微调仍需单独的数据集、训练资源和验收方案。

## 九、产品扩展能力

- 语音：`/api/voice/transcribe`、`/api/voice/speak`，优先调用配置的 SiliconFlow ASR/TTS 模型；模型或接口明确不支持时才返回可确认的降级结果。
- 社区：`/api/social/feed`、`/api/social/posts`、点赞、评论和关注接口。
- 饮食计划：`/api/plans/generate` 返回菜单与购物清单。
- 舌体观察：`POST /api/tongue/analyze` 使用 `TONGUE_YOLO_MODEL` 权重定位舌体，并返回检测框、置信度和非诊断性颜色/苔质观察。训练可运行 `python scripts/train_tongue_yolo.py --data data/tongue.yaml`。
- 隐私与数据：`/api/privacy/status`、`/api/privacy/consent`、`/api/privacy/memories`、`/api/privacy/export`、`DELETE /api/privacy/data` 提供同意管理、AES-256-GCM 文本保护、长期记忆管理、数据导出和删除。生产环境必须设置独立的 `HEALTH_DATA_ENCRYPTION_KEY`，并使用密钥管理服务保存。

健康文字保护对新写入的画像、对话、测评说明、饮食备注和计划说明透明生效；升级已有实例时应先备份数据库，再在配置独立密钥后执行一次旧记录迁移。密钥配置变更需要重启后端进程才会生效。

旧记录迁移命令：`venv/Scripts/python.exe scripts/migrate_health_text.py`。脚本要求已设置独立密钥，只重写可加密文字字段，不删除记录。
- 视觉工作台：登录页使用健康场景背景图，登录后提供侧栏导航、统计卡片、社区动态和食谱图片。

## 七、目录结构
```
智能健康测评/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── core/                # config / database
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic
│   │   ├── routers/             # assessment/knowledge/graph
│   │   ├── services/            # nrs2002引擎/LLM/文档解析/测评/知识库
│   │   └── utils/               # minio/milvus/neo4j 客户端
│   ├── sql/init.sql             # 建库建表+示例数据+视图
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── api.js               # 接口封装
    │   ├── App.vue              # 顶部导航
    │   └── views/               # 4 个功能页
    └── package.json
```
