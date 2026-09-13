<script setup>
import { computed, onMounted, ref } from 'vue'
import { generateMealPlan, getCurrentPlan } from '../api'
const currentUser = JSON.parse(localStorage.getItem('healthybot_user') || '{"id":"user","name":"林晓晴"}')
const week = ref('本周计划'), checked = ref([]), loading = ref(true), error = ref('')
const regenerating = ref(false)   // 「重新生成」按钮加载态
const variant = ref(0)            // 当前菜单序号（用于同档位轮换）
const plan = ref({ recipes: [], shopping_list: [] })
const fromAi = ref(false)
const regen = ref(false)
import { pickFoodImage } from '../food-images'
const progress = computed(() => plan.value.shopping_list.length ? Math.round(checked.value.length / plan.value.shopping_list.length * 100) : 0)

// —— 完整购物清单：按食材类别分组，方便按区采买 ——
const SHOP_CATS = [
  { name: '肉禽蛋 / 水产', icon: '🥩', keys: ['鸡胸', '鸡腿', '鸡肉', '牛肉', '猪', '里脊', '虾', '鱼', '三文鱼', '鳕鱼', '龙利', '蛋'] },
  { name: '乳品 / 豆制品', icon: '🥛', keys: ['酸奶', '牛奶', '豆腐', '豆浆', '奶酪', '豆干', '豆'] },
  { name: '主食 / 谷物', icon: '🌾', keys: ['燕麦', '麦片', '藜麦', '糙米', '米', '面', '荞麦', '红薯', '紫薯', '玉米', '奇亚籽', '全麦'] },
  { name: '蔬菜 / 水果', icon: '🥬', keys: ['番茄', '西兰花', '生菜', '菠菜', '蓝莓', '草莓', '香蕉', '苹果', '黄瓜', '彩椒', '青椒', '芦笋', '木耳', '菇', '洋葱', '胡萝卜', '柠檬', '南瓜', '青菜', '油麦菜', '芹菜'] },
  { name: '调味 / 其他', icon: '🧂', keys: ['油', '醋', '酱油', '盐', '蜂蜜', '坚果', '核桃', '杏仁', '芝麻', '酱', '味'] },
]
const OTHER_CAT = { name: '其他', icon: '🛒' }
function shopCategory(text) {
  const t = String(text || '')
  for (const c of SHOP_CATS) if (c.keys.some((k) => t.includes(k))) return c
  return OTHER_CAT
}
/** 按类别归并购物清单，保留原始下标以便勾选状态对应 */
const groupedShopping = computed(() => {
  const groups = SHOP_CATS.map((c) => ({ name: c.name, icon: c.icon, items: [] }))
  const other = { name: OTHER_CAT.name, icon: OTHER_CAT.icon, items: [] }
  plan.value.shopping_list.forEach((text, index) => {
    const cat = shopCategory(text)
    const bucket = groups.find((g) => g.name === cat.name) || other
    bucket.items.push({ text, index })
  })
  return [...groups, other].filter((g) => g.items.length)
})
async function loadPlan(force = false) {
  loading.value = true
  error.value = ''
  // AI 智能问答刚生成的计划：直接展示草稿，不再请求后端
  if (!force && !regen.value) {
    try {
      const draft = JSON.parse(localStorage.getItem('healthybot_plan_draft') || 'null')
      if (draft && draft.recipes?.length) {
        plan.value = draft
        fromAi.value = Boolean(draft.generated_at)
        loading.value = false
        return
      }
    } catch { /* ignore */ }
  }
  // 其次读服务端「当前计划」（含审核状态与营养师备注）
  // force=true（点「重新生成」）时跳过，否则会读到刚才那份、看起来毫无变化
  if (!force) {
    try {
      const cur = await getCurrentPlan(currentUser.id)
      if (cur.data && cur.data.recipes?.length) {
        plan.value = cur.data
        variant.value = Number(cur.data.menu_index) || 0
        fromAi.value = false
        loading.value = false
        return
      }
    } catch { /* 无当前计划则走生成 */ }
  }
  try { const resp = await generateMealPlan({ user_id: currentUser.id, goal: '保持健康', days: 7, variant: variant.value }); plan.value = resp.data || plan.value; variant.value = Number(resp.data?.menu_index) || variant.value; fromAi.value = false; localStorage.removeItem('healthybot_plan_draft') } catch (e) { error.value = e.message || '计划加载失败'; plan.value = { calories_target: 2000, set_label: '演示档', personalization: '连接异常，已显示演示计划；完善健康画像后即可生成个性化方案', recipes: [{ meal: '早餐', name: '牛油果鸡蛋全麦吐司', kcal: 382, ingredients: [] }, { meal: '午餐', name: '藜麦鸡胸能量碗', kcal: 568, ingredients: [] }, { meal: '晚餐', name: '番茄虾仁豆腐煲', kcal: 446, ingredients: [] }], shopping_list: ['鸡胸肉 300g', '藜麦 150g', '牛油果 2个', '西兰花 1颗'] } } finally { loading.value = false } }
/**
 * 随机换一套：从同档位菜单库中随机挑一个「不等于当前」的方案。
 * 菜单库每档 5 套（plan_service.PLAN_SETS），后端按 variant % 5 取对应套。
 */
async function regenPlan() {
  if (regenerating.value) return
  regenerating.value = true
  try {
    const total = Number(plan.value.menu_total) || 5
    const cur = Number(plan.value.menu_index) || 0
    let next = cur
    while (total > 1 && next === cur) next = Math.floor(Math.random() * total)
    variant.value = next
    regen.value = true
    fromAi.value = false
    checked.value = []                                  // 换菜单后原勾选已不对应
    localStorage.removeItem('healthybot_plan_draft')    // 丢弃 AI 问答草稿，避免又被读回来
    await loadPlan(true)
  } finally {
    regenerating.value = false
  }
}
function toggle(i) { checked.value.includes(i) ? checked.value = checked.value.filter(x => x !== i) : checked.value.push(i) }
onMounted(loadPlan)
</script>
<template><div class="page-heading"><div><span class="overline">PLAN · EAT WITH INTENTION</span><h1>饮食计划</h1><p>按照你的目标和习惯，安排好这一周的每一餐。</p></div><div class="segmented"><button :class="{active: week === '本周计划'}" @click="week = '本周计划'">本周计划</button><button :class="{active: week === '购物清单'}" @click="week = '购物清单'">购物清单</button></div></div><div v-if="error" class="alert">{{ error }}</div><div class="plan-hero photo-host"><div class="photo-bg ph-hero-2 mask-light" aria-hidden="true"></div><div><span class="overline">{{ fromAi ? 'GENERATED BY AI · 智能问答生成' : 'THIS WEEK · 7 DAYS' }}</span><h2>{{ plan.set_label || '均衡营养档' }} · 目标 {{ plan.calories_target || '—' }} kcal<span v-if="plan.menu_total > 1" class="menu-badge">方案 {{ (plan.menu_index || 0) + 1 }}/{{ plan.menu_total }}</span></h2><p>{{ plan.personalization || 'AI 根据你的目标生成菜单与购物清单，随时可以重新生成。' }}</p><div class="plan-status"><span v-if="plan.status === 'pending_review'" class="st pending">⏳ 待营养师审核</span><span v-else-if="plan.status === 'approved'" class="st approved">✓ 营养师已确认</span><span v-else-if="plan.status === 'rejected'" class="st rejected">✕ 已驳回，建议重新生成</span><span v-if="plan.source === 'manual'" class="st manual">营养师已调整</span></div><p v-if="plan.review_note" class="review-note">💬 营养师备注：{{ plan.review_note }}</p></div><div class="plan-hero-right"><button class="btn outline-btn" :disabled="regenerating || loading" @click="regenPlan" title="从同档位菜单中随机换一套（不与当前重复，并自动避开过敏原）">{{ regenerating ? '生成中…' : '🎲 随机换一套' }}</button><div class="progress-ring"><strong>{{ progress }}%</strong><span>清单完成</span></div></div></div><div v-if="week === '本周计划'" class="plan-grid"><section class="recipe-list"><div v-if="plan.safety_notes && plan.safety_notes.length" class="safety-card"><div class="safety-head">⚠ 过敏原 / 图谱禁忌提醒（{{ plan.safety_notes.length }} 处）</div><p class="safety-sub">已优先挑选不含冲突食材的菜单，以下菜品仍需留意或替换：</p><div v-for="n in plan.safety_notes" :key="n.recipe" class="safety-row"><b>{{ n.meal }} · {{ n.recipe }}</b><span>{{ n.suggestion }}</span></div></div><div v-if="plan.graph_suitable && plan.graph_suitable.length" class="graph-card"><div class="graph-head">🕸️ 知识图谱适配食材（命中 {{ plan.graph_suitable.length }} 项）</div><p class="graph-sub">按图谱「疾病 ← 营养素 ← 食物」推荐链路，本套菜单已优先选用这些食材：</p><span v-for="f in plan.graph_suitable" :key="f" class="g-tag">{{ f }}</span></div><div class="section-label">今日菜单 <span>{{ plan.recipes.length }} 餐 · {{ plan.recipes.reduce((sum, item) => sum + (item.kcal || 0), 0) }} kcal</span></div><div v-if="loading" class="loading-text">正在生成你的计划…</div><article v-for="(recipe, index) in plan.recipes" :key="recipe.meal" class="recipe-card"><img class="photo-hidden-in-dark" :src="pickFoodImage(recipe)" alt="今日食谱" /><div class="recipe-info"><span class="meal-label">{{ recipe.meal }}</span><h3>{{ recipe.name }}</h3><p>{{ recipe.ingredients?.join(' · ') || '根据你的目标搭配' }}</p></div><span class="recipe-kcal">{{ recipe.kcal }} <small>kcal</small></span><button class="more-btn">•••</button></article></section><aside class="shopping-card photo-host"><span class="photo-corner ph-card-3" aria-hidden="true"></span><div class="shopping-top"><div><span class="overline">SHOPPING LIST</span><h3>本周购物清单</h3></div><span class="progress-pill">{{ progress }}%</span></div><p>买齐这些食材，周末就不用临时决定吃什么了。</p><div class="shopping-progress"><span :style="{width: progress + '%'}"></span></div><label v-for="(item, index) in plan.shopping_list" :key="item" class="check-item"><input type="checkbox" :checked="checked.includes(index)" @change="toggle(index)" /><span>{{ item }}</span></label><button class="btn outline-btn full" @click="week = '购物清单'">查看完整清单 ↗</button></aside></div><section v-else class="shopping-full"><div class="shopping-full-head"><div><span class="overline">SHOPPING LIST · FULL</span><h2>{{ plan.set_label || '本周' }} · 完整购物清单</h2><p>共 {{ plan.shopping_list.length }} 项食材，已备齐 {{ checked.length }} 项。按类别整理，照着买就行。</p></div><div class="progress-ring big"><strong>{{ progress }}%</strong><span>已完成</span></div></div><div v-if="!plan.shopping_list.length" class="empty-text">暂无购物清单，先去生成一份饮食计划。</div><div v-else class="shopping-groups"><div v-for="group in groupedShopping" :key="group.name" class="shopping-group"><div class="group-head"><span class="group-icon" aria-hidden="true">{{ group.icon }}</span><h4>{{ group.name }}</h4><span class="group-count">{{ group.items.length }} 项</span></div><label v-for="it in group.items" :key="it.index" class="check-item"><input type="checkbox" :checked="checked.includes(it.index)" @change="toggle(it.index)" /><span :class="{ 'item-done': checked.includes(it.index) }">{{ it.text }}</span></label></div></div><div class="shopping-actions"><button class="btn ghost" @click="checked = []">清空勾选</button><button class="btn outline-btn" @click="week = '本周计划'">← 返回本周计划</button></div></section></template>
<style scoped>.plan-hero-right { display: flex; flex-direction: column; align-items: center; gap: 10px; } .btn.outline-btn { font-size: 13px; padding: 6px 12px; }
.plan-status { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.st { font-size: 12px; padding: 3px 10px; border-radius: 999px; }
.st.pending { background: #fff7e6; color: #b45309; }
.st.approved { background: #dcfce7; color: #15803d; }
.st.rejected { background: #fee2e2; color: #b91c1c; }
.st.manual { background: #eef7fb; color: #0e7490; }
.review-note { font-size: 12.5px; color: #0e7490; background: #f4fafd; border-radius: 8px; padding: 6px 10px; margin-top: 8px; }

/* —— 完整购物清单视图 —— */
.shopping-full { display: grid; gap: 16px; }
.shopping-full-head {
  display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--card);
  padding: 20px 22px; box-shadow: var(--shadow);
}
.shopping-full-head h2 { margin: 6px 0 6px; font-size: 20px; }
.shopping-full-head p { margin: 0; font-size: 13px; color: var(--text-2); }
.progress-ring.big { width: 92px; height: 92px; flex-shrink: 0; }
.progress-ring.big strong { font-size: 20px; }
.progress-ring.big span { font-size: 11px; }
.shopping-groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.shopping-group {
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--card);
  padding: 14px 16px 10px; box-shadow: var(--shadow);
}
.group-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.group-icon { font-size: 18px; line-height: 1; }
.group-head h4 { margin: 0; font-size: 14px; flex: 1; }
.group-count { font-size: 12px; color: var(--text-2); }
.shopping-group .check-item { display: flex; align-items: center; gap: 9px; padding: 7px 0; }
.item-done { text-decoration: line-through; opacity: .55; }
.shopping-actions { display: flex; justify-content: flex-end; gap: 10px; }

/* —— 方案序号标记 & 生成中按钮 —— */
.menu-badge {
  display: inline-block; margin-left: 10px; vertical-align: 2px;
  font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px;
  background: rgba(95, 158, 63, .14); color: var(--primary);
}
html.dark .menu-badge { background: rgba(77, 227, 255, .14); color: #8fe7ff; }
.btn.outline-btn:disabled { opacity: .6; cursor: not-allowed; }

/* —— 过敏原 / 禁忌提醒卡（由健康画像 + 图谱校验生成）—— */
.safety-card {
  border: 1px solid rgba(196, 74, 58, .45); background: rgba(253, 232, 228, .55);
  border-radius: var(--radius); padding: 12px 14px; margin-bottom: 14px;
}
.safety-head { font-size: 13.5px; font-weight: 600; color: #a13d2d; margin-bottom: 4px; }
.safety-sub { margin: 0 0 8px; font-size: 12.5px; color: var(--text-2); }
.safety-row { display: flex; flex-wrap: wrap; gap: 6px; padding: 5px 0; font-size: 12.5px; border-top: 1px dashed rgba(196, 74, 58, .25); }
.safety-row b { color: var(--text); font-weight: 600; }
.safety-row span { color: #a13d2d; }
html.dark .safety-card { background: rgba(248, 113, 92, .1); border-color: rgba(248, 113, 92, .35); }
html.dark .safety-head, html.dark .safety-row span { color: #fca590; }

/* —— 知识图谱适配食材卡（图谱正向推荐链路命中）—— */
.graph-card {
  border: 1px solid rgba(34, 160, 107, .4); background: rgba(226, 246, 236, .5);
  border-radius: var(--radius); padding: 12px 14px; margin-bottom: 14px;
}
.graph-head { font-size: 13.5px; font-weight: 600; color: #1a7d53; margin-bottom: 4px; }
.graph-sub { margin: 0 0 8px; font-size: 12.5px; color: var(--text-2); }
.g-tag {
  display: inline-block; padding: 3px 10px; margin: 0 6px 6px 0;
  border-radius: 12px; font-size: 12px; line-height: 1.5;
  background: rgba(34, 160, 107, .14); color: #1a7d53;
}
html.dark .graph-card { background: rgba(34, 160, 107, .12); border-color: rgba(34, 160, 107, .38); }
html.dark .graph-head { color: #6ee7a8; }
html.dark .g-tag { background: rgba(34, 160, 107, .22); color: #6ee7a8; }
</style>
