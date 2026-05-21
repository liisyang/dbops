<template>
  <Transition
    enter-active-class="transition ease-out duration-200"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition ease-in duration-150"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex"
    >
      <div
        class="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
        @click="emit('close')"
      />
      <Transition
        enter-active-class="transition ease-out duration-200"
        enter-from-class="translate-x-full"
        enter-to-class="translate-x-0"
        leave-active-class="transition ease-in duration-150"
        leave-from-class="translate-x-0"
        leave-to-class="translate-x-full"
      >
        <aside
          v-if="open"
          class="relative ml-auto flex h-full w-full max-w-3xl flex-col border-l border-outline-variant bg-surface shadow-2xl"
        >
          <header class="border-b border-outline-variant/60 px-6 py-5">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0 space-y-2">
                <div class="flex items-center gap-2">
                  <h2 class="truncate text-lg font-semibold text-on-surface">
                    {{ title }}
                  </h2>
                  <slot name="badge" />
                </div>
                <p v-if="subtitle" class="truncate text-sm text-on-surface-variant">
                  {{ subtitle }}
                </p>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-lg border border-outline-variant px-3 py-1.5 text-sm text-on-surface-variant transition-colors hover:border-primary hover:text-primary"
                @click="emit('close')"
              >
                关闭
              </button>
            </div>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            <div class="space-y-6 text-sm text-on-surface">
              <slot />
            </div>
          </div>
        </aside>
      </Transition>
    </div>
  </Transition>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  subtitle?: string
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()
</script>
