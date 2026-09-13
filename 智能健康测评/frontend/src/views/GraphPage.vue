<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
import { chartThemeName } from '../theme-deep'
import { isDark } from '../theme-mode'
import {
  getGraphData, getGraphStats, initGraph, getDiseases, getDiseaseDetail, getGraphReason,
} from '../api'
// eslint-disable-next-line no-unused-vars -- 下方模板/开关卡片在使用（会被 IDE「优化导入」误删，勿清理）
import { graphRagEnabled, graphRagDefault, toggleGraphRag, initGraphRag } from '../graph-rag'

const loading = ref(false)
const diseases = ref([])
const selectedDisease = ref('')
const diseaseDetail = ref(null)
const message = ref('')
const stats = ref(null)
const viewMode = ref('all')      // all = 全量图谱 / disease = 单个疾病子图
const nodeCount = ref(0)
const linkCount = ref(0)
const reasonDisease = ref('')
const reasonExclude = ref('')
const reasoning = ref(null)
const reasonLoading = ref(false)
let chart = null
let graphData = null

const catColors = ['#22a06b', '#2b7de9', '#e05151'] // 食物/营养素/疾病

// 关系类型 → 边色：正向(蓝/绿) 与 反向(橙/红) 一眼区分
const REL_COLORS = {
  含有: '#93a9c4',
  降低风险: '#2b7de9',
  缓解: '#4aa3e0',
  加重: '#e08a2b',
  适宜: '#22a06b',
  禁忌: '#e05151',
}
const relColor = (rel) => REL_COLORS[rel] || '#b7c5d6'

async function loadStats() {
  try {
    const resp = await getGraphStats()
    stats.value = resp.data
  } catch (e) {
    stats.value = null
  }
}

async function loadGraph() {
  loading.value = true
  try {
    const disease = viewMode.value === 'disease' ? selectedDisease.value : ''
    const resp = await getGraphData(500, disease)
    graphData = resp.data
    nodeCount.value = (graphData.nodes || []).length
    linkCount.value = (graphData.links || []).length
    if (viewMode.value === 'disease' && graphData.found === false) {
      message.value = `图谱中暂无「${selectedDisease.value}」节点，可点「导入预置图谱」。`
    } else {
      message.value = ''
    }
    render()
  } catch (e) {
    message.value = '图谱加载失败：' + e.message
  } finally {
    loading.value = false
  }
}

// 切换筛选：全量 / 单个疾病子图
async function switchMode(mode) {
  viewMode.value = mode
  await loadGraph()
  if (mode === 'disease' && selectedDisease.value) queryDisease()
}

function render() {
  if (!chart) return
  const data = graphData
  const nodes = data.nodes || []
  const dense = nodes.length > 24          // 全量视图节点多，只显示疾病名标签
  const filtered = nodes.length <= 24
  chart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'edge') return `${p.data.source} —${p.data.label?.formatter || ''}→ ${p.data.target}`
        const cat = data.categories[p.data.category] || ''
        return `<b>${p.name}</b><br/>类别：${cat}`
      },
    },
    legend: {
      data: data.categories,
      bottom: 0,
      textStyle: { fontSize: 13 },
    },
    animationDurationUpdate: 1000,
    series: [{
      type: 'graph',
      layout: 'force',
      data: data.nodes,
      links: data.links.map((l) => {
        const rel = l.label?.formatter || ''
        return {
          ...l,
          symbol: ['none', 'arrow'],
          symbolSize: 7,
          lineStyle: { width: rel === '禁忌' || rel === '适宜' ? 2 : 1.5, curveness: 0.05, color: relColor(rel) },
        }
      }),
      categories: data.categories.map((name, i) => ({
        name,
        itemStyle: { color: catColors[i] },
      })),
      roam: true,
      draggable: true,
      force: {
        repulsion: dense ? 900 : 260,
        edgeLength: dense ? [80, 190] : [70, 130],
        gravity: dense ? 0.05 : 0.12,
        layoutAnimation: true,
      },
      label: {
        show: true,
        position: 'right',
        fontSize: filtered ? 13 : 11,
        color: 'inherit',
        formatter: (p) => (!dense || p.data.category === 2 ? p.name : ''),
      },
      emphasis: { focus: 'adjacency' },
      lineStyle: {
        color: '#b7c5d6',
        opacity: 0.8,
        width: 1.5,
      },
    }],
  })
}

function resize() { chart?.resize() }

async function initPreset() {
  if (!confirm('确认把预置营养知识图谱补齐到最新？\n（15 疾病 × 19 营养素 × 44 食物 + 食物↔疾病宜忌直接关系）\n采用增量补齐：只新增缺失的节点与关系，不会删除已有数据。')) return
  try {
    const resp = await initGraph(false)
    const d = resp.data || {}
    const written = d.written
      ? `新增/更新 疾病${d.written.disease} · 营养素${d.written.nutrient} · 食物${d.written.food} · 关系${d.written.relation}`
      : ''
    message.value = `✅ 图谱${d.mode || '导入'}完成 ${written}`
    await loadGraph()
    await loadStats()
  } catch (e) {
    message.value = '导入失败：' + e.message
  }
}

async function loadDiseases() {
  try {
    const resp = await getDiseases()
    diseases.value = resp.data || []
    if (diseases.value.length) {
      selectedDisease.value = diseases.value[0]
      reasonDisease.value = diseases.value[0]
      loadReason()
    }
  } catch (e) {
    diseases.value = []
  }
}

// 多跳推理：疾病 → 营养素 → 食物（含宜吃 / 忌口 / 按过敏原剔除）
async function loadReason() {
  if (!reasonDisease.value) return
  reasonLoading.value = true
  try {
    const resp = await getGraphReason(reasonDisease.value, reasonExclude.value.trim())
    reasoning.value = resp.data?.found ? resp.data : null
    if (!resp.data?.found) message.value = `图谱中未找到「${reasonDisease.value}」`
  } catch (e) {
    reasoning.value = null
    message.value = '推理失败：' + e.message
  } finally {
    reasonLoading.value = false
  }
}

async function queryDisease() {
  if (!selectedDisease.value) return
  try {
    const resp = await getDiseaseDetail(selectedDisease.value)
    diseaseDetail.value = resp.data
  } catch (e) {
    diseaseDetail.value = null
    message.value = '查询失败：' + e.message
  }
}

function initChart() {
  chart = echarts.init(document.getElementById('chart-graph'), chartThemeName())
}

onMounted(() => {
  initChart()
  loadGraph()
  loadStats()
  loadDiseases()
  initGraphRag()          // 对齐后端 .env 的图谱增强默认开关
  window.addEventListener('resize', resize)
})

// 黑白主题切换后重建图谱，保证文字与背景对比度正确
watch(isDark, () => {
  chart?.dispose()
  initChart()
  loadGraph()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
})
</script>

<template>
  <div>
    <!-- AI 问答 · 图谱增强开关（请求级：切换后立即生效，无需重启后端） -->
    <div class="card rag-card">
      <div class="row">
        <div>
          <div class="card-title" style="margin:0">AI 问答 · 图谱增强</div>
          <div class="rag-sub">
            控制智能问答是否把图谱结论（宜吃 / 忌口 / 过敏剔除）注入提示词。
            关闭即为「接入图谱前」的基线，用于答辩对比。本页图谱可视化与多跳推理不受影响。
          </div>
        </div>
        <div class="grow"></div>
        <button
          class="rag-toggle"
          :class="{ on: graphRagEnabled }"
          :aria-pressed="graphRagEnabled"
          :title="graphRagEnabled ? '点击关闭（做对比基线）' : '点击开启（接入图谱）'"
          @click="toggleGraphRag"
        >
          <span class="knob"></span>
        </button>
        <span class="rag-state" :class="{ off: !graphRagEnabled }">
          {{ graphRagEnabled ? '🕸️ 已接入图谱' : '⚪ 未接图谱' }}
        </span>
      </div>
      <div class="rag-hint" :class="{ off: !graphRagEnabled }">
        <template v-if="graphRagEnabled">
          当前提问会带上图谱结构化结论，回答里会出现「参考来源：营养知识图谱·疾病名」。
          <span v-if="!graphRagDefault" class="rag-warn">注意：后端 .env 默认是关闭的，现在是手动开启。</span>
        </template>
        <template v-else>
          当前提问只依赖知识库向量检索 + 健康画像，作对比基线。
          <span class="rag-warn">答辩用法：先在关闭状态问一遍 → 再开启问同一句 → 对比回答具体度与参考来源。</span>
        </template>
      </div>
    </div>

    <!-- 疾病查询面板 -->
    <div class="card">
      <div class="row">
        <div class="card-title" style="margin:0">疾病 → 营养干预知识查询</div>
        <div class="grow"></div>
        <select
          v-model="selectedDisease"
          style="border:1px solid var(--border);border-radius:8px;padding:6px 10px"
        >
          <option v-for="d in diseases" :key="d" :value="d">{{ d }}</option>
        </select>
        <button class="btn" @click="queryDisease">查询关联</button>
        <button class="btn ghost" @click="initPreset">导入预置图谱</button>
      </div>
      <div v-if="diseaseDetail" class="grid-2 mt-16">
        <div>
          <b>疾病：</b>{{ diseaseDetail.disease }}
          <div class="mt-8"><b>营养干预建议：</b>{{ diseaseDetail.advice }}</div>
          <div v-if="diseaseDetail.taboo?.length" class="mt-8">
            <b>图谱禁忌：</b>
            <span v-for="t in diseaseDetail.taboo" :key="t.food" class="tag tag-taboo">{{ t.food }}</span>
          </div>
          <div v-else class="mt-8 muted">图谱禁忌：暂无</div>
        </div>
        <div>
          <b>关联营养素：</b>
          <span
            v-for="n in diseaseDetail.nutrients"
            :key="n.nutrient"
            class="risk-badge risk-低风险"
            style="margin-right:6px"
          >
            {{ n.nutrient }}（{{ n.relation }}）
          </span>
          <div class="mt-8"><b>推荐食物：</b>{{ diseaseDetail.foods.join('、') }}</div>
          <div v-if="diseaseDetail.suitable?.length" class="mt-8">
            <b>图谱适宜：</b>
            <span v-for="f in diseaseDetail.suitable" :key="f" class="tag tag-suitable">{{ f }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 多跳推理面板 -->
    <div class="card mt-16">
      <div class="row reason-head">
        <div class="card-title" style="margin:0">🕸️ 图谱多跳推理</div>
        <select v-model="reasonDisease" class="graph-select">
          <option v-for="d in diseases" :key="d" :value="d">{{ d }}</option>
        </select>
        <input
          v-model="reasonExclude"
          class="graph-input"
          placeholder="排除食物（逗号分隔，如：牛奶,酸奶）"
        />
        <button class="btn" :disabled="reasonLoading" @click="loadReason">
          {{ reasonLoading ? '推理中…' : '开始推理' }}
        </button>
      </div>

      <div v-if="reasoning" class="mt-16">
        <div class="reason-block">
          <div class="reason-label">推理链路</div>
          <div v-for="(h, i) in reasoning.hops" :key="i" class="hop-line">{{ h }}</div>
        </div>
        <div class="reason-cols">
          <div class="reason-block">
            <div class="reason-label">宜吃（正向链路）</div>
            <span v-if="!reasoning.recommended.length" class="muted">无</span>
            <span v-for="f in reasoning.recommended" :key="f" class="tag tag-suitable">{{ f }}</span>
          </div>
          <div class="reason-block">
            <div class="reason-label">忌口（禁忌 / 加重链路）</div>
            <span v-if="!reasoning.taboo.length" class="muted">无</span>
            <span v-for="t in reasoning.taboo" :key="t.food" class="tag tag-taboo" :title="t.note">{{ t.food }}</span>
          </div>
          <div class="reason-block">
            <div class="reason-label">已剔除（过敏 / 不耐受）</div>
            <span v-if="!reasoning.excluded?.length" class="muted">无</span>
            <span v-for="e in reasoning.excluded" :key="e.food" class="tag tag-excluded">{{ e.food }}</span>
          </div>
        </div>
      </div>
      <div v-else-if="!reasonLoading" class="muted mt-8">选择疾病后可查看推理链路；填入排除食物（如乳糖不耐受填「牛奶,酸奶」）可观察推荐项被剔除的过程。</div>
    </div>

    <!-- 图谱画布 -->
    <div class="card mt-16">
      <div class="row">
        <div class="card-title" style="margin:0">营养知识图谱（Neo4j）</div>
        <span class="rel-legend">
          <span class="lg"><i class="dot" style="background:#22a06b"></i>食物</span>
          <span class="lg"><i class="dot" style="background:#2b7de9"></i>营养素</span>
          <span class="lg"><i class="dot" style="background:#e05151"></i>疾病</span>
          <span class="lg"><i class="bar" style="background:#93a9c4"></i>含有</span>
          <span class="lg"><i class="bar" style="background:#2b7de9"></i>降低风险/缓解</span>
          <span class="lg"><i class="bar" style="background:#e08a2b"></i>加重</span>
          <span class="lg"><i class="bar" style="background:#22a06b"></i>适宜</span>
          <span class="lg"><i class="bar" style="background:#e05151"></i>禁忌</span>
        </span>
      </div>

      <!-- 视图筛选：全量 / 按疾病逐个查看，避免几百个节点挤成一团 -->
      <div class="graph-toolbar mt-16">
        <div class="segmented">
          <button :class="{ active: viewMode === 'all' }" @click="switchMode('all')">全量图谱</button>
          <button :class="{ active: viewMode === 'disease' }" @click="switchMode('disease')">按疾病查看</button>
        </div>
        <select
          v-if="viewMode === 'disease'"
          v-model="selectedDisease"
          class="graph-select"
          @change="switchMode('disease')"
        >
          <option v-for="d in diseases" :key="d" :value="d">{{ d }}</option>
        </select>
        <span class="graph-count">
          当前 {{ nodeCount }} 个节点 / {{ linkCount }} 条关系
          <template v-if="stats">（图谱共 {{ stats.total }} 个：食物 {{ stats.food }} · 营养素 {{ stats.nutrient }} · 疾病 {{ stats.disease }}<template v-if="stats.relation_total"> · {{ stats.relation_total }} 条关系</template>）</template>
        </span>
        <div class="grow"></div>
        <button class="btn ghost" style="padding:6px 12px;font-size:13px" @click="loadGraph">↻ 重新布局</button>
      </div>
      <div v-if="message" class="report-rule mt-8">{{ message }}</div>
      <div v-if="loading" class="loading-text">图谱加载中…</div>
      <div id="chart-graph" class="chart-box" style="height: 620px"></div>
    </div>
  </div>
</template>

<style scoped>
/* AI 问答 · 图谱增强开关 */
.rag-card .rag-sub { font-size: 12.5px; line-height: 1.7; color: var(--muted); margin-top: 5px; max-width: 720px; }
.rag-toggle {
  position: relative; width: 46px; height: 26px; padding: 0; flex: 0 0 auto;
  border-radius: 13px; border: 1px solid var(--border, #dbe3ee);
  background: rgba(148, 163, 184, .45); cursor: pointer;
  transition: background .2s ease, border-color .2s ease;
}
.rag-toggle .knob {
  position: absolute; top: 2px; left: 2px; width: 20px; height: 20px;
  border-radius: 50%; background: #fff; box-shadow: 0 1px 4px rgba(15, 30, 60, .35);
  transition: transform .2s ease;
}
.rag-toggle.on { background: #22a06b; border-color: #22a06b; }
.rag-toggle.on .knob { transform: translateX(20px); }
.rag-state { font-size: 13px; font-weight: 700; color: #1a7d53; white-space: nowrap; }
.rag-state.off { color: #b45309; }
.rag-hint {
  margin-top: 10px; padding: 8px 12px; border-radius: 8px;
  font-size: 12.5px; line-height: 1.7; color: var(--ink, inherit);
  background: rgba(34, 160, 107, .10);
}
.rag-hint.off { background: rgba(224, 138, 43, .12); }
.rag-warn { color: #b45309; font-weight: 600; }
html.dark .rag-hint { background: rgba(34, 160, 107, .16); }
html.dark .rag-hint.off { background: rgba(224, 138, 43, .18); }
html.dark .rag-state { color: #6ee7a8; }
html.dark .rag-state.off { color: #fcd34d; }
html.dark .rag-warn { color: #fcd34d; }

.graph-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.graph-select {
  border: 1px solid var(--border, #dbe3ee); border-radius: 8px;
  padding: 7px 10px; font: inherit; font-size: 13px;
  background: var(--card, #fff); color: inherit; min-width: 180px;
}
.graph-input {
  border: 1px solid var(--border, #dbe3ee); border-radius: 8px;
  padding: 7px 10px; font: inherit; font-size: 13px;
  background: var(--card, #fff); color: inherit; min-width: 240px;
}
.graph-count { font-size: 12.5px; color: var(--muted); }
.reason-head { flex-wrap: wrap; gap: 10px; }

/* 关系图例 */
.rel-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--muted); }
.rel-legend .lg { display: inline-flex; align-items: center; gap: 5px; }
.rel-legend .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.rel-legend .bar { width: 16px; height: 3px; border-radius: 2px; display: inline-block; }

/* 多跳推理面板 */
.reason-block { margin-bottom: 12px; }
.reason-label { font-size: 12px; font-weight: 700; color: var(--muted); margin-bottom: 6px; }
.reason-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.hop-line {
  font-size: 12.5px; line-height: 1.9; padding: 6px 10px; margin-bottom: 6px;
  border-left: 3px solid var(--primary, #2b7de9);
  background: var(--paper, #f5f8fc); border-radius: 0 6px 6px 0;
  color: var(--ink, inherit); word-break: break-all;
}
.tag {
  display: inline-block; padding: 3px 9px; margin: 0 6px 6px 0;
  border-radius: 12px; font-size: 12px; line-height: 1.5;
}
.tag-suitable { background: rgba(34, 160, 107, .14); color: #1a7d53; }
.tag-taboo { background: rgba(224, 81, 81, .14); color: #c23b3b; }
.tag-excluded { background: rgba(120, 130, 150, .16); color: #6b7280; text-decoration: line-through; }
html.dark .tag-suitable { background: rgba(34, 160, 107, .22); color: #6ee7a8; }
html.dark .tag-taboo { background: rgba(224, 81, 81, .22); color: #fca5a5; }
html.dark .tag-excluded { background: rgba(148, 163, 184, .2); color: #cbd5e1; }
</style>
