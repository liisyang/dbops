<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-on-surface flex items-center gap-2">
          <span class="material-symbols-outlined">dns</span>
          主机管理
        </h1>
        <p class="text-on-surface-variant text-sm mt-1">管理主机信息</p>
      </div>
    </div>

    <div class="bg-surface-container rounded-lg p-8 text-center">
      <span class="material-symbols-outlined text-5xl text-on-surface-variant">computer</span>
      <p class="mt-4 text-on-surface-variant">主机管理加载中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

onMounted(() => {
  // TODO: Load real data
})
</script>