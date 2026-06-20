<!--
  ProposalPanel — 独立变更建议组件
  资产校验功能优化 v2 / 2026-06-17
  - 显示 IP / 实体类型 / 实体名称
  - 支持单条 + 批量操作
  - PORT_CANDIDATE_CONFLICT 必须人工选择 selected_value
-->
<template>
  <OpsSectionCard
    title="变更建议 (Proposals)"
    :description="`batch ${batchRunId || '-'} 共 ${proposals.length} 条建议`"
  >
    <template #actions>
      <div class="flex items-center gap-2">
        <button
          class="ops-secondary-button"
          :disabled="selectedIds.length === 0 || bulkLoading"
          @click="handleBulkAction('approve')"
        >
          批量同意
        </button>
        <button
          class="ops-secondary-button"
          :disabled="selectedIds.length === 0 || bulkLoading"
          @click="handleBulkAction('reject')"
        >
          批量拒绝
        </button>
        <button
          class="ops-primary-button"
          :disabled="selectedIds.length === 0 || bulkLoading"
          @click="handleBulkAction('apply')"
        >
          批量应用
        </button>
      </div>
    </template>

    <OpsEmptyState
      v-if="loading"
      state="loading"
      title="正在加载变更建议"
    />
    <OpsEmptyState
      v-else-if="error"
      state="error"
      title="变更建议加载失败"
      :description="error"
    />
    <OpsEmptyState
      v-else-if="proposals.length === 0"
      state="empty"
      title="暂无变更建议"
      description="该 batch 暂无 proposal。"
    />
    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-outline-variant text-sm">
        <thead class="bg-surface-container text-on-surface-variant">
          <tr>
            <th class="px-3 py-2 w-8">
              <input
                type="checkbox"
                :checked="allSelected"
                @change="toggleAll"
              />
            </th>
            <th class="px-3 py-2 text-left">实体</th>
            <th class="px-3 py-2 text-left">类型</th>
            <th class="px-3 py-2 text-left">字段</th>
            <th class="px-3 py-2 text-left">现值</th>
            <th class="px-3 py-2 text-left">建议值</th>
            <th class="px-3 py-2 text-left">状态</th>
            <th class="px-3 py-2 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-variant">
          <tr v-for="p in proposals" :key="p.id">
            <td class="px-3 py-2">
              <input
                type="checkbox"
                :checked="selectedIds.includes(p.id)"
                @change="toggleOne(p.id)"
              />
            </td>
            <td class="px-3 py-2 font-mono text-xs">
              {{ p.target_type }}#{{ p.target_id }}<br />
              <span class="text-on-surface-variant">{{ entityLabel(p) }}</span>
            </td>
            <td class="px-3 py-2 font-mono text-xs">{{ p.proposal_type }}</td>
            <td class="px-3 py-2 font-mono text-xs">{{ p.field_path || '-' }}</td>
            <td class="px-3 py-2 font-mono text-xs">{{ formatValue(p.current_value) }}</td>
            <td class="px-3 py-2 font-mono text-xs">
              <template v-if="p.proposal_type === 'PORT_CANDIDATE_CONFLICT' && selectedForConflict[p.id] != null">
                {{ selectedForConflict[p.id] }}
              </template>
              <template v-else>{{ formatValue(p.suggested_value) }}</template>
              <button
                v-if="p.proposal_type === 'PORT_CANDIDATE_CONFLICT' && p.status === 'approved'"
                class="ml-2 ops-secondary-button text-xs"
                @click="openConflictPicker(p)"
              >
                选择端口
              </button>
            </td>
            <td class="px-3 py-2">
              <span :class="statusBadge(p.status)">{{ statusLabel(p.status) }}</span>
            </td>
            <td class="px-3 py-2 text-right">
              <button
                v-if="p.status === 'pending'"
                class="ops-secondary-button text-xs"
                @click="handleSingleAction(p.id, 'approve')"
              >
                同意
              </button>
              <button
                v-if="p.status === 'pending' || p.status === 'approved'"
                class="ops-secondary-button text-xs ml-1"
                @click="handleSingleAction(p.id, 'reject')"
              >
                拒绝
              </button>
              <button
                v-if="p.status === 'approved'"
                class="ops-primary-button text-xs ml-1"
                @click="handleSingleApply(p)"
              >
                应用
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <OpsModal
      :open="conflictPickerVisible"
      title="选择候选端口 (PORT_CANDIDATE_CONFLICT)"
      size="sm"
      @close="conflictPickerVisible = false"
    >
      <p class="text-sm mb-3">建议值包含多个候选端口，必须由人工选择单个端口。</p>
      <div class="space-y-2">
        <label
          v-for="cand in conflictCandidates"
          :key="cand"
          class="flex items-center gap-2"
        >
          <input
            type="radio"
            :value="cand"
            v-model="conflictSelected"
          />
          <span class="font-mono text-sm">{{ cand }}</span>
        </label>
      </div>
      <template #footer>
        <button
          class="ops-primary-button"
          :disabled="conflictSelected == null"
          @click="confirmConflictPick"
        >
          确认
        </button>
        <button class="ops-secondary-button ml-2" @click="conflictPickerVisible = false">
          取消
        </button>
      </template>
    </OpsModal>
  </OpsSectionCard>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import OpsSectionCard from './OpsSectionCard.vue'
import OpsEmptyState from './OpsEmptyState.vue'
import OpsModal from './OpsModal.vue'
import { assetsApi } from '@/api/assets'
import type { AssetChangeProposalRow, ProposalStatus, ProposalType } from '@/types/api'
import { proposalStatusBadge, proposalStatusLabel } from '@/constants/proposalStatus'

// L7 (PR review 2026-06-18): use shared types from @/types/api instead
// of redeclaring with plain `string`. Aligned with AssetChangeProposalRow.
// I13 (PR review 2026-06-20): 用 shared AssetChangeProposalRow 替代 local Proposal，
// 字段类型与 backend _to_dict 保持一致。
type Proposal = AssetChangeProposalRow

const props = defineProps<{ batchRunId: number | null }>()

const proposals = ref<Proposal[]>([])
const loading = ref(false)
const error = ref('')
const selectedIds = ref<number[]>([])
const bulkLoading = ref(false)
const selectedForConflict = ref<Record<number, number>>({})

// PORT_CANDIDATE_CONFLICT picker state
const conflictPickerVisible = ref(false)
const conflictProposalId = ref<number | null>(null)
const conflictCandidates = ref<number[]>([])
const conflictSelected = ref<number | null>(null)

const allSelected = computed(() => {
  return proposals.value.length > 0 && selectedIds.value.length === proposals.value.length
})

const load = async () => {
  if (!props.batchRunId) {
    proposals.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    // I4 (PR review 2026-06-18): 按 batch 隔离 proposals，避免跨批 apply。
    proposals.value = await assetsApi.listCollectorProposals(
      { batch_run_id: props.batchRunId, status: undefined },
      { suppressErrorToast: true },
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    proposals.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.batchRunId, () => {
  selectedIds.value = []
  void load()
})

onMounted(() => {
  void load()
})

const toggleOne = (id: number) => {
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter(x => x !== id)
  } else {
    selectedIds.value = [...selectedIds.value, id]
  }
}

const toggleAll = () => {
  if (allSelected.value) {
    selectedIds.value = []
  } else {
    selectedIds.value = proposals.value.map(p => p.id)
  }
}

const entityLabel = (p: Proposal): string => {
  const ev = p.evidence || {}
  const name = (ev.entity_name || ev.ip_address) as string | undefined
  return name || '-'
}

const formatValue = (v: unknown): string => {
  if (v == null) return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

const statusLabel = (s: string): string => proposalStatusLabel(s)
const statusBadge = (s: string): string => proposalStatusBadge(s)

const handleSingleAction = async (id: number, action: 'approve' | 'reject') => {
  try {
    if (action === 'approve') {
      await assetsApi.approveCollectorProposal(id)
    } else {
      await assetsApi.rejectCollectorProposal(id, { reason: '' })
    }
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

const openConflictPicker = (p: Proposal) => {
  const cands = ((p.suggested_value as Record<string, unknown>) || {}).candidates
  if (!Array.isArray(cands)) return
  conflictProposalId.value = p.id
  // H2 (PR review 2026-06-18): coerce candidates with Number() so both
  // integer and string-typed port values from JSON work. Filter !isNaN to
  // avoid silent empty picker.
  conflictCandidates.value = cands
    .map((c) => (typeof c === 'number' ? c : Number(c)))
    .filter((c): c is number => typeof c === 'number' && !isNaN(c))
  conflictSelected.value = selectedForConflict.value[p.id] ?? null
  conflictPickerVisible.value = true
}

const confirmConflictPick = () => {
  if (conflictProposalId.value == null || conflictSelected.value == null) return
  selectedForConflict.value = {
    ...selectedForConflict.value,
    [conflictProposalId.value]: conflictSelected.value,
  }
  conflictPickerVisible.value = false
}

const handleSingleApply = async (p: Proposal) => {
  try {
    if (p.proposal_type === 'PORT_CANDIDATE_CONFLICT') {
      const sel = selectedForConflict.value[p.id]
      if (sel == null) {
        openConflictPicker(p)
        return
      }
      await assetsApi.applyProposalWithValue(p.id, { selected_value: sel })
    } else {
      await assetsApi.applyCollectorProposal(p.id)
    }
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

const handleBulkAction = async (action: 'approve' | 'reject' | 'apply') => {
  if (selectedIds.value.length === 0) return

  // 校验 PORT_CANDIDATE_CONFLICT 是否都选了端口
  const conflictProposals = proposals.value.filter(
    p => selectedIds.value.includes(p.id) && p.proposal_type === 'PORT_CANDIDATE_CONFLICT'
  )
  if (action === 'apply') {
    for (const p of conflictProposals) {
      if (selectedForConflict.value[p.id] == null) {
        error.value = `请先为 proposal #${p.id} (PORT_CANDIDATE_CONFLICT) 选择端口`
        return
      }
    }
  }

  const override_values: Record<string, number> = {}
  for (const p of conflictProposals) {
    const sel = selectedForConflict.value[p.id]
    if (sel != null) {
      override_values[String(p.id)] = sel
    }
  }

  bulkLoading.value = true
  try {
    const result = await assetsApi.batchActionProposals({
      proposal_ids: selectedIds.value,
      action,
      override_values: action === 'apply' ? override_values : undefined,
    })
    if (result.fail_count > 0) {
      const failed = result.results.filter(r => !r.success)
      error.value = `部分失败: ${failed.map(f => `#${f.id}: ${f.error}`).join('; ')}`
    }
    selectedIds.value = []
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    bulkLoading.value = false
  }
}
</script>
