<script setup>
import { computed, onMounted, ref } from 'vue'
import { getAdminOverview, getAdminDetails, getTongueEvaluation } from '../api'

const data = ref(null)
const loading = ref(true)
const error = ref('')
const tongueEval = ref(null)
const tongueEvalLoading = ref(false)
const tongueEvalError = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await getAdminOverview()
    data.value = resp.data
  } catch (e) {
    error.value = e.message || '运营数据加载失败'
  } finally {
    loading.value = false
  }
}

const cards = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    { label: '账号总数', value: d.users.accounts, sub: `健康画像 ${d.users.profiles}`, tone: 'mint' },
    { label: '今日对话', value: d.conversation.messages_today, sub: `累计消息 ${d.conversation.messages}`, tone: 'blue' },
    { label: '待审核内容', value: d.community.pending, sub: d.community.pending ? '需要处理' : '暂无积压', tone: 'amber' },
    { label: '累计测评', value: d.assessment.total, sub: `平均 ${d.assessment.avg_score} 分`, tone: 'rose' },
  ]
})

const trendMax = computed(() => Math.max(1, ...(data.value?.assessment.daily_trend || []).map((t) => t.count)))

const typeIcon = { assessment: '◒', social: '◌', meal: '▦', tongue: '◉' }
const typeLabel = { assessment: '测评', social: '社区', meal: '饮食', tongue: '舌象' }

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function downloadReport() {
  if (!data.value) return
  const blob = new Blob([JSON.stringify(data.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `healthybot_overview_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function gotoModeration() {
  window.dispatchEvent(new CustomEvent('app:switch-tab', { detail: 'community' }))
}

async function runTongueEvaluation() {
  tongueEvalLoading.value = true
  tongueEvalError.value = ''
  try {
    const resp = await getTongueEvaluation('test')
    tongueEval.value = resp.data
  } catch (e) {
    tongueEvalError.value = e.message || '舌象验收失败'
  } finally {
    tongueEvalLoading.value = false
  }
}

// 切换到其它管理页（统计卡与弹窗底部按钮共用）
function goto(tab) {
  window.dispatchEvent(new CustomEvent('app:switch-tab', { detail: tab }))
}

// —— 卡片点击：打开明细弹窗 + 提供跳转入口 ——
const modal = ref({ open: false, kind: '', tab: '', title: '' })
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')

const cardMeta = {
  账号总数: { kind: 'users', tab: '', tabLabel: '' },
  今日对话: { kind: 'conversations', tab: '', tabLabel: '' },
  待审核内容: { kind: 'posts', tab: 'community', tabLabel: '去内容审核台' },
  累计测评: { kind: 'assessments', tab: 'assessment', tabLabel: '去测评数据' },
}

async function openCard(label) {
  const meta = cardMeta[label]
  if (!meta) return
  modal.value = { open: true, kind: meta.kind, tab: meta.tab, title: label }
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const resp = await getAdminDetails(meta.kind, 20)
    detail.value = resp.data
  } catch (e) {
    detailError.value = e.message || '明细加载失败'
  } finally {
    detailLoading.value = false
  }
}

// 直接打开指定类型的明细（业务规模条目 / 最近动态共用）
async function openKind(kind, title) {
  modal.value = { open: true, kind, tab: '', title }
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const resp = await getAdminDetails(kind, 20)
    detail.value = resp.data
  } catch (e) {
    detailError.value = e.message || '明细加载失败'
  } finally {
    detailLoading.value = false
  }
}

// 最近动态类型 → 明细类型
function activityKind(type) {
  return { assessment: 'assessments', social: 'posts', meal: 'meals', tongue: 'tongue' }[type] || 'users'
}

function closeModal() {
  modal.value = { open: false, kind: '', tab: '', title: '' }
  detail.value = null
}

function openCardTab() {
  const tab = modal.value.tab
  closeModal()
  if (tab) goto(tab)
}

function fmtCell(v) {
  if (v === null || v === undefined || v === '') return '—'
  const str = String(v)
  return str.includes('T') && str.length > 16 ? str.replace('T', ' ').slice(0, 16) : str
}

onMounted(load)
</script>

<template>
  <div class="page-heading">
    <div>
      <span class="overline">ADMIN CONSOLE · {{ (data?.generated_at || '').slice(0, 10) || '—' }}</span>
      <h1>早上好，运营团队</h1>
      <p>这里是 HealthyBot 的健康服务全景（全部为真实业务数据）。</p>
    </div>
    <div class="head-actions">
      <button class="btn ghost" @click="load">↻ 刷新</button>
      <button class="btn primary-btn" :disabled="!data" @click="downloadReport">下载运营报告 ↓</button>
    </div>
  </div>

  <div v-if="error" class="alert">{{ error }}</div>
  <div v-if="loading" class="loading-text">正在汇总运营数据…</div>

  <template v-else-if="data">
    <div class="admin-stats">
      <button
        v-for="(c, i) in cards" :key="c.label"
        type="button"
        :class="['admin-stat', c.tone, 'clickable', 'photo-host']"
        :title="`点击查看${c.label}明细`"
        @click="openCard(c.label)"
      >
        <span class="photo-corner" :class="'ph-card-' + (i % 4 + 1)" aria-hidden="true"></span>
        <span>{{ c.label }}<em class="open-hint">查看明细 ›</em></span>
        <strong>{{ c.value }}</strong>
        <em>{{ c.sub }}</em>
      </button>
    </div>

    <section class="panel-card tongue-acceptance">
      <div class="section-label">舌象模型验收 <span>定位指标 · 分类真值缺失时明确标记</span></div>
      <div class="acceptance-actions">
        <button class="btn ghost" :disabled="tongueEvalLoading" @click="runTongueEvaluation">{{ tongueEvalLoading ? '验收计算中…' : '运行验收' }}</button>
        <span v-if="tongueEvalError" class="acceptance-error">{{ tongueEvalError }}</span>
      </div>
      <div v-if="tongueEval" class="acceptance-result">
        <span>测试图片 {{ tongueEval.image_count }}</span>
        <span>Precision {{ tongueEval.detection.precision }}</span>
        <span>Recall {{ tongueEval.detection.recall }} <b :class="tongueEval.acceptance.tongue_detection_recall_passed ? 'pass' : 'fail'">{{ tongueEval.acceptance.tongue_detection_recall_passed ? '达标' : '未达标' }}</b></span>
        <span>F1 {{ tongueEval.detection.f1 }}</span>
        <span class="classification-note">分类：{{ tongueEval.classification.status === 'not_evaluable' ? '不可评估（缺少舌色/苔质真值）' : '已评估' }}</span>
      </div>
    </section>

    <div class="admin-grid">
      <section class="admin-hero photo-host">
        <div class="photo-bg ph-hero-1 mask-deep" aria-hidden="true"></div>
        <div>
          <span class="overline">CONTENT HEALTH</span>
          <h2>社区内容{{ data.community.pending ? '有待审内容' : '运转正常' }}，<br>机器审核 + 人工复核双保险。</h2>
          <p>
            已发布 {{ data.community.published }} 条 / 共 {{ data.community.posts }} 条；
            评论 {{ data.community.comments }} · 点赞 {{ data.community.likes }}；
            待审 {{ data.community.pending }} · 已驳回 {{ data.community.rejected }}。
          </p>
          <button class="dark-btn" @click="gotoModeration">去内容审核台 →</button>
        </div>
        <div class="hero-number">{{ data.community.pass_rate }}<span>%</span><small>发布通过率</small></div>
      </section>

      <section class="activity-card">
        <div class="section-label">最近动态 <span>实时聚合</span></div>
        <div v-if="!data.activities.length" class="empty-text">暂无动态</div>
        <div
          v-for="(item, i) in data.activities" :key="i"
          class="activity-row"
          @click="openKind(activityKind(item.type), typeLabel[item.type] + '动态')"
        >
          <div class="post-avatar small photo-thumb" :class="'ph-thumb-' + (i % 2 + 1)">
            <span>{{ typeIcon[item.type] || '•' }}</span>
          </div>
          <div>
            <strong>{{ item.name }}</strong>
            <span>{{ item.action }}<em class="type-tag">{{ typeLabel[item.type] }}</em></span>
          </div>
          <time>{{ fmtTime(item.time) }}</time>
        </div>
      </section>
    </div>

    <div class="admin-grid lower">
      <section class="panel-card">
        <div class="section-label">近 14 天测评趋势 <span>共 {{ data.assessment.total }} 次</span></div>
        <div v-if="!data.assessment.daily_trend.length" class="empty-text">近 14 天暂无测评</div>
        <div v-else class="mini-bars">
          <div v-for="t in data.assessment.daily_trend" :key="t.date" class="bar-wrap" :title="`${t.date} · ${t.count} 次`">
            <div class="bar" :style="{ height: Math.max(6, Math.round(t.count / trendMax * 100)) + '%' }"></div>
            <small>{{ t.date.slice(5) }}</small>
          </div>
        </div>
        <div class="risk-row">
          <span v-for="(v, k) in data.assessment.risk_distribution" :key="k" class="risk-chip" :class="k">{{ k }} {{ v }}</span>
        </div>
      </section>

      <section class="panel-card">
        <div class="section-label">业务规模</div>
        <div class="scale-grid">
          <button type="button" class="scale-cell" @click="openCard('累计测评')"><strong>{{ data.assessment.total }}</strong><span>测评记录 ›</span></button>
          <button type="button" class="scale-cell" @click="openKind('meals', '饮食记录')"><strong>{{ data.meals.total }}</strong><span>饮食记录 ›</span></button>
          <button type="button" class="scale-cell" @click="openKind('tongue', '舌象记录')"><strong>{{ data.tongue.total }}</strong><span>舌象记录 ›</span></button>
          <button type="button" class="scale-cell" @click="openCard('今日对话')"><strong>{{ data.conversation.conversations }}</strong><span>AI 会话 ›</span></button>
          <button type="button" class="scale-cell" @click="openKind('knowledge', '知识文件')"><strong>{{ data.knowledge.files }}</strong><span>知识文件 ›</span></button>
          <button type="button" class="scale-cell" @click="openKind('users', '健康画像')"><strong>{{ data.users.profiles }}</strong><span>健康画像 ›</span></button>
        </div>
      </section>
    </div>

    <!-- 明细弹窗 -->
    <div v-if="modal.open" class="detail-mask" @click.self="closeModal">
      <div class="detail-modal">
        <div class="detail-head">
          <div>
            <span class="overline">DETAIL</span>
            <h3>{{ detail?.title || modal.title }}</h3>
          </div>
          <button class="detail-close" @click="closeModal">✕</button>
        </div>

        <div v-if="detailLoading" class="loading-text">明细加载中…</div>
        <div v-else-if="detailError" class="alert">{{ detailError }}</div>
        <div v-else-if="!detail?.rows?.length" class="empty-text">暂无明细数据</div>

        <div v-else class="detail-body">
          <table class="data detail-table">
            <thead>
              <tr><th v-for="col in detail.columns" :key="col">{{ col }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in detail.rows" :key="i">
                <td v-for="col in detail.columns" :key="col">{{ fmtCell(row[col]) }}</td>
              </tr>
            </tbody>
          </table>
          <div class="detail-foot">共 {{ detail.total }} 条（最多展示 20 条）</div>
        </div>

        <div class="detail-actions">
          <button class="btn ghost" @click="closeModal">关闭</button>
          <button
            v-if="cardMeta[modal.title]?.tabLabel"
            class="btn primary-btn"
            @click="openCardTab"
          >{{ cardMeta[modal.title].tabLabel }} →</button>
        </div>
      </div>
    </div>
  </template>
</template>

<style scoped>
.head-actions { display: flex; gap: 8px; align-items: center; }

/* —— 可点击卡片 / 条目 —— */
.admin-stat.clickable { cursor: pointer; text-align: left; font: inherit; border: none; width: 100%; transition: transform .18s, box-shadow .18s, border-color .18s; }
.admin-stat.clickable:hover { transform: translateY(-3px); box-shadow: 0 16px 34px -18px rgba(0, 0, 0, .55); border-color: rgba(77, 227, 255, .45); }
.admin-stat.clickable:active { transform: translateY(-1px); }
.open-hint { display: block; font-size: 11px; font-style: normal; opacity: .75; margin-top: 4px; font-weight: 500; }
.scale-cell {
  display: flex; flex-direction: column; gap: 2px; align-items: flex-start;
  border: 1px solid transparent; border-radius: 10px; padding: 6px 8px; margin: -6px -8px;
  background: transparent; color: inherit; font: inherit; cursor: pointer; transition: background .15s, border-color .15s;
}
.scale-cell:hover { background: rgba(77, 227, 255, .08); border-color: rgba(77, 227, 255, .3); }
.scale-cell strong { font-size: 22px; }
.scale-cell span { font-size: 12px; color: var(--muted); }
.activity-row { cursor: pointer; border-radius: 10px; transition: background .15s; }
.activity-row:hover { background: rgba(77, 227, 255, .07); }

/* —— 明细弹窗 —— */
.detail-mask {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(4, 8, 24, .62); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; padding: 32px 20px;
}
.detail-modal {
  width: min(980px, 100%); max-height: 86vh; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--card, #fff); border: 1px solid var(--border, #e3e8ef);
  border-radius: 18px; box-shadow: 0 30px 70px -30px rgba(0, 0, 0, .6);
}
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px 24px 14px; }
.detail-head h3 { margin: 6px 0 0; font-size: 19px; }
.detail-close { border: none; background: transparent; color: var(--muted); font-size: 17px; cursor: pointer; }
.detail-close:hover { color: var(--danger); }
.detail-body { overflow: auto; padding: 0 24px; }
.detail-table { width: 100%; font-size: 13px; }
.detail-table th, .detail-table td { white-space: nowrap; }
.detail-table td:last-child, .detail-table th:last-child { white-space: normal; }
.detail-foot { padding: 10px 0 4px; font-size: 12px; color: var(--muted); }
.detail-actions { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 24px 20px; border-top: 1px solid var(--border, #e3e8ef); margin-top: 8px; }

.admin-grid.lower { margin-top: 16px; grid-template-columns: 1.4fr 1fr; }
.panel-card {
  background: var(--card, #fff); border: 1px solid var(--border, #e5ecf3);
  border-radius: 14px; padding: 16px 18px;
}
.type-tag {
  display: inline-block; margin-left: 8px; padding: 1px 7px; border-radius: 999px;
  font-size: 11px; font-style: normal; background: #eef7fb; color: #0e7490;
}
.mini-bars { display: flex; align-items: flex-end; gap: 6px; height: 120px; margin: 10px 0 6px; }
.bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 4px; }
.bar { width: 100%; background: linear-gradient(180deg, #4de3ff, #0e7490); border-radius: 4px 4px 2px 2px; min-height: 4px; }
.bar-wrap small { font-size: 10px; color: #8a94a6; white-space: nowrap; transform: scale(.92); }
.risk-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.risk-chip { font-size: 12px; padding: 3px 10px; border-radius: 999px; background: #f1f5f9; color: #475569; }
.risk-chip.高风险 { background: #fee2e2; color: #b91c1c; }
.risk-chip.中风险 { background: #ffedd5; color: #b45309; }
.risk-chip.低风险 { background: #e0f2fe; color: #0369a1; }
.risk-chip.无风险 { background: #dcfce7; color: #15803d; }
.scale-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 10px; }
.scale-grid div { display: flex; flex-direction: column; gap: 2px; }
.scale-grid strong { font-size: 22px; color: #0f172a; }
.scale-grid span { font-size: 12px; color: #8a94a6; }
.tongue-acceptance { margin-top: 16px; }
.acceptance-actions { display: flex; align-items: center; gap: 12px; margin-top: 10px; }
.acceptance-result { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 14px; color: var(--muted, #687386); font-size: 13px; }
.acceptance-result b { margin-left: 4px; font-weight: 700; } .acceptance-result .pass { color: #15803d; } .acceptance-result .fail { color: #b45309; }
.classification-note { flex-basis: 100%; color: #8b6d3b; }
.acceptance-error { color: #b91c1c; font-size: 12px; }
</style>
