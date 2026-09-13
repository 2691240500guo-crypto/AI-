<script setup>
import { computed, onMounted, ref } from 'vue'
import { getPlanReviewQueue, reviewPlan, updatePlan } from '../api'

const tab = ref('pending_review')
const plans = ref([])
const loading = ref(true)
const error = ref('')
const successMsg = ref('')
const expanded = ref(null)

const tabs = [
  { key: 'pending_review', label: '待审核' },
  { key: 'approved', label: '已通过' },
  { key: 'rejected', label: '已驳回' },
  { key: 'all', label: '全部' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await getPlanReviewQueue(tab.value)
    plans.value = (resp.data || []).map((p) => ({
      ...p,
      shopping_text: (p.shopping_list || []).join('\n'),
    }))
  } catch (e) {
    error.value = e.message || '计划队列加载失败'
  } finally {
    loading.value = false
  }
}
function switchTab(key) { tab.value = key; expanded.value = null; load() }
function flash(msg) {
  successMsg.value = msg
  setTimeout(() => { successMsg.value = '' }, 2400)
}
function toggleExpand(p) { expanded.value = expanded.value === p.plan_id ? null : p.plan_id }

function profileText(p) {
  const pr = p.profile
  if (!pr) return '无画像'
  const parts = [pr.sex, pr.age ? `${pr.age}岁` : null, pr.height_cm ? `${pr.height_cm}cm` : null, pr.weight_kg ? `${pr.weight_kg}kg` : null].filter(Boolean)
  return `${pr.user_name || p.user_id} · ${parts.join(' / ') || '信息不全'}${pr.goal ? ` · 目标：${pr.goal}` : ''}`
}
function addRecipe(p) { p.recipes.push({ meal: '加餐', name: '', kcal: 0, ingredients: [] }) }
function removeRecipe(p, i) { p.recipes.splice(i, 1) }
function ingredientsText(r) { return (r.ingredients || []).join('、') }
function setIngredients(r, text) { r.ingredients = text.split(/[、,，]/).map((s) => s.trim()).filter(Boolean) }

async function save(p) {
  try {
    const resp = await updatePlan(p.plan_id, {
      calories_target: Number(p.calories_target) || undefined,
      recipes: p.recipes,
      shopping_list: p.shopping_text.split('\n').map((s) => s.trim()).filter(Boolean),
      review_note: p.review_note || '',
    })
    Object.assign(p, resp.data, { shopping_text: (resp.data.shopping_list || []).join('\n') })
    flash(resp.message || '已保存')
  } catch (e) {
    error.value = e.message || '保存失败'
  }
}
async function review(p, action) {
  try {
    const resp = await reviewPlan(p.plan_id, action, p.review_note || '', 'admin')
    flash(resp.message || '操作完成')
    if (tab.value !== 'all') plans.value = plans.value.filter((x) => x.plan_id !== p.plan_id)
    else Object.assign(p, resp.data)
  } catch (e) {
    error.value = e.message || '操作失败'
  }
}
const pendingCount = computed(() => plans.value.filter((p) => p.status === 'pending_review').length)

onMounted(load)
</script>

<template>
  <div class="page-heading">
    <div>
      <span class="overline">PLAN REVIEW · 营养师工作台</span>
      <h1>饮食计划审核</h1>
      <p>审核 AI 生成的个性化饮食计划：可直接通过（沿用 AI 版本），也可以人工修改菜谱 / 热量 / 清单后再通过。</p>
    </div>
    <button class="btn ghost" @click="load">↻ 刷新</button>
  </div>

  <div v-if="error" class="alert">{{ error }}</div>
  <div v-if="successMsg" class="success-banner">{{ successMsg }}</div>

  <div class="tab-row">
    <button v-for="t in tabs" :key="t.key" class="tab-btn" :class="{ active: tab === t.key }" @click="switchTab(t.key)">
      {{ t.label }}
    </button>
    <span class="muted" style="margin-left:auto;font-size:12px">共 {{ plans.length }} 条</span>
  </div>

  <div v-if="loading" class="loading-text">加载计划队列…</div>
  <div v-else-if="!plans.length" class="empty-text" style="padding:32px 0;text-align:center">
    {{ tab === 'pending_review' ? '当前没有待审核的计划 🎉' : '该状态下暂无计划' }}
  </div>

  <article v-for="p in plans" :key="p.plan_id" class="plan-card">
    <div class="plan-head" @click="toggleExpand(p)">
      <div class="plan-user">
        <strong>{{ p.profile?.user_name || p.user_id }}</strong>
        <span>{{ profileText(p) }}</span>
      </div>
      <div class="plan-meta">
        <span class="chip">{{ p.set_label || '未命名档位' }}</span>
        <span class="chip">目标 {{ p.calories_target }} kcal</span>
        <span class="chip" :class="p.source === 'manual' ? 'manual' : ''">{{ p.source === 'manual' ? '已人工调整' : 'AI 生成' }}</span>
        <span class="status-chip" :class="p.status">
          {{ p.status === 'pending_review' ? '待审核' : p.status === 'approved' ? '已通过' : '已驳回' }}
        </span>
        <span class="muted" style="font-size:12px">{{ (p.updated_at || '').slice(0, 16).replace('T', ' ') }}</span>
        <button class="btn ghost small">{{ expanded === p.plan_id ? '收起 ▲' : '审核 / 修改 ▼' }}</button>
      </div>
    </div>

    <div v-if="expanded === p.plan_id" class="plan-body">
      <div class="plan-personal">{{ p.personalization }}</div>

      <div class="field-row">
        <label>目标热量（kcal）</label>
        <input v-model.number="p.calories_target" type="number" min="800" max="5000" style="width:120px" />
        <label style="margin-left:16px">档位名称</label>
        <input v-model="p.set_label" style="width:160px" />
      </div>

      <div class="section-label">菜谱（可直接改菜名 / 热量 / 食材）</div>
      <div v-for="(r, i) in p.recipes" :key="i" class="recipe-edit">
        <span class="meal-tag">{{ r.meal }}</span>
        <input v-model="r.name" placeholder="菜名" class="w-name" />
        <input v-model.number="r.kcal" type="number" class="w-kcal" placeholder="kcal" />
        <input :value="ingredientsText(r)" placeholder="食材（用、分隔）" class="w-ing" @change="setIngredients(r, $event.target.value)" />
        <button class="icon-btn" title="删除该餐" @click="removeRecipe(p, i)">✕</button>
      </div>
      <button class="btn ghost small" @click="addRecipe(p)">＋ 添加一餐</button>

      <div class="section-label" style="margin-top:14px">购物清单（每行一项）</div>
      <textarea v-model="p.shopping_text" rows="5" class="shopping-edit"></textarea>

      <div class="section-label" style="margin-top:14px">营养师备注（用户端可见）</div>
      <textarea v-model="p.review_note" rows="2" placeholder="例如：已把晚餐主食减量，注意补充蛋白质" class="note-edit"></textarea>

      <div class="plan-ops">
        <button class="btn ghost" @click="save(p)">保存人工调整</button>
        <button class="btn success" @click="review(p, 'approve')">✓ 通过（{{ p.source === 'manual' ? '发布人工版' : '沿用 AI 版' }}）</button>
        <button class="btn danger" @click="review(p, 'reject')">✕ 驳回</button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.success-banner { background: #d1fae5; color: #065f46; border-radius: 8px; padding: 8px 14px; margin-bottom: 10px; font-size: 13px; }
.tab-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.tab-btn {
  border: 1px solid var(--border, #dbe3ee); background: var(--card, #fff); color: inherit;
  border-radius: 999px; padding: 5px 14px; font-size: 13px; cursor: pointer;
}
.tab-btn.active { border-color: #0e7490; color: #0e7490; background: #eef7fb; }

.plan-card { border: 1px solid var(--border, #e5ecf3); border-radius: 12px; margin-bottom: 12px; background: var(--card, #fff); }
.plan-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; cursor: pointer; flex-wrap: wrap; }
.plan-user { display: flex; flex-direction: column; }
.plan-user strong { font-size: 14px; }
.plan-user span { font-size: 12px; color: #8a94a6; }
.plan-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip { font-size: 12px; padding: 2px 9px; border-radius: 999px; background: #f1f5f9; color: #475569; }
.chip.manual { background: #eef7fb; color: #0e7490; }
.status-chip { font-size: 12px; padding: 2px 9px; border-radius: 999px; }
.status-chip.pending_review { background: #fff7e6; color: #b45309; }
.status-chip.approved { background: #dcfce7; color: #15803d; }
.status-chip.rejected { background: #fee2e2; color: #b91c1c; }
.btn.small { padding: 4px 10px; font-size: 12px; }
.btn.success { background: #10b981; color: #fff; }
.btn.danger { background: #fee2e2; color: #b91c1c; }

.plan-body { border-top: 1px dashed var(--border, #e5ecf3); padding: 14px 16px; }
.plan-personal { font-size: 12.5px; color: #0e7490; background: #f4fafd; border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; }
.field-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.field-row input { border: 1px solid var(--border, #dbe3ee); border-radius: 8px; padding: 5px 8px; font-size: 13px; }
.recipe-edit { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
.meal-tag { min-width: 40px; text-align: center; font-size: 11px; color: #fff; background: #0e7490; border-radius: 6px; padding: 3px 7px; }
.recipe-edit input { border: 1px solid var(--border, #dbe3ee); border-radius: 8px; padding: 5px 8px; font-size: 13px; }
.w-name { flex: 1.2; }
.w-kcal { width: 90px; }
.w-ing { flex: 2; }
.icon-btn { border: none; background: transparent; color: #b91c1c; cursor: pointer; font-size: 13px; }
.shopping-edit, .note-edit {
  width: 100%; border: 1px solid var(--border, #dbe3ee); border-radius: 8px; padding: 8px 10px;
  font-size: 13px; font-family: inherit; resize: vertical;
}
.plan-ops { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
</style>
