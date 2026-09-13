"""从知识库文档自动抽取三元组，扩充营养知识图谱（LLM 辅助建谱）。

背景
----
图谱原先只有人工预置的 57 个节点，覆盖面窄——测评里出现「慢性胃炎」「甲状腺
功能减退」就查不到任何结论。本脚本把知识库（backend/demo_knowledge/*.md，
已入 Milvus 的同一批文档）喂给 LLM，抽取 (食物,关系,营养素/疾病) 三元组补进图谱。

设计要点（防止 LLM 幻觉污染图谱）
--------------------------------
1. 只允许使用文档中**明确出现**的事实，prompt 里显式禁止引入文档外常识
2. 每条关系带 note 证据（文档中的短句依据），便于人工复核
3. 抽取结果落盘为 JSON（backend/data/graph_llm_extraction.json）供审查
4. 写入 Neo4j 时给关系打 source 标记 `llm:<文件名>`，与人工预置关系区分
5. 支持 --dry 预览 / --clean-llm 一键回滚 LLM 抽取的关系

用法（在 backend 目录）
--------------------
  ./venv/Scripts/python.exe scripts/build_graph_from_llm.py --dry       # 只抽取+预览
  ./venv/Scripts/python.exe scripts/build_graph_from_llm.py             # 抽取并写入
  ./venv/Scripts/python.exe scripts/build_graph_from_llm.py --clean-llm # 删除 LLM 抽取的关系
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm_client import get_llm                      # noqa: E402
from app.utils.neo4j_client import get_neo4j, PRESET_DISEASES    # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_DIR = os.path.join(BASE_DIR, "demo_knowledge")
OUT_JSON = os.path.join(BASE_DIR, "data", "graph_llm_extraction.json")
LLM_SOURCE_PREFIX = "llm:"

# 过于泛化的类别词：作为 Food 节点会在排菜匹配时误命中（「蔬菜」会命中所有含蔬菜的菜名），
# 且无法给出"换成什么"的具体建议。这些词在文档里通常是统称，不代表可采购的食材。
GENERIC_FOOD_TERMS = {
    "蔬菜", "水果", "豆类", "全谷物", "深绿色叶菜", "绿叶菜", "肉类",
    "主食", "粗粮", "细粮", "食物", "食材", "膳食", "饮食", "营养",
}

SYSTEM_PROMPT = """你是营养知识图谱的三元组抽取器。请严格从给定文档中抽取结构化知识。

【硬性约束】
1. 只能使用文档中明确写出的信息，禁止引入文档之外的常识或你的先验知识（即使你认为它正确）。
2. 文档中没有明确依据的关系，一律不要输出。
3. 每个关系必须给出 note，内容为文档中的简短依据（不超过 25 字，尽量贴近原文）。
4. 食物、营养素、疾病名使用规范中文名词，不要用句子。

【疾病名对齐】如果文档中的疾病可以对应到下列标准名之一，请使用标准名：
%s

【输出格式】只输出一个 JSON 对象，不要任何解释文字、不要 Markdown 代码块：
{
  "food_nutrient":    [{"food": "燕麦", "nutrient": "膳食纤维", "note": "文档依据"}],
  "nutrient_disease": [{"nutrient": "钾", "relation": "降低风险", "disease": "高血压", "note": "文档依据"}],
  "food_disease":     [{"food": "深海鱼", "relation": "适宜", "disease": "冠心病", "note": "文档依据"}]
}

relation 只能取：nutrient_disease 用「降低风险/缓解/加重」，food_disease 用「适宜/禁忌」。
三类都没有时对应字段返回空数组。""" % "、".join(PRESET_DISEASES)


def _strip_fence(text: str) -> str:
    """去掉 LLM 偶尔包上的 ```json 围栏。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return text


def extract_from_doc(llm, filename: str, content: str) -> dict:
    """对单篇文档调 LLM 抽取三元组。"""
    resp = llm.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"【文档：{filename}】\n{content[:6000]}\n\n请抽取三元组。"},
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    try:
        data = json.loads(_strip_fence(resp))
    except Exception as e:  # noqa: BLE001
        print(f"    ! JSON 解析失败: {e}")
        return {"food_nutrient": [], "nutrient_disease": [], "food_disease": []}
    for key in ("food_nutrient", "nutrient_disease", "food_disease"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def apply_to_graph(extractions: dict) -> dict:
    """把抽取结果 MERGE 进 Neo4j（带 source 标记，幂等）。"""
    client = get_neo4j()
    counts = {"含有": 0, "营养_疾病": 0, "食物_疾病": 0, "跳过泛化词": 0}
    with client.driver.session() as s:
        for filename, data in extractions.items():
            source = f"{LLM_SOURCE_PREFIX}{filename}"
            for item in data.get("food_nutrient", []):
                food, nut = (item.get("food") or "").strip(), (item.get("nutrient") or "").strip()
                if not food or not nut:
                    continue
                if food in GENERIC_FOOD_TERMS:
                    counts["跳过泛化词"] += 1
                    continue
                s.run(
                    "MERGE (f:Food {name: $f}) SET f.llm_source = $src "
                    "MERGE (n:Nutrient {name: $n}) "
                    "MERGE (f)-[r:含有]->(n) "
                    "SET r.note = $note, r.source = $src, r.extractor = 'llm'",
                    f=food, n=nut, note=(item.get("note") or "")[:60], src=source,
                )
                counts["含有"] += 1
            for item in data.get("nutrient_disease", []):
                nut, disease = (item.get("nutrient") or "").strip(), (item.get("disease") or "").strip()
                rel = (item.get("relation") or "").strip()
                if not nut or not disease or rel not in ("降低风险", "缓解", "加重"):
                    continue
                s.run(
                    "MERGE (n:Nutrient {name: $n}) "
                    "MERGE (d:Disease {name: $d}) SET d.llm_verified = true "
                    "MERGE (n)-[r:%s]->(d) "
                    "SET r.note = $note, r.source = $src, r.extractor = 'llm'" % rel,
                    n=nut, d=disease, note=(item.get("note") or "")[:60], src=source,
                )
                counts["营养_疾病"] += 1
            for item in data.get("food_disease", []):
                food, disease = (item.get("food") or "").strip(), (item.get("disease") or "").strip()
                rel = (item.get("relation") or "").strip()
                if not food or not disease or rel not in ("适宜", "禁忌"):
                    continue
                if food in GENERIC_FOOD_TERMS:
                    counts["跳过泛化词"] += 1
                    continue
                s.run(
                    "MERGE (f:Food {name: $f}) SET f.llm_source = $src "
                    "MERGE (d:Disease {name: $d}) "
                    "MERGE (f)-[r:%s]->(d) "
                    "SET r.note = $note, r.source = $src, r.extractor = 'llm'" % rel,
                    f=food, d=disease, note=(item.get("note") or "")[:60], src=source,
                )
                counts["食物_疾病"] += 1
    return counts


def clean_llm_relations() -> int:
    """删除全部 LLM 抽取的关系（人工预置关系不动）。"""
    client = get_neo4j()
    with client.driver.session() as s:
        n = s.run(
            "MATCH ()-[r]->() WHERE r.source STARTS WITH $p "
            "WITH r, count(r) AS c DELETE r RETURN c",
            p=LLM_SOURCE_PREFIX,
        ).single()
        # 清掉 LLM 新建的、不再有任何关系的孤立节点
        s.run(
            "MATCH (n:Food) WHERE n.llm_source IS NOT NULL AND NOT (n)--() "
            "DETACH DELETE n"
        )
    return (n["c"] if n else 0)


def main():
    ap = argparse.ArgumentParser(description="LLM 辅助扩谱")
    ap.add_argument("--dry", action="store_true", help="只抽取并预览，不写图谱")
    ap.add_argument("--from-json", action="store_true",
                    help="跳过 LLM，直接读取已审查的 graph_llm_extraction.json 写入图谱")
    ap.add_argument("--clean-llm", action="store_true", help="删除 LLM 抽取的关系")
    ap.add_argument("--only", default="", help="只处理文件名包含该子串的文档")
    ap.add_argument("--limit", type=int, default=0, help="最多处理几篇文档")
    args = ap.parse_args()

    if args.clean_llm:
        n = clean_llm_relations()
        print(f"已删除 LLM 抽取的关系 {n} 条")
        print("图谱现状:", get_neo4j().graph_stats())
        return

    if args.from_json:
        if not os.path.exists(OUT_JSON):
            print(f"未找到 {OUT_JSON}，请先运行一次抽取")
            return
        with open(OUT_JSON, encoding="utf-8") as fh:
            extractions = json.load(fh)
        total = {k: sum(len(d.get(k, [])) for d in extractions.values())
                 for k in ("food_nutrient", "nutrient_disease", "food_disease")}
        print(f"从 {OUT_JSON} 读取 {len(extractions)} 篇文档的三元组，合计 {total}")
        counts = apply_to_graph(extractions)
        print("写入条数:", counts)
        print("图谱现状:", get_neo4j().graph_stats())
        return

    files = sorted(f for f in os.listdir(DOC_DIR) if f.endswith(".md"))
    if args.only:
        files = [f for f in files if args.only in f]
    if args.limit:
        files = files[:args.limit]
    if not files:
        print("没有匹配的文档")
        return

    print(f"待抽取文档 {len(files)} 篇：{files}\n")
    llm = get_llm()
    extractions: dict = {}
    for i, name in enumerate(files, 1):
        path = os.path.join(DOC_DIR, name)
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        print(f"[{i}/{len(files)}] {name} ({len(content)} 字) -> 抽取中…")
        data = extract_from_doc(llm, name, content)
        extractions[name] = data
        print(f"    食物-营养素 {len(data['food_nutrient'])} · "
              f"营养素-疾病 {len(data['nutrient_disease'])} · "
              f"食物-疾病 {len(data['food_disease'])}")

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(extractions, fh, ensure_ascii=False, indent=2)
    print(f"\n抽取结果已保存: {OUT_JSON}")

    total = {k: sum(len(d[k]) for d in extractions.values())
             for k in ("food_nutrient", "nutrient_disease", "food_disease")}
    print("合计:", total)

    if args.dry:
        print("\n[dry-run] 未写入图谱。示例：")
        for name, data in list(extractions.items())[:2]:
            print(f"  --- {name} ---")
            for item in (data["food_disease"] + data["food_nutrient"])[:6]:
                print("   ", item)
        return

    print("\n写入图谱…")
    counts = apply_to_graph(extractions)
    print("写入条数:", counts)
    print("图谱现状:", get_neo4j().graph_stats())


if __name__ == "__main__":
    main()
