<template>
  <header class="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
    <div class="space-y-1">
      <h1 class="text-2xl font-semibold text-on-surface">{{ title }}</h1>
      <p v-if="subtitle" class="text-sm text-on-surface-variant">
        {{ subtitle }}
      </p>
    </div>

    <div v-if="$slots.actions" class="flex items-center gap-3">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>
