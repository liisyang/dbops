export interface LanguageOption {
  value: string
  label: string
}

// 语言列表
export const LANGUAGE_LIST: LanguageOption[] = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'pt-BR', label: 'Português' },
]

// 检测浏览器语言
export function detectLanguage(): string {
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
export function getUserLanguage(): string {
  return localStorage.getItem('userLanguage') || detectLanguage()
}

// 设置用户语言
export function setUserLanguage(lang: string): void {
  localStorage.setItem('userLanguage', lang)
}

export default {
  LANGUAGE_LIST,
  detectLanguage,
  getUserLanguage,
  setUserLanguage,
}
