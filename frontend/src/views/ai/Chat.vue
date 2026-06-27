<template>
  <OpsPage>
    <OpsPageHeader
      title="AI Copilot"
      subtitle="基于 Dify 的智能运维对话（C5 落地交互界面）"
    />
    <OpsSectionCard>
      <OpsEmptyState
        state="development"
        title="Chat UI 将在 C5 实现"
        description="当前页提供路由占位与 capabilities 灰度。完整对话 UI（会话列表 + 消息流 + 输入框 + 错误兜底）由 Phase 3.6 C5 落地。"
      />
    </OpsSectionCard>
  </OpsPage>
</template>

<script setup lang="ts">
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
</script>
