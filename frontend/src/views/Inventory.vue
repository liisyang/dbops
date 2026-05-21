<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-on-surface flex items-center gap-2">
          <span class="material-symbols-outlined">inbox</span>
          主机清单
        </h1>
        <p class="text-on-surface-variant text-sm mt-1">管理主机库存信息</p>
      </div>
    </div>

    <div class="bg-surface-container rounded-lg p-8 text-center">
      <span class="material-symbols-outlined text-5xl text-on-surface-variant">inventory_2</span>
      <p class="mt-4 text-on-surface-variant">主机清单加载中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

onMounted(() => {
  // TODO: Load real data
})
</script>