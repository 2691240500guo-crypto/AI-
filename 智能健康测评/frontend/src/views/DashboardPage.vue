<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { chartThemeName } from '../theme-deep'
import { isDark } from '../theme-mode'
import {
  currentUserId,
  getAssessmentStats,
  getAssessmentHistory,
  getKnowledgeStats,
  getKnowledgeFiles,
} from '../api'

const stats = ref(null)
const kbStats = ref(null)
// 用户端只展示当前登录用户的测评明细，避免形成跨用户浏览入口。
const selectedUser = ref(currentUserId('USER001'))
const history = ref([])

// ===== 统计卡点击 → 明细弹窗 =====
const CARD_META = {
  total:     { title: '累计测评人次 · 明细' },
  avg:       { title: '平均总分 · 明细' },
  'high-risk': { title: '高风险人数 · 明细' },
  'kb-files':  { title: '知识库文件 · 明细' },
  'kb-chunks': { title: '知识分块 · 明细' },
}
const modal = ref({ open: false, kind: '' })
const kbFiles = ref([])
const detailLoading = ref(false)
const detailError = ref('')

const RISK_LEVELS = ['无风险', '低风险', '中风险', '高风险']

// 当前账号的三维平均分（与雷达图同口径）
const myDimAvg = computed(() => {
  const all = history.value
  const avg = (k) => (all.length ? (all.reduce((s, r) => s + (r[k] || 0), 0) / all.length).toFixed(1) : '—')
  return {
    营养受损: avg('nutritional_impairment_score'),
    疾病严重度: avg('disease_severity_score'),
    年龄加分: avg('age_score'),
    总分: avg('total_score'),
  }
})

async function openCard(kind) {
  modal.value = { open: true, kind }
  detailError.value = ''
  if ((kind === 'kb-files' || kind === 'kb-chunks') && !kbFiles.value.length) {
    detailLoading.value = true
    try {
      const resp = await getKnowledgeFiles(200)
      kbFiles.value = resp.data || []
    } catch (e) {
      detailError.value = e.message || '文件列表加载失败'
    } finally {
      detailLoading.value = false
    }
  }
}

function closeModal() {
  modal.value = { open: false, kind: '' }
}

/** 弹窗表格内容：按卡片类型组装，全部来自已加载的统计/明细数据 */
const detailTable = computed(() => {
  const s = stats.value || {}
  const dist = s.risk_distribution || {}
  const total = s.total || 0
  const pct = (n) => (total ? ((n / total) * 100).toFixed(1) + '%' : '—')

  switch (modal.value.kind) {
    case 'total': {
      const trend = s.daily_trend || []
      return {
        columns: ['日期', '测评人次'],
        rows: trend.map((t) => ({ 日期: t.date, 测评人次: t.count })),
        note: `近 14 天合计 ${trend.reduce((a, b) => a + b.count, 0)} 人次，全站累计 ${total} 人次。`,
      }
    }
    case 'avg':
      return {
        columns: ['维度', '满分', '当前账号平均'],
        rows: [
          { 维度: '营养受损', 满分: 3, 当前账号平均: myDimAvg.value.营养受损 },
          { 维度: '疾病严重度', 满分: 3, 当前账号平均: myDimAvg.value.疾病严重度 },
          { 维度: '年龄加分', 满分: 1, 当前账号平均: myDimAvg.value.年龄加分 },
          { 维度: '总分', 满分: 7, 当前账号平均: myDimAvg.value.总分 },
        ],
        note: `全站 ${total} 人次测评的平均总分为 ${s.avg_score ?? '—'} 分（满分 7）。`,
      }
    case 'high-risk':
      return {
        columns: ['风险等级', '人数', '占比'],
        rows: RISK_LEVELS.map((lv) => ({
          风险等级: lv,
          人数: dist[lv] ?? 0,
          占比: pct(dist[lv] ?? 0),
        })),
        note: '为保护用户隐私，此页仅展示统计口径，不列出其他用户的测评记录。',
      }
    case 'kb-files':
    case 'kb-chunks': {
      const rows = kbFiles.value.map((f) => ({
        文件名: f.file_name,
        类型: f.file_type || '—',
        大小: f.file_size ? `${(f.file_size / 1024).toFixed(1)} KB` : '—',
        向量块: f.chunk_count ?? 0,
        状态: f.status || '—',
        入库时间: (f.upload_time || '').replace('T', ' ').slice(0, 16) || '—',
      }))
      if (modal.value.kind === 'kb-chunks') rows.sort((a, b) => b.向量块 - a.向量块)
      return {
        columns: ['文件名', '类型', '大小', '向量块', '状态', '入库时间'],
        rows,
        note: `共 ${kbStats.value?.total_files ?? rows.length} 个文件 / ${kbStats.value?.total_chunks ?? 0} 个向量块（存储于 Milvus）。`,
      }
    }
    default:
      return { columns: [], rows: [], note: '' }
  }
})

let chartPie = null
let chartTrend = null
let chartRadar = null
let chartBar = null

const riskColors = {
  无风险: '#22a06b',
  低风险: '#2b7de9',
  中风险: '#e2a03f',
  高风险: '#e05151',
}

function initCharts() {
  const domPie = document.getElementById('chart-risk')
  const domTrend = document.getElementById('chart-trend')
  const domRadar = document.getElementById('chart-dim')
  const domBar = document.getElementById('chart-bar')
  const theme = chartThemeName()
  chartPie = echarts.init(domPie, theme)
  chartTrend = echarts.init(domTrend, theme)
  chartRadar = echarts.init(domRadar, theme)
  chartBar = echarts.init(domBar, theme)
}

// 黑白主题切换后重建图表，保证文字与背景对比度正确
function disposeCharts() {
  ;[chartPie, chartTrend, chartRadar, chartBar].forEach((c) => c?.dispose())
  chartPie = chartTrend = chartRadar = chartBar = null
}

watch(isDark, async () => {
  disposeCharts()
  await nextTick()
  initCharts()
  renderCharts()
})

function renderCharts() {
  if (!stats.value) return

  // 1. 风险等级分布（环形饼图）
  const dist = stats.value.risk_distribution || {}
  chartPie.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    color: Object.values(riskColors),
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      label: { show: true, formatter: '{b}\n{c}人 ({d}%)', fontSize: 12 },
      data: Object.entries(dist).map(([name, value]) => ({ name, value })),
    }],
  })

  // 2. 近14天测评趋势（折线）
  const trend = stats.value.daily_trend || []
  chartTrend.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: trend.map((t) => t.date), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      name: '测评人次',
      type: 'line',
      smooth: true,
      areaStyle: { opacity: 0.15 },
      data: trend.map((t) => t.count),
      itemStyle: { color: '#2b7de9' },
    }],
  })

  // 3. 三维得分均值（雷达）
  const all = history.value
  const avg = (key) =>
    all.length
      ? (all.reduce((s, r) => s + (r[key] || 0), 0) / all.length).toFixed(1)
      : 0
  chartRadar.setOption({
    tooltip: {},
    radar: {
      indicator: [
        { name: '营养受损', max: 3 },
        { name: '疾病严重度', max: 3 },
        { name: '年龄加分', max: 1 },
        { name: '总分', max: 7 },
      ],
      radius: '65%',
    },
    series: [{
      type: 'radar',
      data: [{
        value: [avg('nutritional_impairment_score'), avg('disease_severity_score'), avg('age_score'), avg('total_score')],
        name: '平均得分',
        areaStyle: { opacity: 0.25 },
        itemStyle: { color: '#e2a03f' },
        lineStyle: { color: '#e2a03f', width: 2 },
      }],
    }],
  })

  // 4. 各风险档得分均值（柱状）
  const levels = ['无风险', '低风险', '中风险', '高风险']
  const data = levels.map((lv) => {
    const rows = all.filter((r) => r.risk_level === lv)
    return {
      name: lv,
      value: rows.length
        ? (rows.reduce((s, r) => s + r.total_score, 0) / rows.length).toFixed(1)
        : 0,
      count: rows.length,
    }
  })
  chartBar.setOption({
    tooltip: {
      formatter: (p) => `${p.name}：均值 ${p.value} 分（${data[p.dataIndex].count} 人）`,
    },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: levels },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      barWidth: 40,
      label: { show: true, position: 'top' },
      data: data.map((d, i) => ({
        value: d.value,
        itemStyle: { color: Object.values(riskColors)[i], borderRadius: [6, 6, 0, 0] },
      })),
    }],
  })
}

function resizeCharts() {
  chartPie?.resize(); chartTrend?.resize(); chartRadar?.resize(); chartBar?.resize()
}

async function loadData() {
  try {
    const [s, kb] = await Promise.all([
      getAssessmentStats(),
      getKnowledgeStats().catch(() => null),
    ])
    stats.value = s.data
    kbStats.value = kb?.data || null
  } catch (e) {
    console.error(e)
  }
  await nextTick()
  renderCharts()
  loadUserHistory()
}

async function loadUserHistory() {
  try {
    const resp = await getAssessmentHistory(selectedUser.value, 100)
    history.value = resp.data || []
  } catch (e) {
    history.value = []
  }
  await nextTick()
  // 用个人历史刷新雷达/柱状
  if (stats.value) {
    const all = history.value
    const avg = (key) =>
      all.length ? (all.reduce((s, r) => s + (r[key] || 0), 0) / all.length).toFixed(1) : 0
    chartRadar.setOption({
      series: [{ data: [{
        value: [avg('nutritional_impairment_score'), avg('disease_severity_score'), avg('age_score'), avg('total_score')],
        name: `${selectedUser.value} 平均`,
      }] }],
    })
    const levels = ['无风险', '低风险', '中风险', '高风险']
    const data = levels.map((lv) => {
      const rows = all.filter((r) => r.risk_level === lv)
      return rows.length
        ? (rows.reduce((s, r) => s + r.total_score, 0) / rows.length).toFixed(1)
        : 0
    })
    chartBar.setOption({
      series: [{ data: data.map((v, i) => ({ value: v, itemStyle: { color: Object.values(riskColors)[i], borderRadius: [6, 6, 0, 0] } })) }],
    })
  }
}

onMounted(() => {
  loadData()
  initCharts()
  window.addEventListener('resize', resizeCharts)
})
onBeforeUnmount(() => window.removeEventListener('resize', resizeCharts))
</script>

<template>
  <div>
    <!-- 顶部统计 -->
    <div class="stat-grid">
      <button type="button" class="stat-card clickable" title="查看累计测评人次明细" @click="openCard('total')">
        <div class="num">{{ stats?.total ?? '-' }}</div>
        <div class="label">累计测评人次 <em class="open-hint">查看明细 ›</em></div>
      </button>
      <button type="button" class="stat-card clickable" title="查看平均总分明细" @click="openCard('avg')">
        <div class="num">{{ stats?.avg_score ?? '-' }}</div>
        <div class="label">平均总分（满分 7） <em class="open-hint">查看明细 ›</em></div>
      </button>
      <button type="button" class="stat-card clickable" title="查看高风险人数明细" @click="openCard('high-risk')">
        <div class="num" style="color: var(--danger)">{{ stats?.risk_distribution?.['高风险'] ?? 0 }}</div>
        <div class="label">高风险人数 <em class="open-hint">查看明细 ›</em></div>
      </button>
      <button type="button" class="stat-card clickable" title="查看知识库文件列表" @click="openCard('kb-files')">
        <div class="num">{{ kbStats?.total_files ?? '-' }}</div>
        <div class="label">知识库文件 <em class="open-hint">查看明细 ›</em></div>
      </button>
      <button type="button" class="stat-card clickable" title="查看知识分块明细" @click="openCard('kb-chunks')">
        <div class="num">{{ kbStats?.total_chunks ?? '-' }}</div>
        <div class="label">知识分块（Milvus） <em class="open-hint">查看明细 ›</em></div>
      </button>
    </div>

    <!-- 图表区 -->
    <div class="chart-grid mt-16">
      <div class="card">
        <div class="card-title">风险等级分布</div>
        <div id="chart-risk" class="chart-box" style="height: 320px"></div>
      </div>
      <div class="card">
        <div class="card-title">近 14 天测评趋势</div>
        <div id="chart-trend" class="chart-box" style="height: 320px"></div>
      </div>
      <div class="card">
        <div class="card-title">分维度平均得分</div>
        <div id="chart-dim" class="chart-box" style="height: 320px"></div>
      </div>
      <div class="card">
        <div class="card-title">各风险等级得分均值</div>
        <div id="chart-bar" class="chart-box" style="height: 320px"></div>
      </div>
    </div>

    <!-- 个人历史明细 -->
    <div class="card mt-16">
      <div class="row">
        <div class="card-title" style="margin:0">用户测评明细</div>
        <div class="grow"></div>
        <span class="muted">当前账号：{{ selectedUser }}</span>
      </div>
      <table v-if="history.length" class="data mt-16">
        <thead>
          <tr>
            <th>测评时间</th><th>姓名</th><th>年龄</th><th>BMI</th>
            <th>营养</th><th>疾病</th><th>年龄分</th><th>总分</th><th>等级</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in history" :key="h.record_id">
            <td>{{ h.assessment_time }}</td>
            <td>{{ h.user_name }}</td>
            <td>{{ h.age }}</td>
            <td>{{ h.bmi ?? '--' }}</td>
            <td>{{ h.nutritional_impairment_score }}</td>
            <td>{{ h.disease_severity_score }}</td>
            <td>{{ h.age_score }}</td>
            <td style="font-weight:700">{{ h.total_score }}</td>
            <td><span :class="'risk-badge risk-' + h.risk_level">{{ h.risk_level }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-text">该用户暂无测评记录</div>
    </div>

    <!-- 统计卡明细弹窗 -->
    <div v-if="modal.open" class="detail-mask" @click.self="closeModal">
      <div class="detail-modal">
        <div class="detail-head">
          <div>
            <span class="overline">DETAIL</span>
            <h3>{{ CARD_META[modal.kind]?.title || '明细' }}</h3>
          </div>
          <button class="detail-close" @click="closeModal">✕</button>
        </div>

        <div v-if="detailLoading" class="loading-text">明细加载中…</div>
        <div v-else-if="detailError" class="alert">{{ detailError }}</div>
        <div v-else-if="!detailTable.rows.length" class="empty-text">暂无明细数据</div>

        <div v-else class="detail-body">
          <table class="data detail-table">
            <thead>
              <tr><th v-for="col in detailTable.columns" :key="col">{{ col }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in detailTable.rows" :key="i">
                <td v-for="col in detailTable.columns" :key="col">{{ row[col] }}</td>
              </tr>
            </tbody>
          </table>
          <div class="detail-foot">{{ detailTable.note }}</div>
        </div>

        <div class="detail-actions">
          <button class="btn ghost" @click="closeModal">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* —— 可点击统计卡 —— */
.stat-card.clickable {
  cursor: pointer; text-align: left; font: inherit; width: 100%;
  border: 1px solid var(--border, #e3e8ef);
  transition: transform .18s, box-shadow .18s, border-color .18s;
}
.stat-card.clickable:hover {
  transform: translateY(-3px);
  border-color: var(--primary, #5f9e3f);
  box-shadow: 0 16px 34px -18px rgba(0, 0, 0, .45);
}
.stat-card.clickable:active { transform: translateY(-1px); }
.open-hint {
  display: block; margin-top: 4px; font-size: 11px; font-style: normal;
  font-weight: 500; opacity: .7;
}
.stat-card.clickable:hover .open-hint { opacity: 1; color: var(--primary); }

/* —— 明细弹窗 —— */
.detail-mask {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(4, 8, 24, .62); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; padding: 32px 20px;
}
.detail-modal {
  width: min(880px, 100%); max-height: 86vh; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--card, #fff); border: 1px solid var(--border, #e3e8ef);
  border-radius: 18px; box-shadow: 0 30px 70px -30px rgba(0, 0, 0, .6);
}
.detail-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; padding: 20px 24px 14px;
}
.detail-head h3 { margin: 6px 0 0; font-size: 19px; }
.detail-close { border: none; background: transparent; color: var(--muted); font-size: 17px; cursor: pointer; }
.detail-close:hover { color: var(--danger); }
.detail-body { overflow: auto; padding: 0 24px; }
.detail-table { width: 100%; font-size: 13px; }
.detail-foot { padding: 10px 0 4px; font-size: 12px; color: var(--muted); line-height: 1.6; }
.detail-actions {
  display: flex; justify-content: flex-end; gap: 10px;
  padding: 14px 24px 20px; border-top: 1px solid var(--border, #e3e8ef); margin-top: 8px;
}
</style>
