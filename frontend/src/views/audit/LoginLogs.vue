<template>
  <div class="space-y-4">
    <div class="bg-surface-container rounded-lg p-8 text-center">
      <span class="material-symbols-outlined text-5xl text-on-surface-variant">construction</span>
      <h2 class="mt-4 text-xl font-semibold text-on-surface">功能开发中</h2>
      <p class="mt-2 text-on-surface-variant">登录日志功能即将上线</p>
      <router-link to="/dashboard" class="inline-block mt-4 px-4 py-2 bg-primary text-on-primary rounded-xl hover:bg-primary/90 transition-colors">
        返回仪表盘
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>