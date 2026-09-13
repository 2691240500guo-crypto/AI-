"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.security import decode_token
from app.routers import assessment, knowledge, graph, assistant, meals, product, admin, privacy, companion
from app.utils.redis_cache import redis_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动：初始化数据库表 + Neo4j 预置图谱（幂等）"""
    logging.info("== 智能健康测评系统启动 ==")
    # 1. MySQL 建表
    try:
        init_db()
        logging.info("✓ MySQL 表结构就绪")
    except Exception as e:  # noqa: BLE001
        logging.error("✗ MySQL 初始化失败: %s", e)
    # 2. Neo4j 预置图谱（幂等，不重置）
    try:
        from app.utils.neo4j_client import get_neo4j
        get_neo4j().init_preset_graph(reset=False)
    except Exception as e:  # noqa: BLE001
        logging.warning("⚠ Neo4j 图谱初始化跳过（可稍后调用 /api/graph/init）: %s", e)
    yield
    logging.info("== 服务关闭 ==")


app = FastAPI(
    title="智能健康测评系统 - NRS2002 营养风险筛查",
    description=(
        "全闭环：多模态知识库构建 → 营养风险测评(NRS2002) → "
        "数据存储与查询 → 可视化展示（ECharts / Neo4j 图谱）"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS：允许本地前端调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------
# 统一 JWT 鉴权中间件
#   - 白名单：健康检查 / 登录 / 文档
#   - 其余 /api/* 必须携带有效 Bearer Token
#   - 管理端接口（admin、内容审核、图谱初始化、知识库上传/删除）要求 role=admin
# ---------------------------------------------------------------
PUBLIC_PATHS = {"/", "/api/health", "/api/auth/login"}
PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/favicon.ico")
ADMIN_PREFIXES = ("/api/admin", "/api/social/moderation")
ADMIN_EXACT = {"/api/graph/init"}


def _need_admin(path: str, method: str) -> bool:
    if path.startswith(ADMIN_PREFIXES) or path in ADMIN_EXACT:
        return True
    if path.startswith("/api/knowledge/upload"):
        return True
    if path.startswith("/api/knowledge/files") and method == "DELETE":
        return True
    return False


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method.upper()

    # 预检请求 / 非 API / 白名单直接放行
    if method == "OPTIONS" or not path.startswith("/api"):
        return await call_next(request)
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    payload = decode_token(token)
    if not payload:
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期，请重新登录"})

    request.state.user = {
        "id": payload.get("sub"),
        "role": payload.get("role"),
        "name": payload.get("name", ""),
    }

    if _need_admin(path, method) and request.state.user["role"] != "admin":
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限"})

    return await call_next(request)

# 路由注册
app.include_router(assessment.router)
app.include_router(knowledge.router)
app.include_router(graph.router)
app.include_router(assistant.router)
app.include_router(meals.router)
app.include_router(product.router)
app.include_router(admin.router)
app.include_router(privacy.router)
app.include_router(companion.router)


@app.get("/api/health", tags=["系统"])
def health_check():
    return {"status": "ok", "service": "智能健康测评系统",
            "version": "1.0.0", "redis": redis_status()}


@app.get("/", tags=["系统"])
def root():
    return {
        "name": "智能健康测评系统",
        "docs": "/docs",
        "health": "/api/health",
            "routers": ["/api/assessment", "/api/knowledge", "/api/graph", "/api/assistant", "/api/meals", "/api/auth", "/api/social", "/api/plans", "/api/voice", "/api/privacy", "/api/reports", "/api/pet"],
    }
