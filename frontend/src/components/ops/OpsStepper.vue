<template>
  <div class="w-full">
    <ol class="flex flex-col gap-4 rounded-2xl border border-white/10 bg-transparent px-1 py-1 lg:flex-row lg:items-center lg:justify-between">
      <li
        v-for="(step, index) in steps"
        :key="step.label"
        class="relative flex min-w-0 flex-1 items-start gap-3 px-3 py-2"
        :aria-current="index + 1 === currentStep ? 'step' : undefined"
      >
        <div
          class="flex aspect-square h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold"
          :class="circleClass(index)"
        >
          <span v-if="index + 1 < currentStep" class="material-symbols-outlined text-[16px] leading-none text-white">check</span>
          <span v-else class="leading-none text-white">{{ index + 1 }}</span>
        </div>

        <div class="min-w-0">
          <div class="text-sm font-medium text-on-surface">
            {{ step.label }}
          </div>
          <p v-if="step.description" class="mt-0.5 text-xs text-slate-400">
            {{ step.description }}
          </p>
        </div>

        <div
          v-if="index < steps.length - 1"
          class="pointer-events-none absolute right-[-0.75rem] top-1/2 hidden h-px w-6 -translate-y-1/2 bg-white/10 lg:block"
        />
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
interface StepperStep {
  label: string
  description?: string
}

const props = defineProps<{
  steps: StepperStep[]
  currentStep: number
}>()

function getStepState(index: number) {
  if (index + 1 < props.currentStep) return 'complete'
  if (index + 1 === props.currentStep) return 'current'
  return 'upcoming'
}

function circleClass(index: number) {
  const state = getStepState(index)
  if (state === 'complete') return 'border-emerald-300/30 bg-emerald-500/70 text-white shadow-[inset_0_0_16px_rgba(236,253,245,0.14)]'
  if (state === 'current') return 'border-blue-300/45 bg-blue-500 text-white shadow-[inset_0_0_16px_rgba(219,234,254,0.12)]'
  return 'border-white/10 bg-slate-600/70 text-slate-300'
}
</script>
