import { defineStore } from 'pinia'
import { detectTimezone, setUserTimezone } from '@/utils/timezone'
import { detectLanguage } from '@/utils/i18n'

export const useUserStore = defineStore('user', {
  state: () => ({
    timezone: localStorage.getItem('userTimezone') || detectTimezone(),
    language: localStorage.getItem('userLanguage') || detectLanguage(),
    username: localStorage.getItem('username') || '',
    userId: localStorage.getItem('userId') || null,
    token: localStorage.getItem('token') || '',
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    locale: (state) => state.language,
  },

  actions: {
    setUserTimezone(tz) {
      this.timezone = tz
      setUserTimezone(tz)
    },

    setUserLanguage(lang) {
      this.language = lang
      localStorage.setItem('userLanguage', lang)
    },

    login(userData, token) {
      this.token = token
      this.username = userData.username
      this.userId = userData.id
      // 时区可从后端同步或用户设置
      if (userData.timezone) {
        this.timezone = userData.timezone
        setUserTimezone(userData.timezone)
      } else {
        const detectedTz = localStorage.getItem('userTimezone') || detectTimezone()
        this.timezone = detectedTz
        setUserTimezone(detectedTz)
      }
      // 语言可从后端同步
      if (userData.language) {
        this.language = userData.language
        localStorage.setItem('userLanguage', userData.language)
      } else {
        const detectedLang = localStorage.getItem('userLanguage') || detectLanguage()
        this.language = detectedLang
        localStorage.setItem('userLanguage', detectedLang)
      }
      localStorage.setItem('token', token)
      localStorage.setItem('username', userData.username)
      localStorage.setItem('userId', userData.id)
    },

    logout() {
      this.token = ''
      this.username = ''
      this.userId = null
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('userId')
    },

    // 从后端同步用户配置
    syncFromBackend(userData) {
      if (userData.timezone) {
        this.timezone = userData.timezone
        setUserTimezone(userData.timezone)
      }
      if (userData.language) {
        this.language = userData.language
        localStorage.setItem('userLanguage', userData.language)
      }
    },
  },
})
