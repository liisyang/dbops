<template>
  <form
    class="flex items-end gap-2 rounded-lg border border-outline-variant/40 bg-surface-container p-2"
    @submit.prevent="handleSubmit"
  >
    <textarea
      ref="textareaRef"
      v-model="text"
      class="min-h-[40px] max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none"
      :placeholder="placeholder"
      :disabled="disabled"
      rows="1"
      @keydown.enter.exact.prevent="handleSubmit"
      @input="autoResize"
    />
    <button
      type="submit"
      class="ops-primary-button inline-flex h-9 items-center gap-1.5 px-3"
      :disabled="disabled || !text.trim()"
    >
      <span class="material-symbols-outlined text-[18px]">send</span>
      发送
    </button>
  </form>
</template>

<script setup lang="ts">
/**
 * AI Copilot — 输入框（textarea + 发送按钮）
 *
 * 设计：
 * - v-model 双向绑定，发送后由父组件清空
 * - Enter 发送；Shift+Enter 换行（textarea 自身支持）
 * - disabled 时 textarea 与按钮同时禁用，避免重复点击
 * - autoResize 适配内容高度（最大 160px）
 */
import { ref, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  disabled?: boolean
  placeholder?: string
}>(), {
  disabled: false,
  placeholder: '输入消息，Enter 发送，Shift+Enter 换行',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send', value: string): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const text = ref(props.modelValue)

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function handleSubmit() {
  const trimmed = text.value.trim()
  if (!trimmed || props.disabled) return
  emit('send', trimmed)
  text.value = ''
  nextTick(autoResize)
}
</script>
