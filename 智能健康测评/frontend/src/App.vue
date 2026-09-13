<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import LoginPage from './views/LoginPage.vue'
import AssistantPage from './views/AssistantPage.vue'
import AssessmentPage from './views/AssessmentPage.vue'
import DashboardPage from './views/DashboardPage.vue'
import KnowledgePage from './views/KnowledgePage.vue'
import GraphPage from './views/GraphPage.vue'
import CommunityPage from './views/CommunityPage.vue'
import MealPlanPage from './views/MealPlanPage.vue'
import AdminPage from './views/AdminPage.vue'
import AdminPlanPage from './views/AdminPlanPage.vue'
import MarketingPage from './views/MarketingPage.vue'
import TonguePage from './views/TonguePage.vue'
import CompanionPage from './views/CompanionPage.vue'
import { isDark, toggleTheme } from './theme-mode'

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('healthybot_user') || 'null')
  } catch {
    localStorage.removeItem('healthybot_user')
    return null
  }
}
const storedRole = localStorage.getItem('healthybot_role')
const role = ref(storedRole === 'admin' || storedRole === 'user' ? storedRole : '')
const user = ref(readStoredUser())
const active = ref(role.value === 'admin' ? 'admin' : 'assistant')
const userTabs = [
  { key: 'assistant', label: 'AI 智能问答', icon: '✦', comp: AssistantPage },
  { key: 'assessment', label: '营养测评', icon: '◒', comp: AssessmentPage },
  { key: 'community', label: '健康广场', icon: '◌', comp: CommunityPage },
  { key: 'meal-plan', label: '饮食计划', icon: '▦', comp: MealPlanPage },
  { key: 'tongue', label: '舌体观察', icon: '◉', comp: TonguePage },
  { key: 'dashboard', label: '健康趋势', icon: '⌁', comp: DashboardPage },
  { key: 'companion', label: '周报 · 小萌宠', icon: '♡', comp: CompanionPage },
]
const adminTabs = [
  { key: 'admin', label: '运营总览', icon: '▥', comp: AdminPage },
  { key: 'marketing', label: '产品官网 Demo', icon: '✦', comp: MarketingPage },
  { key: 'assessment', label: '测评数据', icon: '◒', comp: AssessmentPage },
  { key: 'plan-review', label: '计划审核', icon: '▦', comp: AdminPlanPage },
  { key: 'community', label: '内容审核', icon: '◌', comp: CommunityPage },
  { key: 'knowledge', label: '知识库', icon: '▤', comp: KnowledgePage },
  { key: 'graph', label: '知识图谱', icon: '⌘', comp: GraphPage },
]
const tabs = computed(() => role.value === 'admin' ? adminTabs : userTabs)
const current = computed(() => tabs.value.find(t => t.key === active.value)?.comp || tabs.value[0].comp)
function onLogin(payload) { role.value = payload.role; user.value = payload.user; active.value = payload.role === 'admin' ? 'admin' : 'assistant' }

// 允许子页面（如 AI 智能问答生成饮食计划后）触发跨 tab 跳转
function onSwitchTab(event) {
  const key = event?.detail
  if (key && tabs.value.some((t) => t.key === key)) active.value = key
}
onMounted(() => window.addEventListener('app:switch-tab', onSwitchTab))
onUnmounted(() => window.removeEventListener('app:switch-tab', onSwitchTab))
// —— 侧栏关心评语：点击卡片切换下一条 ——
const careMessages = [
  { title: '今天也要照顾好自己', text: '记录一点点，身体会给你答案。' },
  { title: '慢慢来，比较快', text: '健康不是冲刺，是一天一天的小习惯。' },
  { title: '喝口水吧', text: '一杯温水下肚，身体会谢谢你。' },
  { title: '这一餐，吃得开心一点', text: '均衡不是苛刻，是让身体舒服。' },
  { title: '今晚早点睡', text: '睡够了，明天的你才有力气。' },
  { title: '你已经在变好了', text: '坚持记录的人，变化都看得见。' },
  { title: '站起来伸个懒腰', text: '坐久了走两步，肩颈会轻松很多。' },
  { title: '情绪也值得被照顾', text: '不开心的时候，先深呼吸三次。' },
]
const careIndex = ref(0)
const care = computed(() => careMessages[careIndex.value])
function nextCare() {
  careIndex.value = (careIndex.value + 1) % careMessages.length
}

function logout() {
  // 清理本应用所有会话字段，确保退出后可以切换到另一端重新登录。
  localStorage.removeItem('healthybot_role')
  localStorage.removeItem('healthybot_user')
  localStorage.removeItem('healthybot_token')
  role.value = ''
  user.value = null
  active.value = 'assistant'
}
</script>

<template>
  <!-- 顶层：黑白底色切换按钮（浮层，z-index 最高，登录页也可见） -->
  <button
    class="theme-toggle"
    type="button"
    :title="isDark ? '切换到浅色白底' : '切换到深色黑底'"
    @click="toggleTheme"
  >
    <span class="tt-icon">{{ isDark ? '☾' : '☀' }}</span>
    <span class="tt-label">{{ isDark ? '深色' : '浅色' }}</span>
  </button>

  <LoginPage v-if="!role" @login="onLogin" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand-mark"><span class="brand-dot"></span><span>Healthy<span>Bot</span></span></div>
      <div class="role-chip">{{ role === 'admin' ? '管理端' : '用户端' }} · {{ user?.name || '演示用户' }}</div>
      <nav class="side-nav"><button v-for="t in tabs" :key="t.key" :class="{active: active === t.key}" @click="active = t.key"><span class="nav-icon">{{ t.icon }}</span>{{ t.label }}</button></nav>
      <div
        class="care-card photo-host"
        role="button"
        tabindex="0"
        :title="`点击切换下一句（${careIndex + 1}/${careMessages.length}）`"
        @click="nextCare"
        @keydown.enter.prevent="nextCare"
        @keydown.space.prevent="nextCare"
      >
        <span class="photo-corner care-photo ph-card-2" aria-hidden="true"></span>
        <transition name="care-fade" mode="out-in">
          <div class="care-body" :key="careIndex">
            <strong>{{ care.title }}</strong>
            <span>{{ care.text }}</span>
          </div>
        </transition>
      </div>
      <div class="sidebar-footer"><button class="logout-btn" @click="logout">退出登录 <span>↗</span></button></div>
    </aside>
    <main class="main-shell"><header class="main-topbar"><div class="breadcrumb">{{ role === 'admin' ? '管理中心' : '我的健康空间' }} <span>/</span> {{ tabs.find(t => t.key === active)?.label }}</div><div class="top-actions"><button class="icon-btn" title="通知">◔</button><div class="avatar">{{ (user?.name || '健').slice(0, 1) }}</div><button class="top-logout" title="退出当前账号" @click="logout"><span>↪</span><span>退出</span></button></div></header><div class="content-wrap"><component :is="current" :key="active" /></div></main>
  </div>
</template>
