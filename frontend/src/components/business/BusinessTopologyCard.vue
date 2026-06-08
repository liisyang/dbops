<template>
  <OpsSectionCard title="拓扑关系" subtitle="业务系统、关联集群和层次拓扑结构。" icon="hub">
    <template #actions>
      <span class="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs text-primary">
        <span class="material-symbols-outlined text-[12px] leading-none">autorenew</span>
        自动更新
      </span>
    </template>

    <div v-if="!clusters.length" class="py-6">
      <OpsEmptyState state="empty" title="暂无关联集群" description="当前业务系统没有返回集群关系。" />
    </div>

    <div v-else class="space-y-4">
      <div class="relative overflow-hidden rounded-xl border border-outline-variant/50 bg-[#0a1820] p-4" style="min-height: 340px;">
        <div class="absolute inset-0 bg-[linear-gradient(to_right,rgba(125,211,252,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(125,211,252,0.05)_1px,transparent_1px)] bg-[size:24px_24px]" />
        <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(34,211,238,0.06),transparent_60%)]" />

        <div class="absolute left-1/2 z-20 -translate-x-1/2" :style="{ top: `${appTopPx}px` }">
          <div class="relative">
            <div class="absolute -inset-1.5 rounded-2xl bg-gradient-to-r from-primary/60 to-cyan-400/60 opacity-70 blur-md" />
            <div class="relative flex flex-col items-center justify-center rounded-xl border border-primary/40 bg-[#0d1e26] px-5 py-3 shadow-xl">
              <span class="absolute right-2 top-2 size-1.5 animate-pulse rounded-full bg-emerald-400" />
              <span class="text-[10px] font-bold uppercase tracking-[0.2em] text-primary">BUSINESS APP</span>
              <span class="mt-1 max-w-[14rem] truncate text-sm font-semibold text-on-surface" :title="systemName || ''">
                {{ systemName || '业务系统' }}
              </span>
              <div class="mt-1 flex items-center gap-1 text-[10px] text-on-surface-variant">
                <span class="material-symbols-outlined text-[12px] leading-none text-emerald-400">verified</span>
                <span>高可用运行中</span>
              </div>
            </div>
          </div>
        </div>

        <svg class="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden="true">
          <defs>
            <filter id="topo-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2.6" />
            </filter>
          </defs>

          <!-- vertical app→bus -->
          <line x1="50%" :y1="laneY.appBottom" x2="50%" :y2="laneY.bus" stroke="#22d3ee" stroke-width="7" stroke-opacity="0.28" stroke-linecap="round" filter="url(#topo-glow)" />
          <line x1="50%" :y1="laneY.appBottom" x2="50%" :y2="laneY.bus" stroke="#a5f3fc" stroke-width="2.2" stroke-opacity="0.98" stroke-linecap="round" />

          <!-- bus horizontal -->
          <template v-if="topologyClusters.length > 1">
            <line :x1="`${busStart}%`" :y1="laneY.bus" :x2="`${busEnd}%`" :y2="laneY.bus" stroke="#22d3ee" stroke-width="7" stroke-opacity="0.28" stroke-linecap="round" filter="url(#topo-glow)" />
            <line :x1="`${busStart}%`" :y1="laneY.bus" :x2="`${busEnd}%`" :y2="laneY.bus" stroke="#a5f3fc" stroke-width="2.2" stroke-linecap="round" stroke-opacity="0.98" />
          </template>

          <!-- bus→cluster drops -->
          <g v-for="(x, idx) in clusterPositions" :key="`drop-${idx}`">
            <line :x1="`${x}%`" :y1="laneY.bus" :x2="`${x}%`" :y2="clusterLinkEndY" stroke="#22d3ee" stroke-width="7" stroke-opacity="0.28" stroke-linecap="round" filter="url(#topo-glow)" />
            <line :x1="`${x}%`" :y1="laneY.bus" :x2="`${x}%`" :y2="clusterLinkEndY" stroke="#a5f3fc" stroke-width="2.2" stroke-opacity="0.98" stroke-linecap="round" />
          </g>
        </svg>

        <div class="absolute inset-x-0 z-20" :style="{ top: `${laneY.clusterTop}px` }">
          <div
            v-for="(cluster, idx) in topologyClusters"
            :key="cluster.id"
            class="absolute -translate-x-1/2"
            :style="{ left: `${clusterPositions[idx]}%`, width: `${nodeWidth}px` }"
          >
            <div class="rounded-lg border border-outline-variant/60 bg-[#0d1e26]/90 px-3 py-2 shadow-md backdrop-blur-sm">
              <div class="flex items-center gap-2">
                <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-primary">
                  <span class="material-symbols-outlined text-[14px] leading-none">database</span>
                </span>
                <div class="min-w-0">
                  <p class="truncate text-[11px] font-semibold text-on-surface" :title="cluster.cluster_code">
                    {{ cluster.cluster_code }}
                  </p>
                  <p class="truncate text-[10px] text-on-surface-variant" :title="cluster.cluster_type">
                    {{ formatClusterType(cluster.cluster_type) }}
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div
            v-if="hiddenClusterCount > 0"
            class="absolute right-3 -bottom-2 rounded-lg border border-dashed border-primary/40 bg-primary/5 px-3 py-1.5 text-[11px] font-medium text-primary"
          >
            + {{ hiddenClusterCount }} 个集群折叠显示
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-outline-variant/40 bg-surface-container-low p-3">
        <div class="mb-2 flex items-center justify-between">
          <p class="text-xs font-medium text-on-surface">集群节点清单</p>
          <span class="text-[11px] text-on-surface-variant">
            共 {{ clusters.length }} 个{{ clusters.length > 4 ? ' · 超过 4 个滚动显示' : '' }}
          </span>
        </div>
        <div
          class="space-y-1.5"
          :class="clusters.length > 4 ? 'max-h-40 overflow-auto pr-1' : ''"
        >
          <div
            v-for="cluster in clusters"
            :key="cluster.id"
            class="flex items-center justify-between rounded-md border border-outline-variant/40 bg-surface-container px-3 py-2"
          >
            <div class="min-w-0">
              <p class="truncate text-xs font-medium text-on-surface" :title="cluster.cluster_code">
                {{ cluster.cluster_code }}
              </p>
              <p class="truncate text-[11px] text-on-surface-variant">
                {{ cluster.cluster_name || '-' }}
              </p>
            </div>
            <span class="shrink-0 rounded-full border border-primary/20 bg-primary/5 px-2 py-0.5 text-[10px] font-medium text-primary">
              {{ cluster.cluster_type }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { OpsEmptyState, OpsSectionCard } from '@/components/ops'
import type { ClusterRef } from '@/types/api'

const props = defineProps<{
  systemName?: string | null
  clusters: ClusterRef[]
}>()

const MAX_VISIBLE = 6
const appTopPx = 36
const laneY = {
  appBottom: 130,
  bus: 180,
  clusterTop: 220,
}
const clusterLinkEndY = laneY.clusterTop - 4

const topologyClusters = computed(() => props.clusters.slice(0, MAX_VISIBLE))
const hiddenClusterCount = computed(() => Math.max(props.clusters.length - topologyClusters.value.length, 0))

const clusterPositions = computed(() => getSymmetricPositions(topologyClusters.value.length))

const nodeWidth = computed(() => {
  const count = topologyClusters.value.length
  if (count >= 5) return 132
  if (count === 4) return 148
  return 168
})

const busStart = computed(() => (clusterPositions.value.length > 1 ? clusterPositions.value[0] : 42))
const busEnd = computed(() =>
  clusterPositions.value.length > 1 ? clusterPositions.value[clusterPositions.value.length - 1] : 58
)

function getSymmetricPositions(count: number): number[] {
  if (count <= 0) return []
  if (count === 1) return [50]
  const spanByCount: Record<number, number> = { 2: 44, 3: 62, 4: 76, 5: 84, 6: 90 }
  const span = spanByCount[count] || 90
  const start = 50 - span / 2
  const step = span / (count - 1)
  return Array.from({ length: count }, (_, idx) => start + idx * step)
}

function formatClusterType(type: string) {
  const map: Record<string, string> = {
    SINGLE: '单实例 (Standalone)',
    AG: '双机热备 (Active-Standby)',
    CLUSTER: '集群模式 (Cluster)',
    RAC: 'Oracle RAC',
    MGR: 'MySQL MGR',
  }
  return map[type] || type
}
</script>
