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
export function getUserTimezone() {
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

// 格式化相对时间
export function formatRelative(utcString) {
  if (!utcString) return '-'
  return dayjs(utcString).fromNow()
}

// 常用时区列表
export const TIMEZONE_LIST = [
  { value: 'Asia/Shanghai', label: '北京 (UTC+8)', city: 'Beijing' },
  { value: 'Asia/Taipei', label: '台北 (UTC+8)', city: 'Taipei' },
  { value: 'Asia/Ho_Chi_Minh', label: '胡志明 (UTC+7)', city: 'Ho+Chi+Minh' },
  { value: 'Asia/Bangkok', label: '曼谷 (UTC+7)', city: 'Bangkok' },
  { value: 'Asia/Singapore', label: '新加坡 (UTC+8)', city: 'Singapore' },
  { value: 'Asia/Tokyo', label: '东京 (UTC+9)', city: 'Tokyo' },
  { value: 'Asia/Seoul', label: '首尔 (UTC+9)', city: 'Seoul' },
  { value: 'Asia/Kolkata', label: '印度 (UTC+5:30)', city: 'Mumbai' },
  { value: 'Europe/London', label: '伦敦 (UTC+0)', city: 'London' },
  { value: 'Europe/Paris', label: '巴黎 (UTC+1)', city: 'Paris' },
  { value: 'Europe/Berlin', label: '柏林 (UTC+1)', city: 'Berlin' },
  { value: 'America/New_York', label: '纽约 (UTC-5)', city: 'New+York' },
  { value: 'America/Los_Angeles', label: '洛杉矶 (UTC-8)', city: 'Los+Angeles' },
  { value: 'America/Chicago', label: '芝加哥 (UTC-6)', city: 'Chicago' },
  { value: 'UTC', label: 'UTC', city: 'London' },
]

export default {
  detectTimezone,
  getUserTimezone,
  setUserTimezone,
  formatInTz,
  formatRelative,
  TIMEZONE_LIST,
}
