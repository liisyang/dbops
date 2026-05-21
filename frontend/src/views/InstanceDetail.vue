<template>
  <OpsPage>
    <div class="mb-4">
      <router-link
        to="/assets/instances"
        class="inline-flex items-center gap-2 text-sm text-on-surface-variant transition-colors hover:text-on-surface"
      >
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        返回列表
      </router-link>
    </div>

    <OpsPageHeader title="实例详情" :subtitle="headerSubtitle" />

    <OpsSectionCard v-if="loading" title="实例详情" subtitle="正在加载实例信息">
      <OpsEmptyState state="loading" title="正在加载实例详情" description="请稍候。" />
    </OpsSectionCard>

    <OpsSectionCard v-else-if="error" title="实例详情" subtitle="加载失败">
      <OpsEmptyState state="error" title="实例详情加载失败" :description="error" />
    </OpsSectionCard>

    <section v-else-if="detail" class="space-y-4">
      <OpsSectionCard title="基础信息" icon="info">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in baseFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="角色信息" icon="badge">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in roleFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="主机信息" icon="dns">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in hostFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>

      <OpsSectionCard title="集群信息" icon="hub">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="field in clusterFields" :key="field.label" class="field-card">
            <div class="field-label">{{ field.label }}</div>
            <div class="field-value">{{ field.value }}</div>
          </div>
        </div>
      </OpsSectionCard>
    </section>
  </OpsPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { assetsApi } from '@/api/assets'
import { OpsEmptyState, OpsPage, OpsPageHeader, OpsSectionCard } from '@/components/ops'
import type { InstanceDetail } from '@/types/api'

type DetailField = {
  label: string
  value: string
}

const route = useRoute()
const detail = ref<InstanceDetail | null>(null)
const loading = ref(false)
const error = ref('')
const instanceId = computed(() => {
  const rawId = route.params.id
  return Array.isArray(rawId) ? rawId[0] : rawId
})

const headerSubtitle = computed(() => {
  if (!detail.value) return '查看实例、角色、主机与集群信息。'
  return [detail.value.db_type, detail.value.db_version].filter(Boolean).join(' ') || '查看实例、角色、主机与集群信息。'
})

const baseFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '实例编号', value: formatValue(detail.value.instance_code) },
    { label: '实例名称', value: formatValue(detail.value.instance_name) },
    { label: '数据库类型', value: formatValue(detail.value.db_type) },
    { label: '数据库版本', value: formatValue(detail.value.db_version) },
  ]
})

const roleFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '基础角色', value: formatValue(detail.value.node_role) },
    { label: '专属角色', value: formatValue(detail.value.engine_role) },
    { label: '来源角色', value: formatValue(detail.value.source_node_role) },
  ]
})

const hostFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: '服务器 IP', value: formatValue(detail.value.server_ip) },
    { label: '主机名', value: formatValue(detail.value.hostname) },
    { label: '站点', value: formatValue([detail.value.country, detail.value.factory_area].filter(Boolean).join(' / ')) },
    { label: '部署类型', value: formatValue(detail.value.deploy_type) },
    { label: 'Provider', value: formatValue(detail.value.provider) },
  ]
})

const clusterFields = computed<DetailField[]>(() => {
  if (!detail.value) return []

  return [
    { label: 'Cluster', value: formatValue(detail.value.cluster_code) },
    { label: 'Cluster 名称', value: formatValue(detail.value.cluster_name) },
    { label: '集群类型', value: formatValue(detail.value.cluster_type) },
  ]
})

watch(
  () => route.params.id,
  async () => {
    const id = instanceId.value
    if (!id) {
      detail.value = null
      error.value = '缺少实例 ID'
      return
    }

    loading.value = true
    error.value = ''

    try {
      detail.value = await assetsApi.getInstance(id)
    } catch (err: any) {
      detail.value = null
      error.value = err?.response?.data?.detail || err?.message || '加载失败'
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  return String(value)
}
</script>


