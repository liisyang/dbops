<template>
  <div class="flex h-screen overflow-hidden">
    <!-- Sidebar -->
    <aside class="fixed left-0 top-0 h-full w-64 z-40 bg-[#0a151a]/80 backdrop-blur-xl flex flex-col py-8 border-r border-[#424754]/15 font-['Inter'] uppercase tracking-[0.05rem] text-[0.75rem]">
      <!-- Logo -->
      <div class="px-6 mb-12 flex items-center gap-3">
        <div class="h-10 w-10 rounded-lg flex items-center justify-center bg-gradient-to-br from-[#4d8eff] to-[#2b5fc4] shadow-[0_8px_20px_rgba(77,142,255,0.25)]">
          <span class="text-white font-black text-lg leading-none">D</span>
        </div>
        <div>
          <h2 class="text-[#d8e4ec] font-black block">DBOPS</h2>
          <p class="text-[#c2c6d6] opacity-70 lowercase font-normal tracking-normal text-[0.65rem]">运维平台</p>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="flex-grow space-y-2">
        <template v-for="item in menuItems" :key="item.key">
          <!-- Submenu -->
          <div v-if="item.children">
            <button
              @click="toggleSubmenu(item.key)"
              class="w-full flex items-center px-6 py-3 text-[#c2c6d6] opacity-70 hover:bg-[#121d23] hover:text-[#9ecaff] transition-all cursor-pointer"
              :class="{ 'text-[#d8e4ec] bg-[#162127]': openSubmenus[item.key] }"
            >
              <span class="material-symbols-outlined mr-3">{{ item.icon }}</span>
              <span class="flex-1 text-left">{{ item.label }}</span>
              <span class="material-symbols-outlined text-sm transition-transform" :class="{ 'rotate-90': openSubmenus[item.key] }">
                chevron_right
              </span>
            </button>
            <!-- Children -->
            <div v-if="openSubmenus[item.key]" class="ml-4">
              <router-link
                v-for="child in item.children"
                :key="child.path"
                :to="child.path"
                class="flex items-center px-6 py-3 text-[#c2c6d6] opacity-70 hover:bg-[#121d23] hover:text-[#9ecaff] transition-all cursor-pointer"
                :class="{ 'text-[#d8e4ec] bg-[#162127] border-l-2 border-[#9ecaff]': isActive(child.path) }"
              >
                <span class="material-symbols-outlined mr-3 text-base">{{ child.icon }}</span>
                <span>{{ child.label }}</span>
              </router-link>
            </div>
          </div>
          <!-- Single menu item -->
          <router-link
            v-else
            :to="item.path!"
            class="flex items-center px-6 py-3 text-[#c2c6d6] opacity-70 hover:bg-[#121d23] hover:text-[#9ecaff] transition-all cursor-pointer"
            :class="{ 'text-[#d8e4ec] bg-[#162127] border-l-2 border-[#9ecaff]': isActive(item.path!) }"
          >
            <span class="material-symbols-outlined mr-3">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </router-link>
        </template>
      </nav>

      <!-- Bottom Section -->
      <div class="border-t border-[#424754]/15 pt-6 mt-auto">
        <button
          @click="handleLogout"
          class="w-full flex items-center px-6 py-3 text-[#c2c6d6] opacity-70 hover:bg-[#121d23] hover:text-[#9ecaff] transition-all"
        >
          <span class="material-symbols-outlined mr-3">logout</span>
          退出登录
        </button>
      </div>
    </aside>

    <!-- Main Canvas -->
    <div class="ml-64 flex-1 flex flex-col h-screen overflow-hidden">
      <!-- Top Navigation -->
      <header class="fixed top-0 left-64 right-0 z-50 border-b border-white/10 bg-[#0a151a]/78 backdrop-blur-xl">
        <div class="flex h-16 items-center justify-between gap-6 px-6">
          <div class="flex min-w-0 items-center gap-6">
            <div class="text-sm font-bold uppercase tracking-[0.22em] text-[#d8e4ec]">Enterprise CMDB</div>

            <nav class="flex min-w-0 flex-1 items-stretch gap-0 overflow-x-auto whitespace-nowrap">
              <router-link
                v-for="tab in topTabs"
                :key="tab.key"
                :to="tab.path"
                class="px-3 py-5 text-xs font-medium transition-colors duration-200"
                :class="isTopTabActive(tab)
                  ? 'border-b-2 border-[#9ecaff] text-[#d8e4ec]'
                  : 'border-b-2 border-transparent text-[#c2c6d6] hover:text-[#d8e4ec]'"
              >
                {{ tab.label }}
              </router-link>
            </nav>
          </div>

          <div class="flex items-center gap-3">
            <button class="flex items-center gap-2 rounded-md bg-[#162127] px-3 py-1.5 text-xs text-[#c2c6d6] transition-colors hover:bg-[#202b32]">
              <span class="material-symbols-outlined text-[16px]">search</span>
              <span class="hidden sm:inline">全局搜索</span>
              <kbd class="rounded bg-[#2b363d] px-1.5 py-0.5 text-[0.6rem] uppercase text-[#b4cad6]">cmd+k</kbd>
            </button>
            <button class="rounded p-2 text-[#c2c6d6] transition-colors hover:bg-[#162127] hover:text-[#d8e4ec]">
              <span class="material-symbols-outlined text-[18px]">notifications</span>
            </button>
            <div class="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 transition-colors hover:bg-[#162127]">
              <div class="flex h-8 w-8 items-center justify-center rounded-full bg-[#2b363d]">
                <span class="material-symbols-outlined text-[#c2c6d6]">account_circle</span>
              </div>
              <span class="text-sm font-medium text-[#d8e4ec] tracking-tight">{{ username }}</span>
            </div>
          </div>
        </div>
      </header>

      <!-- Content -->
      <main class="mt-16 flex-1 overflow-auto bg-[#0a151a] p-10">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const username = ref(localStorage.getItem('username') || 'Admin')

// Menu items
const menuItems = [
  { key: 'dashboard', icon: 'dashboard', label: '仪表盘', path: '/dashboard' },
  {
    key: 'ops',
    icon: 'build',
    label: '自动化运维',
    children: [
      { icon: 'dns', label: '主机清单', path: '/ops/inventory' },
      { icon: 'play_circle', label: '作业执行', path: '/ops/tasks' },
      { icon: 'checklist', label: '批量校验', path: '/ops/batch-verify' },
    ]
  },
      {
        key: 'assets',
        icon: 'folder',
        label: '资产管理',
        children: [
          { icon: 'business', label: '业务', path: '/assets/businesses' },
          { icon: 'cloud', label: '服务器', path: '/assets/servers' },
          { icon: 'storage', label: '数据库实例', path: '/assets/instances' },
          { icon: 'hub', label: '集群', path: '/assets/clusters' },
          { icon: 'person', label: '联系人', path: '/assets/contacts' },
          { icon: 'cloud_upload', label: '导入', path: '/assets/import' },
        ]
      },
  {
    key: 'backup',
    icon: 'sync',
    label: '备份与恢复',
    children: [
      { icon: 'settings', label: '备份策略', path: '/backup/policies' },
      { icon: 'schedule', label: '备份作业', path: '/backup/jobs' },
      { icon: 'restore', label: '恢复中心', path: '/backup/restore' },
    ]
  },
  {
    key: 'sql',
    icon: 'code',
    label: 'SQL分析',
    children: [
      { icon: 'fact_check', label: 'SQL审计', path: '/sql/audit' },
      { icon: 'timer', label: '慢查询', path: '/sql/slow' },
      { icon: 'local_fire_department', label: 'TOP SQL', path: '/sql/top' },
    ]
  },
  {
    key: 'inspection',
    icon: 'health_and_safety',
    label: '巡检与健康',
    children: [
      { icon: 'description', label: '巡检报告', path: '/inspection/reports' },
      { icon: 'favorite', label: '健康检查', path: '/inspection/health' },
    ]
  },
  {
    key: 'audit',
    icon: 'security',
    label: '审计与安全',
    children: [
      { icon: 'history', label: '操作日志', path: '/audit/operations' },
      { icon: 'key', label: '登录日志', path: '/audit/login' },
      { icon: 'visibility', label: '敏感操作', path: '/audit/sensitive' },
    ]
  },
  {
    key: 'credentials',
    icon: 'key',
    label: '凭证中心',
    children: [
      { icon: 'description', label: '凭证引用', path: '/credentials/profiles' },
      { icon: 'link', label: '凭证绑定', path: '/credentials/bindings' },
    ]
  },
  { key: 'knowledge', icon: 'menu_book', label: '知识库', path: '/knowledge' },
]

const openSubmenus = ref<Record<string, boolean>>({})

const topTabs = [
  { key: 'dashboard', label: '仪表盘', path: '/dashboard', match: ['/dashboard'] },
  { key: 'ops', label: '自动化运维', path: '/ops/tasks', match: ['/ops'] },
  { key: 'assets', label: '资产管理', path: '/assets/servers', match: ['/assets'] },
  { key: 'backup', label: '备份与恢复', path: '/backup/policies', match: ['/backup'] },
  { key: 'sql', label: 'SQL分析', path: '/sql/audit', match: ['/sql'] },
  { key: 'inspection', label: '巡检与健康', path: '/inspection/reports', match: ['/inspection'] },
  { key: 'audit', label: '审计与安全', path: '/audit/operations', match: ['/audit'] },
  { key: 'credentials', label: '凭证中心', path: '/credentials/profiles', match: ['/credentials'] },
  { key: 'knowledge', label: '知识库', path: '/knowledge', match: ['/knowledge'] },
] as const

function isActive(path: string) {
  return route.path === path
}

function isTopTabActive(tab: { path: string; match: readonly string[] }) {
  return tab.match.some((prefix) => route.path === prefix || route.path.startsWith(`${prefix}/`))
}

const activeSidebarKey = computed(() => {
  const matched = menuItems.find((item) => {
    if (!item.children) return false
    return item.children.some((child) => route.path === child.path || route.path.startsWith(`${child.path}/`))
  })
  return matched?.key ?? null
})

function toggleSubmenu(key: string) {
  openSubmenus.value[key] = !openSubmenus.value[key]
}

function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  router.push('/login')
}

onMounted(() => {
  username.value = localStorage.getItem('username') || 'Admin'
})

watch(
  activeSidebarKey,
  (key) => {
    openSubmenus.value = key ? { [key]: true } : {}
  },
  { immediate: true }
)
</script>
