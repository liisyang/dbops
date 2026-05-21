<template>
  <OpsPage>
    <OpsPageHeader title="知识库" subtitle="DBA 运维知识沉淀与检索，文档、手册、故障案例一站管理。" />
    <OpsEmptyState
      state="development"
      icon="menu_book"
      title="知识库功能开发中"
      description="该模块正在规划中，敬请期待。"
    />
  </OpsPage>
</template>

<script setup lang="ts">
import { OpsEmptyState, OpsPage, OpsPageHeader } from '@/components/ops'
</script>
