<template>
  <div class="space-y-4 text-xs">
    <!-- Evidence metadata strip -->
    <div class="flex flex-wrap items-center gap-2 text-on-surface-variant">
      <span class="rounded bg-surface-container px-2 py-0.5 font-mono">
        attempt_no={{ evidence.attempt_no ?? result.attempt_no ?? 0 }}
      </span>
      <span v-if="evidence.connector" class="rounded bg-surface-container px-2 py-0.5 font-mono">
        connector={{ evidence.connector }}
      </span>
      <span v-if="evidence.sql_hash" class="rounded bg-surface-container px-2 py-0.5 font-mono">
        sql_hash={{ truncate(evidence.sql_hash, 12) }}
      </span>
      <span v-if="evidence.duration_ms != null" class="rounded bg-surface-container px-2 py-0.5 font-mono">
        duration={{ evidence.duration_ms }}ms
      </span>
      <span v-if="evidence.error_code" class="rounded bg-red-400/10 px-2 py-0.5 font-mono text-red-300">
        error_code={{ evidence.error_code }}
      </span>
      <span
        v-if="evidence.truncated"
        class="rounded bg-amber-400/10 px-2 py-0.5 font-mono text-amber-300"
      >
        truncated=true
      </span>
      <span
        v-if="evidence.stored_row_count != null && evidence.original_row_count != null && evidence.stored_row_count !== evidence.original_row_count"
        class="rounded bg-amber-400/10 px-2 py-0.5 font-mono text-amber-300"
      >
        rows={{ evidence.stored_row_count }}/{{ evidence.original_row_count }}
      </span>
    </div>

    <!-- SQL text -->
    <div v-if="evidence.sql_text" class="rounded border border-outline-variant/30 bg-surface-container/40 p-3">
      <div class="mb-1 text-[11px] font-semibold uppercase text-on-surface-variant">SQL</div>
      <pre class="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-on-surface">{{ evidence.sql_text }}</pre>
    </div>

    <!-- Findings (highest-signal) -->
    <div v-if="Array.isArray(evidence.findings) && evidence.findings.length" class="rounded border border-outline-variant/30 bg-surface-container/40 p-3">
      <div class="mb-2 text-[11px] font-semibold uppercase text-on-surface-variant">
        Findings ({{ evidence.findings.length }})
      </div>
      <ul class="space-y-1">
        <li
          v-for="(f, idx) in evidence.findings"
          :key="idx"
          class="flex items-start gap-2"
        >
          <span
            class="inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
            :class="getFindingClass(f.evaluation_status)"
          >
            {{ f.evaluation_status || 'unknown' }}
          </span>
          <span class="text-on-surface">
            <span v-if="f.row_index != null" class="font-mono text-on-surface-variant">#{{ f.row_index }}</span>
            {{ f.message || '(无 message)' }}
          </span>
        </li>
      </ul>
    </div>

    <!-- Rows (raw data) -->
    <div
      v-if="Array.isArray(evidence.columns) && evidence.columns.length && Array.isArray(evidence.rows) && evidence.rows.length"
      class="rounded border border-outline-variant/30 bg-surface-container/40 p-3"
    >
      <div class="mb-2 text-[11px] font-semibold uppercase text-on-surface-variant">
        Rows ({{ evidence.rows.length }} / {{ evidence.columns.length }} cols)
      </div>
      <div class="max-h-80 overflow-auto">
        <table class="w-full text-[11px]">
          <thead class="sticky top-0 bg-surface-container text-on-surface-variant">
            <tr>
              <th class="px-2 py-1 text-left font-mono">#</th>
              <th
                v-for="(c, ci) in evidence.columns"
                :key="ci"
                class="whitespace-nowrap px-2 py-1 text-left font-mono"
              >
                {{ c }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, ri) in evidence.rows"
              :key="ri"
              class="border-t border-outline-variant/20"
            >
              <td class="px-2 py-1 font-mono text-on-surface-variant">{{ ri }}</td>
              <td
                v-for="(cell, ci) in row"
                :key="ci"
                class="whitespace-nowrap px-2 py-1 font-mono"
              >
                {{ formatCell(cell) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- stderr -->
    <div v-if="evidence.stderr" class="rounded border border-outline-variant/30 bg-red-400/5 p-3">
      <div class="mb-1 text-[11px] font-semibold uppercase text-red-300">stderr</div>
      <pre class="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-red-200">{{ evidence.stderr }}</pre>
    </div>

    <!-- Empty evidence -->
    <div
      v-if="!hasAnyContent"
      class="rounded border border-outline-variant/30 bg-surface-container/40 p-3 text-on-surface-variant"
    >
      无 evidence 数据。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { InspectionResultRow } from '@/types/api'

const props = defineProps<{ result: InspectionResultRow }>()

const evidence = computed(() => props.result.evidence || {})

const hasAnyContent = computed(() => {
  const e = evidence.value
  if (!e || typeof e !== 'object') return false
  if (e.sql_text) return true
  if (e.stderr) return true
  if (Array.isArray(e.findings) && e.findings.length) return true
  if (Array.isArray(e.rows) && e.rows.length) return true
  if (Array.isArray(e.columns) && e.columns.length) return true
  return false
})

function getFindingClass(evalStatus: string | undefined): string {
  const s = (evalStatus || '').toLowerCase()
  if (s === 'critical') return 'border-red-400/30 bg-red-400/10 text-red-200'
  if (s === 'warning') return 'border-amber-400/30 bg-amber-400/10 text-amber-200'
  if (s === 'normal') return 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200'
  return 'border-outline-variant/40 bg-surface-container-high text-on-surface-variant'
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n)}…` : s
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return 'NULL'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
</script>
