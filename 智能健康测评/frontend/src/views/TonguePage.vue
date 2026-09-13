<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { analyzeTongue, currentUserId, getTongueImage, getTongueRecords, saveTongueRecord } from '../api'

const userId = ref(currentUserId('user'))
const file = ref(null)
const preview = ref('')
const result = ref(null)
const loading = ref(false)
const saving = ref(false)
const savedFlag = ref(false)
const error = ref('')
const successMsg = ref('')
const records = ref([])
const recordsLoading = ref(false)
const canvasRef = ref(null)
const imageUrls = new Set()

// —— 分析 ——
function pick(event) {
  file.value = event.target.files?.[0] || null
  result.value = null
  savedFlag.value = false
  if (file.value) preview.value = URL.createObjectURL(file.value)
}
function flash(msg) {
  successMsg.value = msg
  setTimeout(() => { successMsg.value = '' }, 2600)
}
function statusText() {
  const s = result.value?.status
  if (s === 'detected') return `已检出 ${result.value?.features?.length || 0} 项舌象特征`
  if (s === 'not_detected') return '未检测到舌象特征'
  if (s === 'model_missing') return '未加载检测权重'
  return '等待分析'
}

// 特征分组配色：舌色=玫红 / 苔质=琥珀 / 形态=紫 / 分区=蓝
const GROUP_COLORS = {
  color: '#e11d48', coat: '#d97706', shape: '#7c3aed', area: '#0284c7', other: '#0ea5e9',
}
const GROUP_LABELS = { color: '舌色', coat: '苔质', shape: '舌形/舌态', area: '分区', other: '其他' }
// 特征实测可信度（后端 FEATURE_RELIABILITY 同步）：high/medium 才写进结论
const LEVEL_LABELS = {
  high: '可信', medium: '可参考', low: '仅供参考（测得不稳）',
  unusable: '模型对该特征不可用，仅作检出展示', unknown: '未评估',
}
const LEVEL_SHORT = { low: '慎用', unusable: '不可用' }
function chipTitle(f) {
  const lv = LEVEL_LABELS[f.level] || LEVEL_LABELS.unknown
  const m = f.recall != null ? ` · 测试集图级召回 ${Math.round(f.recall * 100)}%` : ''
  const n = f.reliability_note ? ` · ${f.reliability_note}` : ''
  return `${GROUP_LABELS[f.group] || ''} · 置信度 ${(f.confidence * 100).toFixed(1)}% · 可信度：${lv}${m}${n}`
}
const legendGroups = computed(() => {
  const groups = new Set((result.value?.features || []).map((f) => f.group))
  return Object.keys(GROUP_COLORS).filter((g) => groups.has(g)).map((g) => ({ key: g, label: GROUP_LABELS[g] }))
})

async function drawBoxes() {
  await nextTick()
  const canvas = canvasRef.value
  if (!canvas || !preview.value || !result.value?.features?.length) return
  const ctx = canvas.getContext('2d')
  const img = new Image()
  img.onload = () => {
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    ctx.drawImage(img, 0, 0)
    const dets = result.value.detections?.length ? result.value.detections : result.value.features
    const fontPx = Math.max(12, canvas.width * 0.024)
    ctx.font = `600 ${fontPx}px system-ui, sans-serif`
    ctx.lineWidth = Math.max(2, canvas.width * 0.0035)
    dets.forEach((d) => {
      if (!d?.box) return
      const color = GROUP_COLORS[d.group] || GROUP_COLORS.other
      const [x1, y1, x2, y2] = d.box
      ctx.strokeStyle = color
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
      // 每个框各带自己的标签（同图多标签），框太靠顶时标签放到框内
      const label = `${d.label || d.class_name} ${Math.round((d.confidence || 0) * 100)}%`
      const tw = ctx.measureText(label).width + 10
      let ty = y1 - fontPx - 6
      if (ty < 0) ty = y1 + 2
      ctx.fillStyle = color
      ctx.fillRect(x1, ty, tw, fontPx + 6)
      ctx.fillStyle = '#ffffff'
      ctx.fillText(label, x1 + 5, ty + fontPx - 1)
    })
  }
  img.src = preview.value
}
async function analyze() {
  if (!file.value) return
  loading.value = true
  error.value = ''
  try {
    const resp = await analyzeTongue(file.value)
    result.value = resp.data
    if (result.value?.status === 'detected' || result.value?.status === 'demo') {
      savedFlag.value = false
      await drawBoxes()
    }
  } catch (e) {
    error.value = e.message || '舌体检测失败'
  } finally {
    loading.value = false
  }
}

// —— 保存为历史记录 ——
async function saveRecord() {
  if (!file.value || !result.value || savedFlag.value) return
  saving.value = true
  error.value = ''
  try {
    const resp = await saveTongueRecord(file.value, userId.value, '')
    if (resp.data) {
      savedFlag.value = true
      flash('已保存到舌象记录 ✓')
      await loadRecords()
    } else {
      flash(resp.message || '未检出清晰舌体，本次不保存')
    }
  } catch (e) {
    error.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// —— 历史记录与趋势 ——
async function loadRecords() {
  recordsLoading.value = true
  try {
    const resp = await getTongueRecords(userId.value)
    for (const url of imageUrls) URL.revokeObjectURL(url)
    imageUrls.clear()
    const rows = resp.data || []
    records.value = await Promise.all(rows.map(async (row) => {
      if (!row.image_url || !String(row.image_url).startsWith('/api/tongue/images/')) return row
      try {
        const blob = await getTongueImage(row.id)
        const url = URL.createObjectURL(blob)
        imageUrls.add(url)
        return { ...row, image_url: url }
      } catch {
        return { ...row, image_url: '' }
      }
    }))
  } catch (e) {
    error.value = e.message || '历史记录加载失败'
  } finally {
    recordsLoading.value = false
  }
}
function colorHex(colorText) {
  const c = colorText || ''
  if (c.includes('暗红') || c.includes('紫')) return '#9f1239'
  if (c.includes('偏红') || c === '红') return '#e11d48'
  if (c.includes('淡红')) return '#fda4af'
  if (c.includes('淡白')) return '#e2e8f0'
  return '#cbd5e1'
}
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const timeline = computed(() => [...records.value].reverse()) // 旧→新，最新在右
const trendSummary = computed(() => {
  if (records.value.length < 2) return ''
  const latest = records.value[0]
  const prev = records.value[1]
  const colorSame = latest.tongue_color === prev.tongue_color
  const latestCoat = latest.coat_type || latest.coat
  const previousCoat = prev.coat_type || prev.coat
  const coatSame = latestCoat === previousCoat
  const parts = []
  if (colorSame) parts.push(`舌色无明显变化（${latest.tongue_color}）`)
  else parts.push(`舌色由「${prev.tongue_color}」变为「${latest.tongue_color}」`)
  if (!coatSame) parts.push(`舌苔类型由「${previousCoat}」变为「${latestCoat}」`)
  return parts.join('；')
})

onMounted(loadRecords)
onBeforeUnmount(() => {
  for (const url of imageUrls) URL.revokeObjectURL(url)
})
</script>

<template>
  <div class="page-heading">
    <div>
      <span class="overline">TONGUE OBSERVATION · YOLO + TREND</span>
      <h1>舌体观察</h1>
      <p>上传舌象照片，定位舌体区域并观察颜色 / 苔质，保存后可查看历史趋势。</p>
    </div>
  </div>
  <div v-if="error" class="alert">{{ error }}</div>
  <div v-if="successMsg" class="success-banner">{{ successMsg }}</div>

  <div class="tongue-layout">
    <section class="card tongue-upload">
      <div class="upload-zone">
        <input type="file" accept="image/*" @change="pick" />
        <div v-if="!preview">选择或拖入舌象图片</div>
        <img v-else :src="preview" alt="待检测舌象" />
      </div>
      <button class="btn primary-btn full" :disabled="!file || loading" @click="analyze">
        {{ loading ? '检测中…' : '开始舌体分析' }}
      </button>
      <div class="disclaimer">仅供健康观察参考，不能替代医疗诊断；请避免在强光、滤镜或严重遮挡下拍摄。</div>
    </section>

    <section class="card tongue-result">
      <div class="card-title">检测结果</div>
      <div v-if="!result" class="empty-text">检测结果会显示在这里。</div>
      <div v-else>
        <div class="result-status" :class="result.status">
          {{ statusText() }}
          <span v-if="result.demo" class="demo-badge">DEMO</span>
        </div>
        <p v-if="result.message" class="muted">{{ result.message }}</p>
        <div v-if="result.best && preview" class="preview-wrap">
          <canvas ref="canvasRef" class="tongue-canvas"></canvas>
        </div>

        <!-- 检出特征（一张舌象可同时检出多项）；实测不稳的会带「慎用/不可用」角标 -->
        <div v-if="result.features?.length" class="feature-list">
          <span
            v-for="f in result.features"
            :key="f.code"
            class="feature-chip"
            :class="{ 'lv-weak': f.level === 'low', 'lv-off': f.level === 'unusable' }"
            :style="{ borderColor: GROUP_COLORS[f.group] || GROUP_COLORS.other, color: GROUP_COLORS[f.group] || GROUP_COLORS.other }"
            :title="chipTitle(f)"
          >{{ f.label }}<b>{{ Math.round(f.confidence * 100) }}%</b><i v-if="!f.reliable" class="lv-badge">{{ LEVEL_SHORT[f.level] || '?' }}</i></span>
          <span v-for="g in legendGroups" :key="g.key" class="legend-item">
            <i :style="{ background: GROUP_COLORS[g.key] }"></i>{{ g.label }}
          </span>
        </div>
        <p v-if="result.features?.some((f) => !f.reliable)" class="reliability-hint">
          带「慎用 / 不可用」角标的特征在测试集上识别不稳定，<b>未参与下方结论推导</b>，仅作检出展示。
        </p>

        <!-- 推导结论（每条都附依据，可溯源） -->
        <div v-if="result.conclusion" class="conclusion-box">
          <div class="advice-title">观察结论 <span class="muted" style="font-weight:400">（由检出特征按规则推导）</span></div>
          <div class="conclusion-row">
            <span class="c-label">舌色</span>
            <strong>{{ result.conclusion.tongue_color.value }}</strong>
            <span class="c-evidence">{{ result.conclusion.tongue_color.evidence }}</span>
          </div>
          <div class="conclusion-row">
            <span class="c-label">苔质</span>
            <strong>{{ result.conclusion.coat_color.value }}</strong>
            <span class="c-evidence">{{ result.conclusion.coat_color.evidence }}</span>
          </div>
          <div class="conclusion-row">
            <span class="c-label">覆盖范围</span>
            <strong>{{ result.conclusion.coat_thickness.value }}</strong>
            <span class="c-evidence">{{ result.conclusion.coat_thickness.evidence }}</span>
          </div>
          <div v-if="result.conclusion.morphology?.length" class="conclusion-row">
            <span class="c-label">形态特征</span>
            <strong>{{ result.conclusion.morphology.filter((m) => m.reliable).map((m) => m.label).join('、') || '未检出可信特征' }}</strong>
            <span class="c-evidence">
              置信度 {{ result.conclusion.morphology.filter((m) => m.reliable).map((m) => Math.round(m.confidence * 100) + '%').join(' / ') || '—' }}
            </span>
          </div>
          <div v-if="result.conclusion.morphology?.some((m) => !m.reliable)" class="conclusion-row">
            <span class="c-label">仅检出</span>
            <strong class="weak">{{ result.conclusion.morphology.filter((m) => !m.reliable).map((m) => m.label).join('、') }}</strong>
            <span class="c-evidence">模型测得不稳，未作为结论</span>
          </div>
          <p class="c-note">{{ result.conclusion.note }}</p>
          <ul v-if="result.capability_limits?.length" class="c-limits">
            <li v-for="(t, i) in result.capability_limits" :key="i">{{ t }}</li>
          </ul>
        </div>

        <!-- 通俗解读 + 可执行建议（用户能看懂的部分） -->
        <div v-if="result.advice" class="advice-box">
          <div class="advice-title">观察解读</div>
          <p class="advice-summary">{{ result.advice.summary }}</p>
          <div v-if="result.advice.constitution" class="constitution-box">
            <div class="constitution-heading">
              <span>体质倾向</span>
              <strong>{{ result.advice.constitution.label }}</strong>
            </div>
            <p class="constitution-plain">{{ result.advice.constitution.plain }}</p>
            <div v-if="result.advice.constitution.evidence?.length" class="constitution-evidence">
              观察依据：
              <span v-for="item in result.advice.constitution.evidence" :key="item">{{ item }}</span>
            </div>
          </div>
          <p class="advice-plain"><b>舌色：</b>{{ result.advice.color.plain }}</p>
          <p class="advice-plain"><b>舌苔：</b>{{ result.advice.coat.plain }}</p>
          <p class="advice-plain"><b>覆盖范围：</b>{{ result.advice.thickness.plain }}</p>
          <p v-for="m in result.advice.morphology" :key="m.label" class="advice-plain">
            <b>{{ m.label }}：</b>{{ m.plain }}
          </p>

          <div class="advice-title mt-8">接下来可以这样做</div>
          <ul class="advice-tips">
            <li v-for="tip in result.advice.tips" :key="tip">{{ tip }}</li>
          </ul>

          <p class="advice-quality">{{ result.advice.quality }}</p>
          <p class="advice-watch">{{ result.advice.watch }}</p>
        </div>

        <p v-if="result.best" class="tech-line">
          技术信息：检出 {{ result.detections?.length || 0 }} 个特征框
          · 模型类别数 {{ result.model_classes || '—' }}
          · 最高置信度 {{ (result.best.confidence * 100).toFixed(1) }}%
          · 图片 {{ result.image_size?.width || '—' }}×{{ result.image_size?.height || '—' }}
        </p>
        <button
          v-if="result.status === 'detected'"
          class="btn primary-btn full save-btn"
          :disabled="saving || savedFlag"
          @click="saveRecord"
        >
          {{ savedFlag ? '已保存到舌象记录 ✓' : saving ? '保存中…' : '保存到舌象记录' }}
        </button>
        <p class="disclaimer">{{ result.disclaimer }}</p>
      </div>
    </section>
  </div>

  <!-- 历史记录 & 趋势 -->
  <section class="card trend-card">
    <div class="card-title">舌象记录 · 趋势观察 <span class="muted" style="font-weight:400;font-size:12px">仅演示该用户 {{ userId }} 的保存记录</span></div>
    <div v-if="recordsLoading" class="loading-text">加载历史记录…</div>
    <div v-else-if="!records.length" class="empty-text">
      还没有保存记录。完成一次分析后点「保存到舌象记录」，多次保存即可查看舌色 / 苔质趋势。
    </div>
    <template v-else>
      <div v-if="trendSummary" class="trend-summary">📈 与上次对比：{{ trendSummary }}</div>
      <div class="trend-track">
        <div v-for="(r, i) in timeline" :key="r.id" class="trend-point">
          <span class="trend-line" v-if="i > 0"></span>
          <div class="trend-dot" :style="{ background: colorHex(r.tongue_color) }" :title="r.tongue_color"></div>
          <strong>{{ r.tongue_color }}</strong>
          <span class="muted">{{ r.coat_type || r.coat }}</span>
          <small>{{ fmtTime(r.created_at) }}</small>
        </div>
      </div>
      <div class="record-list">
        <div v-for="(r, index) in records" :key="r.id" class="record-row">
          <img v-if="r.image_url" :src="r.image_url" class="record-thumb" alt="舌象原图" />
          <div v-else class="record-thumb placeholder">无图</div>
          <div class="record-info">
            <div>
              <span class="record-no">第 {{ records.length - index }} 次</span>
              <span v-if="r.status === 'demo'" class="demo-badge">DEMO</span>
              <span class="muted" style="margin-left:8px">{{ fmtTime(r.created_at) }}</span>
            </div>
            <div>
              <span class="dot-inline" :style="{ background: colorHex(r.tongue_color) }"></span>
              舌色 <b>{{ r.tongue_color }}</b> · 舌苔类型 <b>{{ r.coat_type || r.coat }}</b>
              <span v-if="r.constitution?.label"> · 体质倾向 <b>{{ r.constitution.label }}</b></span>
              · 置信度 {{ (r.confidence * 100).toFixed(1) }}%
            </div>
            <p v-if="r.constitution?.plain" class="record-constitution">{{ r.constitution.plain }}</p>
            <p v-if="r.note" class="muted">{{ r.note }}</p>
          </div>
        </div>
      </div>
      <p class="disclaimer" style="margin-top:10px">趋势仅作图像观察参考，受光线 / 白平衡 / 拍摄角度影响，如有不适请及时就医。</p>
    </template>
  </section>
</template>

<style scoped>
/* 检出特征标签 + 分组图例 */
.feature-list { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 10px 0 4px; }
.feature-chip {
  display: inline-flex; align-items: baseline; gap: 4px;
  padding: 2px 9px; border-radius: 999px; border: 1px solid currentColor;
  font-size: 12px; background: rgba(255, 255, 255, .65);
}
.feature-chip b { font-weight: 700; font-size: 11px; opacity: .8; }
/* 可信度角标：low=斜纹虚线 / unusable=灰化加删除感 */
.feature-chip .lv-badge {
  font-style: normal; font-size: 10px; padding: 0 5px; border-radius: 999px;
  border: 1px dashed currentColor; opacity: .85;
}
.feature-chip.lv-weak { border-style: dashed; opacity: .75; }
.feature-chip.lv-off { border-style: dashed; opacity: .5; text-decoration: line-through; }
.feature-chip.lv-off .lv-badge, .feature-chip.lv-weak .lv-badge { text-decoration: none; }
.reliability-hint { margin: 4px 0 0; font-size: 11.5px; color: #8a94a6; }
.legend-item { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: #6b7280; }
.legend-item i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }

/* 推导结论（带依据） */
.conclusion-box {
  margin: 12px 0 4px; padding: 12px 14px;
  border: 1px solid rgba(14, 116, 144, .28); border-radius: 12px;
  background: rgba(240, 249, 255, .7);
}
.conclusion-row { display: flex; align-items: baseline; gap: 8px; padding: 3px 0; font-size: 13px; flex-wrap: wrap; }
.c-label { min-width: 62px; color: #6b7280; font-size: 12px; }
.conclusion-row strong { color: #0e7490; }
.conclusion-row strong.weak { color: #9aa3b2; font-weight: 500; }
.c-evidence { font-size: 11.5px; color: #8a94a6; }
.c-note { margin-top: 8px; font-size: 11.5px; color: #8a94a6; }
.c-limits { margin: 6px 0 0 16px; padding: 0; font-size: 11.5px; color: #8a94a6; }
.c-limits li { list-style: disc; }
html.dark .feature-chip { background: rgba(255, 255, 255, .06); }
html.dark .legend-item { color: #9aa3b2; }
html.dark .conclusion-box { background: rgba(14, 116, 144, .12); border-color: rgba(77, 227, 255, .25); }
html.dark .conclusion-row strong { color: #7fe3ff; }
html.dark .c-label, html.dark .c-evidence, html.dark .c-note { color: #9aa3b2; }
html.dark .reliability-hint, html.dark .c-limits { color: #9aa3b2; }
html.dark .conclusion-row strong.weak { color: #7d8798; }

/* 观察解读与建议 */
.advice-box {
  margin: 14px 0 6px; padding: 14px 16px;
  border: 1px solid rgba(95, 158, 63, .35); border-radius: 12px;
  background: rgba(234, 244, 220, .45);
}
.advice-title { font-size: 13px; font-weight: 700; color: var(--primary); margin-bottom: 8px; }
.advice-summary { margin: 0 0 8px; font-size: 13.5px; font-weight: 600; line-height: 1.6; }
.constitution-box {
  margin: 10px 0 12px; padding: 10px 12px;
  border-left: 3px solid #5f9e3f; background: rgba(255, 255, 255, .65);
  border-radius: 6px;
}
.constitution-heading { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-2); }
.constitution-heading strong { color: var(--primary); font-size: 15px; }
.constitution-plain { margin: 5px 0 6px; font-size: 13px; line-height: 1.7; }
.constitution-evidence { font-size: 11.5px; color: var(--text-2); }
.constitution-evidence span { display: inline-block; margin-left: 5px; padding: 1px 6px; border-radius: 999px; background: rgba(95, 158, 63, .12); color: var(--primary); }
.advice-plain { margin: 0 0 6px; font-size: 13px; line-height: 1.7; color: var(--text-2); }
.advice-tips { margin: 0 0 8px; padding-left: 18px; }
.advice-tips li { font-size: 13px; line-height: 1.8; }
.advice-quality { margin: 8px 0 4px; font-size: 12px; color: var(--text-2); }
.advice-watch { margin: 0; font-size: 12px; color: var(--text-2); line-height: 1.7; }
.tech-line { margin: 10px 0 0; font-size: 11.5px; color: var(--text-2); opacity: .85; }
html.dark .advice-box { background: rgba(52, 211, 153, .08); border-color: rgba(52, 211, 153, .3); }
html.dark .constitution-box { background: rgba(255, 255, 255, .06); }

.preview-wrap {
  margin: 12px 0;
  border-radius: 10px;
  overflow: hidden;
  background: #0a0e1a;
  display: flex;
  justify-content: center;
}
.tongue-canvas { max-width: 100%; height: auto; display: block; }
.demo-badge {
  display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 999px;
  font-size: 11px; letter-spacing: 0.08em; background: #fff4d6; color: #8a6d1a; vertical-align: 1px;
}
.success-banner {
  background: #d1fae5; color: #065f46; border-radius: 8px; padding: 8px 14px; margin-bottom: 10px; font-size: 13px;
}
.save-btn { margin-top: 12px; }

/* 历史趋势 */
.trend-card { margin-top: 16px; }
.trend-summary {
  background: #eef7fb; border: 1px solid #cfe3ee; border-radius: 10px;
  padding: 8px 14px; font-size: 13px; margin-bottom: 14px;
}
.trend-track { display: flex; align-items: flex-start; gap: 0; margin: 14px 2px; overflow-x: auto; padding-bottom: 4px; }
.trend-point { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 88px; position: relative; }
.trend-dot { width: 18px; height: 18px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 2px #dbe3ee; }
.trend-point strong { font-size: 12px; text-align: center; }
.trend-point small { color: #8a94a6; font-size: 11px; }
.trend-line { position: absolute; top: 9px; right: 50%; width: calc(100% - 18px); border-top: 2px dashed #dbe3ee; }
.trend-point:first-child .trend-line { display: none; }

.record-list { display: flex; flex-direction: column; gap: 10px; }
.record-row { display: flex; gap: 12px; align-items: flex-start; border: 1px solid var(--border, #e5ecf3); border-radius: 10px; padding: 8px; }
.record-thumb { width: 84px; height: 84px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
.record-thumb.placeholder {
  display: flex; align-items: center; justify-content: center; background: #eef1f6;
  color: #a5aebd; font-size: 12px;
}
.record-info { flex: 1; font-size: 13px; line-height: 1.7; }
.record-constitution { margin: 2px 0 0; color: var(--text-2); font-size: 12px; }
.record-no { font-weight: 600; color: #0e7490; }
.dot-inline { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; }
</style>
