/**
 * 食谱配图：按菜名/食材关键词挑一张真实食物照片。
 *
 * 图片来源：Pexels（Pexels License —— 免费使用、可商用、无需署名）
 * 已下载到本地 src/assets/food/，避免依赖网络（答辩断网也能正常显示）。
 *   15110875 燕麦莓果早餐 · 19573136 早餐碗 · 2402506 水煮蛋吐司
 *   25315523 鸡胸沙拉 · 27039877 虾仁豆腐汤 · 31683415 三文鱼西兰花
 *   19725453 烤鱼配米饭 · 14537684 烤时蔬 · 10506640 米饭主食
 */
import oat from './assets/food/food-oat.jpg'
import breakfast from './assets/food/food-breakfast.jpg'
import egg from './assets/food/food-egg.jpg'
import salad from './assets/food/food-salad.jpg'
import soup from './assets/food/food-tofu.jpg'
import salmon from './assets/food/food-salmon.jpg'
import fish from './assets/food/food-fish.jpg'
import veggie from './assets/food/food-veggie.jpg'
import staple from './assets/food/food-staple.jpg'

// 关键词规则：从上往下匹配，命中即用（越具体的放越前）
const RULES = [
  { keys: ['燕麦', '麦片', '酸奶', '牛奶', '奇亚', '莓', '蓝莓', '草莓', '香蕉', '酸奶杯'], img: oat },
  { keys: ['沙拉', '藜麦', '生菜', '油醋', '轻食', '鸡胸沙拉'], img: salad },
  { keys: ['汤', '煲', '豆腐', '虾', '丝瓜', '冬瓜', '菌菇汤', '羹'], img: soup },
  { keys: ['三文鱼', '鲑鱼'], img: salmon },
  { keys: ['蛋', '煎蛋', '水煮蛋', '蒸蛋', '蛋饼'], img: egg },
  { keys: ['鱼', '鲈鱼', '巴沙', '鳕鱼', '带鱼', '龙利鱼'], img: fish },
  { keys: ['米饭', '杂粮饭', '糙米', '荞麦', '面', '红薯', '紫薯', '玉米', '土豆', '主食', '粥'], img: staple },
  { keys: ['蔬菜', '时蔬', '西兰花', '菠菜', '木耳', '彩椒', '芦笋', '青菜', '番茄', '黄瓜', '菇'], img: veggie },
]

// 按餐次兜底
const MEAL_FALLBACK = { 早餐: breakfast, 午餐: salad, 晚餐: fish, 加餐: oat }

/**
 * 给一份食谱挑配图。
 * @param {{name?: string, ingredients?: string[], meal?: string}} recipe
 */
export function pickFoodImage(recipe) {
  const text = [recipe?.name || '', ...(recipe?.ingredients || [])].join(' ')
  for (const rule of RULES) {
    if (rule.keys.some((k) => text.includes(k))) return rule.img
  }
  return MEAL_FALLBACK[recipe?.meal] || breakfast
}

export const FOOD_IMAGES = { oat, breakfast, egg, salad, soup, salmon, fish, veggie, staple }
