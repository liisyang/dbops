import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

// 检测浏览器时区
export function detectTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

// 获取用户时区设置
function getUserTimezone() {
  return localStorage.getItem('userTimezone') || detectTimezone()
}

// 设置用户时区
export function setUserTimezone(tz) {
  localStorage.setItem('userTimezone', tz)
}

// 格式化时间为用户时区
export function formatInTz(utcString, pattern = 'YYYY-MM-DD HH:mm:ss') {
  const tz = getUserTimezone()
  if (!utcString) return '-'
  return dayjs(utcString).tz(tz).format(pattern)
}

