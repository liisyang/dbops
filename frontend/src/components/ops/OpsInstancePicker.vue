<template>
  <div class="field-card">
    <div class="flex items-center justify-between mb-2">
      <span class="field-label mb-0">
        资产 ID
        <span v-if="selectedIds.length" class="text-xs text-primary ml-1">(已选 {{ selectedIds.length }})</span>
        <span v-else class="text-xs text-on-surface-variant ml-1">(留空默认巡检全部)</span>
      </span>
      <button type="button" class="text-xs text-primary hover:underline" @click="toggleSelectAll">
        {{ allSelected ? '取消全选' : '全选' }}
      </button>
    </div>
    <input
      v-model="searchText"
      type="text"
      class="field-input mb-2 text-xs"
      placeholder="搜索实例名称或 IP..."
    />
    <select v-model="dbTypeFilter" class="field-input mb-2 text-xs" @change="onDbTypeChange">
      <option value="">全部类型</option>
      <option v-for="dt in dbTypes" :key="dt.type_code" :value="dt.type_code">
        {{ dt.name }} ({{ dt.type_code }})
      </option>
    </select>
    <!-- selected tags -->
    <div v-if="selectedIds.length" class="flex flex-wrap gap-1 mb-2">
      <span
        v-for="id in selectedIds"
        :key="id"
        class="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] text-on-surface"
      >
        {{ getInstanceLabel(id) }}
        <button type="button" class="text-on-surface-variant hover:text-red-300" @click="removeId(id)">&times;</button>
      </span>
    </div>
    <div class="max-h-[240px] overflow-y-auto space-y-1 rounded border border-outline-variant/40 p-2">
      <label
        v-for="i in filteredInstances"
        :key="i.id"
        class="flex items-center gap-2 rounded px-2 py-1.5 text-xs cursor-pointer hover:bg-surface-container-high transition-colors"
        :class="selectedIds.includes(i.id) ? 'bg-primary/10' : ''"
      >
        <input
          type="checkbox"
          :value="i.id"
          :checked="selectedIds.includes(i.id)"
          @change="toggleId(i.id)"
          class="rounded"
        />
        <span class="font-mono text-on-surface min-w-[72px]">{{ i.instance_name }}</span>
        <span class="text-on-surface-variant min-w-[100px]">{{ i.server_ip }}:{{ i.port }}</span>
        <span class="text-on-surface-variant/60 text-[10px] min-w-[48px]">{{ i.cluster_type || '-' }}</span>
        <span class="text-on-surface-variant/60 text-[10px] min-w-[40px]">{{ i.node_role }}</span>
        <span class="text-on-surface-variant/60 text-[10px] truncate">{{ i.db_version || '-' }}</span>
      </label>
      <p v-if="!filteredInstances.length" class="text-xs text-on-surface-variant px-2 py-2">
        {{ instances.length ? '无匹配实例' : '加载中...' }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { assetsApi } from '@/api/assets'
import type { InstanceRow } from '@/types/api'

const props = defineProps<{
  modelValue: number[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number[]]
}>()

const instances = ref<InstanceRow[]>([])
const dbTypes = ref<{ type_code: string; name: string }[]>([])
const searchText = ref('')
const dbTypeFilter = ref('')

const selectedIds = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const filteredInstances = computed(() => {
  let list = instances.value
  if (dbTypeFilter.value) {
    list = list.filter((i) => (i.db_type_code || '').toUpperCase() === dbTypeFilter.value.toUpperCase())
  }
  const kw = searchText.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((i) =>
      (i.instance_name || '').toLowerCase().includes(kw)
      || (i.server_ip || '').toLowerCase().includes(kw)
      || (i.instance_code || '').toLowerCase().includes(kw)
    )
  }
  return list
})

const allSelected = computed(() =>
  filteredInstances.value.length > 0 && filteredInstances.value.every((i) => selectedIds.value.includes(i.id))
)

function toggleId(id: number) {
  const arr = [...selectedIds.value]
  const idx = arr.indexOf(id)
  if (idx >= 0) {
    arr.splice(idx, 1)
  } else {
    arr.push(id)
  }
  selectedIds.value = arr
}

function removeId(id: number) {
  selectedIds.value = selectedIds.value.filter((v) => v !== id)
}

function toggleSelectAll() {
  if (allSelected.value) {
    const visibleIds = new Set(filteredInstances.value.map((i) => i.id))
    selectedIds.value = selectedIds.value.filter((id) => !visibleIds.has(id))
  } else {
    const existing = new Set(selectedIds.value)
    for (const i of filteredInstances.value) {
      existing.add(i.id)
    }
    selectedIds.value = Array.from(existing)
  }
}

function onDbTypeChange() {
  searchText.value = ''
}

function getInstanceLabel(id: number): string {
  const inst = instances.value.find((i) => i.id === id)
  return inst ? `${inst.instance_name} (${inst.server_ip}:${inst.port})` : `#${id}`
}

async function loadDbTypes() {
  try {
    dbTypes.value = await assetsApi.listDbTypes()
  } catch {
    dbTypes.value = []
  }
}

async function loadInstances() {
  try {
    const res = await assetsApi.listInstances({ page_size: 500 })
    instances.value = res.items || []
  } catch {
    instances.value = []
  }
}

onMounted(() => {
  loadInstances()
  loadDbTypes()
})
</script>
