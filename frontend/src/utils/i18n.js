import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

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

