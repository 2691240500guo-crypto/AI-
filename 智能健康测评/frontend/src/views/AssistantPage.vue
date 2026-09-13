<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import {
  analyzeMeal,
  confirmMeal,
  currentUserId,
  createPrivacyMemory,
  deleteConversation,
  deletePrivacyMemory,
  erasePrivacyData,
  exportPrivacyData,
  getAssistantProfile,
  getConversationMessages,
  getConversations,
  getDailyMeals,
  getPrivacyMemories,
  getPrivacyStatus,
  renameConversation,
  sendAssistantMessage,
  updateAssistantProfile,
  updatePrivacyConsent,
  synthesizeSpeech,
  transcribeVoice,
} from '../api'
// eslint-disable-next-line no-unused-vars -- 卡片头开关/气泡标注在使用（会被 IDE「优化导入」误删，勿清理）
import { graphRagEnabled, toggleGraphRag, initGraphRag } from '../graph-rag'

// 使用登录账号作为业务用户 ID，跨刷新/跨页面归属同一用户（不再每次随机生成）
const userId = ref(currentUserId('user'))
const profile = reactive({
  user_name: '演示用户', sex: '其他', age: null, height_cm: null, weight_kg: null,
  goal: '保持健康', allergies: '', conditions: '', preferences: '',
})
const messages = ref([])
// —— 消息区滚动：智能跟随（用户在底部时自动跟随，上翻看历史时不打断）——
const messagesRef = ref(null)
const atBottom = ref(true)

async function scrollToBottom(smooth = true) {
  await nextTick()
  const el = messagesRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  atBottom.value = true
}

/** 距底部 <80px 视为「在底部」：用户主动上翻时不被强行拽回 */
function onMessagesScroll() {
  const el = messagesRef.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

/** 点击输入框：直接回到最新一条对话 */
function onComposeFocus() {
  if (!atBottom.value) scrollToBottom()
}
const draft = ref('')
const conversationId = ref(null)
const chatLoading = ref(false)
const pageError = ref('')
const successMsg = ref('')
const profileSaved = ref(false)
// 过敏/疾病、基础疾病为必填项：AI 要据此避讳过敏原与饮食禁忌，缺失会导致推送不安全
const needProfile = ref(false)      // 画像未完善时需要就近提示
const profileCardRef = ref(null)

/** 画像必填项缺失清单（空字符串视为未填；填「无」也算明确作答） */
const missingProfileFields = computed(() => {
  const miss = []
  if (!String(profile.allergies || '').trim()) miss.push('过敏 / 疾病')
  if (!String(profile.conditions || '').trim()) miss.push('基础疾病')
  return miss
})
const profileComplete = computed(() => missingProfileFields.value.length === 0)
const selectedFile = ref(null)
const mealLoading = ref(false)
const mealResult = ref(null)
const mealDate = ref(new Date().toISOString().slice(0, 10))
const mealType = ref('午餐')
const daily = ref({ meals: [], totals: {}, score: 0, score_message: '', target_calories: 2000, meal_count: 0 })
// —— 语音输入状态：idle 待命 / recording 录音中 / transcribing 转写中 ——
const voiceState = ref('idle')
const recording = computed(() => voiceState.value === 'recording')
const voiceSeconds = ref(0)
const voiceError = ref('')          // 就近提示：显示在输入框下方，不放页面顶部
const voiceText = ref('')
const memories = ref([])
const memoryDraft = ref('')
const privacy = reactive({ consent: false, encryption_configured: false })
const needConsent = ref(false)      // 未同意隐私说明时需要就近提示
const pendingText = ref('')         // 同意后自动补发的内容
const privacyLoading = ref(false)
let recorder
let voiceChunks = []

const totals = computed(() => daily.value.totals || {})
const mealTotals = computed(() => {
  const items = mealResult.value?.items || []
  return items.reduce((sum, item) => ({
    calories: sum.calories + Number(item.calories || 0),
    protein_g: sum.protein_g + Number(item.protein_g || 0),
    fat_g: sum.fat_g + Number(item.fat_g || 0),
    carbs_g: sum.carbs_g + Number(item.carbs_g || 0),
  }), { calories: 0, protein_g: 0, fat_g: 0, carbs_g: 0 })
})

// —— 餐照识别：图片预览 + 结果可视化 ——
const selectedImageURL = ref('')   // 本地 blob 预览地址
const mealBarRef = ref(null)       // 各食物热量柱状图
const mealPieRef = ref(null)       // 三大营养素环形图
let mealBarChart = null
let mealPieChart = null

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function fmtSize(bytes) {
  if (bytes == null) return ''
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function setSelectedFile(file) {
  if (selectedImageURL.value) { URL.revokeObjectURL(selectedImageURL.value); selectedImageURL.value = '' }
  selectedFile.value = file
  if (file) selectedImageURL.value = URL.createObjectURL(file)
}

function clearSelectedFile() {
  setSelectedFile(null)
}

function handleChartResize() {
  mealBarChart?.resize()
  mealPieChart?.resize()
}

/** 食物列表变化时重画两张图（识别结果 / 手动编辑都实时联动） */
function renderMealCharts() {
  const items = (mealResult.value?.items || []).filter((it) => it.name?.trim())
  const ink = cssVar('--ink', '#333')
  const grid = 'rgba(128,128,128,.18)'
  if (items.length && mealBarRef.value) {
    mealBarChart ||= echarts.init(mealBarRef.value)
    mealBarChart.setOption({
      title: { text: '各食物热量 (kcal)', left: 'center', top: 6, textStyle: { color: ink, fontSize: 13 } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 10, right: 42, top: 34, bottom: 6, containLabel: true },
      xAxis: { type: 'value', axisLabel: { color: ink }, splitLine: { lineStyle: { color: grid } } },
      yAxis: { type: 'category', data: items.map((it) => it.name), axisLabel: { color: ink, width: 80, overflow: 'truncate' }, axisLine: { lineStyle: { color: grid } } },
      series: [{
        name: '热量', type: 'bar', barMaxWidth: 16,
        data: items.map((it) => ({ value: Number(it.calories) || 0, name: it.name })),
        itemStyle: { borderRadius: [0, 8, 8, 0], color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#8fdc9e' }, { offset: 1, color: '#3fa96f' }]) },
        label: { show: true, position: 'right', color: ink, fontSize: 11 },
      }],
    }, true)
    mealBarChart.resize()
  } else if (mealBarChart) { mealBarChart.dispose(); mealBarChart = null }
  if (items.length && mealPieRef.value) {
    mealPieChart ||= echarts.init(mealPieRef.value)
    mealPieChart.setOption({
      title: { text: '三大营养素占比 (g)', left: 'center', top: 6, textStyle: { color: ink, fontSize: 13 } },
      tooltip: { trigger: 'item', formatter: '{b}: {c} g ({d}%)' },
      legend: { bottom: 4, textStyle: { color: ink, fontSize: 11 }, itemWidth: 12, itemHeight: 8 },
      series: [{
        type: 'pie', radius: ['42%', '66%'], center: ['50%', '52%'],
        data: [
          { name: '蛋白质', value: Math.round(mealTotals.value.protein_g * 10) / 10, itemStyle: { color: '#5B8FF9' } },
          { name: '脂肪', value: Math.round(mealTotals.value.fat_g * 10) / 10, itemStyle: { color: '#F6BD16' } },
          { name: '碳水', value: Math.round(mealTotals.value.carbs_g * 10) / 10, itemStyle: { color: '#5AD8A6' } },
        ],
        label: { color: ink, fontSize: 11, formatter: '{b} {d}%' },
        emphasis: { scaleSize: 4 },
      }],
    }, true)
    mealPieChart.resize()
  } else if (mealPieChart) { mealPieChart.dispose(); mealPieChart = null }
}
watch(() => mealResult.value?.items, () => nextTick(renderMealCharts), { deep: true })

// —— 会话管理 ——
const conversations = ref([])
const convLoading = ref(false)
const agentLabels = { nutrition: '营养师 Agent', exercise: '运动 Agent', sleep: '睡眠 Agent', health: '健康管理 Agent' }

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadConversations() {
  convLoading.value = true
  try {
    const resp = await getConversations(userId.value)
    conversations.value = resp.data || []
  } catch (e) {
    /* 会话列表失败不阻塞主流程 */
  } finally {
    convLoading.value = false
  }
}

async function openConversation(conv) {
  if (conv.id === conversationId.value) return
  try {
    const resp = await getConversationMessages(conv.id, userId.value)
    const data = resp.data || {}
    conversationId.value = data.conversation_id
    messages.value = (data.messages || []).map((m) => ({
      role: m.role,
      content: m.content,
      agent: m.role === 'assistant' ? (agentLabels[m.agent] || '') : '',
    }))
    // 历史接口同时返回 LangGraph 运行轨迹；按最终回答挂回对应消息，支持旧会话回放。
    for (const run of (data.agent_runs || [])) {
      const target = [...messages.value].reverse().find((m) => m.role === 'assistant' && m.content === run.final_answer)
      if (!target) continue
      target.agentPlan = (run.agent_plan || []).map((key) => agentLabels[key] || key)
      target.agentTrace = (run.steps || []).map((step) => ({
        agent: agentLabels[step.agent] || step.agent,
        answer: step.output_text || '',
        toolCalls: step.tool_calls || [],
        sources: step.sources || [],
      }))
      target.stepCount = target.agentTrace.length
      // 历史回放：从工具轨迹反推当时是否走了图谱，保证旧会话也能正确标注
      const graphCalls = (run.steps || [])
        .flatMap((step) => step.tool_calls || [])
        .filter((call) => call.name === 'graph_search')
      if ((run.steps || []).length) {
        target.graphEnabled = graphCalls.length > 0
        target.graphDiseases = [...new Set(graphCalls.flatMap((call) => call.diseases || []))]
      }
    }
    pageError.value = ''
    await scrollToBottom(false)   // 打开历史会话：直接落到最新一条，不播动画
  } catch (e) {
    pageError.value = e.message || '会话读取失败'
  }
}

function newConversation() {
  conversationId.value = null
  messages.value = []
  pageError.value = ''
  flash('已开启新对话')
}

async function renameConv(conv) {
  const title = window.prompt('重命名会话', conv.title)
  if (!title || !title.trim()) return
  try {
    await renameConversation(conv.id, title.trim(), userId.value)
    await loadConversations()
    flash('已重命名')
  } catch (e) {
    pageError.value = e.message || '重命名失败'
  }
}

async function deleteConv(conv) {
  if (!window.confirm(`删除会话「${conv.title}」？该会话的历史消息将一并删除。`)) return
  try {
    await deleteConversation(conv.id, userId.value)
    if (conversationId.value === conv.id) newConversation()
    await loadConversations()
    flash('会话已删除')
  } catch (e) {
    pageError.value = e.message || '删除失败'
  }
}

// 演示快捷问句：方便答辩快速展示三种能力
const quickPrompts = [
  '帮我制定一份 7 天减脂饮食计划',
  '帮我记一下：早餐吃了两个鸡蛋和一杯牛奶',
  '最近睡眠浅，深睡很少，怎么改善？',
  '我在减脂，最近睡眠浅，运动也没力气，怎么安排？',
]
function usePrompt(text) {
  draft.value = text
  pendingText.value = text
  sendMessage()
}

function flash(msg) {
  successMsg.value = msg
  setTimeout(() => { successMsg.value = '' }, 2600)
}

async function load() {
  try {
    const [p, d] = await Promise.all([
      getAssistantProfile(userId.value),
      getDailyMeals(userId.value, mealDate.value),
    ])
    Object.assign(profile, p.data || {})
    daily.value = d.data || daily.value
  } catch (e) {
    pageError.value = e.message || '助手数据加载失败'
  }
}

async function loadPrivacy() {
  privacyLoading.value = true
  try {
    const [statusResp, memoryResp] = await Promise.all([getPrivacyStatus(), getPrivacyMemories()])
    Object.assign(privacy, statusResp.data || {})
    privacy.consent = Boolean(statusResp.data?.consent?.granted)
    memories.value = memoryResp.data || []
  } catch (e) {
    pageError.value = e.message || '隐私设置加载失败'
  } finally {
    privacyLoading.value = false
  }
}

async function toggleConsent() {
  try {
    const resp = await updatePrivacyConsent({ granted: !privacy.consent, policy_version: 'v1.0' })
    privacy.consent = Boolean(resp.data?.granted)
    flash(privacy.consent ? '已同意健康数据使用说明' : '已撤回健康数据使用同意')
    // 若是「同意并继续」触发，请同意后立刻把待发送内容发出去
    if (privacy.consent && needConsent.value) {
      needConsent.value = false
      const text = (pendingText.value || draft.value || '').trim()
      pendingText.value = ''
      if (text) {
        draft.value = text
        await sendMessage()
      }
    }
  } catch (e) {
    pageError.value = e.message || '同意状态更新失败'
  }
}

/** 未同意时点「同意并继续」：授权成功后自动发送刚才的问题 */
async function grantAndContinue() {
  if (privacy.consent) {
    const text = (draft.value || '').trim()
    if (text) await sendMessage()
    return
  }
  await toggleConsent()
}

async function addMemory() {
  const content = memoryDraft.value.trim()
  if (!content) return
  if (!privacy.consent) {
    pageError.value = '请先同意健康数据使用说明'
    return
  }
  try {
    const resp = await createPrivacyMemory({ content })
    memories.value = [resp.data, ...memories.value.filter((item) => item.id !== resp.data?.id)]
    memoryDraft.value = ''
    flash('已保存到长期记忆')
  } catch (e) {
    pageError.value = e.message || '长期记忆保存失败'
  }
}

async function removeMemory(memory) {
  try {
    await deletePrivacyMemory(memory.id)
    memories.value = memories.value.filter((item) => item.id !== memory.id)
    flash('长期记忆已删除')
  } catch (e) {
    pageError.value = e.message || '长期记忆删除失败'
  }
}

/** 把导出的原始数据整理成用户看得懂的文字报告（不是 JSON） */
function buildReadableReport(d) {
  const L = []
  const pad = (n) => String(n).padStart(2, '0')
  const fmtTime = (v) => {
    if (!v) return '—'
    const s = String(v).replace('T', ' ')
    return s.length > 16 ? s.slice(0, 16) : s
  }
  const show = (v) => (v === null || v === undefined || v === '' ? '无记录' : v)
  const row = (k, v) => L.push(`  ${k}：${show(v)}`)

  const prof = d.profile || {}
  const consent = d.consent || {}
  const meals = d.meals || []
  const tongues = d.tongue_records || []
  const plans = d.plans || []
  const convs = d.conversations || []
  const assess = d.assessments || []
  const memories = d.memories || []
  const posts = d.community?.posts || []
  const msgTotal = convs.reduce((n, c) => n + (c.messages?.length || 0), 0)

  L.push('HealthyBot 健康数据导出报告')
  L.push('====================================')
  L.push(`导出时间：${fmtTime(d.exported_at)}`)
  L.push(`账号：${show(prof.user_name || d.user_id)}`)
  L.push('')

  L.push('一、基本资料')
  row('昵称', prof.user_name)
  row('性别', prof.sex)
  row('年龄', prof.age ? `${prof.age} 岁` : '')
  row('身高 / 体重', (prof.height_cm || prof.weight_kg)
    ? `${prof.height_cm || '—'} 厘米 / ${prof.weight_kg || '—'} 公斤` : '')
  row('健康目标', prof.goal)
  row('过敏情况', prof.allergies)
  row('基础疾病', prof.conditions)
  row('饮食偏好', prof.preferences)
  L.push('')

  L.push('二、隐私授权状态')
  row('健康数据使用授权', consent.granted
    ? `已同意（${fmtTime(consent.agreed_at)}）`
    : (consent.revoked_at ? `已撤回（${fmtTime(consent.revoked_at)}）` : '未同意'))
  row('授权说明版本', consent.policy_version)
  L.push('')

  L.push('三、健康记录概览')
  row('营养风险测评', `${assess.length} 条`)
  row('饮食记录', `${meals.length} 条`)
  row('舌象观察', `${tongues.length} 条`)
  row('饮食计划', `${plans.length} 份`)
  row('AI 健康问答', `${convs.length} 个会话（共 ${msgTotal} 条消息）`)
  row('长期记忆', `${memories.length} 条`)
  row('社区动态', `${posts.length} 条`)
  L.push('')

  L.push('四、记录明细')
  L.push('')
  L.push('【营养风险测评】')
  if (!assess.length) L.push('  暂无记录')
  assess.slice(0, 20).forEach((a) => {
    L.push(`  · ${fmtTime(a.assessment_time)}　总分 ${show(a.total_score)}/7　风险等级：${show(a.risk_level)}`)
  })
  L.push('')
  L.push('【饮食记录】')
  if (!meals.length) L.push('  暂无记录')
  meals.slice(0, 20).forEach((m) => {
    const items = (Array.isArray(m.items) ? m.items : []).map((i) => i?.name || i?.food || '').filter(Boolean).join('、')
    L.push(`  · ${show(m.meal_date)} ${show(m.meal_type)}　${items || m.note || '未记录食物'}　${Math.round(m.calories || 0)} 千卡`)
  })
  L.push('')
  L.push('【舌象观察】')
  if (!tongues.length) L.push('  暂无记录')
  tongues.slice(0, 20).forEach((t) => {
    const status = t.status === 'demo' ? '演示规则观察' : show(t.status)
    L.push(`  · ${fmtTime(t.created_at)}　舌色：${show(t.tongue_color)}　状态：${status}`)
  })
  L.push('')
  L.push('【饮食计划】')
  if (!plans.length) L.push('  暂无记录')
  plans.slice(0, 10).forEach((pl) => {
    const st = { pending_review: '待营养师审核', approved: '已通过', rejected: '已驳回' }[pl.status] || show(pl.status)
    L.push(`  · ${show(pl.set_label)}　目标 ${show(pl.calories_target)} 千卡/天　${pl.days || '—'} 天　状态：${st}`)
    if (pl.review_note) L.push(`      营养师备注：${pl.review_note}`)
  })
  L.push('')
  L.push('【AI 健康问答】')
  if (!convs.length) L.push('  暂无记录')
  convs.slice(0, 15).forEach((c) => {
    L.push(`  · ${fmtTime(c.updated_at)}　${show(c.title)}（${c.messages?.length || 0} 条消息）`)
  })
  L.push('')
  L.push('【长期记忆】')
  if (!memories.length) L.push('  暂无记录')
  memories.slice(0, 20).forEach((m) => L.push(`  · ${show(m.content)}`))
  L.push('')
  L.push('【社区动态】')
  if (!posts.length) L.push('  暂无记录')
  posts.slice(0, 20).forEach((po) => {
    const text = String(po.content || '').replace(/\s+/g, ' ').slice(0, 40)
    L.push(`  · ${fmtTime(po.created_at)}　${text}${text.length >= 40 ? '…' : ''}`)
  })
  L.push('')
  L.push('====================================')
  L.push('本报告由 HealthyBot 生成，仅供个人健康数据留存与参考，不构成医疗诊断建议。')
  return L.join('\n')
}

async function downloadPrivacyData() {
  try {
    const resp = await exportPrivacyData()
    const report = buildReadableReport(resp.data || {})
    // 加 BOM，保证 Windows 记事本打开不乱码
    const blob = new Blob(['\ufeff' + report], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const stamp = new Date().toISOString().slice(0, 10)
    link.href = url
    link.download = `HealthyBot-健康数据报告-${userId.value}-${stamp}.txt`
    link.click()
    URL.revokeObjectURL(url)
    flash('已导出可读版健康数据报告（.txt）')
  } catch (e) {
    pageError.value = e.message || '数据导出失败'
  }
}

async function eraseHealthData() {
  if (!window.confirm('将删除画像、会话、测评、饮食、舌象、计划和社区数据，登录账号保留。确认继续吗？')) return
  try {
    await erasePrivacyData()
    memories.value = []
    messages.value = []
    conversationId.value = null
    privacy.consent = false
    flash('健康数据已删除，登录账号仍保留')
  } catch (e) {
    pageError.value = e.message || '健康数据删除失败'
  }
}

/** 拦截提示条上的「去完善画像」：滚动到右侧画像卡片并聚焦第一个必填框 */
function scrollToProfile() {
  profileCardRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  profileCardRef.value?.querySelector('textarea')?.focus()
}

async function saveProfile() {
  if (!profileComplete.value) {
    pageError.value = `请先填写必填项：${missingProfileFields.value.join('、')}（没有就填「无」），AI 需要据此避开过敏原和饮食禁忌`
    return
  }
  profileSaved.value = false
  try {
    const resp = await updateAssistantProfile(userId.value, profile)
    Object.assign(profile, resp.data || {})
    profileSaved.value = true
    flash('健康画像已保存，后续建议将更贴合你的情况')
    setTimeout(() => { profileSaved.value = false }, 1800)
    // 若此前发送被「画像未完善」拦截，保存成功后自动补发
    if (needProfile.value) {
      needProfile.value = false
      const text = (pendingText.value || draft.value || '').trim()
      pendingText.value = ''
      if (text) {
        draft.value = text
        await sendMessage()
      }
    }
  } catch (e) {
    pageError.value = e.message || '画像保存失败'
  }
}

/**
 * 确认健康数据授权。
 * 前端缓存可能过期（例如在别处已授权），所以本地为 false 时先向服务端复核一次，
 * 只有服务端也确认未授权才拦截——避免出现「点发送毫无反应」的情况。
 */
async function ensureConsent() {
  if (privacy.consent) return true
  try {
    const resp = await getPrivacyStatus()
    privacy.consent = Boolean(resp.data?.consent?.granted)
  } catch (e) {
    /* 复核失败则维持本地判断 */
  }
  return privacy.consent
}

async function sendMessage() {
  const text = draft.value.trim()
  if (!text || chatLoading.value) return
  if (!(await ensureConsent())) {
    // 就近提示：输入框上方会出现提示条，点「同意并发送」后自动补发这句
    needConsent.value = true
    pendingText.value = text
    pageError.value = ''
    return
  }
  needConsent.value = false
  if (!profileComplete.value) {
    // 就近提示：必填画像缺失时拦截发送，保存画像后自动补发这句
    needProfile.value = true
    pendingText.value = text
    pageError.value = ''
    return
  }
  needProfile.value = false
  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  chatLoading.value = true
  pageError.value = ''
  scrollToBottom()   // 发送后立即跟随到底部（含「正在生成」气泡）
  try {
    const resp = await sendAssistantMessage({
      user_id: userId.value,
      conversation_id: conversationId.value,
      message: text,
      // 请求级图谱开关：随每次提问下发，切换后立即生效，无需重启后端
      use_graph: graphRagEnabled.value,
    })
    const answer = resp.data || {}
    conversationId.value = answer.conversation_id
    const msg = {
      role: 'assistant',
      content: answer.answer || '',
      agent: answer.agent_label || '',
      // 标注这条回答是否用到了图谱（null = 结构化分支，不标注）
      graphEnabled: answer.graph_enabled,
      graphDiseases: answer.graph_diseases || [],
    }
    if (answer.agent_plan?.length) {
      msg.agentPlan = answer.agent_plan.map((key) => agentLabels[key] || key)
      msg.agentTrace = (answer.agent_trace || []).map((step) => ({
        agent: agentLabels[step.agent] || step.agent,
        answer: step.answer || '',
      }))
      msg.stepCount = answer.step_count || msg.agentTrace.length
    }
    if (answer.plan) msg.plan = answer.plan                 // 饮食计划卡片
    // 这条计划回复是 LLM 叙述还是模板兜底（答辩时可直接看到模型被调用）
    if (answer.plan) msg.narrationSource = answer.narration_source || ''
    if (answer.meal_draft) {                                // 记饮食：待确认草稿
      msg.mealDraft = {
        items: answer.meal_draft.items || [],
        meal_type: answer.meal_draft.meal_type || mealType.value,
        calories: answer.meal_draft.calories || 0,
        saved: false,
      }
    }
    messages.value.push(msg)
    if (atBottom.value) scrollToBottom()   // 用户在底部时才自动跟随，翻历史不打扰
    loadConversations()   // 刷新会话列表标题 / 时间
  } catch (e) {
    pageError.value = e.message || '发送失败'
  } finally {
    chatLoading.value = false
  }
}

/** AI 生成的饮食计划 → 缓存并跳到「饮食计划」页 */
function applyPlan(plan) {
  if (!plan) return
  try {
    localStorage.setItem('healthybot_plan_draft', JSON.stringify({ ...plan, generated_at: Date.now(), source: 'ai' }))
  } catch (e) { /* ignore */ }
  window.dispatchEvent(new CustomEvent('app:switch-tab', { detail: 'meal-plan' }))
}

/** 确认并保存对话中识别出的饮食草稿 */
async function saveDraft(msg) {
  if (!msg?.mealDraft?.items?.length || msg.mealDraft.saved) return
  try {
    await confirmMeal({
      user_id: userId.value,
      meal_type: msg.mealDraft.meal_type || mealType.value,
      meal_date: mealDate.value,
      items: msg.mealDraft.items,
      note: 'AI 对话智能记录',
    })
    msg.mealDraft.saved = true
    flash('已保存进今日饮食记录 ✓')
    await refreshDaily()
  } catch (e) {
    pageError.value = e.message || '保存失败'
  }
}

function onFile(event) {
  const file = event.target.files?.[0] || null
  setSelectedFile(file)
  event.target.value = '' // 允许再次选择同一张图片
}

function addManualMealItem() {
  if (!mealResult.value) {
    mealResult.value = { source: 'manual', message: '请补充食物与营养估算后保存', items: [] }
  }
  mealResult.value.items ||= []
  mealResult.value.items.push({ name: '', grams: 100, calories: 0, protein_g: 0, fat_g: 0, carbs_g: 0 })
}

function removeMealItem(index) {
  mealResult.value?.items?.splice(index, 1)
}

async function analyze() {
  if (!selectedFile.value || mealLoading.value) return
  mealLoading.value = true
  pageError.value = ''
  try {
    const resp = await analyzeMeal(selectedFile.value)
    mealResult.value = resp.data
  } catch (e) {
    pageError.value = e.message || '餐照分析失败'
  } finally {
    mealLoading.value = false
  }
}

async function saveMeal() {
  const items = (mealResult.value?.items || []).filter((item) => item.name?.trim())
  if (!items.length) {
    pageError.value = '请至少填写一种食物后再保存'
    return
  }
  try {
    await confirmMeal({
      user_id: userId.value,
      meal_type: mealType.value,
      meal_date: mealDate.value,
      items,
      note: mealResult.value.source === 'text' ? 'AI 文字识别' : 'AI 餐照识别',
    })
    mealResult.value = null
    setSelectedFile(null)
    flash('已写入今日饮食记录 ✓')
    await refreshDaily()
  } catch (e) {
    pageError.value = e.message || '饮食记录保存失败'
  }
}

onMounted(() => window.addEventListener('resize', handleChartResize))
onUnmounted(() => {
  window.removeEventListener('resize', handleChartResize)
  mealBarChart?.dispose()
  mealPieChart?.dispose()
  if (selectedImageURL.value) URL.revokeObjectURL(selectedImageURL.value)
})

async function refreshDaily() {
  try {
    const resp = await getDailyMeals(userId.value, mealDate.value)
    daily.value = resp.data || daily.value
  } catch (e) {
    pageError.value = e.message || '饮食汇总加载失败'
  }
}

/** 选一个当前浏览器支持的录音格式（Chrome 用 webm/opus，Safari 需要 mp4） */
function pickAudioMime() {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  return candidates.find((t) => MediaRecorder.isTypeSupported(t)) || ''
}

let voiceTimer = null
function clearVoiceTimer() {
  if (voiceTimer) { clearInterval(voiceTimer); voiceTimer = null }
  voiceSeconds.value = 0
}

function stopRecording() {
  clearVoiceTimer()
  try { recorder?.stop() } catch { /* 已停止则忽略 */ }
}

/**
 * 语音输入：录音 → 停止 → 转写 → 填入输入框。
 *
 * 关键：任何一步失败都必须在**输入框附近**给出明确原因。
 * 之前 getUserMedia 没有 try/catch，麦克风被拒绝时静默失败，
 * 用户只会看到"点了没反应"（错误还显示在页面最顶部，根本看不到）。
 */
async function toggleRecording() {
  voiceError.value = ''
  if (voiceState.value === 'recording') { stopRecording(); return }
  if (voiceState.value === 'transcribing') return

  if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
    voiceError.value = '录音需要 https 或 localhost 环境，请用 http://localhost:5173 访问'
    return
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    voiceError.value = '当前浏览器不支持麦克风录音，建议改用 Chrome / Edge'
    return
  }
  if (typeof MediaRecorder === 'undefined') {
    voiceError.value = '当前浏览器不支持录音功能（MediaRecorder），建议改用 Chrome / Edge'
    return
  }

  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    const msg = {
      NotAllowedError: '麦克风权限被拒绝：点地址栏的锁图标 → 允许麦克风，然后重试',
      PermissionDeniedError: '麦克风权限被拒绝：请在浏览器设置中允许本站使用麦克风',
      NotFoundError: '没有检测到麦克风设备，请检查设备是否连接',
      NotReadableError: '麦克风被其他程序占用，请关闭占用的程序后重试',
    }[e?.name]
    voiceError.value = msg || `麦克风启动失败：${e?.name || e?.message || '未知错误'}`
    return
  }

  const mime = pickAudioMime()
  voiceChunks = []
  try {
    recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
  } catch (e) {
    stream.getTracks().forEach((t) => t.stop())
    voiceError.value = `录音器初始化失败：${e?.message || '浏览器不支持该音频格式'}`
    return
  }
  const usedMime = recorder.mimeType || mime || 'audio/webm'

  recorder.ondataavailable = (e) => { if (e.data && e.data.size) voiceChunks.push(e.data) }
  recorder.onerror = (e) => {
    clearVoiceTimer()
    voiceState.value = 'idle'
    stream.getTracks().forEach((t) => t.stop())
    voiceError.value = `录音出错：${e?.error?.name || '未知错误'}`
  }

  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop())
    clearVoiceTimer()
    const blob = new Blob(voiceChunks, { type: usedMime })
    if (!blob.size) {
      voiceState.value = 'idle'
      voiceError.value = '没有录到声音，请靠近麦克风再试一次'
      return
    }
    voiceState.value = 'transcribing'
    try {
      const ext = usedMime.includes('mp4') ? 'm4a' : (usedMime.includes('ogg') ? 'ogg' : 'webm')
      const resp = await transcribeVoice(new File([blob], `voice.${ext}`, { type: usedMime }))
      const text = resp.data?.text || ''
      if (text) {
        voiceText.value = text
        draft.value = text
        if (resp.data?.pending) {
          voiceError.value = '语音识别服务暂不可用，已填入占位文字，请直接修改后再发送'
        }
      } else {
        voiceError.value = '没有识别出文字，请说清楚一些或换个安静的环境'
      }
    } catch (e) {
      voiceError.value = e.message || '语音转写失败，请重试'
    } finally {
      voiceState.value = 'idle'
    }
  }

  recorder.start()
  voiceState.value = 'recording'
  voiceSeconds.value = 0
  // 最长录 60 秒，避免忘记点停止
  voiceTimer = setInterval(() => {
    voiceSeconds.value += 1
    if (voiceSeconds.value >= 60) stopRecording()
  }, 1000)
}
async function playLastAnswer() {
  const answer = [...messages.value].reverse().find(item => item.role === 'assistant')?.content
  if (!answer) return
  try { const resp = await synthesizeSpeech(answer); const base64 = resp.data?.audio_base64; if (base64) new Audio(`data:audio/mpeg;base64,${base64}`).play() } catch (e) { pageError.value = e.message || '语音播放失败' }
}

onMounted(() => { load(); loadConversations(); loadPrivacy(); initGraphRag() })
</script>

<template>
  <div class="assistant-page">
    <div class="assistant-header">
      <div>
        <div class="eyebrow">HealthyBot · AI 智能问答</div>
        <h1>AI 智能问答</h1>
        <p>问他健康问题、让他制定饮食计划，或直接帮你记下今天吃了什么。</p>
      </div>
      <div class="assistant-id">用户 ID <strong>{{ userId }}</strong></div>
    </div>

    <div v-if="pageError" class="alert">{{ pageError }}</div>
    <div v-if="successMsg" class="success-banner">{{ successMsg }}</div>

    <div class="assistant-layout">
      <div class="assistant-main">
      <section class="card chat-panel">
        <div class="card-title">智能对话 · 饮食计划 / 饮食记录 / 健康问答</div>
        <div class="quick-prompts">
          <button v-for="p in quickPrompts" :key="p" class="chip" :disabled="chatLoading" @click="usePrompt(p)">{{ p }}</button>
        </div>
        <div class="chat-messages-wrap">
          <div ref="messagesRef" class="chat-messages" @scroll="onMessagesScroll">
          <div v-if="!messages.length" class="empty-text">
            试试：帮我制定一份 7 天减脂饮食计划 · 帮我记一下早餐吃了两个鸡蛋和一杯牛奶 · 如何改善深睡
          </div>
          <div v-for="(item, index) in messages" :key="index" :class="['chat-bubble', item.role]">
            <div v-if="item.agent" class="chat-agent">
              <span>{{ item.agent }}</span>
              <span
                v-if="item.graphEnabled === true"
                class="rag-badge on"
                :title="item.graphDiseases?.length
                  ? '本次回答已引入图谱推理：' + item.graphDiseases.join('、')
                  : '本次回答已启用图谱增强（未命中疾病节点）'"
              >🕸️ 已接入图谱<template v-if="item.graphDiseases?.length"> · {{ item.graphDiseases.join('、') }}</template></span>
              <span
                v-else-if="item.graphEnabled === false"
                class="rag-badge off"
                title="本次回答未使用图谱（对比基线）"
              >⚪ 未用图谱</span>
            </div>
            <span class="msg-text">{{ item.content }}</span>

            <details v-if="item.agentPlan?.length" class="agent-workflow">
              <summary>本次协作 · {{ item.stepCount }} 步</summary>
              <div class="agent-plan">
                <span v-for="(agent, agentIndex) in item.agentPlan" :key="agent">
                  {{ agent }}<b v-if="agentIndex < item.agentPlan.length - 1">→</b>
                </span>
              </div>
              <div v-for="(step, stepIndex) in item.agentTrace" :key="stepIndex" class="agent-step">
                <strong>{{ step.agent }}</strong>
                <p>{{ step.answer }}</p>
              </div>
            </details>

            <!-- AI 生成的饮食计划卡片 -->
            <div v-if="item.plan" class="msg-card plan-card">
              <div class="plan-card-head">
                <span class="plan-head-left">
                  <strong>{{ item.plan.set_label }}</strong>
                  <span v-if="item.narrationSource === 'llm'" class="llm-chip" title="这段说明由大模型生成（热量与菜品数据来自规则引擎，可核对）">🤖 LLM 生成</span>
                </span>
                <span>目标热量 {{ item.plan.calories_target }} kcal/天 · {{ item.plan.days }} 天</span>
              </div>
              <div v-for="r in item.plan.recipes" :key="r.meal" class="plan-row">
                <span class="meal-tag">{{ r.meal }}</span>
                <span class="recipe-name">{{ r.name }}</span>
                <span class="recipe-kcal">{{ r.kcal }} kcal</span>
              </div>
              <div class="plan-foot">
                <span>购物清单 {{ item.plan.shopping_list?.length || 0 }} 项</span>
                <button class="btn success small" @click="applyPlan(item.plan)">应用并打开饮食计划 →</button>
              </div>
            </div>

            <!-- AI 记饮食：待确认草稿卡片 -->
            <div v-if="item.mealDraft" class="msg-card draft-card">
              <div class="draft-head">
                <strong>{{ item.mealDraft.meal_type }} · 待确认记录</strong>
                <span>合计约 {{ item.mealDraft.calories || 0 }} kcal</span>
              </div>
              <table class="data compact">
                <thead><tr><th>食物</th><th>估重(g)</th><th>热量</th><th>蛋白(g)</th><th>脂肪(g)</th><th>碳水(g)</th></tr></thead>
                <tbody>
                  <tr v-for="(it, i) in item.mealDraft.items" :key="i">
                    <td><input v-model="it.name" /></td>
                    <td><input v-model.number="it.grams" type="number" /></td>
                    <td>{{ it.calories }}</td><td>{{ it.protein_g }}</td><td>{{ it.fat_g }}</td><td>{{ it.carbs_g }}</td>
                  </tr>
                </tbody>
              </table>
              <div class="draft-foot">
                <button class="btn success small" :disabled="item.mealDraft.saved" @click="saveDraft(item)">
                  {{ item.mealDraft.saved ? '已保存到今日记录 ✓' : '保存到今日记录' }}
                </button>
                <span v-if="item.mealDraft.saved" class="saved-hint">已写入 <strong>{{ mealDate }}</strong></span>
              </div>
            </div>
          </div>
          <div v-if="chatLoading" class="chat-bubble assistant typing">
            <div class="chat-agent"><span>AI 助手</span></div>
            <div class="typing-row">
              <span class="typing-dots"><i></i><i></i><i></i></span>
              <span class="typing-text">正在生成回答…</span>
            </div>
          </div>
          </div>
          <button
            v-if="!atBottom"
            class="scroll-bottom-btn"
            title="回到最新消息"
            @click="scrollToBottom()"
          >↓ 回到最新</button>
        </div>
        <div v-if="!privacy.consent" class="consent-inline">
          <span class="ci-text">发送前需同意「健康数据使用说明」（仅用于本地健康助手服务，可随时撤回）</span>
          <button class="btn small" :disabled="privacyLoading" @click="grantAndContinue">
            {{ privacyLoading ? '处理中…' : '同意并发送' }}
          </button>
        </div>
        <div v-if="privacy.consent && !profileComplete" class="consent-inline profile-inline">
          <span class="ci-text">⚠ 首次问答前请完善右侧「健康画像」：<b>{{ missingProfileFields.join('、') }}</b>（没有就填「无」），AI 需要据此避开过敏原和饮食禁忌</span>
          <button class="btn small" @click="scrollToProfile">去完善画像</button>
        </div>
        <div class="chat-compose">
          <textarea v-model="draft" rows="3" placeholder="输入问题，或说“帮我制定减脂饮食计划 / 帮我记：午餐吃了…”" @keydown.enter.exact.prevent="sendMessage" @focus="onComposeFocus" />
          <button
            class="voice-btn"
            :class="{ recording, busy: voiceState === 'transcribing' }"
            :disabled="voiceState === 'transcribing'"
            :title="voiceState === 'recording' ? '停止录音' : (voiceState === 'transcribing' ? '转写中…' : '语音输入')"
            @click="toggleRecording"
          >{{ voiceState === 'recording' ? '■' : (voiceState === 'transcribing' ? '…' : '♩') }}</button><button class="btn" :disabled="chatLoading || !draft.trim()" @click="sendMessage">发送</button><button class="voice-btn" title="播放最近回复" @click="playLastAnswer">◖</button>
        </div>
        <div v-if="voiceState !== 'idle' || voiceError" class="voice-status" :class="{ 'is-error': !!voiceError }">
          <template v-if="voiceState === 'recording'">🎙 正在录音 {{ voiceSeconds }} 秒 — 说完点「■」停止（最长 60 秒）</template>
          <template v-else-if="voiceState === 'transcribing'">⏳ 正在转写，请稍候…</template>
          <template v-else>{{ voiceError }}</template>
        </div>
        <div class="disclaimer">健康建议仅供参考，不能替代医疗诊断。</div>
      </section>

      <section class="card">
        <div class="card-title">拍餐照，生成饮食记录</div>
        <div class="meal-toolbar">
          <label class="meal-file-btn btn ghost">
            <input type="file" accept="image/*" @change="onFile" />
            📷 {{ selectedFile ? '重新选图' : '选择餐照' }}
          </label>
          <select v-model="mealType"><option>早餐</option><option>午餐</option><option>晚餐</option><option>加餐</option></select>
          <button class="btn" :disabled="!selectedFile || mealLoading" @click="analyze">{{ mealLoading ? '分析中…' : '开始识别' }}</button>
        </div>
        <div v-if="selectedImageURL" class="meal-preview">
          <img :src="selectedImageURL" alt="餐照预览" />
          <div class="meal-preview-meta">
            <strong :title="selectedFile?.name">{{ selectedFile?.name }}</strong>
            <span>{{ fmtSize(selectedFile?.size) }} · 识别后可在下方核对修正</span>
          </div>
          <button class="more-btn" title="移除图片" @click="clearSelectedFile">×</button>
        </div>
        <div v-if="mealResult" class="meal-result">
          <div class="muted">{{ mealResult.message }}</div>
          <div v-if="mealResult.items?.length" class="meal-charts">
            <div ref="mealBarRef" class="meal-chart"></div>
            <div ref="mealPieRef" class="meal-chart"></div>
          </div>
          <table class="data" v-if="mealResult.items?.length">
            <thead><tr><th>食物</th><th>估重(g)</th><th>热量</th><th>蛋白质</th><th>脂肪</th><th>碳水</th></tr></thead>
            <tbody><tr v-for="(item, index) in mealResult.items" :key="index"><td><input v-model="item.name" placeholder="食物名称" /></td><td><input v-model.number="item.grams" type="number" min="0" /></td><td><input v-model.number="item.calories" type="number" min="0" /></td><td><input v-model.number="item.protein_g" type="number" min="0" step="0.1" /></td><td><input v-model.number="item.fat_g" type="number" min="0" step="0.1" /></td><td><input v-model.number="item.carbs_g" type="number" min="0" step="0.1" /><button class="more-btn" title="移除该食物" @click="removeMealItem(index)">×</button></td></tr></tbody>
          </table>
          <button class="btn ghost small" @click="addManualMealItem">＋ 手动添加食物</button>
          <div class="nutrition-strip"><span>热量 {{ mealTotals.calories }} kcal</span><span>蛋白质 {{ mealTotals.protein_g }} g</span><span>脂肪 {{ mealTotals.fat_g }} g</span><span>碳水 {{ mealTotals.carbs_g }} g</span></div>
          <button class="btn success" :disabled="!mealResult.items?.length" @click="saveMeal">确认并写入今日记录</button>
        </div>
      </section>
      <section class="card">
        <div class="card-title">今日饮食摘要</div>
        <div class="daily-toolbar"><input v-model="mealDate" type="date" @change="refreshDaily" /><span class="daily-score">{{ daily.score ?? '—' }}<small v-if="daily.score !== null">/100</small></span></div>
        <p v-if="daily.score_message" class="hint">{{ daily.score_message }}</p>
        <div class="nutrition-strip daily"><span>{{ totals.calories || 0 }} kcal</span><span>蛋白质 {{ totals.protein_g || 0 }} g</span><span>脂肪 {{ totals.fat_g || 0 }} g</span><span>碳水 {{ totals.carbs_g || 0 }} g</span></div>
        <div v-if="daily.meals?.length" class="daily-meals"><div v-for="meal in daily.meals" :key="meal.id" class="daily-meal"><strong>{{ meal.meal_type }}</strong><span>{{ meal.calories }} kcal</span><span>{{ meal.items.map(item => item.name).join('、') }}</span></div></div>
        <div v-else class="empty-text">还没有记录，先让 AI 帮你记一餐，或拍一张餐照。</div>
      </section>
      </div>

      <aside class="assistant-side">
        <section class="card conv-card">
          <div class="card-title conv-head">
            会话记录
            <button class="btn ghost small" @click="newConversation">＋ 新对话</button>
          </div>
          <div v-if="convLoading" class="muted" style="font-size:12px">加载中…</div>
          <div v-else-if="!conversations.length" class="empty-text">还没有历史会话</div>
          <div
            v-for="c in conversations"
            :key="c.id"
            class="conv-item"
            :class="{ active: c.id === conversationId }"
            @click="openConversation(c)"
          >
            <div class="conv-main">
              <strong>{{ c.title }}</strong>
              <span>{{ c.message_count }} 条 · {{ fmtTime(c.updated_at) }}</span>
            </div>
            <div class="conv-ops">
              <button title="重命名" @click.stop="renameConv(c)">✎</button>
              <button title="删除" @click.stop="deleteConv(c)">✕</button>
            </div>
          </div>
        </section>
        <section ref="profileCardRef" class="card" :class="{ 'profile-alert': !profileComplete }">
          <div class="card-title">我的健康画像 <span v-if="!profileComplete" class="req-badge">有必填项未完成</span></div>
          <div class="form-grid one-col">
            <div class="form-item"><label>称呼</label><input v-model="profile.user_name" /></div>
            <div class="form-item"><label>年龄</label><input v-model.number="profile.age" type="number" min="1" max="120" /></div>
            <div class="form-item"><label>身高 / 体重</label><div class="inline-fields"><input v-model.number="profile.height_cm" type="number" placeholder="cm" /><input v-model.number="profile.weight_kg" type="number" placeholder="kg" /></div></div>
            <div class="form-item"><label>健康目标</label><input v-model="profile.goal" placeholder="如：保持健康 / 减脂 / 增肌" /></div>
            <div class="form-item" :class="{ 'req-missing': !String(profile.allergies || '').trim() }">
              <label><i class="req">*</i>过敏 / 疾病（必填）</label>
              <textarea v-model="profile.allergies" rows="2" placeholder="如：对虾、芒果过敏；没有请填「无」" />
              <textarea v-model="profile.conditions" rows="2" placeholder="基础疾病，如：高血压、糖尿病；没有请填「无」" :class="{ 'req-missing': !String(profile.conditions || '').trim() }" />
            </div>
            <div class="form-item"><label>饮食偏好</label><input v-model="profile.preferences" placeholder="如：少油、素食" /></div>
          </div>
          <button class="btn ghost full" @click="saveProfile">{{ profileSaved ? '已保存' : '保存画像' }}</button>
          <p class="hint" :class="{ 'req-hint': !profileComplete }">{{ profileComplete ? '画像保存后，AI 制定的饮食计划会按你的性别/年龄/身高/体重与目标自动算热量。' : '必填项：过敏/疾病 与 基础疾病（没有请填「无」）。AI 会据此避开过敏原与饮食禁忌，完善后才能开始问答。' }}</p>
        </section>
        <section class="card privacy-card">
          <div class="card-title">隐私与数据</div>
          <div class="privacy-status" :class="{ good: privacy.encryption_configured }">
            <span class="status-dot"></span>
            {{ privacy.encryption_configured ? '健康文字字段和长期记忆已启用 AES-256-GCM' : '开发环境加密密钥未单独配置' }}
          </div>
          <label class="consent-row"><input type="checkbox" :checked="privacy.consent" @change="toggleConsent" /> <span>同意健康数据用于本地健康助手服务</span></label>
          <div class="memory-title">长期记忆 <span>{{ memories.length }}/100</span></div>
          <div v-if="privacyLoading" class="muted">加载中…</div>
          <div v-else-if="!memories.length" class="empty-text">暂无记忆。对话中说“记住……”或在这里添加。</div>
          <div v-for="memory in memories" :key="memory.id" class="memory-row">
            <span>{{ memory.content }}</span><button title="删除记忆" @click="removeMemory(memory)">×</button>
          </div>
          <div class="memory-add"><input v-model="memoryDraft" maxlength="500" placeholder="例如：我对虾过敏" @keydown.enter.prevent="addMemory" /><button class="btn ghost small" :disabled="!memoryDraft.trim()" @click="addMemory">添加</button></div>
          <div class="privacy-actions"><button class="btn ghost small" @click="downloadPrivacyData">导出我的数据（可读版）</button><button class="btn danger small" @click="eraseHealthData">删除健康数据</button></div>
          <p class="hint">导出为排版好的文字报告（.txt），可直接阅读；删除会清理健康记录和社区关联数据，账号本身不会删除。</p>
        </section>
      </aside>
    </div>

  </div>
</template>

<style scoped>
/* 未同意隐私说明时的就近提示 */
.consent-inline {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  border: 1px solid rgba(217, 154, 43, .45); background: rgba(251, 240, 218, .6);
  color: #8a6320; border-radius: 10px; padding: 9px 12px; margin: 4px 0 10px; font-size: 12.5px;
}
.consent-inline .ci-text { flex: 1; min-width: 200px; line-height: 1.5; }
html.dark .consent-inline { background: rgba(251, 191, 36, .12); border-color: rgba(251, 191, 36, .35); color: #fcd34d; }

/* 画像必填项缺失：提示条与画像卡片高亮 */
.profile-inline { border-color: rgba(196, 74, 58, .45); background: rgba(253, 232, 228, .6); color: #a13d2d; }
html.dark .profile-inline { background: rgba(248, 113, 92, .12); border-color: rgba(248, 113, 92, .35); color: #fca590; }
.profile-alert { border-color: rgba(196, 74, 58, .5); box-shadow: 0 0 0 3px rgba(196, 74, 58, .08); }
.req-badge { margin-left: 8px; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; background: rgba(196, 74, 58, .12); color: #a13d2d; }
html.dark .req-badge { background: rgba(248, 113, 92, .16); color: #fca590; }
.req { color: #c44a3a; font-style: normal; font-weight: 700; margin-right: 3px; }
.req-missing { border-color: rgba(196, 74, 58, .55) !important; }
.req-hint { color: #a13d2d; font-weight: 600; }
html.dark .req-hint { color: #fca590; }

/* 图谱增强开关：问答页顶部小开关，与知识图谱页共享同一状态 */
.chat-head { margin-bottom: 10px; }
.chat-head .card-title { flex: 1 1 auto; }
.rag-mini {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border, #dbe3ee); border-radius: 999px;
  padding: 4px 12px; font-size: 12px; font-weight: 600; cursor: pointer;
  background: var(--card, #fff); color: #b45309;
}
.rag-mini.on { color: #1a7d53; border-color: rgba(34, 160, 107, .5); background: rgba(34, 160, 107, .1); }
.rag-mini-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
html.dark .rag-mini { background: rgba(148, 163, 184, .1); color: #fcd34d; border-color: rgba(148, 163, 184, .3); }
html.dark .rag-mini.on { color: #6ee7a8; border-color: rgba(34, 160, 107, .45); background: rgba(34, 160, 107, .16); }

/* 回答气泡上的图谱状态标注（答辩时一眼可辨本条是否走了图谱） */
.chat-bubble .chat-agent { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rag-badge { font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; }
.rag-badge.on { background: rgba(34, 160, 107, .14); color: #1a7d53; }
.rag-badge.off { background: rgba(148, 163, 184, .18); color: #64748b; }
html.dark .rag-badge.on { background: rgba(34, 160, 107, .22); color: #6ee7a8; }
html.dark .rag-badge.off { background: rgba(148, 163, 184, .2); color: #cbd5e1; }

.quick-prompts { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 10px; }
/* —— 消息区滚动 / 等待反馈 —— */
.chat-messages-wrap { position: relative; display: flex; flex-direction: column; flex: 1; min-height: 0; }
.scroll-bottom-btn {
  position: absolute; right: 14px; bottom: 10px; z-index: 3;
  padding: 5px 12px; font-size: 12px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--card); color: var(--ink);
  box-shadow: 0 4px 14px rgba(16, 32, 24, .14); cursor: pointer;
}
.scroll-bottom-btn:hover { border-color: var(--primary); color: var(--primary); }
.chat-bubble.typing { display: block; }
.typing-row { display: flex; align-items: center; gap: 8px; }
.typing-dots { display: inline-flex; gap: 4px; }
.typing-dots i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: .3; animation: typingBlink 1.2s infinite; }
.typing-dots i:nth-child(2) { animation-delay: .2s; }
.typing-dots i:nth-child(3) { animation-delay: .4s; }
@keyframes typingBlink {
  0%, 100% { opacity: .25; transform: translateY(0); }
  50% { opacity: .95; transform: translateY(-3px); }
}
.typing-text { font-size: 13px; opacity: .72; }
.plan-card-head .llm-chip, .plan-head-left {
  display: inline-flex; align-items: center; gap: 8px;
}
.plan-card-head .llm-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 999px; white-space: nowrap;
  background: rgba(63, 169, 111, .14); color: #2f7d55; border: 1px solid rgba(63, 169, 111, .3);
}
html.dark .plan-card-head .llm-chip { background: rgba(77, 227, 255, .12); color: #7fe3ff; border-color: rgba(77, 227, 255, .3); }
/* —— 餐照识别：图片预览 + 结果图表 —— */
.meal-file-btn { position: relative; cursor: pointer; user-select: none; }
.meal-file-btn input[type='file'] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.meal-preview { display: flex; align-items: center; gap: 12px; margin: 10px 0; padding: 8px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
.meal-preview img { width: 92px; height: 68px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
.meal-preview-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.meal-preview-meta strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meal-preview-meta span { font-size: 12px; color: var(--muted, #8a8f99); }
.meal-charts { display: grid; grid-template-columns: 3fr 2fr; gap: 12px; margin: 10px 0 12px; }
.meal-chart { height: 220px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
@media (max-width: 900px) { .meal-charts { grid-template-columns: 1fr; } }
.chip {
  border: 1px solid var(--border, #dbe3ee);
  background: var(--card, #fff);
  color: inherit; border-radius: 999px; padding: 5px 12px; font-size: 12.5px; cursor: pointer;
}
.chip:hover { border-color: #4de3ff; color: #0e7490; }
.chip:disabled { opacity: .5; cursor: default; }
.msg-text { white-space: pre-line; }
.agent-workflow {
  margin-top: 10px; border: 1px solid #cfe3ee; border-radius: 8px;
  background: #f8fcfe; color: #334155; text-align: left; font-size: 12px;
}
.agent-workflow summary { padding: 8px 10px; cursor: pointer; color: #0e7490; font-weight: 600; }
.agent-plan { display: flex; flex-wrap: wrap; gap: 5px; padding: 0 10px 8px; color: #64748b; }
.agent-plan span { display: inline-flex; align-items: center; gap: 5px; }
.agent-plan b { color: #0e7490; font-weight: 500; }
.agent-step { padding: 8px 10px; border-top: 1px dashed #dbeaf1; }
.agent-step strong { color: #0f172a; }
.agent-step p { margin: 4px 0 0; white-space: pre-line; line-height: 1.5; }
.success-banner {
  background: #d1fae5; color: #065f46; border-radius: 8px; padding: 8px 14px; margin-bottom: 10px; font-size: 13px;
}
.hint { font-size: 12px; color: var(--muted, #8a94a6); margin-top: 8px; line-height: 1.5; }
.privacy-status { display: flex; align-items: center; gap: 6px; color: #9a6700; font-size: 12px; margin-bottom: 9px; }
.privacy-status.good { color: #047857; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.consent-row { display: flex; align-items: flex-start; gap: 7px; font-size: 12px; line-height: 1.5; }
.consent-row input { margin-top: 2px; }
.memory-title { display: flex; justify-content: space-between; margin-top: 14px; font-size: 12px; color: #334155; font-weight: 600; }
.memory-title span { color: var(--muted, #8a94a6); font-weight: 400; }
.memory-row { display: flex; gap: 6px; align-items: flex-start; padding: 6px 0; border-bottom: 1px solid #edf2f5; font-size: 12px; line-height: 1.45; }
.memory-row span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.memory-row button { border: 0; background: transparent; color: #94a3b8; cursor: pointer; font-size: 16px; line-height: 1; padding: 0 2px; }
.memory-row button:hover { color: #dc2626; }
.memory-add { display: flex; gap: 6px; margin-top: 9px; }
.memory-add input { min-width: 0; flex: 1; }
.privacy-actions { display: flex; gap: 6px; margin-top: 12px; }
.btn.danger { color: #b42318; border-color: #fecaca; }
.btn.danger:hover { background: #fff1f2; }

/* 对话内卡片 */
.msg-card {
  margin-top: 10px; border: 1px solid #cfe3ee; border-radius: 12px; overflow: hidden;
  background: linear-gradient(180deg, #f6fbfe, #fff); text-align: left;
}
.plan-card-head, .draft-head {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 9px 14px; font-size: 13px; background: #eef7fb;
}
.plan-card-head span, .draft-head span { color: #0e7490; font-size: 12px; }
.plan-row {
  display: flex; align-items: center; gap: 10px; padding: 7px 14px;
  border-top: 1px dashed #e2edf4; font-size: 13px;
}
.meal-tag { min-width: 40px; font-size: 11px; color: #fff; background: #0e7490; border-radius: 6px; padding: 2px 7px; text-align: center; }
.recipe-name { flex: 1; }
.recipe-kcal { color: #b45309; font-weight: 600; }
.plan-foot, .draft-foot {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 9px 14px; border-top: 1px solid #e2edf4; font-size: 12px; color: #0e7490;
}
.btn.small { padding: 5px 12px; font-size: 12.5px; }
.btn.success { background: #10b981; color: #fff; }
.btn.success:disabled { background: #a7f3d0; color: #065f46; cursor: default; }
.saved-hint { color: #065f46; }
table.data.compact { margin: 0; width: 100%; font-size: 12px; }
table.data.compact input { width: 70px; padding: 2px 4px; }

/* 会话记录 */
.conv-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.conv-item {
  display: flex; align-items: center; gap: 8px; padding: 7px 8px; border-radius: 8px;
  cursor: pointer; border: 1px solid transparent;
}
.conv-item:hover { background: #f5f9fc; }
.conv-item.active { background: #eef7fb; border-color: #cfe3ee; }
.conv-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.conv-main strong { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-main span { font-size: 11px; color: var(--muted, #8a94a6); }
.conv-ops { display: flex; gap: 2px; opacity: 0; transition: opacity .15s; }
.conv-item:hover .conv-ops { opacity: 1; }
.conv-ops button {
  border: none; background: transparent; cursor: pointer; font-size: 12px; color: #64748b;
  padding: 2px 5px; border-radius: 6px;
}
.conv-ops button:hover { background: #e2e8f0; color: #0f172a; }

/* —— 语音输入：就近状态 / 错误提示 —— */
.voice-btn.busy { opacity: .65; cursor: progress; }
.voice-status {
  margin-top: 8px; padding: 7px 12px; border-radius: 8px; font-size: 12.5px; line-height: 1.6;
  background: rgba(95, 158, 63, .12); color: var(--primary); border: 1px solid rgba(95, 158, 63, .3);
}
.voice-status.is-error {
  background: rgba(217, 154, 43, .14); color: #8a6320; border-color: rgba(217, 154, 43, .4);
}
html.dark .voice-status { background: rgba(77, 227, 255, .1); color: #8fe7ff; border-color: rgba(77, 227, 255, .3); }
html.dark .voice-status.is-error { background: rgba(251, 191, 36, .12); color: #fcd34d; border-color: rgba(251, 191, 36, .35); }
</style>
