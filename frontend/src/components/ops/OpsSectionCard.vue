<template>
  <section class="rounded-lg bg-surface-container p-5">
    <header v-if="title || subtitle || $slots.actions" class="flex items-start justify-between gap-4">
      <div class="space-y-1">
        <div v-if="title" class="flex items-center gap-2">
          <span
            v-if="icon"
            class="inline-flex h-6 w-6 items-center justify-center rounded-md border border-white/10 bg-white/5 text-[14px] text-sky-200"
          >
            <span class="material-symbols-outlined text-[14px] leading-none">{{ icon }}</span>
          </span>
          <h2 class="text-base font-semibold text-on-surface">
            {{ title }}
          </h2>
        </div>
        <p v-if="subtitle" class="text-xs text-on-surface-variant">
          {{ subtitle }}
        </p>
      </div>
      <div class="shrink-0">
        <slot name="actions" />
      </div>
    </header>

    <div :class="title || subtitle || $slots.actions ? 'mt-4' : ''">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title?: string
  subtitle?: string
  icon?: string
}>()
</script>
