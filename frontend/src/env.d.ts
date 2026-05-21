/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// Locale modules
declare module '@/locales/zh-CN'
declare module '@/locales/zh-TW'
declare module '@/locales/en'
declare module '@/locales/ja'
declare module '@/locales/pt-BR'

// Global properties for Vue
interface Window {
  $formatTime: (utcString: string | null | undefined, pattern?: string) => string
}
