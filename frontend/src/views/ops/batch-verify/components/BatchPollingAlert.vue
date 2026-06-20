<!--
  BatchPollingAlert — 黄色轮询错误条

  由详情页 BatchVerifyDetail 在 pollError 非空时渲染。
-->
<template>
  <div
    v-if="message"
    class="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 flex items-center justify-between"
  >
    <span>{{ message }}</span>
    <button class="underline text-xs" @click="emit('dismiss')">关闭</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{ message: string }>()
const emit = defineEmits<{ (e: 'dismiss'): void }>()
</script>