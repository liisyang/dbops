/*
 * useBatchVerifyOptions — 列表页 + 详情页共用的 options composable
 *
 * 加载 dbTypes + checkCodes，按 target_scope 派生 dbInstanceCheckCodes / serverCheckCodes。
 */

import { computed, ref, type ComputedRef } from 'vue'
import { assetsApi } from '@/api/assets'
import type { CollectorCheckDefinitionRow, DbTypeRow } from '@/types/api'

export interface DbTypeOption {
  code: string
  name: string
}

export function useBatchVerifyOptions() {
  const checkCodes = ref<CollectorCheckDefinitionRow[]>([])
  const dbTypesRaw = ref<DbTypeRow[]>([])
  const loading = ref(false)

  const dbTypes: ComputedRef<DbTypeOption[]> = computed(() => {
    return dbTypesRaw.value.map((dt) => ({
      code: (dt as unknown as { type_code?: string; code?: string }).type_code
        ?? (dt as unknown as { code?: string }).code
        ?? String(dt.id),
      name: dt.name,
    }))
  })

  const dbInstanceCheckCodes: ComputedRef<CollectorCheckDefinitionRow[]> = computed(() =>
    checkCodes.value.filter((c) => c.target_scope === 'db_instance'),
  )

  const serverCheckCodes: ComputedRef<CollectorCheckDefinitionRow[]> = computed(() =>
    checkCodes.value.filter((c) => c.target_scope === 'server'),
  )

  async function loadOptions() {
    loading.value = true
    try {
      const [dbTypesResult, checkCodesResult] = await Promise.allSettled([
        assetsApi.listDbTypes(),
        assetsApi.listCheckCodes({ is_enabled: true }, { suppressErrorToast: true }),
      ])
      if (dbTypesResult.status === 'fulfilled') {
        dbTypesRaw.value = dbTypesResult.value
      } else {
        console.warn('useBatchVerifyOptions.loadOptions: listDbTypes failed', dbTypesResult.reason)
      }
      if (checkCodesResult.status === 'fulfilled') {
        checkCodes.value = checkCodesResult.value
      } else {
        console.warn('useBatchVerifyOptions.loadOptions: listCheckCodes failed', checkCodesResult.reason)
      }
    } finally {
      loading.value = false
    }
  }

  return {
    checkCodes,
    dbTypes,
    dbInstanceCheckCodes,
    serverCheckCodes,
    loading,
    loadOptions,
  }
}