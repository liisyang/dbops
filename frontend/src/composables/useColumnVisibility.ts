import { computed, ref, watch } from 'vue'

export interface ColumnDef {
  key: string
  label: string
  defaultVisible?: boolean
}

interface ColState {
  order: string[]
  visible: string[]
}

export function useColumnVisibility(tableKey: string, columns: ColumnDef[]) {
  const storageKey = `col:${tableKey}`

  function loadState(): ColState {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<ColState>
        // Merge saved order with any new columns added since last save
        const savedOrder = parsed.order ?? []
        const allKeys = columns.map((c) => c.key)
        const merged = [
          ...savedOrder.filter((k) => allKeys.includes(k)),
          ...allKeys.filter((k) => !savedOrder.includes(k)),
        ]
        return {
          order: merged,
          visible: (parsed.visible ?? allKeys).filter((k) => allKeys.includes(k)),
        }
      }
    } catch {}
    return {
      order: columns.map((c) => c.key),
      visible: columns.filter((c) => c.defaultVisible !== false).map((c) => c.key),
    }
  }

  const state = loadState()
  const orderedKeys = ref<string[]>(state.order)
  const visibleSet = ref<Set<string>>(new Set(state.visible))

  watch(
    [orderedKeys, visibleSet],
    ([order, visible]) => {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ order: [...order], visible: [...visible] }),
      )
    },
    { deep: true },
  )

  // All columns in current order
  const orderedColumns = computed(() =>
    orderedKeys.value.map((k) => columns.find((c) => c.key === k)!).filter(Boolean),
  )

  // Only visible columns in current order
  const visibleColumns = computed(() =>
    orderedColumns.value.filter((c) => visibleSet.value.has(c.key)),
  )

  function isVisible(key: string) {
    return visibleSet.value.has(key)
  }

  function toggleColumn(key: string) {
    const next = new Set(visibleSet.value)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    visibleSet.value = next
  }

  function moveUp(key: string) {
    const arr = [...orderedKeys.value]
    const idx = arr.indexOf(key)
    if (idx <= 0) return
    ;[arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]]
    orderedKeys.value = arr
  }

  function moveDown(key: string) {
    const arr = [...orderedKeys.value]
    const idx = arr.indexOf(key)
    if (idx < 0 || idx >= arr.length - 1) return
    ;[arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]]
    orderedKeys.value = arr
  }

  function reorderColumn(fromKey: string, toKey: string) {
    if (fromKey === toKey) return
    const arr = [...orderedKeys.value]
    const fromIdx = arr.indexOf(fromKey)
    const toIdx = arr.indexOf(toKey)
    if (fromIdx < 0 || toIdx < 0) return
    arr.splice(fromIdx, 1)
    arr.splice(toIdx, 0, fromKey)
    orderedKeys.value = arr
  }

  function resetColumns() {
    orderedKeys.value = columns.map((c) => c.key)
    visibleSet.value = new Set(
      columns.filter((c) => c.defaultVisible !== false).map((c) => c.key),
    )
  }

  return {
    orderedColumns,
    visibleColumns,
    isVisible,
    toggleColumn,
    moveUp,
    moveDown,
    reorderColumn,
    resetColumns,
  }
}
