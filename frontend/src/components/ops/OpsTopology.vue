<template>
  <div class="space-y-6">
    <div
      v-if="nodes.length"
      class="relative overflow-hidden rounded-xl border border-outline-variant/60 bg-[#0d1e26] p-4"
      style="min-height: 28rem;"
    >
      <svg class="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
        <line
          v-for="edge in resolvedEdges"
          :key="edge.id"
          :x1="`${edge.from.x}%`"
          :y1="`${edge.from.y}%`"
          :x2="`${edge.to.x}%`"
          :y2="`${edge.to.y}%`"
          stroke="#2b4555"
          stroke-width="2"
          stroke-linecap="round"
        />
      </svg>

      <button
        v-for="node in nodes"
        :key="node.id"
        type="button"
        class="absolute w-40 -translate-x-1/2 -translate-y-1/2 rounded-xl border px-4 py-3 text-left shadow-lg transition-all"
        :class="selectedNode?.id === node.id
          ? 'border-[#91caff] bg-[#1a3040] shadow-[#91caff]/20'
          : 'border-[#2b4555] bg-[#122430] hover:border-[#3d6070]'"
        :style="{ left: `${node.x}%`, top: `${node.y}%` }"
        @click="selectNode(node)"
      >
        <div class="text-[11px] uppercase tracking-[0.18em] text-[#7fa9dd]">{{ node.kind }}</div>
        <div class="mt-2 break-words text-sm font-semibold text-white">{{ node.label }}</div>
        <div v-if="node.subtitle" class="mt-1 break-words text-xs text-[#b8c7e0]">{{ node.subtitle }}</div>
      </button>
    </div>

    <OpsEmptyState
      v-else
      title="暂无可展示的架构节点"
      description="当前集群没有可用于生成拓扑的 VIP 或实例数据。"
    />

    <div v-if="selectedNode" class="rounded-xl border border-outline-variant/60 bg-background p-4">
      <div class="text-xs uppercase tracking-wide text-on-surface-variant">{{ selectedNode.kind }}</div>
      <div class="mt-2 text-base font-semibold text-on-surface">{{ selectedNode.label }}</div>
      <div v-if="selectedNode.subtitle" class="mt-1 text-sm text-on-surface-variant">{{ selectedNode.subtitle }}</div>

      <dl class="mt-4 grid gap-3 sm:grid-cols-2">
        <div
          v-for="item in selectedNode.meta"
          :key="`${selectedNode.id}-${item.label}`"
          class="rounded-lg border border-outline-variant/60 bg-surface px-3 py-2"
        >
          <dt class="text-xs uppercase tracking-wide text-on-surface-variant">{{ item.label }}</dt>
          <dd class="mt-1 break-words text-sm text-on-surface">{{ item.value }}</dd>
        </div>
      </dl>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import OpsEmptyState from './OpsEmptyState.vue'

type TopologyMetaItem = {
  label: string
  value: string
}

type TopologyNode = {
  id: string
  kind: string
  label: string
  subtitle?: string
  x: number
  y: number
  meta: TopologyMetaItem[]
}

type TopologyEdge = {
  id: string
  from: string
  to: string
}

const props = defineProps<{
  nodes: TopologyNode[]
  edges: TopologyEdge[]
}>()

const selectedNode = ref<TopologyNode | null>(props.nodes[0] ?? null)

const nodeMap = computed(() => {
  return new Map(props.nodes.map((node) => [node.id, node]))
})

const resolvedEdges = computed(() => {
  return props.edges
    .map((edge) => {
      const from = nodeMap.value.get(edge.from)
      const to = nodeMap.value.get(edge.to)
      if (!from || !to) return null
      return { ...edge, from, to }
    })
    .filter((edge): edge is TopologyEdge & { from: TopologyNode; to: TopologyNode } => Boolean(edge))
})

watch(
  () => props.nodes,
  (nodes) => {
    if (!nodes.length) {
      selectedNode.value = null
      return
    }
    if (!selectedNode.value || !nodes.some((node) => node.id === selectedNode.value?.id)) {
      selectedNode.value = nodes[0]
    }
  },
  { deep: true }
)

function selectNode(node: TopologyNode) {
  selectedNode.value = node
}
</script>
