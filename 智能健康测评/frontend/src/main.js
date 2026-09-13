import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { initTheme } from './theme-mode'

// 挂载前先应用主题，避免刷新时闪一下
initTheme()

createApp(App).mount('#app')
