<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="open" class="fixed inset-0 z-40 flex justify-end">
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/60 backdrop-blur-[3px]"
          @click="emit('close')"
        />

        <!-- Drawer Panel -->
        <Transition
          enter-active-class="transition ease-out duration-250"
          enter-from-class="translate-x-full"
          enter-to-class="translate-x-0"
          leave-active-class="transition ease-in duration-200"
          leave-from-class="translate-x-0"
          leave-to-class="translate-x-full"
        >
          <aside
            v-if="open"
            class="relative flex h-full w-full flex-col border-l border-outline-variant/50 bg-surface-container shadow-[-25px_0_50px_-12px_rgba(0,0,0,0.5)]"
            :class="widthClass"
          >
            <!-- Header -->
            <header class="flex items-start justify-between gap-4 border-b border-outline-variant/40 px-6 py-4">
              <div class="flex min-w-0 flex-1 items-start gap-3">
                <div
                  v-if="icon"
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/15"
                >
                  <span class="material-symbols-outlined text-[20px] text-primary">{{ icon }}</span>
                </div>
                <div class="min-w-0 flex-1">
                  <h2 class="truncate text-base font-semibold text-on-surface">{{ title }}</h2>
                  <p v-if="subtitle" class="mt-0.5 truncate text-xs text-on-surface-variant">{{ subtitle }}</p>
                </div>
              </div>
              <button
                type="button"
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-white/10 hover:text-on-surface"
                @click="emit('close')"
              >
                <span class="material-symbols-outlined text-[20px]">close</span>
              </button>
            </header>

            <!-- Body -->
            <div class="flex-1 overflow-y-auto px-6 py-5">
              <slot />
            </div>

            <!-- Footer -->
            <footer v-if="$slots.footer" class="border-t border-outline-variant/40 px-6 py-4">
              <slot name="footer" />
            </footer>
          </aside>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  subtitle?: string
  icon?: string
  width?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()

const widthClass = computed(() => {
  switch (props.width) {
    case 'sm': return 'max-w-sm'
    case 'md': return 'max-w-md'
    case 'lg': return 'max-w-2xl'
    case 'xl': return 'max-w-4xl'
    case 'full': return 'max-w-full'
    default: return 'max-w-3xl'
  }
})
</script>
