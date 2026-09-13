<script setup>
import { ref, reactive, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { chartThemeName } from '../theme-deep'
import { isDark } from '../theme-mode'
import {
  createAssessment,
  currentUserId,
  getAssessmentHistory,
  getAssessGraphHint,
  getDiseases,
} from '../api'

const loading = ref(false)
const submitting = ref(false)
const result = ref(null)
const graphHints = ref([])          // 图谱命中提示（模糊匹配可能命中多个疾病）
const graphDiseases = ref([])       // 图谱标准疾病列表（快选标签数据源）
const history = ref([])
const error = ref('')
const role = localStorage.getItem('healthybot_role') || 'user'
const isAdmin = role === 'admin'
const loggedInUserId = currentUserId('USER001')

const form = reactive({
  user_id: loggedInUserId,
  user_name: '演示用户',
  sex: '男',
  age: 45,
  height_cm: 170,
  weight_kg: 65,
  weight_loss_pct: 0,
  disease_level: '无',
  disease_condition: '',
  dietary_intake: '正常',
  need_llm_report: true,
})

const diseaseLevels = [
  { value: '无', label: '无 / 健康' },
  { value: '轻度', label: '轻度（稳定期慢性病：糖尿病/高血压等）' },
  { value: '中度', label: '中度（需卧床/大手术/肺炎/肿瘤放化疗）' },
  { value: '重度', label: '重度（ICU/重症监护）' },
]
const dietaryOptions = ['正常', '减少25%', '减少50%', '减少75%', '几乎不进食']

// —— 疾病快选标签：数据源为图谱标准疾病列表，点选后写入 disease_condition ——
// 历史实测：自由文本「高血压（稳定期）」等写法曾让图谱命中率只有 5%，
// 改为从标准列表点选，从源头消除漂移；下方输入框仍保留，兜底图谱之外的描述。
const selectedDiseases = computed({
  get: () => (form.disease_condition || '').split('、').filter(Boolean),
  set: (arr) => { form.disease_condition = arr.join('、') },
})
function toggleDisease(name) {
  const cur = selectedDiseases.value
  selectedDiseases.value = cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name]
}
getDiseases().then((r) => { graphDiseases.value = r.data || [] }).catch(() => {})

// 前端预算 BMI（仅供参考）
const previewBmi = computed(() => {
  if (form.height_cm > 0 && form.weight_kg > 0) {
    const h = form.height_cm / 100
    return (form.weight_kg / (h * h)).toFixed(1)
  }
  return '--'
})

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const resp = await createAssessment({
      ...form,
      weight_loss_pct: Number(form.weight_loss_pct) || 0,
      age: Number(form.age),
    })
    result.value = resp.data
    // 若命中疾病，查图谱提示（后端模糊匹配可能命中多个疾病，展示成多张卡）
    const disease = form.disease_condition.trim()
    if (disease) {
      try {
        const gr = await getAssessGraphHint(disease)
        graphHints.value = gr.data?.hints || (gr.data?.hint ? [gr.data.hint] : [])
      } catch (e) {
        graphHints.value = []
      }
    } else {
      graphHints.value = []
    }
    form.user_id = resp.data?.user_id || loggedInUserId
    await loadHistory(form.user_id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    error.value = e.message || '测评失败'
  } finally {
    submitting.value = false
  }
}

async function loadHistory(userId = form.user_id) {
  try {
    const resp = await getAssessmentHistory(userId, 20)
    history.value = resp.data || []
  } catch (e) {
    history.value = []
  }
}

// —— 本次得分构成图（饼图 / 柱状图可切换）——
const chartMode = ref('pie')
const scoreChartEl = ref(null)
let scoreChart = null

const scoreItems = computed(() => {
  const r = result.value
  if (!r) return []
  return [
    { name: '营养受损', value: r.nutritional_impairment_score ?? 0 },
    { name: '疾病严重度', value: r.disease_severity_score ?? 0 },
    { name: '年龄加分', value: r.age_score ?? 0 },
  ]
})
const scoreTotal = computed(() => scoreItems.value.reduce((s, i) => s + i.value, 0))

function renderScoreChart() {
  const el = scoreChartEl.value
  if (!el || !result.value) return
  if (!scoreChart || scoreChart.getDom() !== el) {
    if (scoreChart) scoreChart.dispose()
    scoreChart = echarts.init(el, chartThemeName())
  }
  const items = scoreItems.value
  const colors = ['#4de3ff', '#f472b6', '#fbbf24']

  if (chartMode.value === 'pie') {
    scoreChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}：{c} 分（{d}%）' },
      legend: { bottom: 0, itemWidth: 10, itemHeight: 10 },
      series: [{
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderWidth: 2 },
        label: { formatter: '{b}\n{c} 分', fontSize: 12 },
        labelLine: { length: 10, length2: 8 },
        data: items.map((i, idx) => ({ ...i, itemStyle: { color: colors[idx] } })),
      }],
    }, true)
  } else {
    scoreChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      xAxis: { type: 'category', data: items.map((i) => i.name) },
      yAxis: { type: 'value', max: 3, interval: 1 },
      series: [{
        type: 'bar',
        barWidth: 42,
        label: { show: true, position: 'top', formatter: '{c} 分' },
        itemStyle: { borderRadius: [6, 6, 0, 0] },
        data: items.map((i, idx) => ({ value: i.value, itemStyle: { color: colors[idx] } })),
      }],
    }, true)
  }
}

watch([result, chartMode], async () => {
  await nextTick()
  renderScoreChart()
})

// 黑白主题切换后重建图表，保证文字对比度
watch(isDark, async () => {
  await nextTick()
  if (scoreChart) { scoreChart.dispose(); scoreChart = null }
  renderScoreChart()
})

onBeforeUnmount(() => { if (scoreChart) { scoreChart.dispose(); scoreChart = null } })

// 快速填充示例
function fillSample(level) {
  const samples = {
    high: {
      user_name: '张大爷', sex: '男', age: 75,
      height_cm: 165, weight_kg: 46,
      weight_loss_pct: 12, disease_level: '中度',
      disease_condition: '慢阻肺急性加重期', dietary_intake: '减少50%',
    },
    mid: {
      user_name: '王先生', sex: '男', age: 68,
      height_cm: 170, weight_kg: 52,
      weight_loss_pct: 8, disease_level: '中度',
      disease_condition: '胃癌术后化疗期', dietary_intake: '减少60%',
    },
    low: {
      user_name: '李阿姨', sex: '女', age: 65,
      height_cm: 158, weight_kg: 48,
      weight_loss_pct: 4.6, disease_level: '轻度',
      disease_condition: '2型糖尿病稳定期', dietary_intake: '正常',
    },
    none: {
      user_name: '健康青年', sex: '男', age: 30,
      height_cm: 175, weight_kg: 68,
      weight_loss_pct: 0, disease_level: '无',
      disease_condition: '', dietary_intake: '正常',
    },
  }
  Object.assign(form, samples[level])
  // 普通用户的示例测评也必须归属到当前账号；管理员保留指定演示对象的能力。
  form.user_id = isAdmin ? 'USER' + Date.now().toString().slice(-6) : loggedInUserId
}

loadHistory()
</script>

<template>
  <div>
    <!-- 测评表单 -->
    <div class="card">
      <div class="card-title">NRS2002 营养风险筛查（0-7 分制，≥3 分为高风险）</div>
      <div class="row mt-8" style="margin-bottom: 18px">
        <span class="muted">快速示例：</span>
        <button class="btn danger" style="padding:4px 12px" @click="fillSample('high')">高风险患者</button>
        <button class="btn warning" style="padding:4px 12px" @click="fillSample('mid')">中风险患者</button>
        <button class="btn success" style="padding:4px 12px" @click="fillSample('low')">低风险示例</button>
        <button class="btn ghost" style="padding:4px 12px" @click="fillSample('none')">健康对照</button>
      </div>

      <div class="form-grid">
        <div class="form-item">
          <label>用户ID<span class="req">*</span></label>
          <input v-model="form.user_id" placeholder="唯一标识" />
        </div>
        <div class="form-item">
          <label>姓名<span class="req">*</span></label>
          <input v-model="form.user_name" />
        </div>
        <div class="form-item">
          <label>性别</label>
          <select v-model="form.sex">
            <option>男</option><option>女</option><option>其他</option>
          </select>
        </div>
        <div class="form-item">
          <label>年龄（岁）<span class="req">*</span></label>
          <input v-model.number="form.age" type="number" min="1" max="120" />
        </div>
        <div class="form-item">
          <label>身高（cm）</label>
          <input v-model.number="form.height_cm" type="number" />
        </div>
        <div class="form-item">
          <label>体重（kg）</label>
          <input v-model.number="form.weight_kg" type="number" />
        </div>
        <div class="form-item">
          <label>BMI（自动估算）</label>
          <input :value="previewBmi" disabled />
        </div>
        <div class="form-item">
          <label>近3个月体重下降(%)</label>
          <input v-model.number="form.weight_loss_pct" type="number" min="0" max="60" step="0.1" />
        </div>
        <div class="form-item">
          <label>疾病严重程度<span class="req">*</span></label>
          <select v-model="form.disease_level">
            <option v-for="d in diseaseLevels" :key="d.value" :value="d.value">{{ d.label }}</option>
          </select>
        </div>
        <div class="form-item">
          <label>疾病描述（点选图谱标准疾病，可多选）</label>
          <div class="disease-chips">
            <button v-for="d in graphDiseases" :key="d" type="button"
                    class="disease-chip" :class="{ active: selectedDiseases.includes(d) }"
                    @click="toggleDisease(d)">{{ d }}</button>
          </div>
          <input v-model="form.disease_condition" placeholder="点选上方标签自动填入；也可手动输入其他描述（多个用、分隔）" />
        </div>
        <div class="form-item">
          <label>进食情况</label>
          <select v-model="form.dietary_intake">
            <option v-for="d in dietaryOptions" :key="d" :value="d">{{ d }}</option>
          </select>
        </div>
        <div class="form-item">
          <label>LLM 报告增强</label>
          <select v-model="form.need_llm_report">
            <option :value="true">生成 AI 个性化报告（SiliconFlow）</option>
            <option :value="false">仅规则评分（快）</option>
          </select>
        </div>
      </div>

      <div class="row mt-16">
        <button class="btn" :disabled="submitting" @click="submit">
          {{ submitting ? '评估中…（评分+生成报告）' : '开始测评' }}
        </button>
        <span v-if="error" style="color: var(--danger)">{{ error }}</span>
      </div>
    </div>

    <!-- 测评结果 -->
    <div v-if="result" class="card mt-16">
      <div class="card-title">测评结果</div>
      <div class="stat-grid" style="margin-bottom: 16px">
        <div class="stat-card">
          <div class="num" :style="{ color: result.total_score >= 3 ? 'var(--danger)' : result.total_score >= 1 ? 'var(--warning)' : 'var(--success)' }">{{ result.total_score }}<span style="font-size:16px"> / 7 分</span></div>
          <div class="label">NRS2002 总分</div>
        </div>
        <div class="stat-card">
          <div class="num">{{ result.nutritional_impairment_score }}</div>
          <div class="label">营养受损 (0-3)</div>
        </div>
        <div class="stat-card">
          <div class="num">{{ result.disease_severity_score }}</div>
          <div class="label">疾病严重度 (0-3)</div>
        </div>
        <div class="stat-card">
          <div class="num">{{ result.age_score }}</div>
          <div class="label">年龄加分 (0-1)</div>
        </div>
        <div class="stat-card">
          <div class="num">
            <span :class="'risk-badge risk-' + result.risk_level">{{ result.risk_level }}</span>
          </div>
          <div class="label">风险等级</div>
        </div>
      </div>

      <div class="grid-2">
        <div>
          <div class="card-title">评分依据</div>
          <div class="report-rule">{{ result.basis }}</div>

          <div class="card-title mt-16">基础建议（规则模板）</div>
          <div class="report-rule">{{ result.recommendations }}</div>

          <div v-if="graphHints.length" class="card-title mt-16">🕸️ 知识图谱命中提示（{{ graphHints.length }} 项）</div>
          <div v-for="h in graphHints" :key="h.disease" class="report-rule">
            <b>疾病「{{ h.disease }}」关联营养素：</b>
            <span v-for="n in h.nutrients" :key="n" style="margin-right:8px" class="risk-badge risk-低风险">{{ n }}</span>
            <div class="mt-8"><b>推荐食物：</b>{{ h.foods.join('、') }}</div>
            <div v-if="h.suitable && h.suitable.length" class="mt-8">
              <b>图谱适宜：</b>
              <span v-for="f in h.suitable" :key="f" class="g-tag g-ok">{{ f }}</span>
            </div>
            <div v-if="h.taboo && h.taboo.length" class="mt-8">
              <b>图谱禁忌：</b>
              <span v-for="t in h.taboo" :key="t.food" class="g-tag g-no" :title="t.note">{{ t.food }}</span>
            </div>
            <div class="mt-8"><b>干预建议：</b>{{ h.advice }}</div>
          </div>

          <!-- 本次得分构成：饼图 / 柱状图一键切换 -->
          <div class="score-head mt-16">
            <div class="card-title" style="margin:0">本次得分构成</div>
            <div class="grow"></div>
            <div class="segmented seg-mini">
              <button :class="{ active: chartMode === 'pie' }" @click="chartMode = 'pie'">饼图</button>
              <button :class="{ active: chartMode === 'bar' }" @click="chartMode = 'bar'">柱状图</button>
            </div>
          </div>
          <div v-if="scoreTotal === 0" class="empty-text">
            本次三项得分均为 0（无营养风险），无需展示构成图。
          </div>
          <template v-else>
            <div ref="scoreChartEl" class="score-chart"></div>
            <div class="score-meta">
              三项合计 {{ scoreTotal }} 分 ·
              风险等级 <span :class="'risk-badge risk-' + result.risk_level">{{ result.risk_level }}</span>
            </div>
          </template>
        </div>
        <div>
          <div v-if="result.llm_report" class="card-title">AI 个性化报告（DeepSeek-V4-Flash）</div>
          <div v-if="result.llm_report" class="report">{{ result.llm_report }}</div>
          <div v-else class="report-rule">本次未生成 LLM 报告（未启用或生成失败，已用规则模板兜底）。</div>
        </div>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="card mt-16">
      <div class="card-title">该用户历史测评（最近 {{ history.length }} 次）</div>
      <table v-if="history.length" class="data">
        <thead>
          <tr>
            <th>#</th><th>时间</th><th>姓名</th><th>年龄</th><th>BMI</th>
            <th>营养/疾病/年龄分</th><th>总分</th><th>等级</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(h, i) in history" :key="h.record_id">
            <td>{{ history.length - i }}</td>
            <td>{{ h.assessment_time }}</td>
            <td>{{ h.user_name }}</td>
            <td>{{ h.age }}</td>
            <td>{{ h.bmi ?? '--' }}</td>
            <td>{{ h.nutritional_impairment_score }} + {{ h.disease_severity_score }} + {{ h.age_score }}</td>
            <td style="font-weight:700">{{ h.total_score }}</td>
            <td><span :class="'risk-badge risk-' + h.risk_level">{{ h.risk_level }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-text">暂无历史记录</div>
    </div>
  </div>
</template>

<style scoped>
.score-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.seg-mini { padding: 3px; }
.seg-mini button { padding: 4px 12px; font-size: 12px; }
.score-chart { width: 100%; height: 250px; }
.score-meta { margin-top: 6px; font-size: 12.5px; color: var(--muted); }
.disease-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.disease-chip {
  padding: 4px 11px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--line, #d9ded6); border-radius: 999px;
  background: var(--card, #fff); color: var(--muted, #737b72);
}
.disease-chip:hover { border-color: var(--primary, #526d4e); color: var(--primary, #526d4e); }
.disease-chip.active {
  background: var(--primary, #526d4e); border-color: var(--primary, #526d4e);
  color: var(--bg, #fff); font-weight: 600;
}
/* 图谱 适宜/禁忌 标签 */
.g-tag {
  display: inline-block; padding: 3px 9px; margin: 0 6px 6px 0;
  border-radius: 12px; font-size: 12px; line-height: 1.5;
}
.g-ok { background: rgba(34, 160, 107, .14); color: #1a7d53; }
.g-no { background: rgba(224, 81, 81, .14); color: #c23b3b; }
html.dark .g-ok { background: rgba(34, 160, 107, .22); color: #6ee7a8; }
html.dark .g-no { background: rgba(224, 81, 81, .22); color: #fca5a5; }
</style>
