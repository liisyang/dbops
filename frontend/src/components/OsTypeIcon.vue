<template>
  <!-- Devicon CDN SVG icons -->
  <img
    v-if="iconUrl"
    :src="iconUrl"
    :width="px"
    :height="px"
    :title="label"
    :alt="label"
    class="inline-block shrink-0"
  />
  <!-- Custom inline SVG for OSes not in Devicon -->
  <svg
    v-else-if="customIcon"
    :width="px"
    :height="px"
    viewBox="0 0 32 32"
    :title="label"
    class="inline-block shrink-0"
    xmlns="http://www.w3.org/2000/svg"
  >
    <rect width="32" height="32" rx="5" :fill="customIcon.bg" />
    <text
      x="16" y="21"
      text-anchor="middle"
      font-family="Arial,sans-serif"
      font-weight="700"
      :font-size="customIcon.fontSize"
      fill="white"
    >{{ customIcon.label }}</text>
  </svg>
  <!-- Fallback -->
  <span
    v-else
    class="material-symbols-outlined shrink-0"
    :style="{ fontSize: `${px}px` }"
    :title="label"
  >computer</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  osName: string       // e.g. 'Linux', 'Windows'
  osVersion?: string   // e.g. 'CentOS_7.9_x64', 'OracleLinux_8.10_x64'
  size?: 'sm' | 'md' | 'lg'
}>(), {
  osVersion: '',
  size: 'md',
})

const CDN = 'https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons'

// keyword → devicon SVG
const DEVICON_MAP: Array<[string, string]> = [
  ['centos',       `${CDN}/centos/centos-plain.svg`],
  ['oraclelinux',  `${CDN}/oracle/oracle-original.svg`],
  ['oracle linux', `${CDN}/oracle/oracle-original.svg`],
  ['rockylinux',   `${CDN}/rockylinux/rockylinux-plain.svg`],
  ['rocky',        `${CDN}/rockylinux/rockylinux-plain.svg`],
  ['ubuntu',       `${CDN}/ubuntu/ubuntu-plain.svg`],
  ['debian',       `${CDN}/debian/debian-plain.svg`],
  ['fedora',       `${CDN}/fedora/fedora-plain.svg`],
  ['opensuse',     `${CDN}/opensuse/opensuse-plain.svg`],
  ['suse',         `${CDN}/opensuse/opensuse-plain.svg`],
  ['redhat',       `${CDN}/redhat/redhat-plain.svg`],
  ['rhel',         `${CDN}/redhat/redhat-plain.svg`],
  ['almalinux',    `${CDN}/almalinux/almalinux-plain.svg`],
  ['alma',         `${CDN}/almalinux/almalinux-plain.svg`],
  ['windows',      `${CDN}/windows11/windows11-original.svg`],
]

// keyword → custom tile
const CUSTOM_MAP: Array<[string, { label: string; bg: string; fontSize: number }]> = [
  ['aix',       { label: 'AIX', bg: '#1F70C1', fontSize: 8 }],
  ['kylin',     { label: 'KL',  bg: '#CC0000', fontSize: 10 }],
  ['uos',       { label: 'UOS', bg: '#0057A8', fontSize: 8 }],
  ['euleros',   { label: 'EUL', bg: '#CF3838', fontSize: 8 }],
  ['openeuler', { label: 'EUL', bg: '#CF3838', fontSize: 8 }],
  ['anolis',    { label: 'ANO', bg: '#E04A2F', fontSize: 8 }],
]

// Combine os_name + os_version into one searchable string
const searchStr = computed(() =>
  `${props.osName} ${props.osVersion}`.toLowerCase().replace(/[_\s]+/g, ' ').trim()
)

const iconUrl = computed(() => {
  for (const [kw, url] of DEVICON_MAP) {
    if (searchStr.value.includes(kw)) return url
  }
  return null
})

const customIcon = computed(() => {
  for (const [kw, icon] of CUSTOM_MAP) {
    if (searchStr.value.includes(kw)) return icon
  }
  return null
})

const label = computed(() => [props.osName, props.osVersion].filter(Boolean).join(' '))
const px = computed(() => ({ sm: 16, md: 20, lg: 24 }[props.size]))
</script>
