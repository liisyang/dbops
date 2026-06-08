<template>
  <section class="preview-info-section">
    <div class="flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2">
        <span class="inline-flex h-7 w-7 items-center justify-center rounded-md border border-primary/25 bg-primary/10">
          <span class="material-symbols-outlined text-[15px] text-primary">{{ icon }}</span>
        </span>
        <h3 class="min-w-0 truncate text-sm font-semibold text-slate-100">
          {{ title }}
        </h3>
      </div>
      <span v-if="tag" class="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-[11px] text-slate-300">
        {{ tag }}
      </span>
    </div>

    <div class="mt-3">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  icon: string
  tag?: string
}>()
</script>
