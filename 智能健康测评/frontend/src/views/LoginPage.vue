<script setup>
import { reactive, ref } from 'vue'
import { loginAccount } from '../api'
const emit = defineEmits(['login'])
const fixedRole = import.meta.env.VITE_DEFAULT_ROLE || ''
const form = reactive({ account: '', password: '', role: fixedRole || 'user' })
const error = ref('')
const loading = ref(false)
async function login() {
  error.value = ''
  if (!form.account || !form.password) { error.value = '请输入账号和密码'; return }
  loading.value = true
  try {
    const resp = await loginAccount({ account: form.account, password: form.password, role: form.role })
    const payload = resp.data || { role: form.role, user: { id: form.account, name: form.role === 'admin' ? '运营管理员' : '林晓晴' } }
    localStorage.setItem('healthybot_role', payload.role)
    localStorage.setItem('healthybot_user', JSON.stringify(payload.user))
    if (payload.token) localStorage.setItem('healthybot_token', payload.token)
    emit('login', payload)
  } catch (e) {
    error.value = e.message || (form.role === 'admin' ? '管理端账号或密码不正确' : '用户端账号或密码不正确')
  }
  loading.value = false
}
</script>
<template>
  <div class="login-screen">
    <div class="login-visual"><div class="visual-glow glow-a"></div><div class="visual-glow glow-b"></div><img class="visual-reference" src="/login-reference.png" alt="HealthyBot 健康工作台预览"><div class="visual-copy"><span class="overline">HEALTHYBOT · YOUR DAILY CARE</span><h1>让健康管理<br><em>变得有温度</em></h1><p>记录每一餐、每一次运动和每一晚睡眠，AI 会陪你把复杂的健康问题变成今天就能做的小事。</p><div class="visual-stats"><span><b>4</b> 个健康 Agent</span><span><b>24h</b> 连续陪伴</span></div></div><div class="visual-orbit"><span class="orbit-dot one"></span><span class="orbit-dot two"></span><span class="orbit-line"></span></div></div>
    <div class="login-panel"><div class="login-brand"><span class="brand-dot"></span><strong>HealthyBot</strong></div><div class="login-copy"><span class="overline">WELCOME BACK</span><h2>登录你的健康空间</h2><p>继续今天的健康记录。</p></div><div v-if="!fixedRole" class="role-switch"><button :class="{active: form.role === 'user'}" @click="form.role = 'user'">用户端</button><button :class="{active: form.role === 'admin'}" @click="form.role = 'admin'">管理端</button></div><form @submit.prevent="login"><label>账号<input v-model="form.account" :placeholder="form.role === 'admin' ? '请输入管理账号' : '请输入用户账号'" autocomplete="username" /></label><label>密码<input v-model="form.password" type="password" placeholder="请输入密码" autocomplete="current-password" /></label><div class="form-meta"><span>演示账号：{{ form.role === 'admin' ? 'admin / admin123' : 'user / user123' }}</span><a href="#">忘记密码？</a></div><button class="login-btn" :disabled="loading">{{ loading ? '登录中…' : '进入健康空间' }} <span>→</span></button></form><div v-if="error" class="login-error">{{ error }}</div><div class="login-foot">登录即代表你同意健康数据使用说明 · 数据仅用于本地演示</div></div>
  </div>
</template>
