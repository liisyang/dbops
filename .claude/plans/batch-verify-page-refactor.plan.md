# Plan: 批量校验页面拆分重构（BatchVerify 列表 + 详情双页化）

**Source PRD / Input**: `.claude/plans/batch-verify-page-refactor-input-2026-06-18.md`
**Selected Milestone**: Phase 1 — 路由拆分 + 组件化 + composables 抽离
**Complexity**: **Medium-Large**（拆路由 + 6 个子组件 + 4 个 composables + 1 个 utils，全文 ~1500 行迁移）

## Round 2 Review Fixes（实施前必须先消化的修订）

按"另一轮评审"的 10 项必改 + 6 项补充 + 6 项产品决策，本 plan 已修订如下。**所有改动已落到下面正文，旧摘要保留只作来源**。

| 修订 # | 来源 | 处理 |
|---|---|---|
| 1 | `useBatchDetail/useBatchItems` 接收 `number`，组件复用时拿旧 id | **改为接收 `Ref<number \| null>`**，每次请求时 `unref()` 取最新 |
| 2 | `useBatchPolling` 字段名 `batchRunId` vs 调用方 `batchRunIdRef` 不一致 | **统一为 `batchRunIdRef`**，且 `onTick` 接 `AbortSignal` |
| 3 | 详情页 mount 后立刻 `loadBatchDetail` + 立刻 `startPolling(immediate=true)` → 双 fetch | **`startPolling({ immediate: false })` 默认**，mount 主动 fetch 一次就够了 |
| 4 | `setup` 顶层 `void loadBatchDetail()` 触发异步 | **统一放 `onMounted(async ...)`** |
| 5 | `onBeforeUnmount(stopPolling)` 在 composable + 调用方重复注册 | **composable 内部独享**，详情页不再注册 |
| 6 | `BatchCreateCard` 只 emit `batchRunId`，丢 `batch_code`/`dispatch_count` | **emit 完整 `BatchRunCreateResponse`**，成功消息通过 `router.push({ query: { created: '1' } })` 在详情页 toast |
| 7 | `BatchItemTable` 改 `:filters` prop 是反模式 | **改为 `v-model:status` / `v-model:checkCode`** |
| 8 | `canCancelBatch` 在详情页里出现但未定义 | **放进 `batchVerifyFormatters.ts` 导出** |
| 9 | `TERMINAL_BATCH_STATUS_SET.has(s)` 散落 | **封装 `isTerminalBatchStatus()`** 进 utils |
| 10 | Task 5 "Mirror: Tasks.vue 单文件" 与本任务目录化目标矛盾 | **删除该 mirror 行**，明确目录化 |
| 11 | `assetsApi.listBatchItems` 第三个参数是 `{ suppressErrorToast }`，**不支持 `signal`** | **Plan 显式标注 abort 边界**：仅 `getBatchRun` / `listBatchRuns` 走 signal，`listBatchItems` 不传 signal，沿用旧行为 |
| 12 | 列表页 `loading` vs 轮询 `refreshing` 不分 | **`useBatchDetail` / `useBatchItems` 同时暴露 `loading` + `refreshing`** |
| 13 | 轮询失败清空 items 表 | **`loadItems({ preserveOnError: true })` 选项**，轮询场景不破坏现有数据 |
| 14 | `BatchCreateCard` 失去表单内部错误提示 | **校验错误留在子组件内部**，仅接口错误透传父组件 |
| 15 | 删除旧 `BatchVerify.vue` 没做"只剩 router 引用"校验 | **新增 Task 0.1 grep 校验** |

## Round 3 Review Fixes（评审再迭代）

按"第 3 轮评审"的 6 个必改 + 3 个小优化 + 6 个产品决策，本 plan 进一步修订如下。

| 修订 # | 来源 | 处理 |
|---|---|---|
| 16 | `isRunning = isTerminal(status) === false`，`undefined.status` 会让 `isRunning` 误为 `true` | **null-safe 重写**：`!!status && !isTerminalBatchStatus(status)`；`isTerminalBatchStatus` 自身加 null/空字符串短路返回 `false` |
| 17 | `/1 → /2` 路由切换时旧请求可能晚于新请求返回，**旧响应覆盖新数据** | **`useBatchDetail` / `useBatchItems` 内部加 `requestSeq` 单调递增序号** + `batchRunId !== unref(batchRunIdRef)` 双保险；详情页 `watch(batchRunId)` 时先 `reset()` 再 `refresh()` |
| 18 | `setInterval` 在接口耗时 > 5s 时会形成并发 tick | **`useBatchPolling` 改用递归 `setTimeout`**：上一轮 tick 完成（含 await）后再排下一轮 |
| 19 | 顶部"刷新"按钮只调 `refreshDetail()`，下面 5 个 section 不会刷新 | **顶部刷新 = 刷新全页面**：用 `assetReportRefreshKey` / `proposalRefreshKey` 触发 `:key` 重建，`AssetVerifyReport` / `ProposalPanel` 随之重 load |
| 20 | `selectedItemId` 字段不稳定风险 | **改用 `item_key` 作选中主键**（语义稳定，不依赖 DB id 是否返回；表内已用 `item_key` 作主列）；`loadItems` 成功后保留旧 key，缺失则默认第一条 |
| 21 | `BatchCreateCard` 同时在子组件内部和 emit error 给父组件展示 → **错误重复** | **统一收敛**：表单校验 + 接口错误**全部在子组件内部**展示；父组件**只 emit `created`**，不接 `error` |
| 22 | Acceptance 写"9 条"但实际已超过 9 条 | **改为"全部回归点检查清单通过"**，不写死数量 |
| 23 | `loadItems` 类型里出现 `signal` 但实际不支持 → 误导调用方 | **从公开 API 类型里去掉 `signal`**；如未来后端支持再补 |
| 24 | `dismissCreatedBanner` 用空 `query: {}` 会丢其它 query | **只删 created/code/dispatches 三个键**，保留其它（如未来筛选条件） |

## Round 4 Review Fixes（第 4 轮评审必改 + 建议）

按"第 4 轮评审"的 3 个必须优化 + 2 个建议优化 + 3 个现场确认 + 3 个小修正，本 plan 进一步修订如下。

| 修订 # | 来源 | 处理 |
|---|---|---|
| 25 | 详情页 `onMounted` 只 `refreshDetail()` 不 `loadItems()` → 终态批次首次进入明细不加载，running 批次等 5s 后才有 items | **新增 `reloadDetailPage()` 统一函数**，`onMounted` / `watch(batchRunId)` / `handleManualRefresh` 三处统一调用 `Promise.all([refreshDetail, loadItems])` |
| 26 | `BatchItemTable` 的 `check_code` 筛选下拉数据来源缺失：列表页 `BatchCreateCard` 和详情页 `BatchItemTable` 都需要 `check_codes`，plan 没明确来源 | **新增 `useBatchVerifyOptions` composable**（5 号 composable），同时拉 `dbTypes` + `checkCodes`，按 `target_scope` 派生 `dbInstanceCheckCodes` / `serverCheckCodes`；`BatchCreateCard` 与 `BatchVerifyDetail` 都复用 |
| 27 | 顶部"刷新"只刷新 detail / asset report / proposal panel，**漏了执行项 items + `VerifyItemDetail` 依赖的 `selectedItemForDetail`** | **`handleManualRefresh` 改为 `Promise.allSettled([refreshDetail, loadItems({ preserveOnError: true })])`**，配合 Round 3 #19 的 refreshKey 重建 |
| 28 | 轮询启动逻辑有 4 个入口（`onMounted` / `watch(batchRunId)` / `watch(isRunning)` / `useBatchPolling` 内部终态自停），逻辑绕且容易重复触发 | **删除 `watch(isRunning)`**，轮询启动由"页面加载流程"统一负责（封装 `syncPollingAfterLoad()` helper），终态自停由 `useBatchPolling` 内部负责，**单 owner** |
| 29 | `useBatchPolling` 返回 `isRunning: Ref<boolean>` 与详情页派生 `isRunning`（批次是否运行中）**命名冲突** | **改名 `isPolling`**（轮询器是否运行中），避免误用 |
| 30 | `BatchRunTable` 子组件契约漏 `error` prop，但 Task 4.2 列表页已用 `:error="error"` | **明确 `BatchRunTable` props 补 `error?: string`**，对应在表格空态/错误态切换 |
| 31 | `TERMINAL_BATCH_STATUS_SET.has(status.toLowerCase())` 在 NewType brand set 上可能过不了 TS 类型 | **`isTerminalBatchStatus` helper 内部做一次安全 `as never` 转换**，调用方拿布尔值，类型问题集中收口 |
| 32 | `route.query.code` 类型是 `string \| string[] \| null`，`createdMessage` 直接用可能拿到数组 | **新增 `firstQueryValue(value: unknown): string` helper**，统一 query 取值，`createdMessage` 走 helper |

### Round 4 现场确认（不阻塞实施，但需补 confirm）

| 确认项 | 现状 | 处置 |
|---|---|---|
| `item_key` 是否在同一 batch 内唯一 | 后端未明文约束（schema 已有 `batch_run_id` 索引但未唯一） | **实施前在 `backend/app/models/batch_run.py` 验证**：确认 `BatchRunItemRow.item_key` 在 `batch_run_id` 维度唯一；若不唯一，`BatchItemTable` 选中主键降级为 `${dispatch_run_id}::${item_key}` 组合 key |
| `?created=1` 分享 URL 是否带成功条 | 用户分享 URL → 对方看到"批量任务已创建" → 不准确 | **可接受**（已在 Round 3 产品决策项），不增加"只显示一次"逻辑 |
| `BatchCreateCard` 是否独立拉 options | 方案 A：组件各自拉；方案 B：共用 composable | **采用方案 B**（新增 `useBatchVerifyOptions`，避免重复接口调用） |

## Round 5 Review Fixes（第 5 轮评审 P0 必改 + 现场确认）

按"第 5 轮评审"的 6 个 P0 必改 + 3 个现场确认 + 1 个小建议，本 plan 进一步修订如下。

| 修订 # | 来源 | 处理 |
|---|---|---|
| 33 | `BatchVerifyList.vue` 示例代码漏传 `useBatchVerifyOptions` 给 `BatchCreateCard`，与子组件 props 契约冲突 | **Task 4.2 示例补全**：`useBatchVerifyOptions` 实例化 + 4 个 props 透传（`dbTypes` / `dbInstanceCheckCodes` / `serverCheckCodes` / `optionsLoading`） |
| 34 | `handleManualRefresh()` 后未调用 `syncPollingAfterLoad()`，手动刷新改变状态后轮询要等下一轮 tick 才纠正 | **`handleManualRefresh` 末尾 `syncPollingAfterLoad()`**，与 mount / watch(batchRunId) 走同一单 owner |
| 35 | `retryFailed` / `cancelBatch` 成功后只 `loadBatchDetail({ silent: true })`，items / Proposal / VerifyItemDetail 停留旧数据 | **页面级 `handleRetryFailed` / `handleCancelBatch` 包装**：`Promise.allSettled([refreshDetail, loadItems({ preserveOnError: true })])` + `proposalRefreshKey++` + `syncPollingAfterLoad()`；模板 `@retry` / `@cancel` 改绑包装函数 |
| 36 | `BatchItemTable.checkCodeOptions` 传全量 `checkCodes`，会出现不属于当前批次范围的检查项（如 server 类型出现在 db_instance 批次） | **`itemCheckCodeOptions` 按当前 items 实际出现的 `check_code` 派生**：`new Set(items.map(it => it.check_code).filter(Boolean))` 过滤 `checkCodes`；永远不会筛出空结果，最贴合当前批次 |
| 37 | `useBatchPolling` 骨架里 `isPolling` ref 没有维护逻辑 | **明确 `startPolling` 置 `true` / `stopPolling` 置 `false`**；`tick()` `finally` 里比对 `currentController.signal` 清旧 controller 引用，避免旧引用残留 |
| 38 | Validation 写"mount 后只触发一次 fetch"，与 Round 4 #25（detail + items 并行）矛盾 | **改口径**："mount 后 1 次 detail fetch + 1 次 items fetch；无额外 polling tick；后续 running 批次每 5s 才进入轮询 tick" |

### Round 5 现场确认（不阻塞实施，但实施前必须现场查证）

| 确认项 | 现状 | 处置 |
|---|---|---|
| **`item_key` 在 batch 内唯一** | 后端未必约束 | **实施前必跑**：`grep -RIn "item_key" backend/app/models backend/app/services backend/app/api`；若不唯一则用组合 key `${dispatch_run_id}::${item_key}`（已落入 #36 备选方案） |
| **`listDbTypes()` 真实返回字段** | plan 假设 `{ code, name }`，历史接口可能返回 `db_type_code` / `db_type_name` | **实施前必跑**：`grep -RIn "listDbTypes\|db_type_code\|db_type_name" frontend/src`；字段不同时在 `useBatchVerifyOptions` 内部 map 标准化 |
| **`createBatchRun` 真实返回字段** | plan 假设返回 `batch_run_id`，可能返回 `id` | **实施前必跑**：`grep -RIn "BatchRunCreateResponse\|batch_run_id" backend/app/api backend/app/services`；字段不同时 `BatchVerifyList.handleCreated` 与 `useBatchVerifyOptions` / `useBatchDetail` 同步调整 |

### Round 5 小建议（不强制）

- **`useBatchVerifyOptions` 模块级 cache**：本轮**不引入**（保持简单）；options 接口轻量，列表页 + 详情页各拉一次可接受。后续如出现性能问题再加 `let cachedLoaded = false` 模式。

## Summary

把当前 793 行的 `BatchVerify.vue`（6 个 Section 堆在一页）按"列表 + 详情"双页拆分：

```
/ops/batch-verify              → BatchVerifyList.vue     # 创建任务 + 批次列表
/ops/batch-verify/:batchRunId  → BatchVerifyDetail.vue   # 摘要 + 报告 + dispatch + items + proposals
```

并把页面级状态、API 调用、轮询逻辑下沉到 composables，把格式化函数抽出到 utils，把每个 Section 抽成独立子组件。**业务行为 0 改动**（行为契约以 `batch-verify-page-refactor-input-2026-06-18.md` § 9 为准）。

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Page shell | `frontend/src/components/ops/OpsPage.vue` + `OpsPageHeader.vue` | 所有页面统一用 `OpsPage` 包，标题走 `OpsPageHeader`，副标题/icon/actions slot |
| Section card | `frontend/src/components/ops/OpsSectionCard.vue` | 每个 Section 一个 `OpsSectionCard`，标题/icon/description/`#actions` slot |
| Empty / loading / error | `frontend/src/components/ops/OpsEmptyState.vue` | 三态统一 `state="loading"\|"empty"\|"error"`，不写自定义态 |
| Table | 现有 `BatchVerify.vue:131-184` / `AssetVerifyReport.vue:38-85` | 原生 `<table>` + `OpsTableShell` 包装，不用第三方 |
| Button class | 现有 `BatchVerify.vue:111,176` | `ops-primary-button` / `ops-secondary-button` / `text-primary` 文字按钮 |
| Field class | 现有 `BatchVerify.vue:14-23,192-194` | `field-card` + `field-label` + `field-value` 三件套 |
| Tailwind palette | 现有 status badge 颜色 | `emerald`/`amber`/`red`/`sky`/`slate` + `/10` 透明度背景 + `/30` border |
| 类型 / 终态集 | `frontend/src/types/api.ts:970-982` | `TERMINAL_BATCH_STATUS_SET` 已 NewType brand，单一来源，**禁止**重新声明 |
| Composable 输入 | （仓库暂未存在 `src/composables/`，需新建） | 命名 `useXxx.ts`；返回 reactive state + actions；不直接挂 onMounted/onBeforeUnmount 给调用方以外的地方 |
| Options/options 类 composable | （仓库暂未存在此模式，但与本视图其它 composable 同源） | `useXxxOptions` 返回 `xxxOptions / loading / loadOptions`；可同时被列表页和详情页复用，使用方用 `Promise.allSettled` 容错 |
| 路由 query 取值 | `vue-router` `LocationQuery` | `route.query[key]` 类型是 `string \| string[] \| null \| undefined`；统一走 `firstQueryValue()` helper 取单值，避免类型分支散落 |
| 子组件 props 契约 | `AssetVerifyReport.vue:116` `ProposalPanel.vue:196` `VerifyItemDetail.vue:91` | 已经稳定：`batchRunId: number \| null` / `item: VerifyItem \| null`，**禁止**改 |
| 轮询 AbortController + 错误可见 | `BatchVerify.vue:426-467`（P1 修复） | `useBatchPolling` 必须完整保留：AbortController、错误不静默、不清空详情、终态自停 |

## Files to Change

### 新增

| 文件 | 作用 |
|---|---|
| `frontend/src/views/ops/batch-verify/BatchVerifyList.vue` | 列表页编排（创建 + 列表） |
| `frontend/src/views/ops/batch-verify/BatchVerifyDetail.vue` | 详情页编排（摘要 + 报告 + dispatch + items + proposals） |
| `frontend/src/views/ops/batch-verify/components/BatchCreateCard.vue` | 新建批量任务表单 |
| `frontend/src/views/ops/batch-verify/components/BatchRunTable.vue` | 批次列表表格 + 行点击 |
| `frontend/src/views/ops/batch-verify/components/BatchSummaryCard.vue` | 7 格栅格摘要 + skipped 提示条 |
| `frontend/src/views/ops/batch-verify/components/BatchDispatchTable.vue` | 分发明细表格 |
| `frontend/src/views/ops/batch-verify/components/BatchItemTable.vue` | 执行项表格 + 筛选 + 选中态 |
| `frontend/src/views/ops/batch-verify/components/BatchPollingAlert.vue` | 黄色轮询错误条 |
| `frontend/src/views/ops/batch-verify/composables/useBatchRuns.ts` | 列表页加载批次列表 |
| `frontend/src/views/ops/batch-verify/composables/useBatchDetail.ts` | 加载/取消/重跑单个批次 |
| `frontend/src/views/ops/batch-verify/composables/useBatchItems.ts` | 加载 items + 筛选 + 选中 |
| `frontend/src/views/ops/batch-verify/composables/useBatchPolling.ts` | 5s 轮询 + AbortController + 终态停 |
| `frontend/src/views/ops/batch-verify/composables/useBatchVerifyOptions.ts` | **Round 4 #26**：加载 `dbTypes` + `checkCodes`，按 `target_scope` 派生，列表页 `BatchCreateCard` + 详情页 `BatchItemTable` 共用 |
| `frontend/src/views/ops/batch-verify/utils/batchVerifyFormatters.ts` | 状态徽章 / 时间 / item 派生字段 + `firstQueryValue` + `isTerminalBatchStatus` 含 `as never` 类型收口 |

### 修改

| 文件 | 改动 |
|---|---|
| `frontend/src/router/index.ts:55-61` | 把 `BatchVerify` 路由拆成两条：list（`/ops/batch-verify`） + detail（`/ops/batch-verify/:batchRunId`，props `route => ({ batchRunId: Number(route.params.batchRunId) })`） |
| `frontend/src/views/ops/BatchVerify.vue` | **删除**（删除前所有内容已迁出） |

### 不动（确认）

| 文件 | 原因 |
|---|---|
| `frontend/src/components/ops/AssetVerifyReport.vue` | props 契约稳定，原样复用 |
| `frontend/src/components/ops/ProposalPanel.vue` | props `batchRunId` 契约稳定，原样复用（含 PORT_CANDIDATE_CONFLICT picker） |
| `frontend/src/components/ops/VerifyItemDetail.vue` | props `item: VerifyItem \| null` 契约稳定，原样复用 |
| `frontend/src/api/assets.ts` | 端点齐全，不增不改 |
| `frontend/src/types/api.ts` | `BatchRunRow` / `BatchRunItemRow` / `BatchRunCreatePayload` / `TERMINAL_BATCH_STATUS_SET` 已经收齐，不增 |

---

## Tasks

### Task 0：建立模块骨架（不动业务）

#### Task 0.1 先验证旧文件唯一引用方

- **Action**：实施任何文件改动前，**先 grep 验证旧 `BatchVerify.vue` 只被 router 引用**：
  ```bash
  grep -RIn "views/ops/BatchVerify\.vue\|@/views/ops/BatchVerify" frontend/src
  grep -RIn "name: 'BatchVerify'" frontend/src
  grep -RIn "from '@/views/ops/BatchVerify" frontend/src
  ```
- **预期结果**：仅 `router/index.ts:55-61` 命中，无其它 import / 静态引用。
- **如有命中**：先解决（更新导入方），再进入 Task 0.2。

#### Task 0.2 建立目录骨架

- **Action**：在 `frontend/src/views/ops/batch-verify/` 下创建空目录骨架：
  - `components/`（空目录加 `.gitkeep`）
  - `composables/`（空目录加 `.gitkeep`）
  - `utils/`（空目录加 `.gitkeep`）
- **Mirror**：与 `frontend/src/views/backup/` 现有目录风格一致（备份页面已经有 `backup/Policies.vue` 等单文件 + 目录化混用，本视图选择**目录化**）。
- **Validate**：`ls frontend/src/views/ops/batch-verify/` 显示三个子目录。

### Task 1：抽取 utils（无副作用）

- **Action**：把 `BatchVerify.vue` 中所有纯函数搬到 `batchVerifyFormatters.ts`：
  - `formatTime(val)`（包 `formatInTz`）
  - `isCancelled(status)`
  - `formatStatusLabel(status)`（9 种 batch/dispatch 状态）→ 命名 `formatBatchStatusLabel`
  - `getStatusBadgeClass(status)`（同上）→ 命名 `getBatchStatusBadgeClass`
  - `getItemStatusBadgeClass(status)`（5 种 item 状态）
  - `formatItemStatusLabel(status)`
  - `formatItemResult(item)`
  - `formatItemMessage(item)`
  - `getItemFactsCount(item)`
- **新增辅助（Round 2 + Round 3 评审补强）**：
  - `isTerminalBatchStatus(status: string \| null \| undefined): boolean`
    - **实现（Round 3 null-safe + Round 4 #31 类型安全）**：
      ```ts
      export function isTerminalBatchStatus(status: string | null | undefined): boolean {
        if (!status) return false   // 空字符串 / null / undefined → 视为非终态（语义：还没拿到状态）
        // NewType brand set 需要一次 as never 转换集中收口，调用方拿布尔值
        return TERMINAL_BATCH_STATUS_SET.has(status.toLowerCase() as never)
      }
      ```
    - 关键：**空状态 ≠ 终态**。`undefined` 返回 `false`，详情页 `isRunning` 计算依赖此语义（修订 #16）
    - **类型收口（Round 4 #31）**：`as never` 集中在这一个函数内部，调用方拿 `boolean` 不接触 brand set，避免散落到页面
  - `canCancelBatch(status: string \| null \| undefined)`：迁移 `BatchVerify.vue:761-765` 谓词，详情页可直接 `v-bind` / 调用
  - **`firstQueryValue(value: unknown): string`（Round 4 #32 新增）**：
    ```ts
    export function firstQueryValue(value: unknown): string {
      if (Array.isArray(value)) return String(value[0] ?? '')
      return value == null ? '' : String(value)
    }
    ```
    - **职责**：把 `route.query` 的 `string | string[] | null | undefined` 统一收口成 `string`，调用方不再判类型
    - **使用方**：`createdMessage` 拿 `firstQueryValue(route.query.code)` / `firstQueryValue(route.query.dispatches)`
- **导出策略**：每个函数 `export function`；命名空间前缀避免冲突（例如 `getBatchStatusBadgeClass` / `getItemStatusBadgeClass`，与现有 `ProposalPanel.vue:283 statusBadge` 风格一致，但统一前缀以便于 IDE 自动补全）。
- **禁止重复声明终态集**：`TERMINAL_BATCH_STATUS_SET` 仍由 `@/types/api` 唯一导出，本文件 `import { TERMINAL_BATCH_STATUS_SET } from '@/types/api'` 后再包一层函数。
- **Validate**：`vue-tsc --noEmit` 通过；`grep "formatStatusLabel" frontend/src/views/ops/BatchVerify.vue` 应为 0（旧文件后续删除前的占位）。

### Task 2：抽取 composables

#### Task 2.1 `useBatchRuns`

- **Action**：列表页用。封装 `assetsApi.listBatchRuns({ limit: 20 })`，返回 `{ batches, loading, error, loadBatches, refresh }`。
- **Mirror**：参考 `BatchVerify.vue:698-707 loadBatches`，但加上 `error` ref；失败时不写入 `pollError`（列表页无轮询），仅暴露 `error.value`。
- **Validate**：手动创建一个批次后调用 `refresh()` 列表能拉到新数据。

#### Task 2.2 `useBatchDetail`（**接 `Ref<number \| null>` + `requestSeq` + `reset()`**）

- **Action**：详情页用。封装 `getBatchRun` / `retryFailedBatchItems` / `cancelBatchRun`。
- **API**（Round 2 + Round 3 修订）：
  ```ts
  function useBatchDetail(batchRunIdRef: Ref<number | null>): {
    batchDetail: Ref<BatchRunRow | null>
    loading: Ref<boolean>             // 首次加载 / 主动 refresh
    refreshing: Ref<boolean>          // 轮询 / 静默刷新
    error: Ref<string>
    retryLoading: Ref<boolean>
    cancelLoading: Ref<boolean>
    loadBatchDetail: (opts?: { silent?: boolean; signal?: AbortSignal }) => Promise<void>
    refreshDetail: (opts?: { signal?: AbortSignal }) => Promise<void>
    retryFailed: () => Promise<void>
    cancelBatch: () => Promise<void>
    reset: () => void    // Round 3 修订 #17：清空 batchDetail / error / loading / refreshing + 让进行中旧请求作废
  }
  ```
- **契约**：
  - **每次调用前 `unref(batchRunIdRef)`，路由切换 / props 变化自动跟随**
  - **`requestSeq` 守卫（Round 3 修订 #17）**：单调递增 `seq` 写入闭包变量；拿到响应后比对 `seq !== requestSeq` 或 `batchRunId !== unref(batchRunIdRef)` 时**直接 return**，避免旧响应覆盖新数据
    ```ts
    let requestSeq = 0
    async function loadBatchDetail(opts) {
      const batchRunId = unref(batchRunIdRef)
      if (!batchRunId) { batchDetail.value = null; return }
      const seq = ++requestSeq
      const silent = opts.silent === true
      silent ? (refreshing.value = true) : (loading.value = true)
      error.value = ''
      try {
        const result = await assetsApi.getBatchRun(batchRunId, { signal: opts.signal })
        if (seq !== requestSeq) return
        if (batchRunId !== unref(batchRunIdRef)) return
        batchDetail.value = result
      } catch (err) {
        if (seq !== requestSeq) return
        if (err instanceof DOMException && err.name === 'AbortError') return
        error.value = err instanceof Error ? err.message : '加载批次详情失败'
      } finally {
        if (seq === requestSeq) {
          loading.value = false
          refreshing.value = false
        }
      }
    }
    ```
  - **`reset()`（Round 3 修订 #17）**：调用方在路由切换时主动 `reset()`，清空状态 + `requestSeq++` 让进行中请求作废
    ```ts
    function reset() {
      requestSeq++
      batchDetail.value = null
      error.value = ''
      loading.value = false
      refreshing.value = false
    }
    ```
  - `cancelBatch()` 必须保留 `window.confirm('确认取消该批次？已启动的 AWX Job 会被请求 cancel，未启动的 dispatch 不会下发。')` 文案（产品决策：**保留 `window.confirm`，不做 `OpsConfirmDialog` 升级**）
  - `retryFailed()` / `cancelBatch()` 调用成功后 `loadBatchDetail({ silent: true })`
  - `loadBatchDetail({ silent: true })` 只改 `refreshing` 不改 `loading`；默认 `{ silent: false }` 改 `loading`
  - 错误暴露到 `error.value`，**不**清空 `batchDetail`（沿用 P1 修复；但 `reset()` 是显式场景，会清空）
- **Mirror**：`BatchVerify.vue:709-781` 既有实现。

#### Task 2.3 `useBatchItems`（**接 `Ref<number \| null>` + `preserveOnError` + `requestSeq` + 选中用 `item_key`**）

- **Action**：详情页用。封装 `listBatchItems(id, params)`。
- **API**（Round 2 + Round 3 修订）：
  ```ts
  function useBatchItems(batchRunIdRef: Ref<number | null>): {
    items: Ref<BatchRunItemRow[]>
    itemFilters: { status: string; check_code: string }   // reactive
    selectedItemKey: Ref<string | null>     // Round 3 修订 #20：用 item_key 而非 id
    selectedItem: ComputedRef<BatchRunItemRow | null>
    selectedItemForDetail: ComputedRef<VerifyItem | null>
    loading: Ref<boolean>
    refreshing: Ref<boolean>
    error: Ref<string>
    loadItems: (opts?: { preserveOnError?: boolean }) => Promise<void>
    selectItem: (item: BatchRunItemRow) => void
    reset: () => void
  }
  ```
- **契约**：
  - `itemFilters` 是 `reactive({ status: '', check_code: '' })`
  - 每次请求前 `unref(batchRunIdRef)` 取最新 id；id 为 `null` 直接 return
  - **`requestSeq` + `reset()` 同 `useBatchDetail`**（Round 3 修订 #17）
  - **非破坏性刷新（Round 2 修订）**：默认 `loadItems()` 失败时 `items = []; selectedItemKey = null`；`loadItems({ preserveOnError: true })` 仅写 `error.value`，保留旧数据（轮询场景必须用这个）
  - **选中主键（Round 3 修订 #20）**：用 `item_key` 作选中态，**不用 `id`**：
    ```ts
    function selectItem(item: BatchRunItemRow) {
      selectedItemKey.value = item.item_key
    }
    const selectedItem = computed(() =>
      selectedItemKey.value
        ? items.value.find(it => it.item_key === selectedItemKey.value) ?? null
        : null,
    )
    // loadItems 成功后保留旧 key；缺失则默认第一条
    const oldKey = selectedItemKey.value
    items.value = result
    if (oldKey && result.some(it => it.item_key === oldKey)) {
      selectedItemKey.value = oldKey
    } else {
      selectedItemKey.value = result[0]?.item_key ?? null
    }
    ```
  - **`signal` 不出现在公开类型（Round 3 修订 #23）**：`assetsApi.listBatchItems` 当前第三个参数仅支持 `{ suppressErrorToast }`，**不支持 `signal`**。因此 `loadItems` 的公开类型里**不暴露** signal 参数，避免调用方误以为能 abort。
- **导出派生**：`selectedItemForDetail`（map 到 `VerifyItemDetail` 期望的 `VerifyItem` shape），从当前 `BatchVerify.vue:540-560` 完整搬过来；查表用 `item_key`。

#### Task 2.4 `useBatchPolling`（**P1 修复完整保留 + Round 2 + Round 3 递归 `setTimeout`**）

- **Action**：从 `BatchVerify.vue:411-473`（含 P1 修复的 AbortController + 错误可见）抽取为 composable。
- **API**（Round 2 + Round 3 修订）：
  ```ts
  interface UseBatchPollingOptions {
    batchRunIdRef: Ref<number | null>
    getStatus: () => string | null
    onTick: (signal: AbortSignal) => Promise<void>   // signal 透传
  }
  interface StartPollingOptions {
    immediate?: boolean   // 默认 false，避免与 onMounted 主动 fetch 重复
  }
  function useBatchPolling(opts: UseBatchPollingOptions): {
    pollError: Ref<string>
    isPolling: Ref<boolean>             // Round 4 #29：原 isRunning 改名，避免与详情页派生的"批次是否运行中"isRunning 命名冲突
    startPolling: (options?: StartPollingOptions) => void
    stopPolling: () => void
  }
  ```
- **保留 + 修订行为**：
  - `POLL_INTERVAL = 5000`
  - **递归 `setTimeout`（Round 3 修订 #18）**：tick 完成（含 await）后再排下一轮，**避免接口耗时 > 5s 时的并发 tick**。**不使用 `setInterval`**。
  - 每次 tick 创建新 `AbortController`，component unmount 或 `startPolling()` 重新启动时 `abort()`
  - `tick()` 内部：`const controller = new AbortController(); opts.onTick(controller.signal)`，让支持 signal 的 API 真正能 abort
  - 失败时把 `err.message` 写到 `pollError`，**不**停轮询、不清空详情
  - `AbortError` / `CanceledError` 静默
  - 终态（`isTerminalBatchStatus(getStatus())`）自动 `stopPolling()`
  - `startPolling()` 默认**不**立即 tick
  - `startPolling({ immediate: true })` 立即 tick 一次，再排下一轮
  - composable 内部独享 `onBeforeUnmount(stopPolling)`，调用方**不再注册**
- **实现骨架（Round 3）**：
  ```ts
  const POLL_INTERVAL = 5000
  let timer: number | null = null
  let controller: AbortController | null = null
  let stopped = true

  // Round 5 #37：明确维护 isPolling，调用方可读
  const isPolling = ref(false)

  async function tick() {
    if (stopped) return
    controller?.abort()
    const currentController = new AbortController()
    controller = currentController
    try {
      await opts.onTick(currentController.signal)
      pollError.value = ''
      if (isTerminalBatchStatus(opts.getStatus())) {
        stopPolling()
        return
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (err instanceof Error && err.name === 'CanceledError') return
      pollError.value = err instanceof Error ? err.message : '轮询批次状态失败'
    } finally {
      // Round 5 #37：清旧 controller 引用，避免 stop 后仍残留
      if (controller?.signal === currentController.signal) {
        controller = null
      }
    }
    if (!stopped) {
      timer = window.setTimeout(tick, POLL_INTERVAL)   // 递归 setTimeout
    }
  }

  function startPolling(options: StartPollingOptions = {}) {
    stopPolling()
    // Round 5 #37：batchRunIdRef 无效或已终态，不启动
    if (!unref(opts.batchRunIdRef)) return
    if (isTerminalBatchStatus(opts.getStatus())) return
    stopped = false
    isPolling.value = true   // Round 5 #37
    if (options.immediate) {
      void tick()
    } else {
      timer = window.setTimeout(tick, POLL_INTERVAL)
    }
  }

  function stopPolling() {
    stopped = true
    isPolling.value = false   // Round 5 #37
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
    controller?.abort()
    controller = null
  }

  onBeforeUnmount(stopPolling)
  ```
- **Mirror**：`BatchVerify.vue:411-473` 整体迁移，但 `setInterval` → 递归 `setTimeout`。`watch(selectedBatchId, ...)` 模式搬到 `BatchVerifyDetail.vue`。
- **命名（Round 4 #29 修订）**：返回值里的 `isRunning: Ref<boolean>` **改为 `isPolling: Ref<boolean>`**（轮询器是否运行中），避免与详情页派生的"批次是否运行中"`isRunning` 命名冲突。调用方无需关心此字段（轮询启动/停止由页面加载流程单 owner 负责），保留仅为诊断。

#### Task 2.5 `useBatchVerifyOptions`（**Round 4 #26 新增**）

- **Action**：列表页 + 详情页共用。封装 `assetsApi.listDbTypes()` + `assetsApi.listCheckCodes({ is_enabled: true })`。
- **API**：
  ```ts
  function useBatchVerifyOptions(): {
    checkCodes: Ref<CollectorCheckDefinitionRow[]>
    dbTypes: Ref<Array<{ code: string; name: string }>>
    dbInstanceCheckCodes: ComputedRef<CollectorCheckDefinitionRow[]>
    serverCheckCodes: ComputedRef<CollectorCheckDefinitionRow[]>
    loading: Ref<boolean>
    loadOptions: () => Promise<void>
  }
  ```
- **契约**：
  - **单次加载**：调用方在 `onMounted` 调一次 `loadOptions()`；**不轮询**
  - **`Promise.allSettled` 容错**：两个接口任一失败不影响另一个写回；失败的写到 `console.warn` 即可（不抛到调用方）
  - **`listCheckCodes` 第二个参数传 `{ suppressErrorToast: true }`**，避免列表/详情页加载时弹一堆错误
  - **派生 computed**：按 `item.target_scope` 字段过滤 `'db_instance'` / `'server'`，与 `BatchCreateCard` 现有逻辑一致
  - **不挂 onMounted / onBeforeUnmount**：保持 composable 单一职责，由调用方控制
- **使用方**：
  - **`BatchVerifyList.vue`**：`const { dbTypes, dbInstanceCheckCodes, serverCheckCodes, loading: optionsLoading, loadOptions } = useBatchVerifyOptions()`；`onMounted(loadOptions)`；把 `dbTypes` + `dbInstanceCheckCodes/serverCheckCodes` 通过 props 传给 `BatchCreateCard`
  - **`BatchVerifyDetail.vue`**：`const { checkCodes, loadOptions } = useBatchVerifyOptions()`；`onMounted(loadOptions)`；把 `checkCodes` 通过 `:check-code-options` 传给 `BatchItemTable`（用于筛选下拉）

### Task 3：抽取子组件（沿用既有约定）

| 子组件 | 职责 | 从哪里搬 | emit / v-model |
|---|---|---|---|
| `BatchCreateCard` | 新建任务表单（**全部错误在子组件内部展示**，父组件不接 error） | `BatchVerify.vue:10-127` | `@created(result: BatchRunCreateResponse)` |
| `BatchRunTable` | 批次列表表格 | `BatchVerify.vue:130-185` | `@detail(batchRunId: number)` |
| `BatchSummaryCard` | 7 格栅格摘要 + skipped 提示 | `BatchVerify.vue:188-229` | — |
| `BatchDispatchTable` | 分发明细表格 | `BatchVerify.vue:234-281` | — |
| `BatchItemTable` | 执行项表格 + 筛选 + 选中 | `BatchVerify.vue:283-360` | `v-model:status` / `v-model:checkCode` / `@select(item)` / `@reload` / `@retry` / `@cancel` |
| `BatchPollingAlert` | 黄色错误条 | `BatchVerify.vue:122-125` | `@dismiss` |

- **子组件 props 契约（Round 4 #26 + #30 增补）**：
  - **`BatchRunTable`**（Round 4 #30）：
    ```ts
    const props = defineProps<{
      rows: BatchRunRow[]
      loading: boolean
      error?: string           // 列表页 useBatchRuns 失败时展示
    }>()
    ```
    - 空态/错误态切换：`error` 非空 → 显示 `OpsEmptyState state="error"`；`loading=false && rows.length=0` → 显示 `state="empty"`
  - **`BatchCreateCard`**：
    ```ts
    const props = defineProps<{
      dbTypes: Array<{ code: string; name: string }>
      dbInstanceCheckCodes: CollectorCheckDefinitionRow[]
      serverCheckCodes: CollectorCheckDefinitionRow[]
      optionsLoading?: boolean
    }>()
    ```
    - 选项由父组件 `BatchVerifyList.vue` 通过 `useBatchVerifyOptions` 注入，避免组件内部直接调 API
    - **`optionsLoading` 为 true 时**禁用提交按钮（与 `loading` 并列）
  - **`BatchItemTable`**（Round 4 #26）：
    ```ts
    const props = defineProps<{
      rows: BatchRunItemRow[]
      loading: boolean
      refreshing?: boolean
      selectedItemKey: string | null
      canCancel: boolean
      checkCodeOptions: CollectorCheckDefinitionRow[]   // 详情页 useBatchVerifyOptions 注入
    }>()
    ```
    - `checkCodeOptions` 用于渲染筛选下拉"全部 / CHECK_DB_VERSION / CHECK_PORT_CONFLICT / ..."
    - **不**在子组件内部调 `listCheckCodes`（保持子组件无 API 调用）
  - **`BatchSummaryCard` / `BatchDispatchTable` / `BatchPollingAlert`**：保持原有 props 不变（Round 3 已确认契约）

- **注意**：
  - **`BatchCreateCard` 错误分工（Round 3 修订 #21：单一职责，避免重复）**：
    - **表单校验错误**（如 "请输入有效的资产 ID"）：子组件**内部**展示在表单顶部
    - **创建接口失败**（网络 / 422）：子组件**内部**展示错误条
    - **创建成功**：emit `created(result)`，由父组件决定下一步
    - **`error` emit 已删除**：避免父页面再展示一次造成重复
  - **`@created` 传完整响应（Round 2 修订）**：原 UX 是 `批量任务已创建：${batch_code}，${dispatch_count} 个分发`，父组件需要这两个字段，故 `emit('created', result: BatchRunCreateResponse)`。**不要**只传 `batchRunId`。
  - **`BatchRunTable` 不拉 API**。接收 `rows: BatchRunRow[]`、`loading: boolean` props。
  - **`BatchItemTable` 不拉 API**（Round 2 + Round 3 修订）：
    - 筛选用 `v-model:status` / `v-model:checkCode`（不要 `:filters` prop，Vue 反模式）
    - 子组件内：`const status = defineModel<string>('status', { required: true })`；`const checkCode = defineModel<string>('checkCode', { required: true })`
    - **选中主键用 `item_key`**（Round 3 #20）：`:selected-item-key="..."` 而不是 `:selected-item-id`；emit `@select(item)` 内部以 `item.item_key` 标记选中
    - 父组件：`loadItems()` 通过 `@reload` 触发
    - `retryFailed` / `cancelBatch` 由父组件处理
  - **`BatchSummaryCard` 是纯展示**，props `{ batch: BatchRunRow }`。

### Task 4：拆分路由 + 编排两个页面

#### Task 4.1 router

```ts
{
  path: 'ops/batch-verify',
  name: 'BatchVerify',
  component: () => import('@/views/ops/batch-verify/BatchVerifyList.vue'),
  meta: { title: '批量校验', parent: '自动化运维' },
},
{
  path: 'ops/batch-verify/:batchRunId',
  name: 'BatchVerifyDetail',
  component: () => import('@/views/ops/batch-verify/BatchVerifyDetail.vue'),
  meta: { title: '批量校验详情', parent: '自动化运维' },
  props: route => ({ batchRunId: Number(route.params.batchRunId) }),
}
```

- **错误处理**：详情页 mount 时若 `batchRunId` 为 `NaN` / 负数 → `OpsEmptyState state="error" title="无效的批次 ID"`。

#### Task 4.2 `BatchVerifyList.vue`（**Round 2 + Round 3 + Round 5 全量修订**）

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import BatchCreateCard from './components/BatchCreateCard.vue'
import BatchRunTable from './components/BatchRunTable.vue'
import { useBatchRuns } from './composables/useBatchRuns'
import { useBatchVerifyOptions } from './composables/useBatchVerifyOptions'   // Round 5 #33
import type { BatchRunCreateResponse } from '@/types/api'

const router = useRouter()

const { batches, loading, error, loadBatches } = useBatchRuns()

// Round 5 #33：注入 options 给 BatchCreateCard（避免子组件 props 契约空跑）
const {
  dbTypes,
  dbInstanceCheckCodes,
  serverCheckCodes,
  loading: optionsLoading,
  loadOptions,
} = useBatchVerifyOptions()

onMounted(() => {
  void loadBatches()
  void loadOptions()
})

function goDetail(id: number) {
  router.push({ name: 'BatchVerifyDetail', params: { batchRunId: id } })
}

async function handleCreated(result: BatchRunCreateResponse) {
  await loadBatches()
  // Round 5 现场确认：result.batch_run_id 字段名以实施前 grep 为准
  router.push({
    name: 'BatchVerifyDetail',
    params: { batchRunId: result.batch_run_id },
    query: {
      created: '1',
      code: result.batch_code,
      dispatches: String(result.dispatch_count),
    },
  })
}
</script>

<template>
  <OpsPage>
    <OpsPageHeader
      title="批量校验"
      subtitle="选择资产范围和检查项，统一调度 AWX 批量执行"
      icon="checklist"
    />

    <!-- Round 5 #33：补 4 个 props；BatchCreateCard 子组件内部展示错误 -->
    <BatchCreateCard
      class="mb-6"
      :db-types="dbTypes"
      :db-instance-check-codes="dbInstanceCheckCodes"
      :server-check-codes="serverCheckCodes"
      :options-loading="optionsLoading"
      @created="handleCreated"
    />

    <OpsSectionCard title="批量任务列表">
      <template #actions>
        <button class="ops-secondary-button text-xs" :disabled="loading" @click="loadBatches">
          <span class="material-symbols-outlined text-[16px]">refresh</span>
          刷新
        </button>
      </template>

      <BatchRunTable
        :rows="batches"
        :loading="loading"
        :error="error"
        @detail="goDetail"
      />
    </OpsSectionCard>
  </OpsPage>
</template>
```

- **关键变更**（Round 2 + Round 3 + Round 5 修订）：
  - `handleCreated(result: BatchRunCreateResponse)` 接完整响应
  - 跳详情页时附带 `query.created=1` + `code` + `dispatches`，详情页据此展示成功条
  - **列表页不做 `launchMessage` 持久展示**（用户立即跳走看不到）——成功反馈统一在详情页处理
  - **列表页轮询产品决策确认**：本次**不轮询**，仅提供手动「刷新」按钮（Round 2 决策项 #5 选 A）
  - `error` 来自 `useBatchRuns`，渲染在 `BatchRunTable` 内部（空态/错误态统一由子组件管理）
  - **Round 3 #21：删除 `handleError` / `errorBanner`**。`BatchCreateCard` 内部错误不外泄，避免重复展示
  - **Round 5 #33**：补 `useBatchVerifyOptions` 实例化 + `BatchCreateCard` 4 个 props 透传；`onMounted` 并行 `void loadBatches() + void loadOptions()`
- **注意**：`BatchCreateCard` 的 `@created` 事件契约要在该子组件中**显式** `defineEmits<{ created: [BatchRunCreateResponse] }>()`。

#### Task 4.3 `BatchVerifyDetail.vue`（**Round 2 + Round 3 + Round 4 全量修订**）

```vue
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import OpsPage from '@/components/ops/OpsPage.vue'
import OpsPageHeader from '@/components/ops/OpsPageHeader.vue'
import OpsSectionCard from '@/components/ops/OpsSectionCard.vue'
import OpsEmptyState from '@/components/ops/OpsEmptyState.vue'
import AssetVerifyReport from '@/components/ops/AssetVerifyReport.vue'
import ProposalPanel from '@/components/ops/ProposalPanel.vue'
import VerifyItemDetail from '@/components/ops/VerifyItemDetail.vue'
import BatchSummaryCard from './components/BatchSummaryCard.vue'
import BatchDispatchTable from './components/BatchDispatchTable.vue'
import BatchItemTable from './components/BatchItemTable.vue'
import BatchPollingAlert from './components/BatchPollingAlert.vue'
import { useBatchDetail } from './composables/useBatchDetail'
import { useBatchItems } from './composables/useBatchItems'
import { useBatchPolling } from './composables/useBatchPolling'
import { useBatchVerifyOptions } from './composables/useBatchVerifyOptions'   // Round 4 #26
import { canCancelBatch, firstQueryValue, isTerminalBatchStatus } from './utils/batchVerifyFormatters'   // Round 4 #32

const props = defineProps<{ batchRunId: number }>()
const route = useRoute()
const router = useRouter()

// ── 路由 → Ref（Round 3：让 composable 跟随路由切换） ────────────────
const batchRunIdRef = computed(() =>
  Number.isFinite(props.batchRunId) && props.batchRunId > 0 ? props.batchRunId : null,
)
const invalidId = computed(() => batchRunIdRef.value === null)

// ── composables（接 Ref，自动跟随路由切换） ───────────────────────────
const {
  batchDetail,
  loading: detailLoading,
  refreshing: detailRefreshing,
  error: detailError,
  loadBatchDetail,
  refreshDetail,
  retryFailed,
  cancelBatch,
  reset: resetDetail,    // Round 3 #17
} = useBatchDetail(batchRunIdRef)

const {
  items,
  itemFilters,
  selectedItem,            // Round 3 #20：用 item_key 查表
  selectedItemForDetail,
  loading: itemsLoading,
  refreshing: itemsRefreshing,
  loadItems,
  selectItem,
  reset: resetItems,       // Round 3 #17
} = useBatchItems(batchRunIdRef)

// Round 4 #26：详情页注入 checkCodes 给 BatchItemTable 筛选下拉
const { checkCodes: checkCodeOptions, loadOptions: loadVerifyOptions } = useBatchVerifyOptions()

const { pollError, startPolling, stopPolling, isPolling } = useBatchPolling({   // Round 4 #29: isPolling
  batchRunIdRef,
  getStatus: () => batchDetail.value?.status ?? null,
  onTick: async (signal) => {
    // getBatchRun 支持 signal；listBatchItems 不支持，依赖 preserveOnError 兜底
    await Promise.all([
      loadBatchDetail({ silent: true, signal }),
      loadItems({ preserveOnError: true }),
    ])
  },
})

// ── 派生 ─────────────────────────────────────────────────────────────
const subtitle = computed(() =>
  batchDetail.value ? `批次编号：${batchDetail.value.batch_code}` : '批次详情',
)

// Round 3 #16 null-safe：有状态且非终态才算 running（undefined.status 不再误判为 running）
const isRunning = computed(() => {
  const status = batchDetail.value?.status
  return !!status && !isTerminalBatchStatus(status)
})

// Round 5 #36：按当前 items 实际出现的 check_code 派生筛选下拉
// 优点：永远不会筛出空结果；不会出现 server 类型检查项出现在 db_instance 批次
// 备选（按 target_scope 派生）：scopedCheckCodeOptions 也保留在 utils 里，调用方可二选一
const itemCheckCodeOptions = computed(() => {
  const exists = new Set(
    items.value.map(item => item.check_code).filter((code): code is string => Boolean(code)),
  )
  return checkCodeOptions.value.filter(item => exists.has(item.check_code))
})

// ── 创建成功条：URL query.created === '1' 时显示 ─────────────────────
const showCreatedBanner = computed(() => firstQueryValue(route.query.created) === '1')   // Round 4 #32
const createdMessage = computed(() => {
  if (!showCreatedBanner.value) return ''
  // Round 4 #32：query 统一走 firstQueryValue，避免 string[] 类型分支
  const code = firstQueryValue(route.query.code) || batchDetail.value?.batch_code || ''
  const dispatches =
    firstQueryValue(route.query.dispatches) ||
    String(batchDetail.value?.dispatch_count ?? 0)
  return `批量任务已创建：${code}，${dispatches} 个分发`
})
// Round 3 #24：只删除 created/code/dispatches，保留其它 query
function dismissCreatedBanner() {
  const nextQuery = { ...route.query }
  delete nextQuery.created
  delete nextQuery.code
  delete nextQuery.dispatches
  router.replace({
    name: 'BatchVerifyDetail',
    params: { batchRunId: props.batchRunId },
    query: nextQuery,
  })
}

// ── 顶部「刷新」按钮（Round 3 #19 + Round 4 #27：刷新整个详情页 + items） ─
const assetReportRefreshKey = ref(0)
const proposalRefreshKey = ref(0)
const manualRefreshing = ref(false)
async function handleManualRefresh() {
  manualRefreshing.value = true
  try {
    assetReportRefreshKey.value += 1   // 触发 AssetVerifyReport 重 mount
    proposalRefreshKey.value += 1      // 触发 ProposalPanel 重 mount
    // Round 4 #27：allSettled，detail 失败也不影响 items 刷新；preserveOnError 保留旧 items
    await Promise.allSettled([
      refreshDetail(),
      loadItems({ preserveOnError: true }),
    ])
    // Round 5 #34：手动刷新后状态可能从终态↔running 切换，立即同步轮询决策
    syncPollingAfterLoad()
  } finally {
    manualRefreshing.value = false
  }
}

// ── Round 4 #25 + #28：统一刷新 + 轮询单 owner ────────────────────────
/**
 * 刷新整个详情页（detail + items）。
 * - onMounted / watch(batchRunId) 用默认行为（失败清空）
 * - handleManualRefresh 不走这里，自己 allSettled + preserveOnError
 */
async function reloadDetailPage(opts: { preserveItemsOnError?: boolean } = {}) {
  await Promise.all([
    refreshDetail(),
    loadItems({ preserveOnError: opts.preserveItemsOnError === true }),
  ])
}

/**
 * 轮询启动单 owner（Round 4 #28）。
 * - 页面加载 / 路由切换 / 手动刷新后由本函数统一决策
 * - 终态自动停轮询由 useBatchPolling 内部负责（无须外部 watch）
 */
function syncPollingAfterLoad() {
  if (isRunning.value) {
    startPolling({ immediate: false })
  } else {
    stopPolling()
  }
}

// ── Round 5 #35：retry / cancel 包装成页面级 handler ───────────────────
/**
 * 重跑失败执行项后，同步刷新 detail + items + ProposalPanel，并重新决策轮询
 * （不能直接绑 retryFailed，否则 items / Proposal 会停留旧数据）
 */
async function handleRetryFailed() {
  await retryFailed()
  await Promise.allSettled([
    refreshDetail(),
    loadItems({ preserveOnError: true }),
  ])
  proposalRefreshKey.value += 1   // Proposal 状态可能因 retry 变化
  syncPollingAfterLoad()
}

/** 取消批次后，同步刷新 + 决策轮询（终态） */
async function handleCancelBatch() {
  await cancelBatch()
  await Promise.allSettled([
    refreshDetail(),
    loadItems({ preserveOnError: true }),
  ])
  // Proposal 一般不受 cancel 影响，但 detail.status 已变终态，轮询必须立即停
  syncPollingAfterLoad()
}

// ── 生命周期 ─────────────────────────────────────────────────────────
onMounted(async () => {
  if (invalidId.value) return
  // Round 4 #26：拉 checkCodes 给 BatchItemTable 筛选下拉（不影响详情主体加载）
  void loadVerifyOptions()
  // Round 4 #25：mount 时同时 refreshDetail + loadItems，杜绝终态批次首次进入明细空
  await reloadDetailPage({ preserveItemsOnError: false })
  syncPollingAfterLoad()   // Round 4 #28：单 owner
})

// 路由切换：Round 3 #17 先 reset 再 refresh；Round 4 #25/#28 用统一函数
watch(
  () => props.batchRunId,
  async () => {
    stopPolling()
    pollError.value = ''
    resetDetail()
    resetItems()
    if (invalidId.value) return
    await reloadDetailPage({ preserveItemsOnError: false })
    syncPollingAfterLoad()
  },
)

// Round 4 #28：删除 watch(isRunning)。轮询启动单 owner 在 reloadDetailPage + syncPollingAfterLoad。
// 终态自停由 useBatchPolling 内部（isTerminalBatchStatus(getStatus()) 时 stopPolling）负责。

// composable 内部独享 onBeforeUnmount，此处不再注册
</script>

<template>
  <OpsPage>
    <OpsPageHeader
      :title="batchDetail?.batch_code || '批量校验详情'"
      :subtitle="subtitle"
      icon="analytics"
    >
      <template #actions>
        <button
          class="ops-secondary-button text-xs"
          :disabled="manualRefreshing || detailLoading"
          @click="handleManualRefresh"
        >
          <span class="material-symbols-outlined text-[16px]">refresh</span>
          刷新
        </button>
        <button class="ops-secondary-button text-xs" @click="router.push({ name: 'BatchVerify' })">
          返回列表
        </button>
      </template>
    </OpsPageHeader>

    <div
      v-if="showCreatedBanner"
      class="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200 flex items-center justify-between"
    >
      <span>{{ createdMessage }}</span>
      <button class="underline text-xs" @click="dismissCreatedBanner">关闭</button>
    </div>

    <OpsEmptyState v-if="invalidId" state="error" title="无效的批次 ID" />
    <OpsEmptyState
      v-else-if="detailLoading && !batchDetail"
      state="loading"
      title="正在加载批次详情"
    />
    <OpsEmptyState
      v-else-if="detailError && !batchDetail"
      state="error"
      title="加载失败"
      :description="detailError"
    />
    <template v-else-if="batchDetail">
      <BatchPollingAlert v-if="pollError" :message="pollError" @dismiss="pollError = ''" />
      <BatchSummaryCard :batch="batchDetail" />

      <!-- Round 3 #19：refreshKey 触发重 mount，确保「刷新」按钮语义覆盖全页面 -->
      <AssetVerifyReport
        :key="`asset-report-${batchRunIdRef}-${assetReportRefreshKey}`"
        :batch-run-id="batchDetail.id"
      />

      <OpsSectionCard title="分发明细" icon="send">
        <BatchDispatchTable :rows="batchDetail.dispatches || []" />
      </OpsSectionCard>

      <OpsSectionCard title="执行项明细" icon="fact_check">
        <BatchItemTable
          v-model:status="itemFilters.status"
          v-model:check-code="itemFilters.check_code"
          :rows="items"
          :loading="itemsLoading"
          :refreshing="itemsRefreshing"
          :selected-item-key="selectedItem?.item_key ?? null"
          :can-cancel="canCancelBatch(batchDetail.status)"
          <!-- Round 5 #36：按当前 items 实际出现的 check_code 派生；不传全量 checkCodeOptions -->
          :check-code-options="itemCheckCodeOptions"
          @select="selectItem"
          @reload="loadItems"
          @retry="handleRetryFailed"
          @cancel="handleCancelBatch"
        />
      </OpsSectionCard>

      <VerifyItemDetail :item="selectedItemForDetail" />
      <ProposalPanel
        :key="`proposal-${batchRunIdRef}-${proposalRefreshKey}`"
        :batch-run-id="batchDetail.id"
      />
    </template>
  </OpsPage>
</template>
```

- **要点**（Round 2 + Round 3 + Round 4 全部修订）：
  - **`batchRunIdRef`** computed 把 props 转成 `Ref<number \| null>`，三个 composable 共享，组件复用时自动跟随
  - **`onMounted(async ...)`** 唯一入口，避免 setup 顶层 async
  - **`startPolling({ immediate: false })`** 默认不立即 tick，杜绝 mount 后双 fetch
  - **`onBeforeUnmount` 不在详情页注册**，完全交给 composable 内部
  - **`canCancelBatch` / `isTerminalBatchStatus`** 从 utils 导入，不在页面内临时定义
  - **`isRunning` null-safe**：必须有状态且非终态才算 running（修订 #16）
  - **路由切换 watch** 先 `stopPolling` + `pollError=''` + `resetDetail()` + `resetItems()` 再 `reloadDetailPage` + `syncPollingAfterLoad`（修订 #17 + #25 + #28）
  - **`@created` query 透传**：列表页跳详情时附 `query.created=1&code=&dispatches=`，详情页顶部绿色成功条 + 「关闭」按钮
  - **`dismissCreatedBanner` 选择性删 query**（修订 #24）：只删 created/code/dispatches，保留其它
  - **顶部「刷新」刷新整个详情页**（修订 #19 + #27）：`assetReportRefreshKey` / `proposalRefreshKey` 触发 `:key` 重建 + `Promise.allSettled([refreshDetail, loadItems({ preserveOnError: true })])`
  - **`v-model:status` / `v-model:check-code`** + **`:selected-item-key` 用 item_key**（修订 #20）
  - **`reloadDetailPage()` 统一函数（Round 4 #25）**：`Promise.all([refreshDetail, loadItems])`，mount / 路由切换统一入口，杜绝"详情页首屏 items 不加载"
  - **`syncPollingAfterLoad()` 单 owner（Round 4 #28）**：删除 `watch(isRunning)`，轮询启动由本函数统一决策；终态自停由 `useBatchPolling` 内部负责
  - **`useBatchVerifyOptions` 注入 checkCodes（Round 4 #26）**：`BatchItemTable.checkCodeOptions` 由详情页 `onMounted(loadVerifyOptions)` 异步注入；不阻塞主体加载（`void loadVerifyOptions()`）
  - **`firstQueryValue` 统一 query 取值（Round 4 #32）**：`createdMessage` 走 helper 避免 `string | string[] | null` 类型分支
  - **`isTerminalBatchStatus` 类型收口（Round 4 #31）**：NewType brand set 的 `as never` 转换集中在 helper 内部，页面拿 `boolean` 不接触类型问题
  - **`useBatchPolling` 返回 `isPolling`（Round 4 #29）**：与详情页派生的"批次是否运行中"`isRunning` 不冲突；调用方目前不消费此字段，仅为诊断
  - **Tab 决策确认**：本次**不做 Tab**，纵向堆叠 6 个 Section

### Task 5：清理

- **Action**（按 Round 2 修订 #10 修订）：
  - **删除** `frontend/src/views/ops/BatchVerify.vue`（删除前必须已通过 Task 0.1 的 grep 校验 + `bash scripts/ai/verify.sh`）
  - **删除** `OpsSectionCard v-if="false"`（来自旧 `BatchVerify.vue:362-366,370-372` 的两个逃生口占位）—— Phase 2d 已经稳定
  - 确认 `batch-verify-page-refactor-input-2026-06-18.md` § 10 退化点全部修复：行点击统一化、`selectedItemForDetail` 移到 composable、`pollError`/`launchError` 区域由 ListPage/DetailPage 各自负责
  - **删除顺序**（Round 2 决策项 #6）：
    1. 先完成 Task 1–4（新文件 + 路由切换）
    2. 跑 `vue-tsc --noEmit` + `bash scripts/ai/verify.sh` 全绿
    3. 手动 e2e（Task 6 列表）跑通
    4. **最后**删除旧 `BatchVerify.vue`，单独一个 commit，便于回滚
- **Mirror**：目录化风格，与本视图目标一致。**删除** Round 1 草稿中"Mirror: Tasks.vue 单文件"的矛盾行。
- **Validate**：
  ```bash
  grep -RIn "views/ops/BatchVerify\.vue\|@/views/ops/BatchVerify" frontend/src
  # 预期：0 行
  bash scripts/ai/verify.sh
  # 预期：通过
  ```

### Task 6：验证

按下面 Validation 章节全量执行。

---

## Validation

```bash
# 1) 类型 + 构建
cd frontend
npx vue-tsc --noEmit

# 2) 项目统一入口
cd ..
bash scripts/ai/verify.sh

# 3) 旧文件唯一引用校验（Task 0.1 → Task 5）
grep -RIn "views/ops/BatchVerify\.vue\|@/views/ops/BatchVerify" frontend/src

# 4) onBeforeUnmount 注册次数校验
grep -RIn "onBeforeUnmount" frontend/src/views/ops/batch-verify/
# 预期：composables/useBatchPolling.ts 1 处；详情页 0 处

# 5) 手动 e2e（开发环境：http://localhost:5174）
# 5a) 列表页：打开 /ops/batch-verify
#     - 不创建直接刷新 → 列表为空态
#     - 创建一批 → 跳到详情页（URL 含 ?created=1）
#     - 详情页顶部出现绿色成功条 "批量任务已创建：xxx，N 个分发"
#     - 点击「关闭」按钮 → 成功条消失，URL query 清除
#     - 后退到列表页 → 新批次出现在顶部
# 5b) 详情页：
#     - URL /ops/batch-verify/1 → 加载批次 1
#     - 批次 running 时 5s 轮询，network 面板可见 GET /batch-runs/1 每 5s 一次
#     - **mount 后立即 1 次 detail fetch + 1 次 items fetch**（Round 5 #38 改口径），无立即 polling tick
#     - 批次终态时停止轮询
#     - 触发后端 500 → 黄色 pollError 条出现，轮询继续，items 表不清空
#     - 切换 target_scope 时 check_codes 清空
#     - 选中 skipped item → VerifyItemDetail 显示 skip_reason
#     - PORT_CANDIDATE_CONFLICT proposal → 单条/批量 apply 前必须选端口
#     - 终态后手动「刷新」按钮 → 拉取最新数据
#     - **Round 4 #25**：mount 后立即出现 detail + items 两条并行 fetch（终态批次也有 items）
#     - **Round 4 #26**：打开详情页 ≤2s 后 BatchItemTable 的 check_code 筛选下拉出现所有 enabled 检查项
#     - **Round 4 #27**：点顶部「刷新」按钮出现 detail + items 两条 fetch，items 不空闪烁
#     - **Round 4 #28**：running 批次 mount 后只有 1 次 detail fetch + 1 次 items fetch，后续每 5s 才出现 tick，**无重复启动**
# 5c) 跨页 / 路由复用：
#     - 在详情页点「返回列表」→ 回到 /ops/batch-verify
#     - 直接刷新详情页 URL → 重新加载该批次
#     - 详情页 URL /ops/batch-verify/1 → 改地址栏到 /ops/batch-verify/2 → 数据切换，无 stale
#     - 不存在的 ID（如 /ops/batch-verify/999999）→ OpsEmptyState error
#     - 无效 ID（/ops/batch-verify/abc、/-1）→ OpsEmptyState error "无效的批次 ID"，无 API 调用
# 5d) Round 4 验收补充：
#     - 手动构造 URL /ops/batch-verify/2?created=1&code=test&dispatches=5 → 顶部成功条显示 "批量任务已创建：test，5 个分发"
#     - 构造 /ops/batch-verify/2?code=a&code=b（重复键，Vue Router 解析为数组）→ 不渲染 "[object Object]"
#     - DevTools Network：grep `isRunning` 在 `useBatchPolling` 公开类型中应 0 命中（已改名 `isPolling`）
```

回归点检查清单：

- [ ] 创建成功后跳转到详情页 + 顶部绿色成功条显示 `批量任务已创建：{batch_code}，{N} 个分发`
- [ ] 行点击 / 「详情」按钮跳转到 `/ops/batch-verify/:batchRunId`
- [ ] 详情页刷新可由 URL 还原（包括深链 `/ops/batch-verify/2` 直接刷新）
- [ ] **详情页 mount 后触发 1 次 detail fetch + 1 次 items fetch**（Round 5 #38 改口径），network 面板验证 mount 后立即出现 2 个并行请求 + **无额外 polling tick**；后续 running 批次每 5s 才进入轮询 tick
- [ ] 5s 轮询 + AbortController（仅 batch detail / batch list 请求）+ 错误可见 + 终态停，**全部行为不变**
- [ ] `target_scope` 切换清空 `check_codes`
- [ ] `Proposals` 严格按 `batch_run_id` 隔离
- [ ] `PORT_CANDIDATE_CONFLICT` 必须人工选端口（单条/批量）
- [ ] `skipped` item 继续展示 `raw_result.skip_reason`（fallback `CALLBACK_RESULT_MISSING`）
- [ ] `cancelBatch` 文案（`window.confirm`）、`canCancelBatch` 谓词不变
- [ ] `formatTime` / `formatDuration` 仍走 `@/utils/timezone`，未自行实现
- [ ] **终态后手动「刷新」按钮可拉取最新数据**（不再受 5s 轮询限制）
- [ ] **轮询失败时 `items` 表不空**（`loadItems({ preserveOnError: true })` 生效）
- [ ] **`/ops/batch-verify/1 → /ops/batch-verify/2` 路由切换**：组件复用，详情立即刷新，无 stale 旧数据
- [ ] **无效 ID**（`/ops/batch-verify/abc` / `/ops/batch-verify/-1`）：详情页 `OpsEmptyState state="error" title="无效的批次 ID"`，无 API 调用
- [ ] **`useBatchPolling` 的 `onBeforeUnmount` 仅在 composable 内部注册一次**（grep 验证）
- [ ] **详情页 mount 后 `refreshDetail` + `loadItems` 同 fetch**（Round 4 #25）：network 面板验证 mount 后立即出现 2 个并行请求（detail + items），不再等 5s 才有 items
- [ ] **`BatchItemTable` 检查项筛选下拉有数据**（Round 4 #26）：打开 `/ops/batch-verify/2` 后等 ≤2s，下拉至少出现所有 `is_enabled=true` 的检查项
- [ ] **顶部「刷新」同时刷新 detail + items**（Round 4 #27）：勾选一个执行项后点刷新，network 面板验证出现 `GET /batch-runs/:id` + `GET /batch-runs/:id/items` 两个请求，items 表格无空闪烁
- [ ] **轮询启动单 owner**（Round 4 #28）：进入详情页（running 批次）后 network 面板只有 1 次 mount fetch + 每 5s 一次 tick，**无重复启动**；终态后 network 面板无新请求
- [ ] **`useBatchPolling` 返回 `isPolling` 而非 `isRunning`**（Round 4 #29）：grep `useBatchPolling` 公开 API 不含 `isRunning` 字段名
- [ ] **`route.query` 取值容错**（Round 4 #32）：手动构造 `/ops/batch-verify/2?created=1&code=test&dispatches=5`，成功条正常渲染；构造 `/ops/batch-verify/2?code=a&code=b`（数组）不渲染 "[object Object]"

## Risks

| 风险 | 等级 | 缓解 |
|---|---|---|
| 详情页 `watch(batchRunId)` 时旧轮询未停，导致双重 tick | High | `BatchVerifyDetail.vue` 中显式 `stopPolling()` 后再 `loadBatchDetail()`；`useBatchPolling.startPolling()` 内部也调用 `stopPolling()` 先重置，互为保险；`startPolling({ immediate: false })` 杜绝 mount 后双 fetch |
| **Vue 组件复用：`/ops/batch-verify/1 → /ops/batch-verify/2` 不会重建组件实例**，`props.batchRunId` 变但 composable 内部仍用旧 id | High | composable 全部接 `Ref<number \| null>`，每次请求前 `unref()` 取最新；`batchRunIdRef = computed(() => props.batchRunId)` 作为单一来源 |
| `assetsApi.listBatchItems` 第三个参数**不支持 `signal`**，轮询 tick 内 `loadItems` 的 abort 实际不生效 | Medium | composable 内部**忽略** `signal` 参数（旧行为即如此）；`useBatchPolling.onTick` 的 `signal` 仅用于 `getBatchRun` / `listBatchRuns`；PR review 时显式说明此限制 |
| `assetsApi.getAssetReport`（在 `AssetVerifyReport.vue` 内）不支持 `signal` | Low | 该组件独立维护自己的 `AbortController` 不切实际，**沿用现状**；重构不引入新问题 |
| `selectedItem` 在 `loadItems` 成功后选中第一条，旧选中若已不存在会丢上下文 | Medium | 沿用 `BatchVerify.vue:735-740` 的 "保留旧选中若仍存在" 逻辑；不修改 |
| 详情页直接刷新时 `batchDetail` 为 `null`，轮询不该启动 | Medium | `useBatchPolling.startPolling()` 在 `isTerminal(null)` 时直接 return；`watch(isRunning, ...)` 不会因 null 触发启动 |
| `route.params.batchRunId` 为字符串，`Number()` 转失败为 `NaN` | Medium | `BatchVerifyDetail.vue` 顶部 `invalidId` computed 拦截；不进入数据加载 |
| `AssetVerifyReport` / `ProposalPanel` / `VerifyItemDetail` props 契约被无意修改 | Low | Plan 明确"不动"列表；reviewer 在 PR 中验证 props 签名 |
| `OpsSectionCard v-if="false"` 占位删除后旧调用方残留 | Low | 旧文件整段删除，不存在残留 |
| **轮询失败时 `loadItems` 清空执行项表格** | Medium | `loadItems({ preserveOnError: true })` 选项，轮询场景不破坏现有数据；用户主动筛选走默认行为 |
| 跨页跳转后**成功提示条丢失**（用户跳走看不到） | Medium | 通过 `query.created=1` 在详情页展示成功条；点击「关闭」或下次刷新后消失 |
| 端口冲突弹窗（PORT_CANDIDATE_CONFLICT）跨页保留 `selectedForConflict` 状态 | Low | 状态在 `ProposalPanel` 内部 ref 中，路由切换组件销毁即丢失；当前行为一致，不需保留 |
| `verify.sh` 跑 vue-tsc 时出现死代码（如未使用的 `canCancelBatch`） | Medium | `canCancelBatch` / `isTerminalBatchStatus` 已在 utils 中导出且被详情页引用；reviewer 关注 unused-import |
| `useBatchPolling` 内 `onBeforeUnmount` 与调用方重复注册 | Low（已修订） | composable 内部独享；详情页不再注册 `onBeforeUnmount` |
| `BatchCreateCard` emit 类型契约不一致（`number` vs `BatchRunCreateResponse`） | Low（已修订） | `defineEmits<{ created: [BatchRunCreateResponse]; error: [string] }>()` 强类型；父组件 `handleCreated(result)` 显式解构 |
| `BatchItemTable` 通过 `:filters` prop 直接修改 | Low（已修订） | 改用 `v-model:status` / `v-model:check-code`；子组件用 `defineModel` |
| 旧 `BatchVerify.vue` 在 router 之外被引用（菜单 / 权限 / 静态资源） | Medium | Task 0.1 grep 提前校验，发现即处理 |
| **`isRunning` null 不安全**：`undefined.status` 时 `isTerminal === false` 导致 `isRunning = true` 误启动轮询（Round 3 #16） | High | `isTerminalBatchStatus` 自身 null/空字符串短路返回 `false`；`isRunning` 计算加 `!!status` 前置守卫 |
| **路由切换 `/1 → /2` 旧响应覆盖新数据**（Round 3 #17） | High | composable 内部 `requestSeq` 单调递增 + `batchRunId !== unref(batchRunIdRef)` 双保险；详情页 watch 时 `reset()` 清空 + `requestSeq++` |
| **`setInterval` 并发 tick**（Round 3 #18）：接口耗时 > 5s 时叠加多个未完成的请求 | Medium | `useBatchPolling` 改用递归 `setTimeout`：tick 完成（含 await）后才排下一轮 |
| **顶部「刷新」只刷新摘要，不刷新下面 section**（Round 3 #19）：用户期望刷新整个详情页 | Medium | `assetReportRefreshKey` / `proposalRefreshKey` 触发 `:key` 重建，确保 `AssetVerifyReport` / `ProposalPanel` 一起 reload |
| **执行项选中用 `id` 不稳定**（Round 3 #20） | Low | 改用 `item_key` 作选中主键（语义稳定 + 与表格主列一致） |
| **`BatchCreateCard` 错误重复展示**（Round 3 #21）：子组件内部 + 父页面 errorBanner 同时出现 | Low | 删 `error` emit；表单校验 + 接口错误全部在子组件内部 |
| **`dismissCreatedBanner` 误删其它 query**（Round 3 #24） | Low | 只删 created/code/dispatches 三个键，保留其它 |
| **详情页 `onMounted` 漏 `loadItems`**（Round 4 #25）：终态批次首屏明细不加载，running 批次等 5s 后才有 items | High | 新增 `reloadDetailPage()` 统一函数，`onMounted` / `watch(batchRunId)` / `handleManualRefresh` 三处统一入口 |
| **`BatchItemTable` 检查项筛选下拉数据缺失**（Round 4 #26）：plan 未明确 `check_codes` 来源，子组件无 API 调用契约 | High | 新增 `useBatchVerifyOptions` composable（5 号 composable），列表页 + 详情页共用；`BatchItemTable` 接收 `checkCodeOptions` prop，由父组件注入 |
| **顶部「刷新」漏 items**（Round 4 #27）：只刷新 detail / asset report / proposal panel，items + `selectedItemForDetail` 不动 | Medium | `handleManualRefresh` 改为 `Promise.allSettled([refreshDetail, loadItems({ preserveOnError: true })])`，任一失败不影响另一；`loadItems` 失败保留旧数据 |
| **轮询双 owner 重复触发**（Round 4 #28）：`onMounted` + `watch(batchRunId)` + `watch(isRunning)` + `useBatchPolling` 内部终态自停 4 个入口互相覆盖 | Medium | 删除 `watch(isRunning)`，封装 `syncPollingAfterLoad()` helper，由页面加载流程单 owner 决定启停；终态自停仍由 `useBatchPolling` 内部负责 |
| **`useBatchPolling.isRunning` 命名冲突**（Round 4 #29）：与详情页派生的"批次是否运行中"`isRunning` 同名易误用 | Low | 改名 `isPolling`（轮询器是否运行中）；调用方目前不消费，仅为诊断保留 |
| **`item_key` 在 batch 内不唯一**（Round 4 待 confirm） | Medium | 实施前验证 `backend/app/models/batch_run.py`；不唯一则降级为 `${dispatch_run_id}::${item_key}` 组合 key |
| **NewType brand set TS 类型错误**（Round 4 #31）：`TERMINAL_BATCH_STATUS_SET.has(status.toLowerCase())` 过不了 `vue-tsc` | Low | `isTerminalBatchStatus` helper 内部 `as never` 集中收口；调用方拿 `boolean` 不接触类型 |
| **`route.query.code` 类型分支散落**（Round 4 #32）：直接 `route.query.code` 拿到 `string \| string[] \| null` 可能渲染 "[object Object]" | Low | 新增 `firstQueryValue(value: unknown): string` helper；`createdMessage` 走 helper |
| **`BatchCreateCard` 缺 options props 编译失败**（Round 5 #33）：Round 4 加的 4 个 props 没在列表页示例透传 | High | Task 4.2 重写示例代码：`useBatchVerifyOptions` 实例化 + 4 个 props 透传 |
| **手动刷新后轮询状态延迟纠正**（Round 5 #34）：用户手动刷新从终态↔running 切换后，轮询要等下一轮 tick 才反映 | Medium | `handleManualRefresh` 末尾 `syncPollingAfterLoad()`，与 mount / watch(batchRunId) 同一单 owner |
| **retry / cancel 后停留旧数据**（Round 5 #35）：只 `loadBatchDetail({ silent: true })`，items / Proposal / VerifyItemDetail 旧 | Medium | 包装 `handleRetryFailed` / `handleCancelBatch`：detail + items + proposalRefreshKey + syncPollingAfterLoad |
| **筛选下拉混入其它批次范围检查项**（Round 5 #36）：全量 `checkCodes` 传给 BatchItemTable，server 类型出现在 db_instance 批次 | Low | `itemCheckCodeOptions` 按当前 items 实际 check_code 派生；备选 `scopedCheckCodeOptions`（target_scope）保留 |
| **`useBatchPolling.isPolling` 未维护**（Round 5 #37）：rename 后无 start/stop 同步 | Low | `isPolling.value = true/false` 在 start/stop 内显式更新；tick `finally` 清旧 controller 引用 |
| **`item_key` batch 内不唯一**（Round 5 现场确认 1） | Medium | 实施前 grep `backend/app/models`；不唯一则降级为 `${dispatch_run_id}::${item_key}` 组合 key |
| **`listDbTypes()` 字段不匹配**（Round 5 现场确认 2）：plan 假设 `{ code, name }`，可能为 `db_type_code`/`db_type_name` | Low | 实施前 grep `frontend/src`；不同时在 `useBatchVerifyOptions` 内部 map 标准化 |
| **`createBatchRun` 字段不匹配**（Round 5 现场确认 3）：plan 假设返回 `batch_run_id`，可能为 `id` | Low | 实施前 grep `backend/app`；不同时 `BatchVerifyList.handleCreated` 与 `types/api.ts` 同步调整 |

## Acceptance

- [ ] `frontend/src/views/ops/BatchVerify.vue` 已删除
- [ ] `frontend/src/views/ops/batch-verify/` 包含 2 个页面 + 6 个子组件 + 5 个 composables（新增 `useBatchVerifyOptions`，Round 4）+ 1 个 utils（含 `firstQueryValue` + `as never` 类型收口，Round 4）
- [ ] `frontend/src/router/index.ts` 注册两条路由（list + detail）
- [ ] `vue-tsc --noEmit` 通过
- [ ] `bash scripts/ai/verify.sh` 通过
- [ ] 全部回归点检查清单通过
- [ ] PR 评审通过；`verify-check-optimization-followup-2026-06-18.plan.md` 中的"4 Critical + 11 Important"成果未回归（轮询可见错误、AbortController、PORT_CANDIDATE_CONFLICT 校验、target_scope 清空、proposals 跨批隔离等）
- [ ] 不引入第三方表格 / UI 组件库（继续原生 `<table>` + Tailwind + 现有 ops/ 组件）

## Out of Scope（本次不做）

- `/ops/batch-verify/:batchRunId/items/:itemId` 单独执行项详情页
- 详情页 Tab 化（沿用纵向堆叠）
- 列表页自动轮询（仅手动刷新按钮）
- 详情页"自动刷新"开关 / 失败重跑 / 批次取消的快捷键
- `BatchCreateCard` 表单字段拆 sub-component（保留单文件）
- 状态徽章 / 时间格式化抽出到全局 `composables/useStatusFormatters.ts`（仅本视图内 `utils/batchVerifyFormatters.ts`，避免全局泛化过早）
- `window.confirm` → `OpsConfirmDialog` 升级（产品决策：本次 0 行为改动）

## Product Decisions Confirmed（Round 2 + Round 3 + Round 4 决策项闭环）

| 决策项 | 选择 | 备注 |
|---|---|---|
| 路由 path 风格 | 子路由相对 path（无前导 `/`） | 现有 `router/index.ts` 全为子路由风格，**继续无前导 `/`** |
| 创建成功后是否跳详情页 | **跳详情页** | 配合 `query.created=1` 在详情页顶部展示成功条 |
| 取消确认框 | **`window.confirm`（沿用旧）** | 本次 0 行为改动；统一 UI 留待下一轮 |
| 详情页 Tab | **不做** | 沿用纵向堆叠 6 个 Section |
| 列表页轮询 | **不轮询**，仅手动「刷新」按钮 | 沿用旧行为 + 减少复杂度 |
| 顶部「刷新」范围 | **刷新整个详情页**（Round 3 决定） | `AssetVerifyReport` / `ProposalPanel` 通过 `:key` 重建 + Round 4 追加 `loadItems({ preserveOnError: true })` |
| 执行项选中主键 | **`item_key`**（Round 3 决定） | 语义稳定 + 与表格主列一致；Round 4 待 confirm batch 内唯一性 |
| 创建失败错误展示位置 | **`BatchCreateCard` 内部**（Round 3 决定） | 表单校验 + 接口错误均不外泄给父组件 |
| `?created=1` 分享 URL 是否会带成功条 | **可接受**（Round 4 维持） | 不增加"只显示一次"逻辑；手动关闭即可 |
| 详情页首次加载是否同时拉 items | **同时拉**（Round 4 #25 决定） | 统一通过 `reloadDetailPage()`，杜绝终态批次首屏 items 空 |
| 轮询启动 owner | **页面加载流程单 owner**（Round 4 #28 决定） | 删除 `watch(isRunning)`；终态自停仍由 `useBatchPolling` 内部负责 |
| `BatchItemTable` 检查项筛选下拉来源 | **`useBatchVerifyOptions` 共用 composable**（Round 4 #26 决定） | 列表页 + 详情页复用，避免重复接口调用 |
| `BatchItemTable.checkCodeOptions` 派生方式 | **按当前 items 实际 check_code 派生**（Round 5 #36 决定） | `itemCheckCodeOptions`：永远筛出非空结果；备选 `scopedCheckCodeOptions`（按 `target_scope`）保留在 utils |
| retry / cancel 后是否同步刷新 | **页面级 handler 同步刷新 detail + items + ProposalPanel**（Round 5 #35 决定） | 不能直接绑 composable 原始 `retryFailed` / `cancelBatch`，避免停留旧数据 |
| 手动刷新后是否重新同步轮询 | **是，立即 `syncPollingAfterLoad()`**（Round 5 #34 决定） | 单 owner：mount / watch(batchRunId) / handleManualRefresh / handleRetryFailed / handleCancelBatch 五处统一走 `syncPollingAfterLoad()` |
| `useBatchVerifyOptions` 是否模块级 cache | **不加 cache**（Round 5 小建议） | 保持简单；options 接口轻量，列表 + 详情各拉一次可接受 |