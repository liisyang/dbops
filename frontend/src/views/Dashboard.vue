<template>
  <section class="space-y-6">
    <header>
      <h1 class="text-2xl font-semibold text-on-surface">资产总览</h1>
      <p class="mt-1 text-sm text-on-surface-variant">第一阶段资产底座的汇总视图。</p>
    </header>

    <div class="grid gap-4 md:grid-cols-4">
      <div v-for="card in cards" :key="card.label" class="rounded-lg bg-surface-container p-5">
        <div class="text-xs uppercase text-on-surface-variant">{{ card.label }}</div>
        <div class="mt-2 text-3xl font-semibold text-on-surface">{{ card.value }}</div>
      </div>
    </div>

    <div class="grid gap-4">
      <div class="space-y-4">
        <div class="rounded-lg bg-surface-container p-5">
          <h2 class="text-sm font-medium text-on-surface">按数据库类型分布</h2>
          <p class="mt-1 text-xs text-on-surface-variant">数据库实例数量</p>
          <div class="mt-4">
            <SimpleBarChart :items="dbTypeChart" :as-card="false" />
          </div>
        </div>

        <div class="rounded-lg bg-surface-container p-5">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-sm font-medium text-on-surface">按国家 / 厂区 / 实例数</h2>
              <p class="mt-1 text-xs text-on-surface-variant">按实例数量看地域分布</p>
            </div>
            <div class="rounded-lg bg-surface-container-high px-3 py-2 text-right">
              <div class="text-[11px] uppercase tracking-wide text-on-surface-variant">实例总数</div>
              <div class="mt-1 text-xl font-semibold text-on-surface">{{ dashboard.total_instances }}</div>
            </div>
          </div>

          <div class="mt-4 grid gap-4 lg:grid-cols-2">
            <div class="rounded-lg bg-surface-container-high p-4">
              <h3 class="text-sm font-medium text-on-surface">按国家分布</h3>
              <div class="mt-3">
                <SimpleBarChart :items="countryChart" :as-card="false" />
              </div>
            </div>

            <div class="rounded-lg bg-surface-container-high p-4">
              <h3 class="text-sm font-medium text-on-surface">按厂区分布</h3>
              <div class="mt-3">
                <SimpleBarChart :items="factoryChart" :as-card="false" />
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-lg bg-surface-container p-5">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-sm font-medium text-on-surface">按部署类型 / Provider / 实例数</h2>
              <p class="mt-1 text-xs text-on-surface-variant">按实例数量看部署环境分布</p>
            </div>
            <div class="rounded-lg bg-surface-container-high px-3 py-2 text-right">
              <div class="text-[11px] uppercase tracking-wide text-on-surface-variant">实例总数</div>
              <div class="mt-1 text-xl font-semibold text-on-surface">{{ dashboard.total_instances }}</div>
            </div>
          </div>

          <div class="mt-4 grid gap-4 lg:grid-cols-2">
            <div class="rounded-lg bg-surface-container-high p-4">
              <h3 class="text-sm font-medium text-on-surface">按部署类型分布</h3>
              <div class="mt-3">
                <SimpleBarChart :items="deployTypeChart" :as-card="false" />
              </div>
            </div>

            <div class="rounded-lg bg-surface-container-high p-4">
              <h3 class="text-sm font-medium text-on-surface">按资源提供方分布</h3>
              <div class="mt-3">
                <SimpleBarChart :items="providerChart" :as-card="false" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import SimpleBarChart from '@/components/SimpleBarChart.vue'
import { statsApi } from '@/api/stats'
import type { DashboardSummary, GroupedResult } from '@/types/api'

const dashboard = ref<DashboardSummary>({
  total_business_systems: 0,
  total_clusters: 0,
  total_instances: 0,
  total_servers: 0,
})
const byDbType = ref<GroupedResult<{ db_type: string }>>({ groups: [] })
const byCountry = ref<GroupedResult<{ country: string }>>({ groups: [] })
const byFactory = ref<GroupedResult<{ factory_area: string }>>({ groups: [] })
const byDeployType = ref<GroupedResult<{ deploy_type: string }>>({ groups: [] })
const byProvider = ref<GroupedResult<{ provider: string }>>({ groups: [] })

const cards = computed(() => [
  { label: '业务系统', value: dashboard.value.total_business_systems },
  { label: '集群', value: dashboard.value.total_clusters },
  { label: '实例', value: dashboard.value.total_instances },
  { label: '服务器', value: dashboard.value.total_servers },
])

const factoryChart = computed(() =>
  byFactory.value.groups.map(group => ({
    label: group.factory_area,
    value: group.count,
  })),
)

const dbTypeChart = computed(() =>
  byDbType.value.groups.map(group => ({
    label: group.db_type,
    value: group.count,
  })),
)

const countryChart = computed(() =>
  byCountry.value.groups.map(group => ({
    label: group.country,
    value: group.count,
  })),
)

const deployTypeChart = computed(() =>
  byDeployType.value.groups.map(group => ({
    label: group.deploy_type,
    value: group.count,
  })),
)

const providerChart = computed(() =>
  byProvider.value.groups.map(group => ({
    label: group.provider,
    value: group.count,
  })),
)

onMounted(async () => {
  const [dash, dbTypeStats, countryStats, factoryStats, deployTypeStats, providerStats] = await Promise.all([
    statsApi.getDashboard(),
    statsApi.getSummaryByType(),
    statsApi.getByCountry(),
    statsApi.getByFactory(),
    statsApi.getByDeployType(),
    statsApi.getByProvider(),
  ])
  dashboard.value = dash
  byDbType.value = dbTypeStats
  byCountry.value = countryStats
  byFactory.value = factoryStats
  byDeployType.value = deployTypeStats
  byProvider.value = providerStats
})
</script>
