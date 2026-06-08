<template>
  <OpsPage>
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <a
        class="inline-flex items-center gap-2 text-sm text-on-surface-variant transition-colors hover:text-on-surface cursor-pointer"
        @click.prevent="previewMode = 'data'"
      >
        <span class="material-symbols-outlined text-[16px]">arrow_back</span>
        返回列表
      </a>

      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="ops-secondary-button" @click="previewMode = 'loading'">
          <span class="material-symbols-outlined text-[16px]">hourglass_empty</span>
          加载态
        </button>
        <button type="button" class="ops-secondary-button" @click="previewMode = 'error'">
          <span class="material-symbols-outlined text-[16px]">error</span>
          错误态
        </button>
        <button type="button" class="ops-secondary-button" @click="previewMode = 'empty'">
          <span class="material-symbols-outlined text-[16px]">inbox</span>
          空态
        </button>
        <button type="button" class="ops-primary-button" @click="previewMode = 'data'">
          <span class="material-symbols-outlined text-[16px]">visibility</span>
          数据态
        </button>
      </div>
    </div>

    <!-- Instance Header -->
    <OpsEntityHeader
      :title="previewMode === 'empty' ? '实例详情' : mockInstance.instance_name"
      :subtitle-parts="headerSubtitleParts"
      icon="storage"
      :chips="headerChips"
    />

    <!-- Loading State -->
    <section v-if="previewMode === 'loading'" class="mt-6 rounded-2xl border border-white/5 bg-surface-container p-8">
      <div class="flex flex-col items-center justify-center py-16 text-center">
        <span class="material-symbols-outlined animate-spin text-5xl text-on-surface-variant/40">progress_activity</span>
        <h3 class="mt-5 text-base font-semibold text-on-surface">正在加载实例详情</h3>
        <p class="mt-2 text-sm text-on-surface-variant/60">请稍候，模拟加载中（Mock）。</p>
      </div>
    </section>

    <!-- Error State -->
    <section v-else-if="previewMode === 'error'" class="mt-6 rounded-2xl border border-white/5 bg-surface-container p-8">
      <div class="flex flex-col items-center justify-center py-16 text-center">
        <span class="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-error/10">
          <span class="material-symbols-outlined text-[32px] text-error">error</span>
        </span>
        <h3 class="mt-5 text-base font-semibold text-on-surface">实例详情加载失败</h3>
        <p class="mt-2 text-sm text-on-surface-variant/60">模拟接口错误：连接超时或权限不足（Mock）。</p>
      </div>
    </section>

    <!-- Data State: Two-Column Layout -->
    <div v-else class="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <!-- Left Column: Detail Sections -->
      <div class="space-y-6">
        <section class="rounded-2xl border border-white/5 bg-surface-container p-5">
          <header class="mb-5 flex items-center gap-3">
            <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
              <span class="material-symbols-outlined text-[16px] text-primary">info</span>
            </span>
            <div>
              <h2 class="text-[15px] font-semibold text-on-surface">基础信息</h2>
              <p class="mt-0.5 text-xs text-on-surface-variant/60">实例标识与数据库版本</p>
            </div>
          </header>
          <div class="grid gap-3 sm:grid-cols-2">
            <div v-for="field in baseFields" :key="field.label" class="rounded-xl bg-surface-container-high p-4">
              <div class="text-xs font-medium tracking-wide text-on-surface-variant/70 font-mono">{{ field.label }}</div>
              <div class="mt-2 text-sm font-medium text-on-surface">{{ field.value }}</div>
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-white/5 bg-surface-container p-5">
          <header class="mb-5 flex items-center gap-3">
            <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
              <span class="material-symbols-outlined text-[16px] text-primary">badge</span>
            </span>
            <div>
              <h2 class="text-[15px] font-semibold text-on-surface">角色信息</h2>
              <p class="mt-0.5 text-xs text-on-surface-variant/60">运行职责与拓扑角色</p>
            </div>
          </header>
          <div class="grid gap-3 sm:grid-cols-2">
            <div v-for="field in roleFields" :key="field.label" class="rounded-xl bg-surface-container-high p-4">
              <div class="text-xs font-medium tracking-wide text-on-surface-variant/70 font-mono">{{ field.label }}</div>
              <div class="mt-2 text-sm font-medium text-on-surface">{{ field.value }}</div>
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-white/5 bg-surface-container p-5">
          <header class="mb-5 flex items-center gap-3">
            <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
              <span class="material-symbols-outlined text-[16px] text-primary">dns</span>
            </span>
            <div>
              <h2 class="text-[15px] font-semibold text-on-surface">主机信息</h2>
              <p class="mt-0.5 text-xs text-on-surface-variant/60">宿主机、站点与部署属性</p>
            </div>
          </header>
          <div class="grid gap-3 sm:grid-cols-2">
            <div v-for="field in hostFields" :key="field.label" class="rounded-xl bg-surface-container-high p-4">
              <div class="text-xs font-medium tracking-wide text-on-surface-variant/70 font-mono">{{ field.label }}</div>
              <div class="mt-2 text-sm font-medium text-on-surface">{{ field.value }}</div>
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-white/5 bg-surface-container p-5">
          <header class="mb-5 flex items-center gap-3">
            <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
              <span class="material-symbols-outlined text-[16px] text-primary">hub</span>
            </span>
            <div>
              <h2 class="text-[15px] font-semibold text-on-surface">集群信息</h2>
              <p class="mt-0.5 text-xs text-on-surface-variant/60">集群归属与协同上下文</p>
            </div>
          </header>
          <div class="grid gap-3 sm:grid-cols-2">
            <div v-for="field in clusterFields" :key="field.label" class="rounded-xl bg-surface-container-high p-4">
              <div class="text-xs font-medium tracking-wide text-on-surface-variant/70 font-mono">{{ field.label }}</div>
              <div class="mt-2 text-sm font-medium text-on-surface">{{ field.value }}</div>
            </div>
          </div>
        </section>
      </div>

      <!-- Right Panel: Metrics & Actions -->
      <aside class="space-y-4">
        <!-- Sync Status Card -->
        <section class="rounded-2xl border border-white/5 bg-surface-container p-5">
          <header class="mb-4 flex items-center gap-2.5">
            <span class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5">
              <span class="material-symbols-outlined text-[14px] text-primary">sync</span>
            </span>
            <h3 class="text-sm font-semibold text-on-surface">运行概览</h3>
          </header>

          <div class="space-y-3">
            <!-- Sync Progress -->
            <div class="rounded-xl bg-surface-container-high p-4">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs text-on-surface-variant/70 font-mono">同步进度</div>
                  <div class="mt-1 text-lg font-semibold text-on-surface">{{ mockMetrics.sync_progress }}%</div>
                </div>
                <span class="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] font-medium text-emerald-200">
                  <span class="size-1.5 rounded-full bg-emerald-400"></span>
                  正常
                </span>
              </div>
              <div class="mt-3 h-2 rounded-full bg-surface-container-low">
                <div class="h-2 rounded-full bg-gradient-to-r from-primary/60 to-primary" :style="{ width: `${mockMetrics.sync_progress}%` }" />
              </div>
            </div>

            <!-- Connection Rate -->
            <div class="rounded-xl bg-surface-container-high p-4">
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs text-on-surface-variant/70 font-mono">连接活跃度</div>
                  <div class="mt-1 text-lg font-semibold text-on-surface">{{ mockMetrics.connection_rate }}%</div>
                </div>
                <span class="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-200">
                  <span class="size-1.5 rounded-full bg-amber-400"></span>
                  关注
                </span>
              </div>
              <div class="mt-3 h-2 rounded-full bg-surface-container-low">
                <div class="h-2 rounded-full bg-gradient-to-r from-emerald-400/60 to-emerald-400" :style="{ width: `${mockMetrics.connection_rate}%` }" />
              </div>
            </div>

            <!-- Last Sync Time -->
            <div class="rounded-xl bg-surface-container-high p-4">
              <div class="text-xs text-on-surface-variant/70 font-mono">最近同步时间</div>
              <div class="mt-1.5 text-sm font-medium text-on-surface font-mono">{{ mockMetrics.last_sync_time }}</div>
              <div class="mt-1 text-[11px] text-on-surface-variant/50">Mock 更新时间 · 真实同步待接入</div>
            </div>
          </div>
        </section>

        <!-- Quick Info Card -->
        <section class="rounded-2xl border border-white/5 bg-surface-container p-5">
          <header class="mb-4 flex items-center gap-2.5">
            <span class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5">
              <span class="material-symbols-outlined text-[14px] text-primary">info</span>
            </span>
            <h3 class="text-sm font-semibold text-on-surface">快捷信息</h3>
          </header>

          <div class="space-y-2">
            <div v-for="item in quickInfoItems" :key="item.label" class="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-surface-container-high">
              <span class="text-xs text-on-surface-variant/70 font-mono">{{ item.label }}</span>
              <span class="text-sm font-medium text-on-surface">{{ item.value }}</span>
            </div>
          </div>
        </section>

        <!-- Actions -->
        <div class="flex flex-col gap-2">
          <button type="button" class="ops-primary-button w-full">
            <span class="material-symbols-outlined text-[16px]">edit</span>
            编辑实例
          </button>
          <button type="button" class="ops-secondary-button w-full">
            <span class="material-symbols-outlined text-[16px]">history</span>
            审计日志
          </button>
        </div>
      </aside>
    </div>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import { OpsEntityHeader, OpsPage } from '@/components/ops'

type DetailField = { label: string; value: string }

const previewMode = ref<'data' | 'empty' | 'error' | 'loading'>('data')

const mockInstance = {
  instance_code: 'INS-00481',
  instance_name: 'order-main',
  db_type: 'MySQL',
  db_version: '8.0.36',
  node_role: 'master',
  engine_role: 'primary',
  source_node_role: 'primary',
  server_ip: '10.134.181.168',
  hostname: 'dbops-app-481',
  country: 'CN',
  factory_area: 'CN-SH-1',
  deploy_type: 'KVM',
  provider: 'IDC',
  cluster_code: 'CLU-481',
  cluster_name: 'order-cluster',
  cluster_type: 'MGR',
}

const mockMetrics = {
  sync_progress: 86,
  connection_rate: 92,
  last_sync_time: '2026-05-28 13:58:10',
}

const headerSubtitleParts = computed(() => {
  if (previewMode.value === 'empty') return ['查看实例、角色、主机与集群信息。']
  return [mockInstance.instance_code, mockInstance.db_type, mockInstance.db_version]
})

const headerChips = computed(() => [
  { icon: 'hub', label: `集群 ${mockInstance.cluster_code}` },
  { icon: 'dns', label: `服务器 ${mockInstance.server_ip}` },
])

const baseFields = computed<DetailField[]>(() => [
  { label: '实例编号', value: formatValue(mockInstance.instance_code) },
  { label: '实例名称', value: formatValue(mockInstance.instance_name) },
  { label: '数据库类型', value: formatValue(mockInstance.db_type) },
  { label: '数据库版本', value: formatValue(mockInstance.db_version) },
])

const roleFields = computed<DetailField[]>(() => [
  { label: '基础角色', value: formatValue(mockInstance.node_role) },
  { label: '专属角色', value: formatValue(mockInstance.engine_role) },
  { label: '来源角色', value: formatValue(mockInstance.source_node_role) },
])

const hostFields = computed<DetailField[]>(() => [
  { label: '服务器 IP', value: formatValue(mockInstance.server_ip) },
  { label: '主机名', value: formatValue(mockInstance.hostname) },
  { label: '站点', value: formatValue([mockInstance.country, mockInstance.factory_area].filter(Boolean).join(' / ')) },
  { label: '部署类型', value: formatValue(mockInstance.deploy_type) },
  { label: 'Provider', value: formatValue(mockInstance.provider) },
])

const clusterFields = computed<DetailField[]>(() => [
  { label: 'Cluster', value: formatValue(mockInstance.cluster_code) },
  { label: 'Cluster 名称', value: formatValue(mockInstance.cluster_name) },
  { label: '集群类型', value: formatValue(mockInstance.cluster_type) },
])

const quickInfoItems = computed(() => [
  { label: '数据库类型', value: mockInstance.db_type },
  { label: '部署类型', value: mockInstance.deploy_type },
  { label: '厂区', value: mockInstance.factory_area },
  { label: 'Provider', value: mockInstance.provider },
])

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}
</script>
