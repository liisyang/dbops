<template>
  <OpsPage>
    <OpsPageHeader
      title="UI 预览 · 服务器详情"
      subtitle="模拟 /assets/servers/481，仅用于开发预览（Mock 数据）。"
    />

    <section class="mb-5 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <span class="inline-flex items-center gap-2 text-sm text-on-surface-variant">
          <span class="material-symbols-outlined text-[18px]">preview</span>
          详情页交互预览
        </span>

        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="ops-secondary-button" @click="previewMode = 'loading'">
            <span class="material-symbols-outlined text-[18px]">hourglass_empty</span>
            加载态
          </button>
          <button type="button" class="ops-secondary-button" @click="previewMode = 'empty'">
            <span class="material-symbols-outlined text-[18px]">inbox</span>
            空态
          </button>
          <button type="button" class="ops-primary-button" @click="previewMode = 'data'">
            <span class="material-symbols-outlined text-[18px]">refresh</span>
            数据态
          </button>
        </div>
      </div>

      <OpsEntityHeader
        :title="mockServer.ip_address"
        :subtitle-parts="[mockServer.hostname, mockServer.server_code, mockServer.environment]"
        icon="dns"
        :status="mockServer.status"
        :chips="serverHeaderChips"
      />
    </section>

    <section class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
      <OpsSectionCard title="基礎信息" subtitle="服务器详情基础字段（Mock）" icon="info">
        <div class="preview-info-shell">
          <div class="mt-4 space-y-4">
            <InfoSection
              v-for="group in baseInfoGroups"
              :key="group.key"
              :title="group.title"
              :icon="group.icon"
              :tag="group.subtitle"
            >
              <div class="grid gap-2 md:grid-cols-2">
                <InfoItem
                  v-for="field in group.fields"
                  :key="`${group.key}-${field.label}`"
                  :label="field.label"
                  :value="field.value"
                  :emphasis="field.emphasis"
                />
              </div>
            </InfoSection>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="运行概览" subtitle="面向预览页的关键信息汇总" icon="schema">
        <div class="grid gap-3">
          <MetricCard title="磁盘使用率" :hint="`容量 ${mockServer.disk_gb} GB`" :value="`${mockServer.disk_usage}%`" icon="hard_drive" :percent="mockServer.disk_usage" bar-class="bg-gradient-to-r from-[#4d96ff] to-[#67c3ff]" />
          <MetricCard title="内存使用率" :hint="`容量 ${mockServer.memory_gb} GB`" :value="`${mockServer.memory_usage}%`" icon="memory" :percent="mockServer.memory_usage" bar-class="bg-gradient-to-r from-[#7c6cff] to-[#b06cff]" />
          <MetricCard title="CPU 使用率" :hint="`规格 ${mockServer.cpu_cores} Core`" :value="`${mockServer.cpu_usage}%`" icon="bolt" :percent="mockServer.cpu_usage" bar-class="bg-gradient-to-r from-[#43d19e] to-[#69e6b8]" />

          <section class="preview-muted-card">
            <div class="flex items-start gap-3">
              <span class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                <span class="material-symbols-outlined text-[20px] text-slate-300">schedule</span>
              </span>
              <div class="min-w-0 flex-1">
                <div class="text-sm font-medium text-slate-100">最近心跳</div>
                <div class="mt-1 text-xs text-slate-400">Mock 更新时间 / 实时心跳待接入</div>
              </div>
              <StatusBadge label="在线" tone="success" />
            </div>
            <div class="mt-3 text-sm font-medium text-slate-200">{{ mockServer.last_seen }}</div>
          </section>
        </div>
      </OpsSectionCard>
    </section>

    <OpsSectionCard title="当前关联实例" subtitle="展示当前服务器挂载的实例列表。" icon="hub">
      <OpsEmptyState
        v-if="previewMode === 'loading'"
        state="loading"
        title="关联实例加载中"
        description="用于预览详情页加载态。"
      />

      <div v-else-if="previewInstances.length" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="instance in previewInstances"
          :key="instance.id"
          class="field-card"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="field-label">实例编号</div>
              <div class="field-value font-mono">{{ instance.instance_code || '-' }}</div>
            </div>
            <StatusBadge :label="instance.node_role || instance.engine_role || '-'" tone="neutral" />
          </div>
          <div class="mt-2 text-sm text-on-surface">
            {{ instance.instance_name || '-' }}
          </div>
          <div class="mt-3 grid gap-2 text-xs text-on-surface-variant">
            <div>数据库类型：{{ instance.db_type || '-' }}</div>
            <div>Cluster：{{ instance.cluster_code || '-' }}</div>
            <div>服务器 IP：{{ instance.server_ip || '-' }}</div>
          </div>
        </div>
      </div>

      <OpsEmptyState
        v-else
        state="empty"
        title="暂无关联实例"
        description="当前服务器没有返回实例关系。"
      />
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  OpsEmptyState,
  OpsEntityHeader,
  OpsPage,
  OpsPageHeader,
  OpsSectionCard,
} from '@/components/ops'

import InfoItem from './components/InfoItem.vue'
import InfoSection from './components/InfoSection.vue'
import MetricCard from './components/MetricCard.vue'
import StatusBadge from './components/StatusBadge.vue'

type PreviewInstance = {
  id: number
  instance_code: string
  instance_name: string
  db_type: string
  node_role?: string
  engine_role: string
  cluster_code: string
  server_ip?: string
}

type PreviewField = {
  label: string
  value: string
  emphasis?: boolean
}

type PreviewFieldGroup = {
  key: string
  icon: string
  title: string
  subtitle: string
  fields: PreviewField[]
}

function displayValue(value: string | number | null | undefined, emptyText = '未配置') {
  if (value === null || value === undefined || value === '') return emptyText
  return String(value)
}

const mockServer = {
  ip_address: '10.134.181.168',
  hostname: 'dbops-app-481',
  server_code: 'SRV-00481',
  server_type: 'VM',
  deploy_type: 'KVM',
  provider: 'IDC',
  environment: 'PROD',
  status: 'active',
  os: 'CentOS 7.9',
  cpu_cores: 16,
  cpu_usage: 42,
  memory_gb: 64,
  memory_usage: 68,
  disk_gb: 1024,
  disk_usage: 78,
  factory_area: 'CN-SH-1',
  room_location: 'A3-12',
  owner_team: 'DBA Platform',
  backup_policy: 'daily-02',
  patch_level: '2026.05',
  last_seen: '2026-05-27 10:58:10',
  instance_count: 5,
}

const MOCK_INSTANCES: PreviewInstance[] = [
  { id: 1, instance_code: 'INS-481-01', instance_name: 'order-main', db_type: 'MySQL', node_role: 'master', engine_role: 'primary', cluster_code: 'CLU-481', server_ip: '10.134.181.168' },
  { id: 2, instance_code: 'INS-481-02', instance_name: 'order-standby', db_type: 'MySQL', node_role: 'slave', engine_role: 'standby', cluster_code: 'CLU-481', server_ip: '10.134.181.168' },
  { id: 3, instance_code: 'INS-481-03', instance_name: 'audit-main', db_type: 'PostgreSQL', node_role: 'primary', engine_role: 'primary', cluster_code: 'CLU-713', server_ip: '10.134.181.168' },
  { id: 4, instance_code: 'INS-481-04', instance_name: 'legacy-report', db_type: 'Oracle', node_role: 'standby', engine_role: 'standby', cluster_code: 'CLU-081', server_ip: '10.134.181.168' },
  { id: 5, instance_code: 'INS-481-05', instance_name: 'etl-report', db_type: 'ClickHouse', node_role: 'primary', engine_role: 'primary', cluster_code: 'CLU-905', server_ip: '10.134.181.168' },
]

const previewMode = ref<'data' | 'empty' | 'loading'>('data')
const previewInstances = computed(() => (previewMode.value === 'empty' ? [] : MOCK_INSTANCES))

const baseInfoGroups = computed<PreviewFieldGroup[]>(() => [
  {
    key: 'identity',
    icon: 'badge',
    title: '主机标识',
    subtitle: '优先关注',
    fields: [
      { label: 'IP', value: displayValue(mockServer.ip_address), emphasis: true },
      { label: '主机名', value: displayValue(mockServer.hostname), emphasis: true },
      { label: '服务器编号', value: displayValue(mockServer.server_code) },
      { label: 'DNS 名称', value: displayValue(null) },
      { label: '主机属性', value: displayValue(mockServer.server_type) },
    ],
  },
  {
    key: 'resource',
    icon: 'tune',
    title: '资源规格',
    subtitle: '容量信息',
    fields: [
      { label: 'CPU 核数', value: `${mockServer.cpu_cores} Core`, emphasis: true },
      { label: '内存 GB', value: `${mockServer.memory_gb} GB`, emphasis: true },
      { label: '磁盘 GB', value: `${mockServer.disk_gb} GB`, emphasis: true },
    ],
  },
  {
    key: 'location',
    icon: 'location_on',
    title: '位置与部署',
    subtitle: '机房落点',
    fields: [
      { label: '国家 / 厂区', value: `CN / ${mockServer.factory_area}` },
      { label: '机房位置', value: displayValue(mockServer.room_location) },
      { label: '部署类型', value: displayValue(mockServer.deploy_type) },
      { label: 'Provider', value: displayValue(mockServer.provider) },
    ],
  },
  {
    key: 'system',
    icon: 'settings',
    title: '系统与归属',
    subtitle: '运维上下文',
    fields: [
      { label: 'OS 类型', value: 'Linux' },
      { label: 'OS 版本', value: displayValue(mockServer.os) },
      { label: '业务组', value: displayValue(mockServer.owner_team) },
    ],
  },
])

const serverHeaderChips = computed(() => [
  { icon: 'computer', label: mockServer.server_type },
  { icon: 'view_in_ar', label: mockServer.deploy_type },
  { icon: 'cloud', label: mockServer.provider },
  { icon: 'hub', label: `${mockServer.instance_count} 台实例` },
])
</script>
