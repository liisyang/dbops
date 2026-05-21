<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-on-surface flex items-center gap-2">
          <span class="material-symbols-outlined">upload</span>
          导入历史
        </h1>
        <p class="text-on-surface-variant text-sm mt-1">查看导入操作记录</p>
      </div>
    </div>

    <div class="bg-surface-container rounded-lg p-8 text-center">
      <span class="material-symbols-outlined text-5xl text-on-surface-variant">fact_check</span>
      <p class="mt-4 text-on-surface-variant">导入日志加载中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

onMounted(() => {
  // TODO: Load real data
})
</script>