import { computed, toValue, type MaybeRefOrGetter } from 'vue'

export interface AssetStatBucket {
  label: string
  value: number
}

type LabelGetter<T> = (item: T) => string | null | undefined

export function useAssetStatBuckets<T>(
  items: MaybeRefOrGetter<T[]>,
  getLabel: LabelGetter<T>,
  options?: {
    emptyLabel?: string
  }
) {
  const emptyLabel = options?.emptyLabel ?? '未标记'

  return computed<AssetStatBucket[]>(() => {
    const counts = new Map<string, number>()

    for (const item of toValue(items)) {
      const label = getLabel(item)?.trim() || emptyLabel
      counts.set(label, (counts.get(label) || 0) + 1)
    }

    return Array.from(counts.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value)
  })
}
