/**
 * 主题模式（深空黑底 / 浅色白底）
 * - 状态写入 <html> 的 class：html.dark / html.light
 * - 选择持久化到 localStorage，刷新后保持
 */
import { ref } from 'vue'

const STORAGE_KEY = 'healthybot_theme'

export const isDark = ref(true)

function apply(dark) {
  isDark.value = dark
  const root = document.documentElement
  root.classList.toggle('dark', dark)
  root.classList.toggle('light', !dark)
  root.dataset.theme = dark ? 'dark' : 'light'
  try {
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  } catch (e) {
    /* 隐私模式下忽略 */
  }
}

export function initTheme() {
  let saved = null
  try {
    saved = localStorage.getItem(STORAGE_KEY)
  } catch (e) {
    saved = null
  }
  apply(saved ? saved === 'dark' : true)
}

export function toggleTheme() {
  apply(!isDark.value)
}
