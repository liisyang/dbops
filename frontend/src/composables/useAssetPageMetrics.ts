import { computed, toValue, type MaybeRefOrGetter } from 'vue'

export interface AssetPageMetricItem {
  label: string
  value: number | string
  hint?: string
}

export interface AssetPageMetricContext<T> {
  items: T[]
  total: number
}

export interface AssetPageMetricDefinition<T> {
  label: string
  resolve: (context: AssetPageMetricContext<T>) => number | string
  hint?: string | ((context: AssetPageMetricContext<T>) => string | undefined)
}

export const assetPageMetric = {
  total<T>(label: string, hint?: string): AssetPageMetricDefinition<T> {
    return {
      label,
      hint,
      resolve: (context) => context.total,
    }
  },

  countEquals<T, TValue>(
    label: string,
    selector: (item: T) => TValue,
    expected: TValue,
    hint?: string,
  ): AssetPageMetricDefinition<T> {
    return {
      label,
      hint,
      resolve: (context) => context.items.filter((item) => selector(item) === expected).length,
    }
  },

  countNotEquals<T, TValue>(
    label: string,
    selector: (item: T) => TValue,
    expected: TValue,
    hint?: string,
  ): AssetPageMetricDefinition<T> {
    return {
      label,
      hint,
      resolve: (context) => context.items.filter((item) => selector(item) !== expected).length,
    }
  },

  countMatches<T>(
    label: string,
    predicate: (item: T) => boolean,
    hint?: string,
  ): AssetPageMetricDefinition<T> {
    return {
      label,
      hint,
      resolve: (context) => context.items.filter(predicate).length,
    }
  },
}

export function useAssetPageMetrics<T>(items: MaybeRefOrGetter<T[]>, total: MaybeRefOrGetter<number>, definitions: AssetPageMetricDefinition<T>[]) {
  return computed<AssetPageMetricItem[]>(() => {
    const context = {
      items: toValue(items),
      total: toValue(total),
    }

    return definitions.map((definition) => ({
      label: definition.label,
      value: definition.resolve(context),
      hint: typeof definition.hint === 'function' ? definition.hint(context) : definition.hint,
    }))
  })
}
