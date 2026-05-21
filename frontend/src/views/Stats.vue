<template>
  <section class="space-y-6">
    <header class="flex items-end justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-on-surface">分类统计</h1>
        <p class="mt-1 text-sm text-on-surface-variant">按国家、厂区、部署类型、Provider、业务大类和数据库类型查看资产分布。</p>
      </div>
      <button class="rounded-lg border border-outline-variant px-3 py-2 text-sm text-on-surface" @click="loadAll">
        刷新
      </button>
    </header>

    <div class="grid gap-4 xl:grid-cols-3">
      <article v-for="card in cards" :key="card.title" class="rounded-lg bg-surface-container p-5">
        <h2 class="text-sm font-medium text-on-surface">{{ card.title }}</h2>
        <ul class="mt-4 space-y-3 text-sm">
          <li v-for="row in card.rows" :key="row.key" class="flex items-center justify-between">
            <span class="text-on-surface">{{ row.key }}</span>
            <span class="text-on-surface-variant">{{ row.count }}</span>
          </li>
          <li v-if="!card.rows.length" class="text-on-surface-variant">暂无数据</li>
        </ul>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { statsApi } from '@/api/stats'
import type { GroupedResult } from '@/types/api'

type GenericGroup = GroupedResult<Record<string, string>>

const country = ref<GenericGroup>({ groups: [] })
const factory = ref<GenericGroup>({ groups: [] })
const deployType = ref<GenericGroup>({ groups: [] })
const provider = ref<GenericGroup>({ groups: [] })
const dbType = ref<GenericGroup>({ groups: [] })
const systemGroup = ref<GenericGroup>({ groups: [] })

const cards = computed(() => [
  { title: '按国家', rows: country.value.groups.map(item => ({ key: item.country, count: item.count })) },
  { title: '按厂区', rows: factory.value.groups.map(item => ({ key: item.factory_area, count: item.count })) },
  { title: '按部署类型', rows: deployType.value.groups.map(item => ({ key: item.deploy_type, count: item.count })) },
  { title: '按 Provider', rows: provider.value.groups.map(item => ({ key: item.provider, count: item.count })) },
  { title: '按数据库类型', rows: dbType.value.groups.map(item => ({ key: item.db_type, count: item.count })) },
  { title: '按业务大类', rows: systemGroup.value.groups.map(item => ({ key: item.system_group, count: item.count })) },
])

async function loadAll() {
  const [countryRes, factoryRes, deployRes, providerRes, dbTypeRes, systemGroupRes] = await Promise.all([
    statsApi.getByCountry(),
    statsApi.getByFactory(),
    statsApi.getByDeployType(),
    statsApi.getByProvider(),
    statsApi.getSummaryByType(),
    statsApi.getBySystemGroup(),
  ])
  country.value = countryRes as GenericGroup
  factory.value = factoryRes as GenericGroup
  deployType.value = deployRes as GenericGroup
  provider.value = providerRes as GenericGroup
  dbType.value = dbTypeRes as GenericGroup
  systemGroup.value = systemGroupRes as GenericGroup
}

onMounted(loadAll)
</script>
