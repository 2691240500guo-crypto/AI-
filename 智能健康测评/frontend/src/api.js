// API 封装：统一 axios 实例 + 接口方法
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 180000, // OCR/LLM 可能较慢
})

// 请求拦截：注入登录 token，保证服务端可识别身份
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('healthybot_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    const status = err?.response?.status
    const url = err?.config?.url || ''
    // 登录过期 / 未登录：清理本地会话并回到登录页（登录接口本身的 401 不触发）
    if (status === 401 && !url.includes('/auth/login')) {
      localStorage.removeItem('healthybot_role')
      localStorage.removeItem('healthybot_user')
      localStorage.removeItem('healthybot_token')
      if (!window.__hbReloginHandled) {
        window.__hbReloginHandled = true
        window.alert('登录已过期或未登录，请重新登录')
        window.location.reload()
      }
    }
    const msg =
      err?.response?.data?.detail ||
      err?.response?.data?.message ||
      err?.message ||
      '网络错误'
    return Promise.reject(new Error(msg))
  }
)

/**
 * 获取当前登录用户 ID。
 * 登录成功后 healthybot_user 里保存 { id, name }；id 与后端 AppUser.account 一致，
 * 保证画像 / 对话 / 饮食记录跨刷新、跨页面归属同一用户。
 */
export function currentUserId(fallback = 'user') {
  try {
    const stored = JSON.parse(localStorage.getItem('healthybot_user') || 'null')
    return (stored && stored.id) || fallback
  } catch {
    return fallback
  }
}

// 后端用 demo token 鉴权时无需签名；如未来接入真实 JWT，替换拦截器逻辑即可

// ===== 测评 =====
export const createAssessment = (data) =>
  http.post('/assessment', data)
export const getAssessmentHistory = (userId, limit = 50) =>
  http.get('/assessment/history', { params: { user_id: userId, limit } })
export const getAssessmentStats = () => http.get('/assessment/stats')
export const getAssessmentDetail = (id) =>
  http.get(`/assessment/detail/${id}`)

// ===== 知识库 =====
export const uploadKnowledgeFile = (file, uploadedBy = 'system') => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('uploaded_by', uploadedBy)
  return http.post('/knowledge/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  })
}
export const listKnowledgeFiles = (limit = 100, offset = 0) =>
  http.get('/knowledge/files', { params: { limit, offset } })
export const deleteKnowledgeFile = (id) =>
  http.delete(`/knowledge/files/${id}`)
export const searchKnowledge = (query, topK = 5) =>
  http.post('/knowledge/search', { query, top_k: topK })
export const getKnowledgeStats = () => http.get('/knowledge/stats')
export const getKnowledgeFiles = (limit = 200) =>
  http.get('/knowledge/files', { params: { limit } })

// ===== 图谱 =====
export const initGraph = (reset = false) =>
  http.post('/graph/init', null, { params: { reset } })
export const getGraphData = (limit = 400, disease = '') =>
  http.get('/graph/data', { params: disease ? { limit, disease } : { limit } })
export const getGraphStats = () => http.get('/graph/stats')
export const getDiseases = () => http.get('/graph/diseases')
export const getDiseaseDetail = (name) =>
  http.get(`/graph/disease/${encodeURIComponent(name)}`)
export const getAssessGraphHint = (disease) =>
  http.get('/graph/assess-hint', { params: { disease } })
// 多跳推理：疾病 → 营养素 → 食物，含宜吃/忌口/排除项
export const getGraphReason = (disease, exclude = '') =>
  http.get('/graph/reason', { params: exclude ? { disease, exclude } : { disease } })
// 全部「食物-适宜/禁忌-疾病」直接关系
export const getGraphRelations = (limit = 200) =>
  http.get('/graph/relations', { params: { limit } })
// AI 问答「图谱增强」默认开关（只读，来自后端 .env 的 GRAPH_RAG_ENABLED）
export const getGraphRagStatus = () => http.get('/graph/rag-status')

// ===== 健康助手 =====
export const getAssistantProfile = (userId) =>
  http.get(`/assistant/profile/${encodeURIComponent(userId)}`)
export const updateAssistantProfile = (userId, data) =>
  http.put(`/assistant/profile/${encodeURIComponent(userId)}`, data)
export const sendAssistantMessage = (data) =>
  http.post('/assistant/chat', data)
export const getPrivacyStatus = () => http.get('/privacy/status')
export const updatePrivacyConsent = (data) => http.put('/privacy/consent', data)
export const getPrivacyMemories = () => http.get('/privacy/memories')
export const createPrivacyMemory = (data) => http.post('/privacy/memories', data)
export const deletePrivacyMemory = (id) => http.delete(`/privacy/memories/${id}`)
export const exportPrivacyData = () => http.get('/privacy/export')
export const erasePrivacyData = () => http.delete('/privacy/data', { data: { confirm: 'DELETE_MY_DATA' } })

// ===== 会话管理 =====
export const getConversations = (userId, limit = 50) =>
  http.get('/assistant/conversations', { params: { user_id: userId, limit } })
export const getConversationMessages = (conversationId, userId) =>
  http.get(`/assistant/conversations/${conversationId}/messages`, { params: { user_id: userId } })
export const renameConversation = (conversationId, title, userId) =>
  http.patch(`/assistant/conversations/${conversationId}`, { title }, { params: { user_id: userId } })
export const deleteConversation = (conversationId, userId) =>
  http.delete(`/assistant/conversations/${conversationId}`, { params: { user_id: userId } })
export const analyzeMeal = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/meals/analyze', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  })
}
export const quickLogMeal = (data) => http.post('/meals/quick-log', data)
export const confirmMeal = (data) => http.post('/meals/confirm', data)
export const getDailyMeals = (userId, mealDate) =>
  http.get('/meals/daily', { params: { user_id: userId, meal_date: mealDate } })

// ===== 产品能力 =====
export const loginAccount = (data) => http.post('/auth/login', data)
export const getAdminOverview = () => http.get('/admin/overview')
export const getAdminDetails = (kind, limit = 20) =>
  http.get('/admin/details', { params: { kind, limit } })
export const getTongueEvaluation = (split = 'test') =>
  http.get('/admin/tongue/evaluation', { params: { split }, timeout: 300000 })
export const getSocialFeed = (userId, limit = 20, scope = 'all') => http.get('/social/feed', { params: { user_id: userId, limit, scope } })
export const createSocialPost = (data) => http.post('/social/posts', data)
export const uploadSocialImages = (files, userId = 'user') => {
  const fd = new FormData()
  files.forEach((f) => fd.append('files', f))
  fd.append('user_id', userId)
  return http.post('/social/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}
export const getPostComments = (postId) => http.get(`/social/posts/${postId}/comments`)
export const commentSocialPost = (postId, data) => http.post(`/social/posts/${postId}/comments`, data)
export const likeSocialPost = (postId, userId) => http.post(`/social/posts/${postId}/like`, null, { params: { user_id: userId } })
export const followSocialUser = (targetId, userId) => http.post(`/social/users/${encodeURIComponent(targetId)}/follow`, null, { params: { user_id: userId } })
export const getModerationQueue = (status = 'pending_review', limit = 50) => http.get('/social/moderation/queue', { params: { status, limit } })
export const reviewSocialPost = (postId, action, operator = 'admin') => http.post(`/social/moderation/${postId}/review`, { action, operator })
export const generateMealPlan = (data) => http.post('/plans/generate', data)
export const getCurrentPlan = (userId) => http.get('/plans/current', { params: { user_id: userId } })
// ===== 计划审核（管理端）=====
export const getPlanReviewQueue = (status = 'pending_review', limit = 50) =>
  http.get('/admin/plans', { params: { status, limit } })
export const updatePlan = (planId, data) => http.patch(`/admin/plans/${planId}`, data)
export const reviewPlan = (planId, action, note = '', operator = 'admin') =>
  http.post(`/admin/plans/${planId}/review`, { action, note, operator })
export const transcribeVoice = (file) => { const fd = new FormData(); fd.append('file', file); return http.post('/voice/transcribe', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }) }
export const synthesizeSpeech = (text) => { const fd = new FormData(); fd.append('text', text); return http.post('/voice/speak', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }) }
export const analyzeTongue = (file) => { const fd = new FormData(); fd.append('file', file); return http.post('/tongue/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }) }
export const saveTongueRecord = (file, userId, note = '') => { const fd = new FormData(); fd.append('file', file); fd.append('user_id', userId); fd.append('note', note); return http.post('/tongue/save', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000 }) }
export const getTongueRecords = (userId, limit = 60) => http.get('/tongue/records', { params: { user_id: userId, limit } })
export const getTongueImage = (recordId) => http.get(`/tongue/images/${recordId}`, { responseType: 'blob' })

// ===== 周报/月报与小萌宠 =====
export const getHealthReport = (period = 'week') =>
  http.get('/reports/summary', { params: { period } })
export const sendPetMessage = (data) => http.post('/pet/chat', data)
