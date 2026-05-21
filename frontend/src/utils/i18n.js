import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

// 语言列表
export const LANGUAGE_LIST = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'pt-BR', label: 'Português' },
]

// 默认语言
const DEFAULT_LANGUAGE = 'zh-CN'

// 检测浏览器语言
export function detectLanguage() {
  const browserLang = navigator.language
  // 匹配中文
  if (browserLang.startsWith('zh')) {
    return browserLang === 'zh-TW' || browserLang === 'zh-HK' ? 'zh-TW' : 'zh-CN'
  }
  // 匹配日语
  if (browserLang.startsWith('ja')) return 'ja'
  // 匹配葡萄牙语
  if (browserLang.startsWith('pt')) return 'pt-BR'
  // 默认英语
  return 'en'
}

// 获取用户语言设置
export function getUserLanguage() {
  return localStorage.getItem('userLanguage') || detectLanguage()
}

// 设置用户语言
export function setUserLanguage(lang) {
  localStorage.setItem('userLanguage', lang)
}

export default {
  LANGUAGE_LIST,
  detectLanguage,
  getUserLanguage,
  setUserLanguage,
}
