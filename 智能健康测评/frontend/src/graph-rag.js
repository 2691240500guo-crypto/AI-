/**
 * AI 问答「图谱增强」开关（请求级，非全局）
 *
 * 设计要点：
 * - 开关状态随**每次提问**下发给后端（ChatRequest.use_graph），所以切换后
 *   无需重启后端、也不需要改 .env 就能立刻生效，答辩时可逐条对比。
 * - 状态持久化到 localStorage，知识图谱页与智能问答页共享同一份状态。
 * - 若本地从没有过记录，则对齐后端 .env 的 GRAPH_RAG_ENABLED 默认值，
 *   避免前端写死的 true 与后端配置漂移。
 */
import { ref } from 'vue'
import { getGraphRagStatus } from './api'

const STORAGE_KEY = 'healthybot_graph_rag'

/** 当前开关（true = 本次提问会注入图谱上下文） */
export const graphRagEnabled = ref(true)

/** 后端 .env 的默认值，仅用于页面上做「默认 vs 当前」说明 */
export const graphRagDefault = ref(true)

/** 是否已经和后端对齐过（避免重复请求） */
let synced = false

function persist(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
  } catch (e) {
    /* 隐私 / 无痕模式下忽略 */
  }
}

/** 本地记录；null 表示「用户从未手动切换过，跟随后端默认」 */
function readSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw === null ? null : raw === '1'
  } catch (e) {
    return null
  }
}

export function setGraphRag(value) {
  graphRagEnabled.value = Boolean(value)
  persist(graphRagEnabled.value)
}

export function toggleGraphRag() {
  setGraphRag(!graphRagEnabled.value)
}

/**
 * 应用启动 / 页面挂载时调用：本地记录优先，没有记录则用后端 .env 默认值。
 * 幂等，重复调用只会真正请求后端一次。
 */
export async function initGraphRag() {
  const saved = readSaved()
  if (saved !== null) graphRagEnabled.value = saved
  if (synced) return graphRagEnabled.value
  synced = true
  try {
    const resp = await getGraphRagStatus()
    graphRagDefault.value = Boolean(resp.data?.enabled)
    if (saved === null) graphRagEnabled.value = graphRagDefault.value
  } catch (e) {
    /* 后端不可用时维持本地值，不阻塞页面 */
  }
  return graphRagEnabled.value
}
