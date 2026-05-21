<template>
  <div class="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
    <AssetStatCard
      v-for="item in items"
      :key="item.label"
      :label="item.label"
      :value="item.value"
      :hint="item.hint"
      :icon="item.icon"
      :tone="item.tone"
    />
  </div>
</template>

<script setup lang="ts">
import AssetStatCard from '@/components/AssetStatCard.vue'

defineProps<{
  items: Array<{
    label: string
    value: string | number
    hint?: string
    icon?: string
    tone?: 'primary' | 'success' | 'warning' | 'muted'
  }>
}>()
</script>
