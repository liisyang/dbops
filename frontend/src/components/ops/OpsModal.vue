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
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/60 backdrop-blur-[3px]"
          @click="emit('close')"
        />

        <!-- Modal Panel -->
        <Transition
          enter-active-class="transition ease-out duration-200"
          enter-from-class="opacity-0 scale-95 translate-y-2"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition ease-in duration-150"
          leave-from-class="opacity-100 scale-100 translate-y-0"
          leave-to-class="opacity-0 scale-95 translate-y-2"
        >
          <div
            v-if="open"
            class="relative w-full rounded-2xl border border-outline-variant/50 bg-surface-container shadow-[0_25px_50px_-12px_rgba(0,0,0,0.5)]"
            :class="sizeClass"
          >
            <!-- Header -->
            <header class="flex items-center justify-between border-b border-outline-variant/40 px-6 py-4">
              <div class="flex items-center gap-3">
                <div
                  v-if="icon"
                  class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15"
                >
                  <span class="material-symbols-outlined text-[20px] text-primary">{{ icon }}</span>
                </div>
                <div>
                  <h2 class="text-base font-semibold text-on-surface">{{ title }}</h2>
                  <p v-if="subtitle" class="mt-0.5 text-xs text-on-surface-variant">{{ subtitle }}</p>
                </div>
              </div>
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-white/10 hover:text-on-surface"
                @click="emit('close')"
              >
                <span class="material-symbols-outlined text-[20px]">close</span>
              </button>
            </header>

            <!-- Body -->
            <div class="max-h-[70vh] overflow-y-auto px-6 py-5">
              <slot />
            </div>

            <!-- Footer -->
            <footer v-if="$slots.footer" class="border-t border-outline-variant/40 px-6 py-4">
              <slot name="footer" />
            </footer>
          </div>
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
  size?: 'sm' | 'md' | 'lg' | 'xl'
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()

const sizeClass = computed(() => {
  switch (props.size) {
    case 'sm': return 'max-w-md'
    case 'lg': return 'max-w-3xl'
    case 'xl': return 'max-w-5xl'
    default: return 'max-w-2xl'
  }
})
</script>
