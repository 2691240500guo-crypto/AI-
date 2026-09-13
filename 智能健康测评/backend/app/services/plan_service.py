"""饮食计划生成服务。

供两处复用：
  1. REST 路由 POST /api/plans/generate（前端饮食计划页）
  2. AI 智能问答对话内意图触发（assistant_service.chat 命中“制定饮食计划”时）

个性化逻辑：
  - 读取 UserProfile 画像 → Mifflin-St Jeor 估算基础代谢 × 轻度活动系数
  - 按目标（减脂 -400 / 增肌 +300 / 保持）折算目标热量
  - 近 7 天 MealRecord 实际摄入校准并写入说明
  - 按目标热量从三档菜谱库选档
  - 过敏原/疾病禁忌校验：疾病禁忌规则来自 Neo4j 知识图谱
    （(食物)-[:禁忌]->(疾病) 直接关系），本文件的词表仅作图谱不可用时的兜底
"""
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

logger = logging.getLogger("plan_service")

# ---------------------------------------------------------------
# 饮食计划档位模板库（按目标热量分三档，避免“写死一套模板”的观感）
# 每档一日三餐 + 对应 7 天购物清单；实际分量随 target 档位切换
# ---------------------------------------------------------------
PLAN_SETS = {
    "low": {
        "label": "轻食减负档",
        "range": (1400, 1750),
        "menus": [
            {
                "recipes": [
                    {"meal": "早餐", "name": "无糖酸奶燕麦杯", "kcal": 320,
                     "ingredients": ["即食燕麦 40g", "无糖酸奶 150g", "蓝莓 50g", "奇亚籽 5g"]},
                    {"meal": "午餐", "name": "鸡胸藜麦能量沙拉", "kcal": 540,
                     "ingredients": ["鸡胸肉 120g", "藜麦 70g", "混合生菜 150g", "油醋汁 15ml"]},
                    {"meal": "晚餐", "name": "番茄虾仁豆腐煲", "kcal": 690,
                     "ingredients": ["虾仁 100g", "嫩豆腐 200g", "番茄 2个", "糙米饭 100g"]},
                ],
                "shopping_list": ["即食燕麦 1包", "无糖酸奶 7盒", "蓝莓 2盒", "奇亚籽 1罐", "鸡胸肉 1kg", "藜麦 500g",
                                  "混合生菜 1kg", "虾仁 800g", "嫩豆腐 7盒", "番茄 14个", "糙米 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "全麦鸡蛋蔬菜卷", "kcal": 300,
                     "ingredients": ["全麦卷饼 1张", "鸡蛋 1个", "生菜 50g", "无糖豆浆 250ml"]},
                    {"meal": "午餐", "name": "香煎鸡胸西兰花糙米饭", "kcal": 520,
                     "ingredients": ["鸡胸肉 130g", "西兰花 150g", "糙米饭 100g", "橄榄油 5ml"]},
                    {"meal": "晚餐", "name": "冬瓜虾仁菌菇汤配杂粮饭", "kcal": 660,
                     "ingredients": ["虾仁 90g", "冬瓜 200g", "菌菇 100g", "杂粮饭 100g"]},
                ],
                "shopping_list": ["全麦卷饼 1包", "鸡蛋 7个", "生菜 500g", "无糖豆浆 7盒", "鸡胸肉 1kg",
                                  "西兰花 1.2kg", "糙米 1kg", "虾仁 700g", "冬瓜 2kg", "菌菇 800g", "杂粮米 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "燕麦香蕉蛋白奶昔", "kcal": 290,
                     "ingredients": ["即食燕麦 35g", "香蕉 1根", "低脂牛奶 250ml", "奇亚籽 5g"]},
                    {"meal": "午餐", "name": "低脂鸡胸蔬菜沙拉碗", "kcal": 500,
                     "ingredients": ["鸡胸肉 120g", "混合生菜 150g", "黄瓜 80g", "油醋汁 15ml"]},
                    {"meal": "晚餐", "name": "清蒸鲈鱼配芦笋糙米饭", "kcal": 640,
                     "ingredients": ["鲈鱼 150g", "芦笋 120g", "糙米饭 100g", "姜丝 少许"]},
                ],
                "shopping_list": ["即食燕麦 1包", "香蕉 7根", "低脂牛奶 2L", "奇亚籽 1罐", "鸡胸肉 900g",
                                  "混合生菜 1kg", "黄瓜 7根", "鲈鱼 1.1kg", "芦笋 800g", "糙米 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "紫薯燕麦粥配水煮蛋", "kcal": 310,
                     "ingredients": ["紫薯 100g", "即食燕麦 30g", "水煮蛋 1个", "无糖豆浆 250ml"]},
                    {"meal": "午餐", "name": "鸡丝凉拌荞麦面", "kcal": 480,
                     "ingredients": ["鸡胸肉 100g", "荞麦面 80g", "黄瓜 80g", "胡萝卜 50g"]},
                    {"meal": "晚餐", "name": "虾仁冬瓜汤配蒸南瓜", "kcal": 620,
                     "ingredients": ["虾仁 100g", "冬瓜 200g", "南瓜 150g", "姜丝 少许"]},
                ],
                "shopping_list": ["紫薯 1kg", "即食燕麦 1包", "鸡蛋 7个", "无糖豆浆 7盒", "鸡胸肉 800g",
                                  "荞麦面 500g", "黄瓜 7根", "胡萝卜 500g", "虾仁 800g", "冬瓜 2kg", "南瓜 1.5kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "杂粮包子配无糖豆浆", "kcal": 330,
                     "ingredients": ["杂粮包子 1个", "无糖豆浆 300ml", "圣女果 80g"]},
                    {"meal": "午餐", "name": "金枪鱼蔬菜全麦三明治", "kcal": 470,
                     "ingredients": ["水浸金枪鱼 100g", "全麦面包 2片", "生菜 60g", "番茄 50g"]},
                    {"meal": "晚餐", "name": "鸡蓉菌菇汤配凉拌菠菜糙米饭", "kcal": 650,
                     "ingredients": ["鸡胸肉末 90g", "菌菇 120g", "菠菜 150g", "糙米饭 100g"]},
                ],
                "shopping_list": ["杂粮包子 7个", "无糖豆浆 2.1L", "圣女果 500g", "水浸金枪鱼罐头 7罐", "全麦面包 1袋",
                                  "生菜 500g", "番茄 500g", "鸡胸肉 700g", "菌菇 900g", "菠菜 1kg", "糙米 1kg"],
            },
            # 无海鲜方案：供海鲜/鱼类过敏人群自动避让（此前 5 套均含虾或鱼）
            {
                "recipes": [
                    {"meal": "早餐", "name": "红薯鸡蛋燕麦粥", "kcal": 330,
                     "ingredients": ["红薯 100g", "鸡蛋 1个", "即食燕麦 30g", "蓝莓 30g"]},
                    {"meal": "午餐", "name": "番茄牛肉糙米饭", "kcal": 520,
                     "ingredients": ["瘦牛肉 100g", "番茄 2个", "糙米饭 100g", "西兰花 100g"]},
                    {"meal": "晚餐", "name": "香菇滑鸡藜麦饭", "kcal": 600,
                     "ingredients": ["鸡腿肉 100g", "香菇 80g", "藜麦 80g", "青菜 100g"]},
                ],
                "shopping_list": ["红薯 700g", "鸡蛋 7个", "即食燕麦 1包", "蓝莓 2盒", "瘦牛肉 700g",
                                  "番茄 14个", "糙米 700g", "西兰花 700g", "鸡腿 700g", "香菇 560g",
                                  "藜麦 560g", "青菜 700g"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "南瓜小米粥配水煮蛋", "kcal": 300,
                     "ingredients": ["南瓜 150g", "小米 40g", "鸡蛋 1个"]},
                    {"meal": "午餐", "name": "彩椒牛柳杂粮饭", "kcal": 540,
                     "ingredients": ["牛里脊 110g", "彩椒 100g", "杂粮饭 100g", "橄榄油 5ml"]},
                    {"meal": "晚餐", "name": "萝卜炖鸡腿配糙米饭", "kcal": 610,
                     "ingredients": ["鸡腿肉 120g", "白萝卜 150g", "糙米饭 100g", "菠菜 100g"]},
                ],
                "shopping_list": ["南瓜 1kg", "小米 300g", "鸡蛋 7个", "牛里脊 800g", "彩椒 7个",
                                  "杂粮米 700g", "橄榄油 1瓶", "鸡腿 840g", "白萝卜 1kg", "糙米 700g", "菠菜 700g"],
            },
        ],
    },
    "med": {
        "label": "均衡营养档",
        "range": (1750, 2200),
        "menus": [
            {
                "recipes": [
                    {"meal": "早餐", "name": "牛油果鸡蛋全麦吐司", "kcal": 460,
                     "ingredients": ["全麦吐司 2片", "鸡蛋 1个", "牛油果 半个", "低脂牛奶 200ml"]},
                    {"meal": "午餐", "name": "香煎三文鱼杂粮饭", "kcal": 720,
                     "ingredients": ["三文鱼 150g", "杂粮饭 150g", "西兰花 120g", "柠檬汁 少许"]},
                    {"meal": "晚餐", "name": "彩椒牛肉糙米碗", "kcal": 770,
                     "ingredients": ["瘦牛肉 120g", "彩椒 1个", "糙米饭 150g", "洋葱 50g"]},
                ],
                "shopping_list": ["全麦吐司 1包", "鸡蛋 7个", "牛油果 4个", "低脂牛奶 2L", "三文鱼 1.1kg",
                                  "杂粮米 1kg", "西兰花 1kg", "瘦牛肉 900g", "彩椒 7个", "洋葱 500g", "糙米 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "希腊酸奶坚果芭菲", "kcal": 420,
                     "ingredients": ["无糖希腊酸奶 200g", "混合坚果 20g", "蓝莓 50g", "燕麦脆 30g"]},
                    {"meal": "午餐", "name": "照烧鸡腿杂粮饭配时蔬", "kcal": 700,
                     "ingredients": ["鸡腿肉 180g", "杂粮饭 150g", "时令蔬菜 150g", "照烧汁 15ml"]},
                    {"meal": "晚餐", "name": "番茄牛腩炖土豆配米饭", "kcal": 780,
                     "ingredients": ["牛腩 120g", "番茄 2个", "土豆 150g", "米饭 150g"]},
                ],
                "shopping_list": ["希腊酸奶 1.4kg", "混合坚果 200g", "蓝莓 400g", "燕麦脆 1袋", "鸡腿 1.3kg",
                                  "杂粮米 1kg", "时令蔬菜 1kg", "牛腩 900g", "番茄 14个", "土豆 1kg", "大米 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "鸡蛋牛油果贝果", "kcal": 450,
                     "ingredients": ["贝果 1个", "鸡蛋 1个", "牛油果 半个", "黑咖啡 1杯"]},
                    {"meal": "午餐", "name": "虾仁滑蛋杂粮饭配菠菜", "kcal": 690,
                     "ingredients": ["虾仁 130g", "鸡蛋 1个", "杂粮饭 150g", "菠菜 120g"]},
                    {"meal": "晚餐", "name": "香菇滑鸡糙米饭", "kcal": 760,
                     "ingredients": ["鸡腿肉 160g", "香菇 100g", "糙米饭 150g", "青菜 120g"]},
                ],
                "shopping_list": ["贝果 1袋", "鸡蛋 14个", "牛油果 4个", "虾仁 900g", "杂粮米 1kg",
                                  "菠菜 900g", "鸡腿 1.2kg", "香菇 700g", "糙米 1kg", "青菜 900g"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "山药小米粥配茶叶蛋", "kcal": 430,
                     "ingredients": ["山药 100g", "小米 40g", "茶叶蛋 1个", "凉拌木耳 50g"]},
                    {"meal": "午餐", "name": "清蒸鳕鱼配藜麦饭", "kcal": 700,
                     "ingredients": ["鳕鱼 160g", "藜麦饭 150g", "芦笋 100g", "柠檬汁 少许"]},
                    {"meal": "晚餐", "name": "豆腐牛肉菌菇汤配杂粮饭", "kcal": 760,
                     "ingredients": ["嫩豆腐 200g", "瘦牛肉 100g", "金针菇 80g", "杂粮饭 150g"]},
                ],
                "shopping_list": ["山药 1kg", "小米 500g", "鸡蛋 7个", "木耳 100g", "鳕鱼 1.2kg",
                                  "藜麦 500g", "芦笋 700g", "柠檬 3个", "嫩豆腐 7盒", "瘦牛肉 800g", "金针菇 600g", "杂粮米 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "红薯燕麦碗配无糖酸奶", "kcal": 440,
                     "ingredients": ["红薯 150g", "即食燕麦 40g", "无糖酸奶 150g", "核桃 2颗"]},
                    {"meal": "午餐", "name": "宫保鸡丁配糙米饭", "kcal": 720,
                     "ingredients": ["鸡腿肉 160g", "花生 15g", "黄瓜 80g", "糙米饭 150g"]},
                    {"meal": "晚餐", "name": "清炒虾仁西葫芦配玉米饭", "kcal": 750,
                     "ingredients": ["虾仁 140g", "西葫芦 150g", "玉米饭 150g", "蒜末 少许"]},
                ],
                "shopping_list": ["红薯 1.2kg", "即食燕麦 1包", "无糖酸奶 7盒", "核桃 200g", "鸡腿 1.2kg",
                                  "花生米 200g", "黄瓜 7根", "糙米 1kg", "虾仁 1kg", "西葫芦 1kg", "玉米碴 500g"],
            },
        ],
    },
    "high": {
        "label": "增能强化档",
        "range": (2200, 2700),
        "menus": [
            {
                "recipes": [
                    {"meal": "早餐", "name": "鸡蛋蔬菜煎饼套餐", "kcal": 640,
                     "ingredients": ["全麦饼 1张", "鸡蛋 2个", "生菜 60g", "无糖豆浆 300ml", "香蕉 1根"]},
                    {"meal": "午餐", "name": "红烧鸡腿便当", "kcal": 950,
                     "ingredients": ["鸡腿 250g", "米饭 200g", "清炒时蔬 150g", "卤蛋 1个"]},
                    {"meal": "晚餐", "name": "番茄肉末豆腐盖饭", "kcal": 860,
                     "ingredients": ["瘦猪肉末 100g", "嫩豆腐 250g", "番茄 2个", "米饭 200g"]},
                ],
                "shopping_list": ["全麦饼 7张", "鸡蛋 14个", "生菜 500g", "无糖豆浆 7盒", "香蕉 7根",
                                  "鸡腿 2kg", "大米 2kg", "时令蔬菜 2kg", "瘦猪肉末 700g", "嫩豆腐 7盒", "番茄 14个"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "花生酱香蕉全麦三明治", "kcal": 660,
                     "ingredients": ["全麦面包 2片", "花生酱 20g", "香蕉 1根", "牛奶 300ml"]},
                    {"meal": "午餐", "name": "黑椒牛肉盖饭配西兰花", "kcal": 980,
                     "ingredients": ["瘦牛肉 150g", "米饭 220g", "西兰花 150g", "黑椒汁 10ml"]},
                    {"meal": "晚餐", "name": "三文鱼意面配时蔬", "kcal": 880,
                     "ingredients": ["三文鱼 150g", "意大利面 80g", "时令蔬菜 150g", "橄榄油 10ml"]},
                ],
                "shopping_list": ["全麦面包 1袋", "花生酱 1瓶", "香蕉 7根", "牛奶 2.1L", "瘦牛肉 1.1kg",
                                  "大米 2kg", "西兰花 1.2kg", "三文鱼 1.1kg", "意大利面 1袋", "时令蔬菜 1kg"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "燕麦蛋白奶昔配水煮蛋", "kcal": 620,
                     "ingredients": ["即食燕麦 50g", "低脂牛奶 300ml", "蛋白粉 1勺", "水煮蛋 2个"]},
                    {"meal": "午餐", "name": "咖喱鸡肉饭配时蔬", "kcal": 960,
                     "ingredients": ["鸡腿肉 200g", "米饭 220g", "土豆 150g", "胡萝卜 100g"]},
                    {"meal": "晚餐", "name": "番茄牛腩面", "kcal": 850,
                     "ingredients": ["牛腩 130g", "面条 100g", "番茄 2个", "青菜 120g"]},
                ],
                "shopping_list": ["即食燕麦 1包", "低脂牛奶 2.1L", "鸡蛋 14个", "鸡腿 1.5kg", "大米 2kg",
                                  "土豆 1kg", "胡萝卜 700g", "牛腩 1kg", "面条 1袋", "番茄 14个", "青菜 900g"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "牛肉煎蛋全麦三明治", "kcal": 650,
                     "ingredients": ["全麦面包 2片", "卤牛肉 60g", "鸡蛋 2个", "牛奶 300ml"]},
                    {"meal": "午餐", "name": "糖醋里脊配米饭", "kcal": 950,
                     "ingredients": ["猪里脊 180g", "米饭 220g", "西兰花 120g", "胡萝卜 60g"]},
                    {"meal": "晚餐", "name": "香煎鸡腿配红薯泥", "kcal": 880,
                     "ingredients": ["鸡腿 220g", "红薯 200g", "芦笋 100g", "橄榄油 8ml"]},
                ],
                "shopping_list": ["全麦面包 1袋", "卤牛肉 500g", "鸡蛋 14个", "牛奶 2.1L", "猪里脊 1.3kg",
                                  "大米 2kg", "西兰花 1kg", "胡萝卜 500g", "鸡腿 1.6kg", "红薯 1.5kg", "芦笋 700g"],
            },
            {
                "recipes": [
                    {"meal": "早餐", "name": "燕麦坚果能量碗配香蕉", "kcal": 630,
                     "ingredients": ["即食燕麦 60g", "混合坚果 25g", "香蕉 1根", "低脂牛奶 350ml"]},
                    {"meal": "午餐", "name": "清炖牛腩面配卤蛋", "kcal": 980,
                     "ingredients": ["牛腩 150g", "面条 120g", "青菜 100g", "卤蛋 1个"]},
                    {"meal": "晚餐", "name": "虾仁豆腐煲配米饭", "kcal": 870,
                     "ingredients": ["虾仁 150g", "嫩豆腐 250g", "混合杂蔬 100g", "米饭 200g"]},
                ],
                "shopping_list": ["即食燕麦 1包", "混合坚果 250g", "香蕉 7根", "低脂牛奶 2.5L", "牛腩 1.1kg",
                                  "面条 1kg", "青菜 700g", "鸡蛋 7个", "虾仁 1.1kg", "嫩豆腐 7盒", "大米 2kg"],
            },
        ],
    },
}


# ---------------------------------------------------------------
# 过敏原 / 疾病饮食禁忌校验
#
# 规则来源分两路，是刻意的分工：
#   1) 疾病禁忌 → Neo4j 知识图谱的 (食物)-[:禁忌]->(疾病) 直接关系
#      营养学规则应该由图谱维护：新增一条边即刻生效，无需改代码、无需发版，
#      还能顺带带上「为什么禁」的说明（r.note）。
#   2) 过敏原   → 本文件的词表
#      过敏是"具体食材写法"级的事实（「鲈鱼」「基围虾」都要算海鲜），
#      枚举成图谱边反而臃肿，词表更直接。
# 图谱不可用时静默降级为兜底词表，不影响出计划。
# ---------------------------------------------------------------
ALLERGEN_KEYWORDS = {
    "海鲜": ["虾", "鱼", "蟹", "贝", "牡蛎", "蛤", "鱿鱼", "海参", "紫菜", "海带", "鲈", "鳕", "三文"],
    "乳糖": ["牛奶", "酸奶", "奶酪", "奶油", "芝士"],
    "坚果": ["坚果", "花生", "核桃", "杏仁", "腰果", "芝麻", "亚麻籽", "奇亚籽"],
    "蛋类": ["鸡蛋", "蛋黄", "蛋清", "蛋"],
    "麸质": ["全麦", "面包", "面条", "馒头", "小麦", "卷饼", "面"],
    "大豆": ["黄豆", "豆浆", "豆腐", "豆干", "毛豆", "豆"],
    "芒果": ["芒果"],
}
# 图谱不可用时的兜底词表（覆盖度远低于图谱，仅保证服务不崩）
DISEASE_AVOID_KEYWORDS = {
    "高血压": ["腌制", "咸菜", "腊肉", "咸鱼", "培根", "火腿", "香肠"],
    "糖尿病": ["含糖", "蜂蜜", "糖浆", "白砂糖"],
    "高血脂": ["动物内脏", "猪肝", "油炸", "肥肉", "五花"],
    "痛风": ["动物内脏", "浓汤", "啤酒"],
}
SUBSTITUTE_HINTS = {
    "海鲜": "可替换为鸡胸肉、瘦牛肉或豆腐",
    "乳糖": "可替换为无糖豆浆或燕麦奶",
    "坚果": "可替换为南瓜籽或直接去掉坚果",
    "蛋类": "可替换为豆腐或瘦肉类蛋白",
    "麸质": "可替换为糙米、藜麦或米粉",
    "大豆": "可替换为鸡蛋或瘦肉",
    "芒果": "可替换为苹果或猕猴桃",
}
# 疾病禁忌的替代方向（图谱 r.note 说明"为什么禁"，这里给"换成什么"）
DISEASE_SUBSTITUTE = {
    "高血压": "改为清蒸/水煮低盐做法，用葱姜蒜、柠檬、香料代替盐调味",
    "2型糖尿病": "改用低 GI 主食（糙米/燕麦/杂粮），不加糖",
    "高血脂": "改用清蒸鱼、鸡胸肉或豆制品替代",
    "冠心病": "改用橄榄油清炒，或用深海鱼替代",
    "痛风": "改用鸡蛋、低脂奶制品等低嘌呤蛋白来源",
}

# 疾病描述 → 图谱标准名 的对齐缓存 {(原文): (时间戳, [标准名])}
_DISEASE_ALIGN_CACHE: dict = {}


def _aligned_diseases(conditions: str) -> list[str]:
    """画像里的疾病描述 → 图谱标准疾病名（带 60 秒缓存 + 静默降级）。"""
    key = (conditions or "").strip()
    if key in ("", "无"):
        return []
    hit = _DISEASE_ALIGN_CACHE.get(key)
    if hit and (time.time() - hit[0]) < 60:
        return hit[1]
    names: list[str] = []
    try:
        from app.utils.neo4j_client import get_neo4j
        names = get_neo4j()._match_diseases(key, limit=6)
    except Exception as e:  # noqa: BLE001
        logger.warning("疾病描述对齐图谱失败，退化为兜底词表: %s", e)
    _DISEASE_ALIGN_CACHE[key] = (time.time(), names)
    return names


def _graph_hits(text: str, conditions: str, relation: str) -> list[dict]:
    """查图谱直接关系（relation = '禁忌' / '适宜'）命中的食物。"""
    diseases = _aligned_diseases(conditions)
    if not diseases:
        return []
    try:
        from app.utils.neo4j_client import get_neo4j
        rows = get_neo4j().find_food_relations(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("图谱食物关系查询失败: %s", e)
        return []
    out = []
    for r in rows:
        if r["relation"] != relation or r["disease"] not in diseases:
            continue
        out.append({
            "reason": f"{r['disease']}饮食禁忌",
            "keyword": r["matched"],
            "food": r["food"],
            "note": r["note"],
            "substitute": DISEASE_SUBSTITUTE.get(r["disease"], "建议咨询营养师调整做法"),
        })
    return out


def _matched_terms(text: str, allergies: str, conditions: str) -> list[dict]:
    """返回文本命中的冲突项 [{reason, keyword, substitute}]。

    疾病禁忌优先走图谱，图谱没给出结论时再叠加兜底词表，按关键词去重。
    """
    hits: list[dict] = []
    allergy_text = (allergies or "").replace("、", " ").replace("，", " ").replace(",", " ")
    for allergen, keywords in ALLERGEN_KEYWORDS.items():
        if allergen not in allergy_text:
            continue
        for kw in keywords:
            if kw in text:
                hits.append({"reason": f"{allergen}过敏", "keyword": kw,
                             "substitute": SUBSTITUTE_HINTS.get(allergen, "")})
                break

    hits.extend(_graph_hits(text, conditions, "禁忌"))

    # 兜底：图谱未命中时用代码词表补足（覆盖度低，但保证离线可用）
    graph_kws = {h["keyword"] for h in hits}
    condition_text = conditions or ""
    for disease, keywords in DISEASE_AVOID_KEYWORDS.items():
        if disease not in condition_text:
            continue
        for kw in keywords:
            if kw in text and kw not in graph_kws:
                hits.append({"reason": f"{disease}饮食禁忌", "keyword": kw,
                             "substitute": "建议替换为低盐/低脂做法"})
                break
    return hits


def _graph_suitable_foods(recipes, conditions: str) -> list[str]:
    """列出这套菜单里命中图谱「适宜」关系的食物（用于优选更贴合病情的菜单）。"""
    diseases = _aligned_diseases(conditions)
    if not diseases:
        return []
    try:
        from app.utils.neo4j_client import get_neo4j
        client = get_neo4j()
    except Exception:  # noqa: BLE001
        return []
    foods: list[str] = []
    for recipe in recipes or []:
        text = " ".join([str(recipe.get("name", ""))] +
                        [str(i) for i in (recipe.get("ingredients") or [])])
        foods.extend(r["food"] for r in client.find_food_relations(text)
                     if r["relation"] == "适宜" and r["disease"] in diseases)
    return list(dict.fromkeys(foods))


def _safety_conflicts(recipes, allergies: str = "", conditions: str = "") -> list[dict]:
    """逐道菜检测过敏原与疾病禁忌，返回冲突清单。

    画像未填过敏/疾病（或填「无」）时直接返回空，不做任何拦截。
    """
    if (allergies or "").strip() in ("", "无") and (conditions or "").strip() in ("", "无"):
        return []
    conflicts = []
    for recipe in recipes or []:
        text = " ".join([str(recipe.get("name", ""))] +
                        [str(i) for i in (recipe.get("ingredients") or [])])
        hits = _matched_terms(text, allergies, conditions)
        if hits:
            conflicts.append({
                "meal": recipe.get("meal", ""),
                "recipe": recipe.get("name", ""),
                "hits": hits,
                "suggestion": "；".join(
                    f"含「{h['keyword']}」({h['reason']})，{h['substitute'] or '建议替换'}"
                    for h in hits
                ),
            })
    return conflicts


def _pick_plan_set(target: float, variant: int = 0,
                   allergies: str = "", conditions: str = "") -> dict:
    """按目标热量选档，并按 variant 在档内轮换菜单。

    每档内置多套等价菜单，重新生成时轮换到下一套，
    避免"点重新生成却毫无变化"的观感。

    画像中带过敏/疾病时，优先挑选**不含冲突食材**的那一套，
    从源头避免"海鲜过敏却排了虾仁"这类问题；全部套都有冲突时，
    退回按 variant 轮换并在 safety_notes 中提示。
    """
    tier = "low" if target < 1750 else ("med" if target <= 2200 else "high")
    spec = PLAN_SETS[tier]
    menus = spec["menus"]
    idx = int(variant) % len(menus)

    # 从 variant 起点开始轮转，优先返回无冲突的菜单
    if (allergies or "").strip() not in ("", "无") or (conditions or "").strip() not in ("", "无"):
        scored = [(i, len(_safety_conflicts(menus[i]["recipes"], allergies, conditions)))
                  for i in range(len(menus))]
        clean = sorted(i for i, n in scored if n == 0)
        if clean:
            # 有疾病画像时，把命中图谱「适宜」关系更多的菜单排在前面，
            # 但只在靠前的候选池内轮转——既更贴合病情，又保留「换一套」的可选性
            if len(clean) > 1 and (conditions or "").strip() not in ("", "无"):
                ranked = sorted(((i, len(_graph_suitable_foods(menus[i]["recipes"], conditions)))
                                 for i in clean), key=lambda x: -x[1])
                pool = [i for i, _ in ranked[:max(2, (len(clean) + 1) // 2)]]
                idx = pool[idx % len(pool)]
            else:
                # 在无冲突的套之间按 variant 轮转，保留「随机换一套」的体验
                idx = clean[idx % len(clean)]
        else:
            # 全都含冲突食材时，选冲突最少的那套并在 safety_notes 里提示替代方案
            idx = min(scored, key=lambda item: item[1])[0]

    menu = menus[idx]
    return {
        "tier": tier,
        "label": spec["label"],
        "menu_index": idx,
        "menu_total": len(menus),
        "recipes": menu["recipes"],
        "shopping_list": menu["shopping_list"],
        "conflicts": _safety_conflicts(menu["recipes"], allergies, conditions),
        "graph_suitable": _graph_suitable_foods(menu["recipes"], conditions),
    }


def _goal_calories(target_kind: str) -> float:
    """按目标类型做热量修正：减脂 -400 / 增肌 +300 / 保持 0。"""
    if "减" in target_kind or "瘦" in target_kind:
        return -400
    if "增" in target_kind or "肌" in target_kind:
        return 300
    return 0


def build_plan(db: Session, user_id: str, goal: str = "", days: int = 7, variant: int = 0) -> dict:
    """生成一份个性化饮食计划，返回可直接序列化的 dict。"""
    from app.models.assistant import UserProfile
    from app.models.meal import MealRecord

    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    goal = (goal or (profile.goal if profile else "") or "保持健康").strip()

    basis_parts: list[str] = []
    target = 2000.0
    if profile and profile.weight_kg and profile.height_cm and profile.age:
        sex = profile.sex or "其他"
        # Mifflin-St Jeor 基础代谢估算 + 轻度活动系数
        bmr = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age + (5 if sex == "男" else -161)
        daily_burn = bmr * 1.375
        target = daily_burn + _goal_calories(goal)
        basis_parts.append(
            f"依据画像（{sex} · {profile.age}岁 · {profile.height_cm}cm · {profile.weight_kg}kg）估算基础代谢约 {int(bmr)} kcal")
        basis_parts.append(f"目标“{goal}”，按轻度活动折算日耗 {int(daily_burn)} kcal，本期目标热量 {int(target)} kcal")
    else:
        basis_parts.append("暂未完善健康画像，按通用 2000 kcal 目标生成（完善后计划将更贴合个人情况）")

    # 近 7 天实际摄入校准
    recent = (
        db.query(MealRecord)
        .filter(MealRecord.user_id == user_id, MealRecord.meal_date >= (datetime.now() - timedelta(days=7)).date())
        .all()
    )
    if recent:
        avg = sum(r.calories or 0 for r in recent) / len(recent)
        basis_parts.append(f"近 7 天日均实际摄入 {int(avg)} kcal")
        if avg > target + 150:
            basis_parts.append(f"与目标差距约 {int(avg - target)} kcal，本期已下调总热量并增加高饱腹食材")
        elif avg < target - 150:
            basis_parts.append("当前摄入偏低，本期适度上调热量以避免代谢下降")

    allergies = (profile.allergies if profile else "") or ""
    conditions = (profile.conditions if profile else "") or ""
    chosen = _pick_plan_set(target, variant, allergies=allergies, conditions=conditions)
    recipes = [{**r, "portion_note": chosen["label"]} for r in chosen["recipes"]]

    # 过敏原/疾病禁忌：能避让的已在选套时避开，剩余冲突给出替代提示
    conflicts = chosen.get("conflicts") or []
    if conflicts:
        basis_parts.append(
            f"已按健康画像做过敏原/知识图谱禁忌校验，有 {len(conflicts)} 处需注意（见安全提示）")
    elif allergies.strip() not in ("", "无") or conditions.strip() not in ("", "无"):
        basis_parts.append("已按健康画像做过敏原/知识图谱禁忌校验，本套菜单无冲突食材")
    suitable_foods = chosen.get("graph_suitable") or []
    if suitable_foods:
        basis_parts.append(
            f"知识图谱针对「{conditions}」推荐食材命中 {len(suitable_foods)} 项："
            + "、".join(suitable_foods[:6]))

    return {
        "user_id": user_id,
        "goal": goal,
        "days": days,
        "calories_target": int(target),
        "set_label": chosen["label"],
        "menu_index": chosen["menu_index"],
        "menu_total": chosen["menu_total"],
        "personalization": "；".join(basis_parts),
        "recipes": recipes,
        "shopping_list": chosen["shopping_list"],
        "safety_notes": conflicts,
        "graph_suitable": suitable_foods,
    }


def _menu_index_of(set_label: str, recipes) -> tuple[int, int]:
    """根据档位标签 + 首道菜名反查菜单序号。

    menu_index 不是数据库字段（避免改表），落库后从内容反推，
    这样历史记录也能正确显示「方案 N/M」。
    """
    first = ""
    for r in (recipes or []):
        if isinstance(r, dict) and r.get("name"):
            first = r["name"]
            break
    for spec in PLAN_SETS.values():
        if spec["label"] != set_label:
            continue
        menus = spec["menus"]
        for i, m in enumerate(menus):
            head = m["recipes"][0]["name"] if m.get("recipes") else ""
            if head and head == first:
                return i, len(menus)
        return 0, len(menus)
    return 0, 1


def serialize_plan(record) -> dict:
    """MealPlan ORM → 前端结构（含审核状态）。"""
    menu_index, menu_total = _menu_index_of(record.set_label or "", record.recipes)
    return {
        "plan_id": record.id,
        "user_id": record.user_id,
        "goal": record.goal,
        "days": record.days,
        "calories_target": record.calories_target,
        "set_label": record.set_label or "",
        "menu_index": menu_index,
        "menu_total": menu_total,
        "personalization": record.personalization or "",
        "recipes": record.recipes or [],
        "shopping_list": record.shopping_list or [],
        "source": record.source or "ai",
        "status": record.status or "pending_review",
        "review_note": record.review_note or "",
        "reviewed_by": record.reviewed_by or "",
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def upsert_plan(db: Session, user_id: str, goal: str = "", days: int = 7, variant: int = 0) -> dict:
    """生成个性化计划并落库（每个用户保留最新一份）。

    重新生成 = 新的 AI 版本 → 状态回到 pending_review，等待管理端审核。
    """
    from app.models.plan import MealPlan

    plan = build_plan(db, user_id, goal, days, variant)
    record = (db.query(MealPlan)
              .filter_by(user_id=user_id)
              .order_by(MealPlan.id.desc())
              .first())
    if record is None:
        record = MealPlan(user_id=user_id)
        db.add(record)
    record.goal = plan["goal"]
    record.days = plan["days"]
    record.calories_target = plan["calories_target"]
    record.set_label = plan["set_label"]
    record.personalization = plan["personalization"]
    record.recipes = plan["recipes"]
    record.shopping_list = plan["shopping_list"]
    record.source = "ai"
    record.status = "pending_review"
    record.review_note = ""
    record.reviewed_by = ""
    record.reviewed_at = None
    db.commit()
    db.refresh(record)
    data = serialize_plan(record)
    # 图谱校验结果按生成时的情况一并返回（不落库，避免改表结构）
    data["safety_notes"] = plan.get("safety_notes", [])
    data["graph_suitable"] = plan.get("graph_suitable", [])
    return data


def get_current_plan(db: Session, user_id: str) -> dict | None:
    """用户当前最新计划（含审核状态），没有则返回 None。

    安全提示按当前画像实时重算（不落库，避免改表结构），
    这样用户后补了过敏/疾病信息，旧计划也会立刻显示冲突提示。
    """
    from app.models.assistant import UserProfile
    from app.models.plan import MealPlan

    record = (db.query(MealPlan)
              .filter_by(user_id=user_id)
              .order_by(MealPlan.id.desc())
              .first())
    if not record:
        return None
    data = serialize_plan(record)
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    allergies = (profile.allergies if profile else "") or ""
    conditions = (profile.conditions if profile else "") or ""
    data["safety_notes"] = _safety_conflicts(record.recipes or [], allergies, conditions)
    data["graph_suitable"] = _graph_suitable_foods(record.recipes or [], conditions)
    return data
