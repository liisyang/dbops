<template>
  <!-- Oracle: custom inline SVG -->
  <svg v-if="isOracle" :width="px" :height="px" viewBox="1 5 30 22" :title="dbType" class="inline-block shrink-0" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="16" cy="16" rx="15" ry="10" fill="#C74634" />
    <text x="16" y="20" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="10" fill="white" letter-spacing="0.5">ORA</text>
  </svg>
  <!-- IBM custom inline SVGs -->
  <svg v-else-if="customIcon" :width="px" :height="px" viewBox="0 0 32 32" :title="dbType" class="inline-block shrink-0" xmlns="http://www.w3.org/2000/svg">
    <rect width="32" height="32" rx="5" :fill="customIcon.bg" />
    <text x="16" y="21" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" :font-size="customIcon.fontSize" fill="white" letter-spacing="0.5">{{ customIcon.label }}</text>
  </svg>
  <!-- Other DBs: devicon CDN SVG -->
  <img v-else-if="iconUrl" :src="iconUrl" :width="px" :height="px" :title="dbType" :alt="dbType" class="inline-block shrink-0" />
  <!-- Fallback: Material Symbol -->
  <span v-else class="material-symbols-outlined shrink-0" :style="{ fontSize: `${px}px` }" :title="dbType">storage</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  dbType: string
  size?: 'sm' | 'md' | 'lg'
}>(), {
  size: 'md',
})

const CDN = 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons'

const ICON_MAP: Record<string, string> = {
  postgresql:    `${CDN}/postgresql/postgresql-plain.svg`,
  postgres:      `${CDN}/postgresql/postgresql-plain.svg`,
  mysql:         `${CDN}/mysql/mysql-original.svg`,
  mariadb:       `${CDN}/mariadb/mariadb-original.svg`,
  'sql server':  `${CDN}/microsoftsqlserver/microsoftsqlserver-plain.svg`,
  sqlserver:     `${CDN}/microsoftsqlserver/microsoftsqlserver-plain.svg`,
  mssql:         `${CDN}/microsoftsqlserver/microsoftsqlserver-plain.svg`,
  mongodb:       `${CDN}/mongodb/mongodb-plain.svg`,
  redis:         `${CDN}/redis/redis-plain.svg`,
  elasticsearch: `${CDN}/elasticsearch/elasticsearch-original.svg`,
}

// IBM custom icons: { label, bg, fontSize }
const CUSTOM_ICON_MAP: Record<string, { label: string; bg: string; fontSize: number }> = {
  db2:        { label: 'DB2', bg: '#1F70C1', fontSize: 9 },
  informix:   { label: 'INF', bg: '#1F70C1', fontSize: 9 },
  informixap: { label: 'AP',  bg: '#1F70C1', fontSize: 11 },
}

const key = computed(() => props.dbType?.toLowerCase().trim() ?? '')
const isOracle = computed(() => key.value === 'oracle')
const customIcon = computed(() => CUSTOM_ICON_MAP[key.value] ?? null)
const iconUrl = computed(() => ICON_MAP[key.value] ?? null)
const px = computed(() => ({ sm: 16, md: 20, lg: 24 }[props.size]))
</script>
