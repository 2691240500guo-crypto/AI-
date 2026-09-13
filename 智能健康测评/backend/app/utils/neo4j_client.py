"""Neo4j 图数据库封装：营养知识图谱 导入 / 查询 / 可视化数据输出"""
import logging
import time
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase

from app.core.config import settings

logger = logging.getLogger("neo4j_client")

# ============================================================
# 预置营养知识图谱（Neo4j 初始化导入）
# 节点：营养素 / 食物 / 疾病
# 关系：(食物)-[:含有]->(营养素)
#        (营养素)-[:降低风险|缓解|加重]->(疾病)
#        (食物)-[:适宜|禁忌]->(疾病)      ← 直接关系，表达"某病宜/忌吃某物"
# ============================================================

PRESET_NUTRIENTS = [
    # (营养素, 作用疾病, 关系, 说明)
    ("蛋白质", "肌少症", "降低风险", "优质蛋白有助维持肌肉量"),
    ("蛋白质", "术后营养不良", "降低风险", "蛋白质是组织修复必需原料"),
    ("膳食纤维", "便秘", "缓解", "促进肠道蠕动"),
    ("膳食纤维", "2型糖尿病", "降低风险", "延缓餐后血糖上升"),
    ("钙", "骨质疏松", "降低风险", "骨钙沉积关键原料"),
    ("维生素D", "骨质疏松", "降低风险", "促进钙吸收"),
    ("铁", "缺铁性贫血", "缓解", "血红蛋白合成原料"),
    ("叶酸", "巨幼细胞性贫血", "缓解", "红细胞成熟必需"),
    ("维生素C", "坏血病", "缓解", "胶原合成辅因子"),
    ("omega-3脂肪酸", "高血脂", "降低风险", "调节血脂"),
    ("钾", "高血压", "降低风险", "对抗钠升压作用"),
    ("不饱和脂肪酸", "冠心病", "降低风险", "改善血脂谱"),
    ("维生素B12", "周围神经病变", "缓解", "神经髓鞘维护"),
    ("锌", "味觉减退", "缓解", "味蕾更新必需"),
    ("碳水化合物", "低血糖", "缓解", "快速供能"),
    # —— 「加重」方向：风险营养素 → 疾病（禁忌关系的营养学依据）——
    ("钠", "高血压", "加重", "钠潴留升高血压"),
    ("嘌呤", "痛风", "加重", "嘌呤代谢产生尿酸"),
    ("脂肪", "高血脂", "加重", "总脂肪摄入过多"),
    ("饱和脂肪", "冠心病", "加重", "升高低密度脂蛋白"),
    ("胆固醇", "高血脂", "加重", "升高血清胆固醇"),
    ("游离糖", "2型糖尿病", "加重", "快速升高血糖"),
    # —— 补充正向关系 ——
    ("膳食纤维", "高血脂", "降低风险", "结合胆汁酸促进胆固醇排出"),
]

PRESET_FOODS = [
    # (食物, 营养素, 说明)
    ("鸡蛋", "蛋白质", "全蛋氨基酸评分高"),
    ("牛奶", "蛋白质", "乳清蛋白易吸收"),
    ("鱼虾", "蛋白质", "低脂高蛋白"),
    ("鸡胸肉", "蛋白质", "高蛋白低脂肪"),
    ("黄豆", "蛋白质", "植物蛋白优质来源"),
    ("燕麦", "膳食纤维", "β-葡聚糖"),
    ("芹菜", "膳食纤维", "粗纤维丰富"),
    ("糙米", "膳食纤维", "全谷物"),
    ("苹果", "膳食纤维", "果胶"),
    ("豆腐", "钙", "传统补钙食物"),
    ("芝麻", "钙", "钙含量高"),
    ("酸奶", "钙", "乳钙+益生菌"),
    ("三文鱼", "维生素D", "富脂鱼类"),
    ("蛋黄", "维生素D", "天然维D来源"),
    ("猪肝", "铁", "血红素铁"),
    ("红肉", "铁", "易吸收血红素铁"),
    ("菠菜", "叶酸", "深绿叶菜"),
    ("西兰花", "叶酸", "十字花科蔬菜"),
    ("柑橘", "维生素C", "维C含量高"),
    ("猕猴桃", "维生素C", "维C含量高于柑橘"),
    ("深海鱼", "omega-3脂肪酸", "EPA/DHA 来源"),
    ("亚麻籽", "omega-3脂肪酸", "植物来源ALA"),
    ("香蕉", "钾", "高钾水果"),
    ("土豆", "钾", "高钾主食"),
    ("橄榄油", "不饱和脂肪酸", "单不饱和脂肪酸"),
    ("坚果", "不饱和脂肪酸", "多不饱和脂肪酸"),
    ("牡蛎", "锌", "含锌量高"),
    ("瘦肉", "锌", "动物性锌"),
    ("米饭", "碳水化合物", "精制碳水快速供能"),
    ("馒头", "碳水化合物", "精制碳水"),
    # —— 风险食物（与疾病构成「禁忌」直接关系的营养学依据）——
    ("腌制食品", "钠", "高钠腌制品"),
    ("咸菜", "钠", "高钠"),
    ("腊肉", "钠", "高钠高脂"),
    ("香肠", "钠", "高钠加工肉"),
    ("火腿", "钠", "高钠加工肉"),
    ("培根", "钠", "高钠加工肉"),
    ("浓汤", "嘌呤", "嘌呤易溶于汤"),
    ("啤酒", "嘌呤", "抑制尿酸排泄"),
    ("动物内脏", "嘌呤", "高嘌呤"),
    ("动物内脏", "胆固醇", "胆固醇含量高"),
    ("油炸食品", "脂肪", "油脂含量高"),
    ("肥肉", "饱和脂肪", "饱和脂肪高"),
    ("含糖饮料", "游离糖", "游离糖含量高"),
    ("蜂蜜", "游离糖", "游离糖占比高"),
    ("白米粥", "碳水化合物", "糊化淀粉升糖快"),
]

PRESET_DISEASES = [
    "肌少症", "术后营养不良", "便秘", "2型糖尿病", "骨质疏松",
    "缺铁性贫血", "巨幼细胞性贫血", "坏血病", "高血脂", "高血压",
    "冠心病", "周围神经病变", "味觉减退", "低血糖", "痛风",
]

# ------------------------------------------------------------
# 食物 ↔ 疾病 直接关系（禁忌 / 适宜）
#
# 为什么需要这一层：
#   仅靠「食物-含有->营养素-降低风险->疾病」两跳链路，只能表达"推荐"，
#   无法表达"高血压忌腌制食品"这类**直接禁忌**（腌制食品不含某个营养素
#   就能反推出禁忌），也无法把禁忌规则交给知识库维护。
#   有了直接关系，禁忌规则从代码常量迁移到图谱，新增一条边即刻生效。
# ------------------------------------------------------------
PRESET_FOOD_DISEASE_RELATIONS = [
    # ---------- 禁忌（应避免/限制） ----------
    ("腌制食品", "禁忌", "高血压", "高钠，直接升高血压"),
    ("咸菜", "禁忌", "高血压", "高钠腌制品"),
    ("腊肉", "禁忌", "高血压", "高钠高脂"),
    ("香肠", "禁忌", "高血压", "高钠加工肉"),
    ("火腿", "禁忌", "高血压", "高钠加工肉"),
    ("培根", "禁忌", "高血压", "高钠加工肉"),
    ("动物内脏", "禁忌", "高血脂", "胆固醇含量高"),
    ("油炸食品", "禁忌", "高血脂", "饱和/反式脂肪高"),
    ("肥肉", "禁忌", "高血脂", "饱和脂肪高"),
    ("含糖饮料", "禁忌", "2型糖尿病", "游离糖升糖快"),
    ("蜂蜜", "禁忌", "2型糖尿病", "游离糖占比高"),
    ("白米粥", "禁忌", "2型糖尿病", "糊化淀粉 GI 高，升糖快"),
    ("浓汤", "禁忌", "痛风", "嘌呤易溶于汤"),
    ("啤酒", "禁忌", "痛风", "抑制尿酸排泄"),
    ("动物内脏", "禁忌", "痛风", "高嘌呤"),
    # ---------- 适宜（推荐/宜吃） ----------
    ("香蕉", "适宜", "高血压", "富钾，对抗钠升压"),
    ("土豆", "适宜", "高血压", "富钾主食"),
    ("菠菜", "适宜", "高血压", "富钾镁"),
    ("燕麦", "适宜", "2型糖尿病", "β-葡聚糖延缓升糖"),
    ("糙米", "适宜", "2型糖尿病", "低 GI 全谷物"),
    ("芹菜", "适宜", "2型糖尿病", "高纤维低 GI"),
    ("豆腐", "适宜", "骨质疏松", "植物钙来源"),
    ("牛奶", "适宜", "骨质疏松", "乳钙吸收率高"),
    ("芝麻", "适宜", "骨质疏松", "钙含量高"),
    ("酸奶", "适宜", "骨质疏松", "乳钙 + 益生菌"),
    ("猪肝", "适宜", "缺铁性贫血", "血红素铁"),
    ("红肉", "适宜", "缺铁性贫血", "血红素铁易吸收"),
    ("柑橘", "适宜", "缺铁性贫血", "维C 促进铁吸收"),
    ("深海鱼", "适宜", "冠心病", "omega-3 改善血脂谱"),
    ("橄榄油", "适宜", "冠心病", "地中海饮食核心"),
    ("坚果", "适宜", "冠心病", "不饱和脂肪酸"),
    ("燕麦", "适宜", "便秘", "膳食纤维促蠕动"),
    ("芹菜", "适宜", "便秘", "粗纤维"),
    ("苹果", "适宜", "便秘", "果胶"),
    ("鸡蛋", "适宜", "肌少症", "全价优质蛋白"),
    ("鸡胸肉", "适宜", "肌少症", "高蛋白低脂"),
    ("牛奶", "适宜", "肌少症", "乳清蛋白易吸收"),
    ("米饭", "适宜", "低血糖", "快速供能"),
    ("牡蛎", "适宜", "味觉减退", "含锌量高"),
    ("瘦肉", "适宜", "味觉减退", "动物性锌"),
    ("西兰花", "适宜", "巨幼细胞性贫血", "叶酸丰富"),
    ("菠菜", "适宜", "巨幼细胞性贫血", "叶酸丰富"),
    ("深海鱼", "适宜", "周围神经病变", "维生素B12 来源"),
    ("猕猴桃", "适宜", "坏血病", "维C 含量高"),
    ("柑橘", "适宜", "坏血病", "维C 来源"),
    ("鸡蛋", "适宜", "术后营养不良", "优质蛋白利于组织修复"),
    ("鱼虾", "适宜", "术后营养不良", "低脂高蛋白"),
    ("黄豆", "适宜", "术后营养不良", "植物蛋白优质来源"),
]

# 食物别名（图谱标准名 ← 常见写法），用于在菜单文本里识别食物
# 注意：别名不要与其它 Food 节点的标准名冲突（例：不要把「猪肝」放进动物内脏，
# 因为「猪肝」本身是补铁推荐食物节点），否则同一次匹配会同时命中矛盾关系。
FOOD_ALIASES = {
    "腌制食品": ["腌菜", "泡菜", "酱菜", "咸蛋", "腐乳"],
    "咸菜": ["榨菜", "梅干菜"],
    "腊肉": ["腊肠", "熏肉"],
    "香肠": ["火腿肠", "热狗肠"],
    "动物内脏": ["猪腰", "腰花", "鸡胗", "鸭肝", "鹅肝"],
    "油炸食品": ["炸鸡", "薯条", "油条", "油炸"],
    "含糖饮料": ["可乐", "奶茶", "果汁饮料", "甜饮料"],
    "白米粥": ["白粥", "稀饭"],
    "浓汤": ["老火汤", "肉汤", "火锅汤"],
    "深海鱼": ["三文鱼", "金枪鱼", "鲭鱼"],
    "鱼虾": ["鲈鱼", "鳕鱼", "虾仁", "基围虾", "带鱼"],
    "红肉": ["牛肉", "羊肉", "瘦猪肉"],
    "坚果": ["核桃", "杏仁", "腰果", "花生"],
    "土豆": ["马铃薯"],
}

# 疾病别名：测评/画像里常见「高血压（稳定期）」「2型糖尿病稳定期」等带限定词的写法，
# 模糊匹配借助别名把口语化描述对齐到图谱标准疾病名。
PRESET_DISEASE_ALIASES = {
    "2型糖尿病": ["糖尿病", "2型糖尿病稳定期", "2型糖尿病（稳定期）", "T2DM", "血糖高"],
    "高血压": ["原发性高血压", "高血压稳定期", "高血压（稳定期）", "血压高"],
    "骨质疏松": ["骨质疏松症", "骨密度低"],
    "缺铁性贫血": ["贫血", "贫血（轻度）"],
    "巨幼细胞性贫血": ["大细胞性贫血"],
    "高血脂": ["血脂高", "高脂血症", "脂肪肝"],
    "冠心病": ["冠状动脉粥样硬化", "心绞痛"],
    "便秘": ["排便困难"],
    "低血糖": ["血糖低"],
    "肌少症": ["肌肉减少", "肌肉量不足"],
    "术后营养不良": ["术后", "术后恢复期", "营养不良", "化疗期"],
    "痛风": ["高尿酸", "高尿酸血症", "痛风性关节炎"],
}

# 疾病 -> 营养干预建议（用于测评命中图谱时展示）
DISEASE_ADVICE = {
    "肌少症": "增加优质蛋白（1.2-1.5g/kg/d）并配合抗阻运动",
    "术后营养不良": "高蛋白高能量，少食多餐，必要时营养制剂",
    "便秘": "增加膳食纤维25-35g/d，保证饮水1.5-2L",
    "2型糖尿病": "控制总碳水，低GI食物，粗细搭配",
    "骨质疏松": "补钙1000-1200mg/d + 维生素D 800IU/d",
    "缺铁性贫血": "补铁 + 维生素C促进吸收，红肉每周2-3次",
    "巨幼细胞性贫血": "补叶酸和维生素B12，多吃深绿蔬菜",
    "坏血病": "补充维生素C 100mg/d以上，多吃新鲜果蔬",
    "高血脂": "减少饱和脂肪，增加omega-3摄入",
    "高血压": "限盐（<5g/d），增加钾摄入，DASH饮食",
    "冠心病": "地中海饮食模式，减少反式脂肪",
    "周围神经病变": "补充维生素B12，控制血糖",
    "味觉减退": "补锌，保证食物多样化",
    "低血糖": "规律进餐，随身携带碳水零食",
    "痛风": "限制高嘌呤食物（内脏/浓汤/啤酒），多饮水，控制体重",
}


class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        self._verify()

    def _verify(self):
        try:
            self.driver.verify_connectivity()
            logger.info("Neo4j 连接成功: %s", settings.NEO4J_URI)
        except Exception as e:  # noqa: BLE001
            logger.error("Neo4j 连接失败: %s", e)
            raise

    def close(self):
        self.driver.close()

    # ---------------- 初始化导入 ----------------
    def _upsert_preset_entities(self, session) -> Dict[str, int]:
        """把预置三元组 MERGE 进图谱（幂等，可反复执行做增量补齐）。

        用 MERGE 而非 CREATE，所以：
          - 首次导入 = 建图
          - 后续补数据（新增疾病/食物/关系）= 只补差异，不动已有节点
        这也是「图谱驱动」能落地的前提——加一条禁忌关系不需要重建整张图。
        """
        counts = {"disease": 0, "nutrient": 0, "food": 0, "relation": 0}

        # 1) 疾病节点（带别名，供模糊匹配对齐口语化描述）
        for d in PRESET_DISEASES:
            session.run(
                "MERGE (d:Disease {name: $name}) "
                "SET d.aliases = $aliases",
                name=d, aliases=PRESET_DISEASE_ALIASES.get(d, []),
            )
            counts["disease"] += 1

        # 2) 营养素节点 + (营养素)-[降低风险|缓解|加重]->(疾病)
        for nut, disease, rel, note in PRESET_NUTRIENTS:
            session.run(
                "MERGE (n:Nutrient {name: $name}) "
                "MERGE (d:Disease {name: $dname}) "
                "MERGE (n)-[r:%s]->(d) "
                "SET r.note = $note" % rel,
                name=nut, dname=disease, note=note,
            )
            counts["nutrient"] += 1
            counts["relation"] += 1

        # 3) 食物节点（带别名）+ (食物)-[:含有]->(营养素)
        for food, nut, note in PRESET_FOODS:
            session.run(
                "MERGE (f:Food {name: $name}) "
                "SET f.aliases = $aliases "
                "MERGE (n:Nutrient {name: $nname}) "
                "MERGE (f)-[r:含有]->(n) "
                "SET r.note = $note",
                name=food, nname=nut, note=note,
                aliases=FOOD_ALIASES.get(food, []),
            )
            counts["food"] += 1
            counts["relation"] += 1

        # 4) (食物)-[适宜|禁忌]->(疾病) 直接关系（禁忌规则的唯一事实来源）
        for food, rel, disease, note in PRESET_FOOD_DISEASE_RELATIONS:
            session.run(
                "MERGE (f:Food {name: $fname}) "
                "SET f.aliases = $aliases "
                "MERGE (d:Disease {name: $dname}) "
                "MERGE (f)-[r:%s]->(d) "
                "SET r.note = $note" % rel,
                fname=food, dname=disease, note=note,
                aliases=FOOD_ALIASES.get(food, []),
            )
            counts["relation"] += 1
        return counts

    def init_preset_graph(self, reset: bool = False):
        """导入预置营养知识图谱（幂等：已有节点时只做增量补齐）。

        注意：Neo4j 容器可能并存其它项目数据（如人才库图谱），
        本方法只用独立标签 Food/Nutrient/Disease，不会影响其它数据。
        """
        with self.driver.session() as s:
            cnt = s.run(
                "MATCH (n) WHERE n:Disease OR n:Nutrient OR n:Food "
                "RETURN count(n) AS c"
            ).single()["c"]
            if reset:
                s.run("MATCH (n) WHERE n:Disease OR n:Nutrient OR n:Food "
                      "DETACH DELETE n")
                cnt = 0
            already = cnt > 0
            counts = self._upsert_preset_entities(s)
            stats = s.run(
                "MATCH (n) WHERE n:Disease OR n:Nutrient OR n:Food "
                "RETURN labels(n)[0] AS label, count(*) AS c"
            ).data()
        mode = "增量补齐" if already else "全量导入"
        logger.info("营养知识图谱%s完成: %s", mode, stats)
        return {"skipped": already, "mode": mode, "written": counts, "nodes": stats}

    def rebuild_relations_from_graph(self) -> Dict[str, int]:
        """对外入口：把预置三元组（含新增的 禁忌/适宜）补齐进图。

        供运维/答辩演示使用：图谱新增一批知识后调一次即可生效，
        无需动任何业务代码。
        """
        with self.driver.session() as s:
            return self._upsert_preset_entities(s)

    # ---------------- 查询 ----------------
    def _match_diseases(self, keyword: str, limit: int = 3) -> List[str]:
        """把自由文本疾病描述对齐到图谱标准疾病名。

        测评/画像里的写法五花八门（「高血压（稳定期）」「2型糖尿病稳定期」），
        精确等值匹配基本查不中（实测命中率 5%），这里用双向 CONTAINS + 别名
        做包含式匹配，按名字长度倒序取最具体的命中。

        结果带 60 秒缓存——排菜时每套菜单都要按画像疾病过滤，
        同一串画像文本会被重复对齐几十次。
        """
        global _MATCH_CACHE
        kw = (keyword or "").strip()
        if not kw:
            return []
        cache_key = (kw, limit)
        hit = _MATCH_CACHE.get(cache_key)
        if hit and (time.time() - hit[0]) < 60:
            return hit[1]
        with self.driver.session() as s:
            rows = s.run(
                """
                MATCH (d:Disease)
                WHERE $kw CONTAINS d.name
                   OR d.name CONTAINS $kw
                   OR any(a IN coalesce(d.aliases, [])
                          WHERE $kw CONTAINS a OR a CONTAINS $kw)
                RETURN d.name AS name
                ORDER BY size(d.name) DESC
                LIMIT $limit
                """,
                kw=kw, limit=limit,
            ).data()
        names = [r["name"] for r in rows]
        _MATCH_CACHE[cache_key] = (time.time(), names)
        return names

    def _disease_detail(self, disease: str) -> Dict[str, Any]:
        """单个标准疾病名 → 关联营养素/食物/直接宜忌关系/建议。"""
        with self.driver.session() as s:
            rows = s.run(
                """
                MATCH (d:Disease {name: $kw})
                OPTIONAL MATCH (d)<-[r]-(n:Nutrient)
                OPTIONAL MATCH (n2:Nutrient)<-[:含有]-(f:Food)
                WHERE n2.name = n.name
                RETURN d.name AS disease,
                       collect(DISTINCT {nutrient: n.name, relation: type(r), note: r.note}) AS nutrients,
                       collect(DISTINCT f.name) AS foods
                """,
                kw=disease,
            ).data()
            if not rows:
                return {}
            row = rows[0]
            direct = s.run(
                """
                MATCH (f:Food)-[r]->(d:Disease {name: $kw})
                WHERE type(r) IN ['适宜', '禁忌']
                RETURN f.name AS food, type(r) AS relation, r.note AS note
                ORDER BY type(r), f.name
                """,
                kw=disease,
            ).data()
        return {
            "disease": row["disease"],
            "nutrients": [x for x in row["nutrients"] if x.get("nutrient")],
            "foods": [f for f in row["foods"] if f],
            "suitable": [r["food"] for r in direct if r["relation"] == "适宜"],
            "taboo": [{"food": r["food"], "note": r["note"]} for r in direct if r["relation"] == "禁忌"],
            "advice": DISEASE_ADVICE.get(row["disease"], ""),
        }

    def search_disease(self, keyword: str) -> List[Dict[str, Any]]:
        """按疾病描述（支持自由文本/多病并列）查询关联的营养素/食物/建议。

        输入「高血压、2型糖尿病」这类组合描述时，可能命中多个疾病节点，
        按匹配具体度返回最多 3 条。
        """
        return [d for d in (self._disease_detail(name)
                            for name in self._match_diseases(keyword)) if d]

    # ---------------- 食物 ↔ 疾病 直接关系 ----------------
    def _food_relation_map(self, ttl: float = 90.0) -> Dict[str, List[Dict[str, Any]]]:
        """加载「食物写法 → 关系列表」映射（含别名），带 TTL 缓存。

        两类关系合并：
          1) 显式直接关系：(食物)-[:适宜|禁忌]->(疾病)
          2) **两跳推断**：(食物)-[:含有]->(营养素)-[降低风险|缓解|加重]->(疾病)
             例：酱油-含有->钠-加重->高血压 ⇒ 酱油对高血压「禁忌」
                 木耳-含有->铁-缓解->缺铁性贫血 ⇒ 木耳对贫血「适宜」
             这条推断让「扩谱新增一条含有关系」自动转化为可用的饮食建议，
             而不只是让图谱多一个节点。推断项带 inferred=True 与 via 字段，
             前端/排查时可与人工确认过的直接关系区分。
        同 (食物,关系,疾病) 组合以显式直接关系优先。

        排菜时会对每套菜单反复调用禁忌校验，逐个查 Neo4j 太慢；
        图谱规模很小，整表读进内存 + 90 秒缓存足够。
        """
        global _FOOD_REL_CACHE, _FOOD_REL_TS
        now = time.time()
        if _FOOD_REL_CACHE is not None and (now - _FOOD_REL_TS) < ttl:
            return _FOOD_REL_CACHE
        try:
            with self.driver.session() as s:
                direct = s.run(
                    """
                    MATCH (f:Food)-[r]->(d:Disease)
                    WHERE type(r) IN ['适宜', '禁忌']
                    RETURN f.name AS food, coalesce(f.aliases, []) AS aliases,
                           type(r) AS relation, d.name AS disease, r.note AS note
                    """
                ).data()
                inferred = s.run(
                    """
                    MATCH (f:Food)-[:含有]->(n:Nutrient)-[r]->(d:Disease)
                    WHERE type(r) IN ['降低风险', '缓解', '加重']
                    RETURN f.name AS food, coalesce(f.aliases, []) AS aliases,
                           n.name AS nutrient, type(r) AS rel,
                           d.name AS disease, r.note AS note
                    """
                ).data()
        except Exception as e:  # noqa: BLE001
            logger.warning("读取食物-疾病关系失败，退化为空映射: %s", e)
            return {}

        mapping: Dict[str, List[Dict[str, Any]]] = {}
        seen: set = set()

        def _add(food: str, aliases, item: Dict[str, Any]) -> None:
            sig = (item["food"], item["relation"], item["disease"])
            if sig in seen:
                return
            seen.add(sig)
            for key in [food] + list(aliases or []):
                mapping.setdefault(key, []).append(item)

        for row in direct:
            _add(row["food"], row["aliases"], {
                "food": row["food"], "relation": row["relation"],
                "disease": row["disease"], "note": row["note"] or "",
                "inferred": False, "via": None,
            })
        for row in inferred:
            relation = "适宜" if row["rel"] in ("降低风险", "缓解") else "禁忌"
            note = f"经「{row['nutrient']}」{row['rel']}"
            if row["note"]:
                note += f"（{row['note']}）"
            _add(row["food"], row["aliases"], {
                "food": row["food"], "relation": relation,
                "disease": row["disease"], "note": note,
                "inferred": True, "via": row["nutrient"],
            })
        _FOOD_REL_CACHE, _FOOD_REL_TS = mapping, now
        return mapping

    def find_food_relations(self, text: str, disease: Optional[str] = None) -> List[Dict[str, Any]]:
        """在自由文本（菜名 + 食材串）中识别图谱食物，返回命中的直接关系。

        返回项含 matched（命中的写法）与 food（图谱标准名），便于前端展示与去重。
        """
        text = text or ""
        if not text:
            return []
        hits: List[Dict[str, Any]] = []
        seen = set()
        for key, relations in self._food_relation_map().items():
            if key not in text:
                continue
            for item in relations:
                if disease and item["disease"] != disease:
                    continue
                sig = (item["food"], item["relation"], item["disease"])
                if sig in seen:
                    continue
                seen.add(sig)
                hits.append({**item, "matched": key})
        return hits

    def reason_path(self, disease_keyword: str,
                    exclude_foods: Optional[List[str]] = None) -> Dict[str, Any]:
        """多跳推理：疾病 → 推荐营养素 → 含该营养素的食物，叠加直接宜忌关系。

        与单跳查询的区别在于**方向区分 + 可解释的推理链 + 可排除项**：
          正向：骨质疏松 ←降低风险— 钙 ——含有—— 牛奶/豆腐/芝麻
          反向：高血压 ←加重— 钠 ——含有—— 腌制食品/香肠（应规避）
          骨质疏松 → 钙 → 牛奶，若用户乳糖不耐受（exclude_foods=['牛奶','酸奶']），
          牛奶会在链路上被剔除并单独记录原因，而不是静默消失。
        """
        names = self._match_diseases(disease_keyword, limit=1)
        if not names:
            return {}
        disease = names[0]
        exclude = {f for f in (exclude_foods or []) if f}

        with self.driver.session() as s:
            rows = s.run(
                """
                MATCH (d:Disease {name: $kw})<-[r]-(n:Nutrient)
                WHERE type(r) IN ['降低风险', '缓解']
                OPTIONAL MATCH (n)<-[:含有]-(f:Food)
                RETURN n.name AS nutrient, type(r) AS relation, r.note AS note,
                       collect(DISTINCT f.name) AS foods
                ORDER BY n.name
                """,
                kw=disease,
            ).data()
            risk_rows = s.run(
                """
                MATCH (d:Disease {name: $kw})<-[r]-(n:Nutrient)
                WHERE type(r) = '加重'
                OPTIONAL MATCH (n)<-[:含有]-(f:Food)
                RETURN n.name AS nutrient, r.note AS note,
                       collect(DISTINCT f.name) AS foods
                ORDER BY n.name
                """,
                kw=disease,
            ).data()

        nutrient_hops: List[Dict[str, Any]] = []
        recommended: List[str] = []
        excluded: List[Dict[str, str]] = []
        for row in rows:
            keep, drop = [], []
            for food in [f for f in (row["foods"] or []) if f]:
                (drop if food in exclude else keep).append(food)
            for food in drop:
                excluded.append({"food": food, "reason": "画像标注不宜（过敏/不耐受），已从推荐中剔除"})
            nutrient_hops.append({
                "nutrient": row["nutrient"],
                "relation": row["relation"],
                "note": row["note"] or "",
                "foods": keep,
            })
            recommended.extend(keep)

        # 「加重」方向：风险营养素所对应的食物 → 明确列为应规避项
        risk_hops: List[Dict[str, Any]] = []
        risk_foods: List[Dict[str, str]] = []
        for row in risk_rows:
            foods = [f for f in (row["foods"] or []) if f]
            risk_hops.append({"nutrient": row["nutrient"],
                              "note": row["note"] or "", "foods": foods})
            for food in foods:
                risk_foods.append({"food": food,
                                   "note": f"富含{row['nutrient']}：{row['note'] or '不利于该疾病控制'}"})

        detail = self._disease_detail(disease)
        suitable = [f for f in detail.get("suitable", []) if f not in exclude]
        for food in detail.get("suitable", []):
            if food in exclude:
                excluded.append({"food": food, "reason": "画像标注不宜（过敏/不耐受），已从推荐中剔除"})
        taboo = list(detail.get("taboo", []))
        for item in risk_foods:  # 加重营养素推断出的规避项，与直接禁忌关系合并
            if item["food"] not in {t["food"] for t in taboo}:
                taboo.append(item)

        # 推荐与规避取差集：同一食物不能既推荐又规避（优先规避）
        blocked = {t["food"] for t in taboo} | exclude
        recommended = [f for f in dict.fromkeys(recommended + suitable) if f not in blocked]
        excluded = list({e["food"]: e for e in excluded}.values())

        hops = [f"{disease} ←{h['relation']}— {h['nutrient']} ——含有—— {'/'.join(h['foods']) or '（无可用食物）'}"
                for h in nutrient_hops if h["foods"]]
        hops += [f"{disease} ←加重— {h['nutrient']} ——含有—— {'/'.join(h['foods'])}（应规避）"
                 for h in risk_hops if h["foods"]]

        return {
            "disease": disease,
            "advice": detail.get("advice", ""),
            "nutrient_hops": nutrient_hops,
            "risk_hops": risk_hops,
            "recommended": recommended,
            "suitable": suitable,
            "taboo": taboo,
            "excluded": excluded,
            "hops": hops,
        }

    def graph_relations(self, limit: int = 60) -> List[Dict[str, Any]]:
        """返回全部 适宜/禁忌 直接关系（演示"规则由图谱维护"用）。"""
        with self.driver.session() as s:
            return s.run(
                """
                MATCH (f:Food)-[r]->(d:Disease)
                WHERE type(r) IN ['适宜', '禁忌']
                RETURN f.name AS food, type(r) AS relation,
                       d.name AS disease, r.note AS note
                ORDER BY type(r), d.name, f.name
                LIMIT $limit
                """,
                limit=limit,
            ).data()

    def get_graph_data(self, limit: int = 200,
                       disease: Optional[str] = None) -> Dict[str, Any]:
        """返回前端图谱可视化数据（ECharts graph 格式）。

        仅返回营养知识图谱的三类节点（Food / Nutrient / Disease）；
        库内可能同时存在其它业务图谱数据（如人才技能图谱的 Talent/Skill/Tag），
        这些节点必须过滤掉，否则可视化会变成一团噪声。

        disease 非空时只返回该疾病及其关联营养素、以及含有这些营养素的食物
        （两跳子图），便于按疾病逐个查看。
        """
        cat_map = {"Food": 0, "Nutrient": 1, "Disease": 2}
        size_map = {"Food": 28, "Nutrient": 24, "Disease": 32}
        categories = ["食物", "营养素", "疾病"]

        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        seen: set = set()

        def add_node(name: Optional[str], label: Optional[str]) -> None:
            if not name or name in seen or label not in cat_map:
                return
            seen.add(name)
            nodes.append({
                "name": name,
                "category": cat_map[label],
                "symbolSize": size_map[label],
            })

        with self.driver.session() as s:
            if disease:
                rows = s.run(
                    """
                    MATCH (d:Disease {name: $disease})
                    OPTIONAL MATCH (n:Nutrient)-[r1]->(d)
                    OPTIONAL MATCH (f:Food)-[r2:含有]->(n)
                    RETURN d.name AS disease,
                           collect(DISTINCT {name: n.name, rel: type(r1)}) AS nutrients,
                           collect(DISTINCT {food: f.name, nutrient: n.name}) AS pairs
                    """,
                    disease=disease,
                ).data()
                if not rows:
                    return {"categories": categories, "nodes": [], "links": [],
                            "disease": disease, "found": False}

                row = rows[0]
                add_node(row["disease"], "Disease")
                for item in row["nutrients"]:
                    nut = item.get("name")
                    if not nut:
                        continue
                    add_node(nut, "Nutrient")
                    links.append({
                        "source": nut, "target": row["disease"],
                        "label": {"show": True, "formatter": item.get("rel") or "关联"},
                    })
                for item in row["pairs"]:
                    food, nut = item.get("food"), item.get("nutrient")
                    if not food or not nut:
                        continue
                    add_node(food, "Food")
                    links.append({
                        "source": food, "target": nut,
                        "label": {"show": True, "formatter": "含有"},
                    })
                # 食物→疾病 直接关系（适宜/禁忌），两跳链路之外的一级连接
                direct_rows = s.run(
                    """
                    MATCH (f:Food)-[r]->(d:Disease {name: $disease})
                    WHERE type(r) IN ['适宜', '禁忌']
                    RETURN f.name AS food, type(r) AS rel
                    """,
                    disease=disease,
                ).data()
                for item in direct_rows:
                    food = item.get("food")
                    if not food:
                        continue
                    add_node(food, "Food")
                    links.append({
                        "source": food, "target": row["disease"],
                        "label": {"show": True, "formatter": item.get("rel") or "关联"},
                    })
                return {
                    "categories": categories, "nodes": nodes, "links": links,
                    "disease": disease, "found": True,
                }

            node_rows = s.run(
                """
                MATCH (n)
                WHERE any(l IN labels(n) WHERE l IN ['Food', 'Nutrient', 'Disease'])
                RETURN n.name AS name, labels(n)[0] AS category
                LIMIT $limit
                """,
                limit=limit,
            ).data()
            rel_rows = s.run(
                """
                MATCH (a)-[r]->(b)
                WHERE any(l IN labels(a) WHERE l IN ['Food', 'Nutrient', 'Disease'])
                  AND any(l IN labels(b) WHERE l IN ['Food', 'Nutrient', 'Disease'])
                RETURN a.name AS source, type(r) AS rel, b.name AS target
                LIMIT $limit
                """,
                limit=limit,
            ).data()

        for n in node_rows:
            add_node(n["name"], n["category"])
        for r in rel_rows:
            if r["source"] in seen and r["target"] in seen:
                links.append({
                    "source": r["source"], "target": r["target"],
                    "label": {"show": True, "formatter": r["rel"]},
                })

        return {
            "categories": categories, "nodes": nodes, "links": links,
            "disease": None, "found": True,
        }

    def graph_stats(self) -> Dict[str, Any]:
        """营养图谱规模统计（节点 + 关系类型分布）"""
        with self.driver.session() as s:
            rows = s.run(
                """
                MATCH (n)
                WHERE any(l IN labels(n) WHERE l IN ['Food', 'Nutrient', 'Disease'])
                RETURN labels(n)[0] AS label, count(*) AS count
                """
            ).data()
            rel_rows = s.run(
                """
                MATCH (a)-[r]->(b)
                WHERE any(l IN labels(a) WHERE l IN ['Food', 'Nutrient', 'Disease'])
                  AND any(l IN labels(b) WHERE l IN ['Food', 'Nutrient', 'Disease'])
                RETURN type(r) AS rel, count(*) AS count
                ORDER BY count DESC
                """
            ).data()
        counts = {r["label"]: r["count"] for r in rows}
        relations = {r["rel"]: r["count"] for r in rel_rows}
        return {
            "food": counts.get("Food", 0),
            "nutrient": counts.get("Nutrient", 0),
            "disease": counts.get("Disease", 0),
            "total": sum(counts.values()),
            "relations": relations,
            "relation_total": sum(relations.values()),
        }

    def get_diseases(self) -> List[str]:
        with self.driver.session() as s:
            rows = s.run("MATCH (d:Disease) RETURN d.name AS name ORDER BY d.name").data()
        return [r["name"] for r in rows]


_neo4j: Optional[Neo4jClient] = None

# 食物→直接关系 映射缓存（见 _food_relation_map）
_FOOD_REL_CACHE: Optional[Dict[str, List[Dict[str, Any]]]] = None
_FOOD_REL_TS: float = 0.0

# 疾病描述对齐结果缓存 {(原文, limit): (时间戳, [标准疾病名])}
_MATCH_CACHE: Dict[Any, Any] = {}


def get_neo4j() -> Neo4jClient:
    global _neo4j
    if _neo4j is None:
        _neo4j = Neo4jClient()
    return _neo4j
