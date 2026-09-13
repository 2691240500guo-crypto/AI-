"""JWT 鉴权与密码哈希。

设计要点：
  - 登录签发 HS256 JWT（sub=账号, role=user|admin, exp 过期时间）
  - 统一鉴权中间件在 main.py 中校验所有 /api 请求（白名单除外）
  - 路由通过 resolve_user_id() 以 token 身份为准，避免前端伪造 user_id
  - 密码支持 pbkdf2 哈希；历史明文密码仍可校验（向后兼容）
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger("security")

ALGO = settings.JWT_ALGORITHM
PBKDF2_ROUNDS = 120_000

DEMO_ACCOUNTS = {
    "user": {"password": "user123", "name": "林晓晴", "role": "user"},
    "admin": {"password": "admin123", "name": "运营管理员", "role": "admin"},
}


def effective_login_account_count(db) -> int:
    """Count unique database accounts plus the built-in demo accounts."""
    try:
        from app.models.auth import AppUser
        accounts = {row.account for row in db.query(AppUser.account).all() if row.account}
    except Exception as exc:  # noqa: BLE001
        logger.info("account count fallback to demo accounts: %s", exc)
        accounts = set()
    return len(accounts | set(DEMO_ACCOUNTS))


# ---------------- 密码 ----------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, salt, digest = stored.split("$", 2)
        except ValueError:
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS).hex()
        return hmac.compare_digest(calc, digest)
    # 兼容历史明文密码（生产建议迁移为 pbkdf2）
    return hmac.compare_digest(password, stored)


# ---------------- Token ----------------
def create_access_token(user_id: str, role: str, name: str = "") -> tuple[str, int]:
    """返回 (token, 有效期秒数)。"""
    minutes = settings.JWT_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "name": name,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)
    return token, minutes * 60


def decode_token(token: str) -> dict | None:
    """解析并校验 token；无效或过期返回 None。"""
    if not token:
        return None
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        logger.info("token 已过期")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("token 校验失败: %s", exc)
        return None


# ---------------- 路由依赖 / 工具 ----------------
def get_current_user(request: Request) -> dict:
    """依赖：必须已登录（中间件已注入 request.state.user）。"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_admin(request: Request) -> dict:
    """依赖：必须是管理员。"""
    user = get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def resolve_user_id(request: Request, claimed: str | None = None, fallback: str = "ANON001") -> str:
    """业务归属用户：以 token 身份为准，未登录时才退回请求里声明的 user_id。"""
    user = getattr(request.state, "user", None)
    if user and user.get("id"):
        return str(user["id"])
    return claimed or fallback


def resolve_scoped_user_id(
    request: Request,
    claimed: str | None = None,
    *,
    allow_admin_claim: bool = False,
) -> str:
    """Return the authenticated user's ID unless an administrator is reviewing a named user.

    This is for records that are both user-owned and visible to administrators. It prevents
    a normal user from swapping a query/body ``user_id`` to read or create another user's data.
    """
    user = get_current_user(request)
    if allow_admin_claim and user.get("role") == "admin" and claimed:
        return str(claimed)
    return str(user["id"])
