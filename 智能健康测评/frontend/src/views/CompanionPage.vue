<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { chartThemeName } from '../theme-deep'
import { isDark } from '../theme-mode'
import { currentUserId, getHealthReport, sendPetMessage } from '../api'

const period = ref('week')
const chartMode = ref('bar') // 饮食累计图表形态：bar 柱状图 / pie 饼图
const nutritionEl = ref(null)
let nutritionChart = null
const report = ref(null)
const loading = ref(false)
const error = ref('')
const message = ref('')
const messages = ref([
  { role: 'assistant', content: '你好呀，我是你的健康小萌宠。告诉我今天吃了什么、睡得怎么样，或者只是聊聊天都可以。' },
])
const chatLoading = ref(false)
const uid = currentUserId()
const petOpen = ref(false)
const petPosition = ref({ x: 0, y: 0 })
const dragging = ref(false)
const dragMoved = ref(false)
const dragStart = ref({ x: 0, y: 0, left: 0, top: 0 })

const periodLabel = computed(() => period.value === 'week' ? '本周' : '本月')
const riskText = computed(() => {
  const dist = report.value?.assessment?.risk_distribution || {}
  const entries = Object.entries(dist).filter(([, count]) => count)
  return entries.length ? entries.map(([key, count]) => `${key} ${count}次`).join(' · ') : '暂无测评记录'
})

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const res = await getHealthReport(period.value)
    report.value = res.data
  } catch (err) {
    error.value = err.message || '报告加载失败'
  } finally {
    loading.value = false
  }
}

async function sendMessage() {
  const text = message.value.trim()
  if (!text || chatLoading.value) return
  messages.value.push({ role: 'user', content: text })
  message.value = ''
  chatLoading.value = true
  try {
    const res = await sendPetMessage({ message: text, user_id: uid })
    messages.value.push({ role: 'assistant', content: res.data?.reply || '我听见啦，我们慢慢来。' })
  } catch (err) {
    messages.value.push({ role: 'assistant', content: err.message || '我暂时没连上，但仍然可以陪你记录。' })
  } finally {
    chatLoading.value = false
  }
}

function clampPetPosition(x, y) {
  const margin = 14
  const size = 68
  return {
    x: Math.max(margin, Math.min(window.innerWidth - size - margin, x)),
    y: Math.max(margin, Math.min(window.innerHeight - size - margin, y)),
  }
}

function startPetDrag(event) {
  if (event.button !== undefined && event.button !== 0) return
  const point = event.touches?.[0] || event
  const current = petPosition.value
  dragStart.value = { x: point.clientX, y: point.clientY, left: current.x, top: current.y }
  dragging.value = true
  dragMoved.value = false
  window.addEventListener('pointermove', movePetDrag)
  window.addEventListener('pointerup', endPetDrag, { once: true })
}

function movePetDrag(event) {
  if (!dragging.value) return
  const dx = event.clientX - dragStart.value.x
  const dy = event.clientY - dragStart.value.y
  if (Math.abs(dx) + Math.abs(dy) > 5) dragMoved.value = true
  petPosition.value = clampPetPosition(dragStart.value.left + dx, dragStart.value.top + dy)
}

function endPetDrag() {
  dragging.value = false
  window.removeEventListener('pointermove', movePetDrag)
  if (!dragMoved.value) petOpen.value = !petOpen.value
}

function petPopupStyle() {
  const width = Math.min(360, window.innerWidth - 24)
  const height = Math.min(430, window.innerHeight - 24)
  const left = Math.max(12, Math.min(window.innerWidth - width - 12, petPosition.value.x + 72))
  const top = Math.max(12, Math.min(window.innerHeight - height - 12, petPosition.value.y - height + 60))
  return { left: `${left}px`, top: `${top}px`, width: `${width}px` }
}

function setInitialPetPosition() {
  if (!petPosition.value.x && !petPosition.value.y) {
    petPosition.value = clampPetPosition(window.innerWidth - 92, window.innerHeight - 100)
    return
  }
  petPosition.value = clampPetPosition(petPosition.value.x, petPosition.value.y)
}

function onEnter(event) {
  if (!event.shiftKey) { event.preventDefault(); sendMessage() }
}

// ===== 饮食累计图表（柱状图 / 饼图切换） =====
const NUTRITION_PALETTE = ['#526d4e', '#98ad7d', '#c9a36b']

function nutritionItems() {
  const meals = report.value?.meals || {}
  return [
    { name: '蛋白质', value: Number(meals.protein_g) || 0 },
    { name: '脂肪', value: Number(meals.fat_g) || 0 },
    { name: '碳水', value: Number(meals.carbs_g) || 0 },
  ]
}

function renderNutritionChart() {
  const el = nutritionEl.value
  if (!el || !report.value) return
  // loading 交替会重建 DOM 节点，旧实例挂在新节点上时先废弃
  if (nutritionChart && nutritionChart.dom !== el) { nutritionChart.dispose(); nutritionChart = null }
  if (!nutritionChart) nutritionChart = echarts.init(el, chartThemeName())
  const items = nutritionItems()
  const hasData = items.some((i) => i.value > 0)
  if (!hasData) { nutritionChart.clear(); return }
  if (chartMode.value === 'bar') {
    nutritionChart.setOption({
      color: NUTRITION_PALETTE,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${v} g` },
      grid: { left: 46, right: 14, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: items.map((i) => i.name), axisTick: { show: false } },
      yAxis: { type: 'value', name: '克(g)' },
      series: [{
        type: 'bar', colorBy: 'item', barWidth: 38,
        data: items.map((i) => i.value),
        itemStyle: { borderRadius: [5, 5, 0, 0] },
        label: { show: true, position: 'top', formatter: '{c} g' },
      }],
    }, true)
  } else {
    nutritionChart.setOption({
      color: NUTRITION_PALETTE,
      tooltip: { trigger: 'item', formatter: '{b}：{c} g（{d}%）' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie', radius: ['38%', '64%'], center: ['50%', '44%'],
        data: items,
        label: { formatter: '{b}\n{d}%' },
        emphasis: { itemStyle: { shadowBlur: 8 } },
      }],
    }, true)
  }
}

function resizeNutritionChart() { nutritionChart?.resize() }

watch([report, chartMode], () => nextTick(renderNutritionChart))
// 黑白主题切换后重建图表，保证文字与背景对比度正确
watch(isDark, () => {
  nutritionChart?.dispose()
  nutritionChart = null
  nextTick(renderNutritionChart)
})

onMounted(() => {
  loadReport()
  setInitialPetPosition()
  window.addEventListener('resize', setInitialPetPosition)
  window.addEventListener('resize', resizeNutritionChart)
})
onUnmounted(() => {
  window.removeEventListener('resize', setInitialPetPosition)
  window.removeEventListener('resize', resizeNutritionChart)
  window.removeEventListener('pointermove', movePetDrag)
})
onBeforeUnmount(() => {
  nutritionChart?.dispose()
  nutritionChart = null
})
</script>

<template>
  <section class="companion-page">
    <div class="page-heading companion-heading">
      <div>
        <p class="eyebrow">CARE COMPANION</p>
        <h1>{{ period === 'week' ? '健康周报' : '健康月报' }}</h1>
        <p class="muted">把已经记录的健康数据整理成一眼能看懂的小结。小萌宠会在角落陪着你。</p>
      </div>
      <div class="period-switch" role="tablist" aria-label="报告周期">
        <button :class="{ active: period === 'week' }" @click="period = 'week'; loadReport()">周报</button>
        <button :class="{ active: period === 'month' }" @click="period = 'month'; loadReport()">月报</button>
      </div>
    </div>

    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="loading" class="report-loading">正在整理{{ periodLabel }}数据…</div>
    <template v-else-if="report">
      <div class="report-range">{{ report.start }} 至 {{ report.end }} · {{ periodLabel }}累计</div>
      <div class="report-grid">
        <article class="report-card accent-card"><span>测评次数</span><strong>{{ report.assessment.count }}</strong><small>平均 {{ report.assessment.average_score }} 分</small></article>
        <article class="report-card"><span>饮食记录</span><strong>{{ report.meals.record_count }}</strong><small>{{ report.meals.calories }} kcal</small></article>
        <article class="report-card"><span>舌象记录</span><strong>{{ report.tongue.record_count }}</strong><small>最新：{{ report.tongue.latest_color }}</small></article>
        <article class="report-card"><span>AI 对话</span><strong>{{ report.conversation_count }}</strong><small>次健康陪伴</small></article>
      </div>
      <div class="report-columns">
        <article class="report-panel">
          <h2>这段时间的观察</h2>
          <p class="risk-line">{{ riskText }}</p>
          <ul v-if="report.highlights?.length"><li v-for="item in report.highlights" :key="item">{{ item }}</li></ul>
          <p v-else class="muted">继续记录，趋势会更清晰。</p>
        </article>
        <article class="report-panel nutrition-panel">
          <div class="panel-head">
            <h2>饮食累计</h2>
            <div class="chart-switch" role="tablist" aria-label="图表类型">
              <button :class="{ active: chartMode === 'bar' }" @click="chartMode = 'bar'">柱状图</button>
              <button :class="{ active: chartMode === 'pie' }" @click="chartMode = 'pie'">饼图</button>
            </div>
          </div>
          <div v-if="report.meals.record_count === 0" class="muted chart-empty">本周期暂无饮食记录，记一餐后这里会出现图表。</div>
          <div v-show="report.meals.record_count > 0" ref="nutritionEl" class="nutrition-chart"></div>
        </article>
      </div>
      <p class="disclaimer">{{ report.disclaimer }}</p>
    </template>

    <button
      class="pet-fab"
      type="button"
      :class="{ dragging }"
      :style="{ left: `${petPosition.x}px`, top: `${petPosition.y}px` }"
      :aria-label="petOpen ? '关闭小萌宠' : '打开小萌宠'"
      :title="petOpen ? '关闭小萌宠' : '打开小萌宠（可拖动）'"
      @pointerdown.prevent="startPetDrag"
    >
      <span class="pet-face" aria-hidden="true">◡̈</span><i></i><i></i>
      <span class="pet-status" aria-hidden="true"></span>
    </button>

    <section v-if="petOpen" class="pet-popup" :style="petPopupStyle()" aria-label="小萌宠聊天">
      <div class="pet-popup-head">
        <div><span class="eyebrow">YOUR LITTLE GUIDE</span><h2>和我聊聊天</h2></div>
        <button class="pet-close" type="button" title="关闭小萌宠" @click="petOpen = false">×</button>
      </div>
      <p class="pet-welcome">我会认真听你说。今天开心或不开心，都可以告诉我。</p>
      <div class="chat-history" aria-live="polite">
        <div v-for="(item, index) in messages" :key="index" :class="['chat-bubble', item.role]">{{ item.content }}</div>
        <div v-if="chatLoading" class="chat-bubble assistant">让我想一想…</div>
      </div>
      <div class="chat-compose"><textarea v-model="message" rows="2" maxlength="1000" placeholder="和我说说你的心情…" @keydown.enter="onEnter"></textarea><button type="button" title="发送消息" :disabled="chatLoading || !message.trim()" @click="sendMessage">发送</button></div>
    </section>
  </section>
</template>

<style scoped>
.companion-page { max-width: 1120px; margin: 0 auto; padding: 8px 0 48px; color: var(--ink, #20251f); }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 12px; }
.eyebrow { margin: 0 0 6px; color: var(--muted, #6a765f); font-size: 11px; letter-spacing: .08em; font-weight: 700; }
h1, h2, p { margin-top: 0; } h1 { margin-bottom: 6px; font-size: clamp(25px, 3vw, 38px); } h2 { margin-bottom: 14px; font-size: 18px; }
.muted, .disclaimer, .report-range { color: var(--muted, #737b72); font-size: 13px; }
.period-switch { display: flex; border: 1px solid var(--line, #d9ded6); background: var(--card, #f6f8f4); padding: 3px; border-radius: 8px; }
.period-switch button { border: 0; background: transparent; padding: 8px 17px; color: var(--muted, #747c73); cursor: pointer; border-radius: 6px; font-weight: 600; }
.period-switch button.active { color: var(--bg, #fff); background: var(--primary, #526d4e); }
.report-range { margin: 20px 0 10px; }
.report-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.report-card, .report-panel { border: 1px solid var(--line, #e2e7df); background: var(--card, #fff); border-radius: 8px; padding: 18px; }
.report-card { min-height: 112px; display: flex; flex-direction: column; gap: 6px; } .report-card span, .report-card small { color: var(--muted, #7b847a); font-size: 12px; } .report-card strong { font-size: 28px; color: var(--ink, #263326); } .accent-card { border-top: 3px solid var(--lime, #98ad7d); }
.report-columns { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; margin-top: 12px; } .report-panel ul { padding-left: 18px; margin: 0; color: var(--muted, #525b51); line-height: 1.8; font-size: 13px; } .risk-line { color: var(--primary-dark, #526d4e); font-weight: 700; font-size: 13px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; } .panel-head h2 { margin-bottom: 0; }
.chart-switch { display: flex; border: 1px solid var(--line, #d9ded6); background: var(--card, #f6f8f4); padding: 2px; border-radius: 7px; }
.chart-switch button { border: 0; background: transparent; padding: 4px 11px; color: var(--muted, #747c73); cursor: pointer; border-radius: 5px; font-weight: 600; font-size: 12px; }
.chart-switch button.active { color: var(--bg, #fff); background: var(--primary, #526d4e); }
.nutrition-chart { width: 100%; height: 240px; margin-top: 8px; }
.chart-empty { padding: 40px 0 20px; text-align: center; }
.disclaimer { margin: 14px 2px 20px; }
.pet-fab { position: fixed; z-index: 30; width: 68px; height: 68px; padding: 0; border: 1px solid var(--line, transparent); border-radius: 50%; background: var(--card, #dbe9d4); box-shadow: 0 9px 22px rgba(0, 0, 0, .28), 0 0 0 4px var(--paper, rgba(255,255,255,.85)); cursor: grab; touch-action: none; transition: box-shadow .18s ease, transform .18s ease; } .pet-fab:hover { transform: translateY(-3px); box-shadow: 0 13px 25px rgba(0, 0, 0, .34), 0 0 0 4px var(--paper, rgba(255,255,255,.9)); } .pet-fab.dragging { cursor: grabbing; transform: scale(1.05); }
.pet-face { display: grid; place-items: center; width: 49px; height: 40px; margin: 6px auto 0; border-radius: 48% 48% 44% 44%; background: var(--paper, #fffaf0); color: var(--primary, #526d4e); font-size: 22px; box-shadow: 0 5px 0 var(--line, #bfd4b4); } .pet-fab i { position: absolute; width: 6px; height: 6px; border-radius: 50%; background: var(--primary, #526d4e); top: 27px; } .pet-fab i:first-of-type { left: 22px; } .pet-fab i:last-of-type { right: 22px; } .pet-status { position: absolute; right: 5px; bottom: 5px; width: 10px; height: 10px; border: 2px solid var(--card, #fff); border-radius: 50%; background: var(--success, #79a56c); }
.pet-popup { position: fixed; z-index: 29; height: min(430px, calc(100vh - 24px)); display: flex; flex-direction: column; padding: 18px; border: 1px solid var(--line, #d7e3d1); border-radius: 14px; background: var(--card, #fbfdf9); box-shadow: 0 18px 50px rgba(0, 0, 0, .38); } .pet-popup-head { display: flex; justify-content: space-between; align-items: flex-start; } .pet-popup-head h2 { margin-bottom: 0; } .pet-close { width: 30px; height: 30px; border: 0; border-radius: 50%; background: var(--primary-light, #eef4eb); color: var(--primary, #526d4e); font-size: 20px; line-height: 1; cursor: pointer; } .pet-welcome { margin: 14px 0 2px; color: var(--muted, #566454); font-size: 13px; line-height: 1.55; }
.chat-history { flex: 1; min-height: 120px; max-height: 260px; overflow-y: auto; padding: 10px 0; } .chat-bubble { width: fit-content; max-width: 85%; padding: 10px 13px; margin: 6px 0; border-radius: 12px; font-size: 13px; line-height: 1.55; white-space: pre-wrap; }
.chat-compose { display: flex; gap: 8px; align-items: flex-end; } .chat-compose textarea { flex: 1; min-height: 45px; resize: vertical; border: 1px solid var(--line, #d8e2d3); border-radius: 6px; padding: 10px; background: var(--card, white); color: var(--ink, #263238); font: inherit; font-size: 13px; } .chat-compose button { border: 0; border-radius: 6px; padding: 10px 16px; color: var(--bg, white); background: var(--primary, #526d4e); cursor: pointer; } .chat-compose button:disabled { cursor: not-allowed; opacity: .45; }
.inline-error { color: var(--danger, #a34f4f); background: var(--card, #fff4f2); border: 1px solid var(--danger, #a34f4f); padding: 10px 12px; border-radius: 6px; font-size: 13px; } .report-loading { padding: 36px 0; color: var(--muted, #687267); }
@media (max-width: 760px) { .page-heading, .report-columns { display: block; } .period-switch { margin-top: 14px; width: fit-content; } .report-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
