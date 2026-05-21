import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import './assets/styles/main.css'
import { formatInTz } from '@/utils/timezone'
import { detectLanguage } from '@/utils/i18n'
import zhCN from '@/locales/zh-CN'
import zhTW from '@/locales/zh-TW'
import en from '@/locales/en'
import ja from '@/locales/ja'
import ptBR from '@/locales/pt-BR'
import App from './App.vue'
import router from './router'

// 检测浏览器语言
const browserLanguage = detectLanguage()

// 创建 i18n 实例
const i18n = createI18n({
  legacy: false,
  locale: browserLanguage,
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
    'zh-TW': zhTW,
    en,
    ja,
    'pt-BR': ptBR
  }
})

const app = createApp(App)
const pinia = createPinia()

// 全局时间格式化过滤器
app.config.globalProperties.$formatTime = (utcString: string | null | undefined, pattern = 'YYYY-MM-DD HH:mm:ss') => {
  return formatInTz(utcString, pattern)
}

app.use(pinia)
app.use(router)
app.use(i18n)
app.mount('#app')