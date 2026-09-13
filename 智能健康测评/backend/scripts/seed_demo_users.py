"""创建多个演示登录账号（含健康画像 + NRS2002 测评样本），支持一键回滚。

为什么需要：
  1. 答辩演示需要「不同用户登录看到各自数据」——登录后 user_id = account，
     测评 / 饮食 / 问答 / 趋势数据天然按账号隔离。
  2. AI 问答页现在强制要求「过敏/疾病 + 基础疾病」必填，新账号必须带画像
     才能直接开始问答，否则一进页面就被拦。
  3. 每个账号预置 3 条测评记录，登录后健康趋势页的雷达图/柱状图立刻有数据。

密码使用与线上一致的 PBKDF2 哈希（app.core.security.hash_password）落库，
不会以明文形式存放在数据库里。

用法（在 backend 目录下）：
  python scripts/seed_demo_users.py --dry     # 只打印账号清单与评分预览
  python scripts/seed_demo_users.py           # 写入账号 + 画像 + 测评样本
  python scripts/seed_demo_users.py --clean   # 删除本次创建的账号及其数据
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.assessment import UserHealthRiskAssessment  # noqa: E402
from app.models.assistant import UserProfile  # noqa: E402
from app.models.auth import AppUser  # noqa: E402
from app.services.nrs2002_engine import evaluate_nrs2002  # noqa: E402

META_FILE = Path(__file__).resolve().parent / "_seed_demo_users.json"

# ---------------------------------------------------------------
# 演示账号（account 必须唯一；登录页为「用户端」，故 role 固定 user）
# 画像中的过敏/疾病、基础疾病为问答页必填项，这里已填好，登录即可直接提问。
# ---------------------------------------------------------------
USERS = [
    {
        "account": "zhangwei", "password": "zhang123", "name": "张伟", "role": "user",
        "profile": {"sex": "男", "age": 35, "height_cm": 178, "weight_kg": 82,
                    "goal": "减脂 8 斤", "allergies": "无", "conditions": "无",
                    "preferences": "少油少盐，爱吃牛肉"},
        "samples": [
            # (BMI, 体重下降%, 疾病严重度, 疾病描述, 进食量, 测评时间, 姓名)
            (26.4, None, "无", "", "正常", "2026-08-26 09:10:00", "张伟"),
            (25.6, 4.0, "无", "", "正常", "2026-09-02 09:20:00", "张伟"),
            (24.9, 2.0, "无", "", "正常", "2026-09-09 09:05:00", "张伟"),
        ],
    },
    {
        "account": "lina", "password": "lina123", "name": "李娜", "role": "user",
        "profile": {"sex": "女", "age": 29, "height_cm": 163, "weight_kg": 49,
                    "goal": "改善贫血、保持体型", "allergies": "芒果过敏",
                    "conditions": "缺铁性贫血（轻度）", "preferences": "清淡，每周吃 2 次红肉"},
        "samples": [
            (18.6, None, "无", "", "正常", "2026-08-27 15:30:00", "李娜"),
            (18.4, None, "无", "", "正常", "2026-09-03 15:40:00", "李娜"),
            (18.7, None, "无", "", "正常", "2026-09-10 16:10:00", "李娜"),
        ],
    },
    {
        "account": "wangqiang", "password": "wang123", "name": "王强", "role": "user",
        "profile": {"sex": "男", "age": 28, "height_cm": 182, "weight_kg": 68,
                    "goal": "增肌 5 公斤", "allergies": "无", "conditions": "无",
                    "preferences": "高蛋白，一日四餐"},
        "samples": [
            (20.5, None, "无", "", "正常", "2026-08-28 08:40:00", "王强"),
            (20.4, None, "无", "", "正常", "2026-09-04 08:30:00", "王强"),
            (20.6, None, "无", "", "正常", "2026-09-11 08:35:00", "王强"),
        ],
    },
    {
        "account": "chenjing", "password": "chen123", "name": "陈静", "role": "user",
        "profile": {"sex": "女", "age": 45, "height_cm": 160, "weight_kg": 64,
                    "goal": "控糖、减重", "allergies": "无",
                    "conditions": "2型糖尿病（口服药控制）", "preferences": "低 GI，杂粮饭"},
        "samples": [
            (25.0, None, "轻度", "2型糖尿病（稳定期）", "正常", "2026-08-29 10:15:00", "陈静"),
            (24.6, 3.0, "轻度", "2型糖尿病（稳定期）", "正常", "2026-09-05 10:20:00", "陈静"),
            (24.2, 2.0, "轻度", "2型糖尿病（稳定期）", "正常", "2026-09-11 10:05:00", "陈静"),
        ],
    },
    {
        "account": "liuyang", "password": "liu123", "name": "刘洋", "role": "user",
        "profile": {"sex": "男", "age": 52, "height_cm": 172, "weight_kg": 79,
                    "goal": "控制血压", "allergies": "海鲜过敏",
                    "conditions": "高血压（服药中）", "preferences": "严格低盐，不吃腌制食品"},
        "samples": [
            (26.7, None, "轻度", "高血压（稳定期）", "正常", "2026-08-30 09:50:00", "刘洋"),
            (26.2, None, "轻度", "高血压（稳定期）", "正常", "2026-09-06 09:45:00", "刘洋"),
            (25.8, 2.0, "轻度", "高血压（稳定期）", "正常", "2026-09-11 09:40:00", "刘洋"),
        ],
    },
    {
        "account": "sunmeng", "password": "sun123", "name": "孙梦", "role": "user",
        "profile": {"sex": "女", "age": 24, "height_cm": 166, "weight_kg": 55,
                    "goal": "减脂、改善睡眠", "allergies": "乳糖不耐受",
                    "conditions": "无", "preferences": "无糖饮品，植物奶替代"},
        "samples": [
            (20.4, None, "无", "", "正常", "2026-08-31 20:10:00", "孙梦"),
            (19.9, 3.0, "无", "", "正常", "2026-09-06 20:20:00", "孙梦"),
            (19.6, 2.0, "无", "", "正常", "2026-09-11 20:15:00", "孙梦"),
        ],
    },
]


def _build_samples(user):
    """按时间顺序编号，保证 assessment_count 与测评时间一致。"""
    rows = []
    for idx, (bmi, wl, lvl, cond, diet, ts, name) in enumerate(
        sorted(user["samples"], key=lambda x: x[5]), start=1
    ):
        nrs = evaluate_nrs2002(bmi=bmi, weight_loss_pct=wl, disease_level=lvl,
                               dietary_intake=diet, age=user["profile"]["age"])
        rows.append({
            "user_id": user["account"], "user_name": name,
            "sex": user["profile"]["sex"], "age": user["profile"]["age"],
            "bmi": bmi, "weight_loss_pct": wl, "disease_level": lvl,
            "disease_condition": cond, "dietary_intake": diet,
            "assessment_time": datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
            "assessment_count": idx, "nrs": nrs,
        })
    return rows


def _preview():
    print(f"{'账号':<12}{'密码':<12}{'姓名':<8}{'画像(过敏/疾病 | 基础疾病)':<34}{'测评':>4}  风险等级")
    print("-" * 96)
    for u in USERS:
        rows = _build_samples(u)
        levels = "/".join(r["nrs"].risk_level for r in rows)
        p = u["profile"]
        prof = f"{p['allergies']} | {p['conditions']}"
        print(f"{u['account']:<12}{u['password']:<12}{u['name']:<8}{prof:<34}{len(rows):>4}  {levels}")


def do_seed():
    db = SessionLocal()
    created_accounts, created_profile_ids, assessment_ids = [], [], []
    try:
        for u in USERS:
            # ---- 1. 登录账号 ----
            existed = db.query(AppUser).filter_by(account=u["account"]).first()
            if existed:
                existed.password = hash_password(u["password"])
                existed.name = u["name"]
                existed.role = u["role"]
                print(f"↻ 账号已存在，已重置密码：{u['account']}")
            else:
                db.add(AppUser(account=u["account"], password=hash_password(u["password"]),
                               name=u["name"], role=u["role"]))
                created_accounts.append(u["account"])
                print(f"＋ 新建账号：{u['account']} / {u['password']}  ({u['name']})")

            # ---- 2. 健康画像（问答页必填项已填好，登录即可提问）----
            prof = db.query(UserProfile).filter_by(user_id=u["account"]).first()
            if not prof:
                prof = UserProfile(user_id=u["account"])
                db.add(prof)
                created_profile_ids.append(u["account"])
            for k, v in u["profile"].items():
                setattr(prof, k, v)

            # ---- 3. 测评样本（健康趋势图直接有数据）----
            for r in _build_samples(u):
                n = r["nrs"]
                db.add(UserHealthRiskAssessment(
                    user_id=r["user_id"], user_name=r["user_name"], sex=r["sex"],
                    age=r["age"], assessment_time=r["assessment_time"],
                    assessment_count=r["assessment_count"], assessment_type="NRS2002",
                    total_score=n.total_score,
                    nutritional_impairment_score=n.nutritional_score,
                    disease_severity_score=n.disease_score,
                    age_score=n.age_score,
                    assessment_basis=n.basis, risk_level=n.risk_level,
                    recommendations=n.recommendations, llm_report=n.recommendations,
                    bmi=r["bmi"], weight_loss_pct=r["weight_loss_pct"],
                    weight_change=("近3个月下降" + str(r["weight_loss_pct"]) + "%")
                    if r["weight_loss_pct"] else "无明显变化",
                    disease_condition=r["disease_condition"],
                    dietary_intake=r["dietary_intake"],
                ))
                db.flush()
                assessment_ids.append(db.query(UserHealthRiskAssessment.id)
                                        .order_by(UserHealthRiskAssessment.id.desc())
                                        .first()[0])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    META_FILE.write_text(json.dumps({
        "seeded_at": datetime.now().isoformat(timespec="seconds"),
        "accounts": [u["account"] for u in USERS],
        "created_accounts": created_accounts,
        "created_profile_user_ids": created_profile_ids,
        "assessment_ids": assessment_ids,
        "passwords": {u["account"]: u["password"] for u in USERS},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"✅ 账号就绪 {len(USERS)} 个；本次新建 {len(created_accounts)} 个，"
          f"测评样本 {len(assessment_ids)} 条")
    print(f"   清单元数据：{META_FILE}")
    print("   回滚：python scripts/seed_demo_users.py --clean")


def do_clean():
    if not META_FILE.exists():
        print("⚠️ 未找到 _seed_demo_users.json，无本次注入记录可回滚")
        return
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    accounts = meta.get("accounts", [])
    ids = meta.get("assessment_ids", [])
    db = SessionLocal()
    try:
        n_ass = (db.query(UserHealthRiskAssessment)
                   .filter(UserHealthRiskAssessment.id.in_(ids))
                   .delete(synchronize_session=False)) if ids else 0
        n_prof = (db.query(UserProfile).filter(UserProfile.user_id.in_(accounts))
                    .delete(synchronize_session=False)) if accounts else 0
        n_user = (db.query(AppUser).filter(AppUser.account.in_(accounts))
                    .delete(synchronize_session=False)) if accounts else 0
        db.commit()
        print(f"🗑️ 已删除：账号 {n_user} 个、画像 {n_prof} 条、测评记录 {n_ass} 条")
        META_FILE.unlink()
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="删除本次创建的账号及其数据")
    ap.add_argument("--dry", action="store_true", help="只预览，不写库")
    args = ap.parse_args()

    if args.clean:
        do_clean()
        sys.exit(0)

    _preview()
    if args.dry:
        print("\n（--dry 模式：未写入数据库）")
    else:
        print()
        do_seed()
