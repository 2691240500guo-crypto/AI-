"""为演示/答辩注入 NRS2002 测评样本数据（可一键回滚）。

为什么需要：健康趋势页的「分维度平均得分」「各风险等级得分均值」只统计
当前登录账号（默认 user）的 history；该账号此前只有 2 条 BMI 22+ 的 0 分记录，
导致雷达图/柱状图全为 0。这里补一批覆盖「BMI 三档 + 四类风险等级 + 近 14 天」
的样本，让四个图表都有可读数据，同时用来演示 BMI 如何驱动营养受损评分。

用法（在 backend 目录下）：
  python scripts/seed_demo_assessment.py --dry     # 只打印评分预览，不写库
  python scripts/seed_demo_assessment.py           # 备份 + 写入演示数据
  python scripts/seed_demo_assessment.py --clean   # 删除本次写入的演示数据

评分全部由 app.services.nrs2002_engine.evaluate_nrs2002 实时计算，
与线上测评接口同一条规则链，保证展示数据与业务逻辑一致。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal  # noqa: E402
from app.models.assessment import UserHealthRiskAssessment  # noqa: E402
from app.services.nrs2002_engine import evaluate_nrs2002  # noqa: E402

ID_FILE = Path(__file__).resolve().parent / "_seed_demo_ids.json"

# (user_id, 姓名, 性别, 年龄, BMI, 体重下降%, disease_level, disease_condition,
#  dietary_intake, 测评时间)
SAMPLES = [
    # —— 当前登录账号 user：覆盖四档风险 + BMI 三档 ——
    ("user", "孙浩", "男", 41, 22.8, None, "无", "", "正常", "2026-08-29 09:20:00"),
    ("user", "马强", "男", 35, 24.1, None, "无", "", "正常", "2026-08-30 14:05:00"),
    ("user", "李静", "女", 29, 21.3, None, "无", "", "正常", "2026-08-31 10:40:00"),
    ("user", "郭涛", "男", 47, 25.6, None, "无", "", "正常", "2026-09-01 08:55:00"),
    ("user", "赵敏", "女", 28, 20.2, None, "无", "", "正常", "2026-09-01 16:30:00"),
    ("user", "周伟", "男", 55, 23.6, None, "轻度", "高血压（稳定期）", "正常", "2026-09-02 11:15:00"),
    ("user", "王磊", "男", 38, 22.0, 6.0, "无", "", "正常", "2026-09-03 09:05:00"),
    ("user", "郑丽华", "女", 63, 19.9, None, "轻度", "2型糖尿病（稳定期）", "正常", "2026-09-03 15:50:00"),
    ("user", "陈志远", "男", 58, 18.9, None, "轻度", "慢性胃炎", "正常", "2026-09-04 10:25:00"),
    ("user", "林晓晴", "女", 32, 19.4, 12.0, "无", "", "正常", "2026-09-06 13:40:00"),
    ("user", "王秀兰", "女", 68, 16.8, None, "中度", "肺部感染住院", "减少50%", "2026-09-07 09:30:00"),
    ("user", "陈建国", "男", 72, 17.6, 12.0, "中度", "结肠肿瘤术后", "正常", "2026-09-08 11:50:00"),
    ("user", "吴淑芬", "女", 74, 18.2, None, "轻度", "骨质疏松", "正常", "2026-09-09 08:20:00"),
    ("user", "黄玉梅", "女", 70, 19.6, None, "中度", "髋部骨折卧床", "正常", "2026-09-10 15:05:00"),
    ("user", "韩雪", "女", 26, 20.4, None, "无", "", "正常", "2026-09-11 09:15:00"),

    # —— 其它演示账号：让「风险等级分布」「近 14 天趋势」更像真实运营数据 ——
    ("DEMO001", "杨帆", "男", 33, 23.2, None, "无", "", "正常", "2026-09-05 10:10:00"),
    ("DEMO002", "何军", "男", 45, 20.8, None, "轻度", "脂肪肝（轻度）", "正常", "2026-09-05 17:25:00"),
    ("DEMO003", "刘敏", "女", 52, 18.6, None, "轻度", "甲状腺功能减退", "正常", "2026-09-07 14:35:00"),
    ("DEMO004", "罗静", "女", 58, 19.1, None, "中度", "胃部手术恢复期", "正常", "2026-09-08 09:45:00"),
    ("DEMO005", "徐丽", "女", 66, 17.9, None, "中度", "肺部感染", "减少25%", "2026-09-10 11:20:00"),
    ("DEMO006", "高鹏", "男", 39, 24.9, None, "无", "", "正常", "2026-09-11 08:40:00"),
]


def _build_rows():
    """按测评时间先后编号，确保 assessment_count 与时间顺序一致。"""
    rows = []
    seq = {}
    for (uid, name, sex, age, bmi, wl, lvl, cond, diet, ts) in sorted(
        SAMPLES, key=lambda x: x[-1]
    ):
        seq[uid] = seq.get(uid, 0) + 1
        nrs = evaluate_nrs2002(
            bmi=bmi, weight_loss_pct=wl, disease_level=lvl,
            dietary_intake=diet, age=age,
        )
        rows.append({
            "user_id": uid, "user_name": name, "sex": sex, "age": age,
            "bmi": bmi, "weight_loss_pct": wl, "disease_level": lvl,
            "disease_condition": cond, "dietary_intake": diet,
            "assessment_time": datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
            "assessment_count": seq[uid], "nrs": nrs,
        })
    return rows


def _preview(rows):
    print(f"{'姓名':<8}{'BMI':>6}{'营养':>5}{'疾病':>5}{'年龄':>5}{'总分':>5}  等级")
    print("-" * 52)
    for r in rows:
        n = r["nrs"]
        print(f"{r['user_name']:<8}{r['bmi']:>6.1f}{n.nutritional_score:>5}"
              f"{n.disease_score:>5}{n.age_score:>5}{n.total_score:>5}  {n.risk_level}")
    from collections import Counter
    print("-" * 52)
    print("风险等级分布：", dict(Counter(r["nrs"].risk_level for r in rows)))
    print("涉及账号：", sorted({r["user_id"] for r in rows}))


def do_seed(rows):
    db = SessionLocal()
    try:
        # 1) 表级备份（幂等：已存在则不覆盖）
        from sqlalchemy import text
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS bak_assessment_20260911 "
            "AS SELECT * FROM user_health_risk_assessment"
        ))
        before_max = db.execute(
            text("SELECT COALESCE(MAX(id),0) FROM user_health_risk_assessment")
        ).scalar()
        db.commit()

        inserted = []
        for r in rows:
            n = r["nrs"]
            rec = UserHealthRiskAssessment(
                user_id=r["user_id"], user_name=r["user_name"], sex=r["sex"],
                age=r["age"], assessment_time=r["assessment_time"],
                assessment_count=r["assessment_count"], assessment_type="NRS2002",
                total_score=n.total_score,
                nutritional_impairment_score=n.nutritional_score,
                disease_severity_score=n.disease_score,
                age_score=n.age_score,
                assessment_basis=n.basis,
                risk_level=n.risk_level,
                recommendations=n.recommendations,
                llm_report=n.recommendations,
                bmi=r["bmi"], weight_loss_pct=r["weight_loss_pct"],
                weight_change=("近3个月下降" + str(r["weight_loss_pct"]) + "%")
                if r["weight_loss_pct"] else "无明显变化",
                disease_condition=r["disease_condition"],
                dietary_intake=r["dietary_intake"],
            )
            db.add(rec)
            db.flush()
            inserted.append(rec.id)
        db.commit()

        ID_FILE.write_text(json.dumps({
            "seeded_at": datetime.now().isoformat(timespec="seconds"),
            "before_max_id": int(before_max),
            "inserted_ids": inserted,
            "count": len(inserted),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"✅ 已写入 {len(inserted)} 条演示测评记录，id 区间 {min(inserted)}~{max(inserted)}")
        print(f"   回滚记录已保存：{ID_FILE}")
        print(f"   表级备份：bak_assessment_20260911")
    finally:
        db.close()


def do_clean():
    if not ID_FILE.exists():
        print("⚠️ 未找到 _seed_demo_ids.json，无本次注入记录可回滚")
        return
    meta = json.loads(ID_FILE.read_text(encoding="utf-8"))
    ids = meta.get("inserted_ids", [])
    if not ids:
        print("⚠️ 记录为空，无需清理")
        return
    db = SessionLocal()
    try:
        n = (db.query(UserHealthRiskAssessment)
               .filter(UserHealthRiskAssessment.id.in_(ids))
               .delete(synchronize_session=False))
        db.commit()
        print(f"🗑️ 已删除 {n} 条演示记录（id: {min(ids)}~{max(ids)}）")
        ID_FILE.unlink()
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="删除本次注入的数据")
    ap.add_argument("--dry", action="store_true", help="只预览评分，不写库")
    args = ap.parse_args()

    if args.clean:
        do_clean()
        sys.exit(0)

    built = _build_rows()
    _preview(built)
    if args.dry:
        print("\n（--dry 模式：未写入数据库）")
    else:
        print()
        do_seed(built)
