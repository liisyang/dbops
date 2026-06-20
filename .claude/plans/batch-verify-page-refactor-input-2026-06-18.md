# 📋 `/ops/batch-verify` 重构设计输入文档

> **页面 URL**：`/ops/batch-verify`（前端 Vite 工程内对应路由 `name: 'BatchVerify'`）
> **Vue 文件**：`frontend/src/views/ops/BatchVerify.vue`（主页面，~793 行）
> **页面标题**：批量校验
> **页面副标题**：选择资产范围和检查项，统一调度 AWX 批量执行
> **页面 icon**：`checklist`
> **功能定位**：管理员选择资产范围与检查项 → 调用后端创建 batch run → 后端 AWX 调度执行 → 前端轮询查看结果 → 处理变更建议（proposals）

---

## 1. 路由与导航

| 路径 | 路由名 | 组件 | 懒加载 |
|---|---|---|---|
| `ops/batch-verify` | `BatchVerify` | `@/views/ops/BatchVerify.vue` | `() => import(...)` |

依赖的公共壳组件（`@/components/ops/`）：
- `OpsPage` / `OpsPageHeader` / `OpsSectionCard` / `OpsTableShell` / `OpsEmptyState` / `OpsModal`

---

## 2. 页面分块（自上而下 6 个 Section）

```
┌─ Section 1: 新建批量任务 (Create Section)
├─ Section 2: 批量任务列表 (Batch Runs List)
├─ Section 3: 结果摘要 (Results Summary)           ← 仅在选中某 batch 后显示
├─ Section 4: 资产维度报告 <AssetVerifyReport>
├─ Section 5: 分发明细 (Dispatches)
└─ Section 6: 执行项明细 (Items)
  ├─ <VerifyItemDetail>（执行项详情，单独 SectionCard）
  └─ <ProposalPanel>（变更建议，单独 SectionCard）
```

---

## 3. 各 Section 详细字段与行为

### 3.1 新建批量任务（Section 1）

**容器**：`OpsSectionCard title="新建批量任务"`，下方一个垂直 `space-y-4` 容器。

| 字段 | 类型 | 默认值 | 必填 | 说明 |
|---|---|---|---|---|
| `target_scope` | radio：`db_instance` / `server` | `db_instance` | ✅ | 目标范围。切换时清空已选 `check_codes` |
| `selectionMode` | radio：`ids` / `filters` | `ids` | ✅ | 资产选择模式 |
| `assetIdsInput` | string | `''` | ids 模式必填 | 按逗号分隔的资产 ID，提交时 `parseInt`+`filter(!isNaN)` |
| `filters.db_type_code` | select | `''` | filters 模式可选 | 来自 `GET /v1/collector/db-types` |
| `filters.status` | select：`active`/`inactive` | `''` | filters 模式可选 | |
| `filters.site_id` | number | `null` | filters 模式可选 | 站点 ID |
| `check_codes` | 多选 checkbox | `[]` | ✅（提交时至少 1 个） | 来源：`GET /v1/collector/check-codes?is_enabled=true`，前端按 `target_scope` 客户端 filter |
| `timeout_seconds` | number | `3` | 否 | 1–60 |
| `max_items_per_dispatch` | number | `100` | 否 | 1–500 |
| `include_related_server` | checkbox | `true` | 否 | 包含关联服务器 |
| 启动按钮 | button | — | — | `ops-primary-button`，icon `rocket_launch` / `hourglass_empty` |
| `launchMessage` | 成功提示条 | — | — | 绿色（emerald） |
| `launchError` | 失败提示条 | — | — | 红色 |
| `pollError` | 轮询错误条 | — | — | 黄色（amber），可关闭 |

**提交 payload**（`POST /v1/collector/batch-runs`）：
```ts
{
  target_scope: 'db_instance' | 'server',
  check_codes: string[],
  timeout_seconds: number,
  max_items_per_dispatch: number,
  include_related_server: boolean,
  // 二选一：
  asset_ids?: number[],            // selectionMode === 'ids'
  filters?: {                       // selectionMode === 'filters'
    db_type_code?: string,
    status?: string,
    site_id?: number,
  }
}
```

**提交后行为**：
1. 显示 `launchMessage`：`批量任务已创建：${batch_code}，${dispatch_count} 个分发`
2. 清空 `assetIdsInput` 与 `form.check_codes`
3. 重新 `loadBatches()`
4. `selectedBatchId = result.batch_run_id`
5. `loadBatchDetail(result.batch_run_id)`

---

### 3.2 批量任务列表（Section 2）

**容器**：`OpsSectionCard title="批量任务列表"`
**数据源**：`GET /v1/collector/batch-runs?limit=20`（`assetsApi.listBatchRuns`）

**表格列**（12 列）：

| 列 | 字段 | 样式 | 备注 |
|---|---|---|---|
| 批次编号 | `batch.batch_code` | `font-mono text-xs` | |
| 类型 | `batch.run_type` | | |
| 范围 | `batch.target_scope` | | |
| 状态 | `batch.status` | 状态徽章（`getStatusBadgeClass` + `formatStatusLabel`） | 9 种状态 |
| 资产数 | `batch.total_asset_count` | | |
| 总 item | `batch.total_item_count` | | |
| 成功 | `batch.success_item_count` | `text-emerald-400` | |
| 失败 | `batch.failed_item_count` | `text-red-400` | |
| 分发数 | `batch.dispatch_count` | | |
| 创建时间 | `batch.created_at` | `text-xs text-on-surface-variant`，`formatTime`（统一时区） | |
| 耗时 | `started_at` → `finished_at` | `formatDuration` | |
| 操作 | 按钮「详情」 | `text-primary` | `.stop` 阻止行点击 |

**行交互**：整行点击 → 选中并加载详情（`selectedBatchId = batch.id; loadBatchDetail(batch.id)`）
**空态**：`OpsEmptyState state="empty" title="暂无批量任务" description="请在上方创建"`

#### 状态徽章全集（9 种 batch/dispatch 状态）

| 英文 | 中文 | 颜色 |
|---|---|---|
| `pending` | 等待中 | amber |
| `launched` / `launching` | 启动中 | sky |
| `running` / `dispatching` | 执行中 | sky |
| `success` | 已完成 | emerald |
| `partial_success` | 部分成功 | amber |
| `failed` | 失败 | red |
| `cancelled` / `canceled` | 已取消 | slate |
| 其它 | 原样回显 | outline |

**已取消的特殊行为**：cancelled dispatch 旁显示 `cancelled_at` 时间戳（`font-mono text-[10px] text-slate-400`），用 `isCancelled()` 谓词同时匹配 UK/US 拼写。

---

### 3.3 结果摘要（Section 3，详情卡片）

**容器**：`OpsSectionCard title="结果摘要" icon="analytics"`
**触发条件**：`batchDetail != null`（即选中了某个 batch）

**栅格**：7 个 `field-card text-center`（响应式 `sm:grid-cols-7`）

| 指标 | 字段 | 样式 |
|---|---|---|
| 总资产数 | `batchDetail.total_asset_count` | `text-2xl font-bold` |
| 总检查项 | `batchDetail.total_item_count` | 同上 |
| 成功 | `batchDetail.success_item_count` | `text-emerald-400` |
| 失败 | `batchDetail.failed_item_count` | `text-red-400` |
| 成功率 | `Math.round(success/total*100)%` | 颜色按区间：≥90 emerald / ≥50 amber / 否则 red |
| 跳过（条件显示） | `batchDetail.skipped_item_count` | `text-slate-300`，仅 `>0` 显示 |
| 总耗时 | `formatDuration(started_at, finished_at)` | `font-mono` |

**跳过提示条**（条件渲染）：若 `skipped_item_count > 0`，显示琥珀色提示 `本批次有 N 项被跳过，常见原因是目标类型未绑定可用凭证，或该项不适用当前批次。`

---

### 3.4 资产维度报告（Section 4）`<AssetVerifyReport>`

**子组件文件**：`frontend/src/components/ops/AssetVerifyReport.vue`
**Props**：`batchRunId: number | null`
**数据源**：`GET /v1/collector/batch-runs/{batchRunId}/asset-report`
**行为**：watch + onMounted 自动 load；提供"刷新"按钮

**表格列**：

| 列 | 字段 | 样式 |
|---|---|---|
| 实体 | `${entity_type}#${entity_id}` + 副行 `entity_name` | `font-mono text-xs` |
| IP | `ip_address` | `font-mono text-xs` |
| DB 端口 | `db_port_status` | 徽章（badge） |
| OS 端口 | `os_port_status` | 徽章 |
| 事实采集 | `fact_status` | 徽章 |
| Facts | `fact_count` | `font-mono text-xs text-right` |
| 错误 | `error_messages[]` | `text-error`，多条用 `<ul>` 列出；空时显示 `-` |

**空/错/加载态**：分别用 `OpsEmptyState state="loading" / "error" / "empty"`。

**返回数据 shape**：
```ts
{
  batch_run_id, batch_code,
  assets: [{
    entity_type, entity_id, entity_name, ip_address,
    db_port_status, os_port_status, fact_status,
    fact_count, error_messages: string[],
    items: Array<Record<string, unknown>>,
    cluster_type_suspected?: Record<string, unknown> | null
  }]
}
```

---

### 3.5 分发明细（Section 5）

**容器**：`OpsSectionCard title="分发明细" icon="send"`
**数据源**：`batchDetail.dispatches`（已嵌入 batch 详情响应中，无需单独请求）

**表格列**（9 列）：

| 列 | 字段 | 备注 |
|---|---|---|
| 分发编号 | `d.dispatch_code` | `font-mono text-xs`，缺省 `-` |
| 网段 | `d.network_zone` | 缺省 `-` |
| 实例组 | `d.awx_instance_group` | 缺省 `-` |
| 状态 | `d.status` | 徽章 + cancelled 时附带 `cancelled_at` |
| Items | `d.item_count` | |
| 成功 | `d.success_item_count` | `text-emerald-400` |
| 失败 | `d.failed_item_count` | `text-red-400` |
| AWX Job | `d.awx_job_id` | `font-mono text-xs`，缺省 `-` |
| 耗时 | `formatDuration(d.launched_at, d.finished_at)` | `font-mono text-xs` |

**空态**：`OpsEmptyState state="empty" title="暂无分发明细"`

---

### 3.6 执行项明细（Section 6）

**容器**：`OpsSectionCard title="执行项明细" icon="fact_check"`
**数据源**：`GET /v1/collector/batch-runs/{id}/items?status=&check_code=`（`assetsApi.listBatchItems`）

**筛选条**（`mb-4 flex flex-wrap items-center gap-3`）：

| 控件 | 类型 | 选项 | 触发 |
|---|---|---|---|
| 状态下拉 | select | 全部 / `success` / `failed` / `pending` / `running` | `@change="loadItems"` |
| 检查项下拉 | select | 全部 / `checkCodeOptions` 各 value | `@change="loadItems"` |
| 重跑失败项 | 文字按钮 | — | `retryFailed()` |
| 取消批次 | 文字按钮（红色） | 仅当 `canCancelBatch(status)` 为真（status ∈ `pending` / `dispatching` / `running`） | `cancelBatch()`（带 `window.confirm`） |

**表格列**（8 列）：

| 列 | 字段 | 样式 | 备注 |
|---|---|---|---|
| Item Key | `item.item_key` | `font-mono text-xs max-w-[200px] truncate`，`title` 完整文本 | |
| 检查项 | `item.check_code` | | |
| 目标 | `${item.target_host}:${item.target_port}` | | |
| 状态 | `item.status` | item 状态徽章（5 种） | |
| 结果 | `formatItemResult(item)` | | 见下 |
| 事实数 | `getItemFactsCount(item)` | | `raw_result.facts.length` |
| 消息 | `formatItemMessage(item)` | `text-xs max-w-[200px] truncate` | |
| 操作 | 「详情」按钮 | 触发 `selectItem(item)` | |

**Item 状态徽章**：

| 英文 | 中文 | 颜色 |
|---|---|---|
| `success` | 成功 | emerald |
| `failed` / `timeout` | 失败 / 超时 | red |
| `skipped` | 跳过 | slate |
| `running` | 执行中 | sky |
| `pending` | 等待中 | amber |
| 其它 | 原样 | outline |

**`formatItemResult(item)` 逻辑**：
- 若 `status === 'skipped'`：返回 `raw_result.skip_reason || result_message || 'skipped'`
- 否则返回 `result_status || candidate_state || raw_result.error_code || status`

**`formatItemMessage(item)` 逻辑**：`result_message || raw_result.skip_reason || raw_result.error_message || '-'`

**行交互**：点击行 → `selectItem(item)`（同时选中下方 `<VerifyItemDetail>`）。当前选中行用 `bg-surface-container-high` 高亮。

**选中默认**：loadItems 后若有结果，自动选中第一条（保留旧选中若仍存在）。

**空态**：`OpsEmptyState state="empty" title="暂无执行项" description="选择状态或检查项筛选"`

---

### 3.7 变更建议 (Proposals) `<ProposalPanel>`

**子组件文件**：`frontend/src/components/ops/ProposalPanel.vue`
**Props**：`batchRunId: number | null`
**数据源**：`GET /v1/collector/proposals?batch_run_id=...&status=undefined`
**行为**：watch + onMounted 自动 load；切 batch 时清空 `selectedIds`

**卡片**：`OpsSectionCard title="变更建议 (Proposals)" description="batch N 共 M 条建议"`
**头部操作**（`#actions` slot）：

| 按钮 | 行为 | 启用条件 |
|---|---|---|
| 批量同意 | `handleBulkAction('approve')` | `selectedIds.length > 0 && !bulkLoading` |
| 批量拒绝 | `handleBulkAction('reject')` | 同上 |
| 批量应用 | `handleBulkAction('apply')` | 同上 |

**表格列**（8 列）：

| 列 | 字段 | 备注 |
|---|---|---|
| ☐ | checkbox | 全选联动 `allSelected` |
| 实体 | `${target_type}#${target_id}` + `entityLabel(p)` 副行（`evidence.entity_name ?? evidence.ip_address`） | `font-mono text-xs` |
| 类型 | `p.proposal_type` | `font-mono text-xs` |
| 字段 | `p.field_path` | `font-mono text-xs` |
| 现值 | `formatValue(p.current_value)` | 对象→`JSON.stringify` |
| 建议值 | `p.suggested_value` 或 PORT_CANDIDATE_CONFLICT 的 `selectedForConflict[id]` | 冲突类型已 approved 时显示「选择端口」按钮 |
| 状态 | `p.status` | 徽章（4 种） |
| 操作 | 按状态显示「同意 / 拒绝 / 应用」 | 见下 |

**状态徽章**（proposal 4 种）：

| 英文 | 中文 | 颜色 |
|---|---|---|
| `pending` | 待审 | amber |
| `approved` | 已同意 | blue |
| `rejected` | 已拒绝 | red |
| `applied` | 已应用 | emerald |
| 其它 | 原样 | outline |

**ProposalType 字面量联合**（8 种）：
`PORT_DRIFT_SUSPECTED` / `PORT_FILL_SUGGESTION` / `PORT_CANDIDATE_CONFLICT` / `IP_DRIFT` / `ASSET_FACT_DRIFT` / `DB_FACT_DRIFT_DETECTED` / `DB_PORT_DRIFT` / `CLUSTER_TYPE_MISMATCH`

**ProposalStatus 字面量联合**（5 种）：
`pending` / `approved` / `rejected` / `applied` / `canceled`

**单条操作按钮显隐**：

| 状态 | 同意 | 拒绝 | 应用 |
|---|---|---|---|
| `pending` | ✅ | ✅ | — |
| `approved` | — | ✅ | ✅ |
| `rejected` / `applied` | — | — | — |

**PORT_CANDIDATE_CONFLICT 弹窗**（`OpsModal size="sm"`）：
- 打开方式：`openConflictPicker(p)` 读取 `suggested_value.candidates[]`
- `candidates` 通过 `Number()` 强转 + `!isNaN` 过滤后作为 radio 选项
- 选完后点「确认」→ 写入 `selectedForConflict[id]`
- 关闭：选「取消」/点击遮罩

**Apply 单条**：`handleSingleApply(p)`：
- 若 `proposal_type === 'PORT_CANDIDATE_CONFLICT'` 且未选端口 → 打开 picker
- 否则 PORT_CANDIDATE_CONFLICT → `POST /apply-with-value { selected_value }`；其它 → `POST /apply`

**Apply 批量**：`handleBulkAction('apply')`：
1. 校验所有 PORT_CANDIDATE_CONFLICT 都已 `selectedForConflict`
2. 构造 `override_values: Record<proposal_id, port>`（仅 apply 时附带）
3. `POST /v1/collector/proposals/batch-action`
4. 部分失败时把 `fail_count > 0` 的错误拼接到组件 `error`

---

### 3.8 执行项详情 `<VerifyItemDetail>`

**子组件文件**：`frontend/src/components/ops/VerifyItemDetail.vue`
**Props**：`item: VerifyItem | null`（组件内部定义的窄接口）
**容器**：`OpsSectionCard v-if="item" title="执行项详情" description="item_key"`

**展示字段**（`dl grid grid-cols-2`）：

| 字段 | 数据源 |
|---|---|
| `check_code` | `item.check_code` |
| `target_scope` | `item.target_scope` |
| `target` | `${target_host}:${target_port}` |
| `asset_id` | `item.asset_id`（由父组件从 `db_instance_id ?? server_id ?? 0` 推导） |
| `is_formal_port` | `item.raw_result?.is_formal_port`（⚠️ 修复后从 raw_result 读取） |
| `port_source` | `item.port_source` |
| `status` | 徽章（5 种：verified/collected/success 绿；missing/failed 红；skipped 琥珀；其它灰） |
| `reachable` | `yes/no`（绿/红） |
| `result_status` | `item.result_status` |
| `message` | `item.result_message`（`break-all`） |
| `skip reason`（条件） | `item.status === 'skipped'` 时显示 `raw_result.skip_reason ?? 'CALLBACK_RESULT_MISSING'` |

**折叠 raw_result**（`<details>`）：
- summary 文案：`raw_result (N facts, Mms)`
- 展开内容：`<pre>` JSON 格式化
- `duration_ms` 优先，回退 `elapsed_ms`

---

## 4. 父→子组件契约（Props 形状）

### 4.1 `<AssetVerifyReport :batch-run-id="selectedBatchId" />`
```ts
batchRunId: number | null   // 来自 BatchVerify 的 selectedBatchId
```

### 4.2 `<ProposalPanel :batch-run-id="selectedBatchId" />`
```ts
batchRunId: number | null
```

### 4.3 `<VerifyItemDetail :item="selectedItemForDetail" />`
```ts
item: {
  item_key: string
  check_code: string
  target_scope: string
  asset_id: number
  target_host: string
  target_port: number
  port_source: string | null
  status: string
  reachable: boolean | null
  result_status: string | null
  result_message: string | null
  candidate_state: string | null
  raw_result: Record<string, unknown> | null
} | null
```
> 注：父组件 `selectedItemForDetail` 从 `BatchRunItemRow` 映射而来，asset_id 推导顺序：`raw.asset_id ?? db_instance_id ?? server_id ?? 0`

---

## 5. 状态机与生命周期

### 5.1 页面 mount 流程
1. `loadBatches()`（拉列表）
2. `assetsApi.listDbTypes()`（异步填充筛选下拉，失败静默）
3. `fetchCheckCodes()`（异步填充检查项 checkbox，失败静默降级到 `[]`）
4. `startPolling()` 暂不启动（未选中任何 batch）

### 5.2 选中 batch 流程
1. 用户点击行/「详情」 → `selectedBatchId = id; loadBatchDetail(id)`
2. `loadBatchDetail`：
   - `getBatchRun(id)` → `batchDetail`
   - `loadItems()`（items 拉到后默认选中第一条）
   - 若 `isBatchRunning`（状态不在终态集）→ `startPolling()`
   - 否则 → `stopPolling()`

### 5.3 轮询机制
- 间隔：`POLL_INTERVAL = 5000`（5 秒）
- 触发条件：`isBatchRunning` 为真（`!TERMINAL_BATCH_STATUS_SET.has(status)`）
- 终止条件：batch 状态进入终态集
- 中断保护：`AbortController`，每次 tick 创建新 controller，组件 unmount / 切换 batch 时 `abort()`
- 错误处理（**P1 修复**）：轮询失败不再静默停轮询/清空 detail，把错误暴露到 `pollError`（黄色条），继续轮询
- 列表 API 失败同样写到 `pollError`（不再 silently fail）

### 5.4 `TERMINAL_BATCH_STATUS_SET`（NewType brand）
位于 `frontend/src/types/api.ts:969-982`，包含 `success` / `failed` / `cancelled` / `canceled` / `partial_success` 等终态。

### 5.5 canCancelBatch
仅当 `status` ∈ `pending` / `dispatching` / `running` 时可取消。

### 5.6 component unmount
`onBeforeUnmount(() => stopPolling())` 释放定时器与 AbortController。

---

## 6. API 全集（`@/api/assets`）

| 方法 | HTTP | URL | 调用点 |
|---|---|---|---|
| `listDbTypes()` | GET | `/v1/collector/db-types` | onMounted（异步、容错） |
| `listCheckCodes({is_enabled:true}, {suppressErrorToast:true})` | GET | `/v1/collector/check-codes` | onMounted（异步、容错） |
| `createBatchRun(payload)` | POST | `/v1/collector/batch-runs` | createBatch |
| `listBatchRuns({limit:20}, {signal?})` | GET | `/v1/collector/batch-runs` | loadBatches / 轮询 |
| `getBatchRun(id, {signal?})` | GET | `/v1/collector/batch-runs/{id}` | loadBatchDetail / 轮询 |
| `listBatchItems(id, {status,check_code}, {suppressErrorToast:true})` | GET | `/v1/collector/batch-runs/{id}/items` | loadItems |
| `retryFailedBatchItems(id, {scope:'failed'})` | POST | `/v1/collector/batch-runs/{id}/retry-failed` | retryFailed |
| `cancelBatchRun(id)` | POST | `/v1/collector/batch-runs/{id}/cancel` | cancelBatch |
| `getAssetReport(id, {suppressErrorToast:true})` | GET | `/v1/collector/batch-runs/{id}/asset-report` | AssetVerifyReport |
| `listCollectorProposals({batch_run_id,status:undefined}, {suppressErrorToast:true})` | GET | `/v1/collector/proposals` | ProposalPanel |
| `approveCollectorProposal(id)` | POST | `/v1/collector/proposals/{id}/approve` | ProposalPanel |
| `rejectCollectorProposal(id, {reason:''})` | POST | `/v1/collector/proposals/{id}/reject` | ProposalPanel |
| `applyCollectorProposal(id)` | POST | `/v1/collector/proposals/{id}/apply` | ProposalPanel |
| `applyProposalWithValue(id, {selected_value, comment?})` | POST | `/v1/collector/proposals/{id}/apply-with-value` | ProposalPanel（PORT_CANDIDATE_CONFLICT） |
| `batchActionProposals({proposal_ids,action,comment?,override_values?})` | POST | `/v1/collector/proposals/batch-action` | ProposalPanel（批量） |

**batchAction 返回**：
```ts
{
  action: string,
  results: Array<{ id, success, error? }>,
  success_count: number,
  fail_count: number
}
```

---

## 7. 核心类型契约（来自 `@/types/api.ts`）

```ts
// 批次创建 payload
interface BatchRunCreatePayload {
  run_type?: string
  target_scope: 'db_instance' | 'server'
  asset_ids?: number[]
  filters?: { db_type_code?: string; status?: string; site_id?: number; target_scope?: 'server' | 'db_instance' }
  check_codes: string[]
  include_related_server?: boolean
  max_items_per_dispatch?: number
  timeout_seconds?: number
}

interface BatchRunCreateResponse {
  batch_run_id, batch_code, status, run_type, target_scope,
  total_asset_count, total_item_count, dispatch_count,
  dispatches: DispatchRunSummary[]
}

interface BatchRunRow {
  id, batch_code, run_type, target_scope, status,
  total_asset_count, total_item_count,
  success_item_count, failed_item_count,
  pending_item_count, running_item_count, skipped_item_count,
  dispatch_count,
  request_payload?, error_message?, created_by?,
  started_at?, finished_at?, created_at?, updated_at?,
  dispatches?: DispatchRunSummary[]
}

interface DispatchRunSummary {
  dispatch_run_id, dispatch_code?, collector_run_id?,
  network_zone?, awx_instance_group?, awx_job_template?, awx_job_id?,
  status, item_count, success_item_count, failed_item_count,
  error_message?, launched_at?, finished_at?, created_at?,
  cancelled_at?
}

interface BatchRunItemRow extends CollectorRunItemRow {
  batch_run_id?, dispatch_run_id?, network_zone?, awx_instance_group?
}

interface CollectorCheckDefinitionRow {
  id, check_code, check_name,
  target_scope: 'server' | 'db_instance',
  task_type: 'PORT_CHECK' | 'DB_PORT_DISCOVERY' | 'OS_DISCOVERY' | 'DB_SQL_COLLECT',
  db_type_code?, os_type_code?, awx_role?,
  default_timeout_seconds, enabled, config?, description?
}
```

---

## 8. 工具函数

- `formatInTz(val)` / `formatDuration(a, b)`：来自 `frontend/src/utils/timezone.ts`，统一时区处理
- `getStatusBadgeClass(status)`：9 种 batch/dispatch 状态 → Tailwind class
- `formatStatusLabel(status)`：同上 → 中文标签
- `getItemStatusBadgeClass(status)` / `formatItemStatusLabel(status)`：item 5 种状态
- `isCancelled(status)`：UK/US 拼写兼容
- `formatItemResult(item)` / `formatItemMessage(item)` / `getItemFactsCount(item)`：item 派生字段

---

## 9. UX 关键点（重构时需要保留）

1. **操作确认**：取消 batch 前 `window.confirm` 弹窗（"确认取消该批次？已启动的 AWX Job 会被请求 cancel，未启动的 dispatch 不会下发。"）
2. **多态占位**：空/加载/错误三态统一 `OpsEmptyState` 渲染
3. **轮询自愈**：5s 间隔 + AbortController + 失败可见 + 终态自动停
4. **target_scope 联动**：切换时清空 `check_codes`（避免残留无效值）
5. **跨批隔离**：proposals 按 `batch_run_id` 严格 filter，避免跨批 apply
6. **PORT_CANDIDATE_CONFLICT 强制人工**：必须先 select port 才能 apply（单条/批量都校验）
7. **跳过原因追溯**：skipped item 显示 `raw_result.skip_reason`，未知时回退 `CALLBACK_RESULT_MISSING`
8. **可降级**：check_codes / db_types 接口失败时静默降级到空数组
9. **响应式栅格**：form 字段大多用 `sm:grid-cols-2/3/7` 适配移动端
10. **SectionCard 模式**：每个区块都是独立 `OpsSectionCard`，可用 v-if 整体折叠

---

## 10. 已知 TODO / 退化点（重构机会点）

- Section 3 中保留了两个 `v-if="false"` 的「Legacy inline」卡（变更建议 / 执行项详情）作为 Phase 2d 回滚逃生口，目前由 `<ProposalPanel>` / `<VerifyItemDetail>` 替代——重构时可考虑彻底清理
- 行点击的两种触发方式（行 onClick + 详情按钮 onClick.stop）存在重复，可统一为行点击 + 右侧操作列
- `selectedItemForDetail` 的推导逻辑写在 `BatchVerify.vue` 里，可下沉到 composable
- `pollError` 与 `launchError` 用同一区域显示，但颜色不同——可考虑统一 toast

---

## 11. 关键文件清单（重构时要同时改的）

```
frontend/src/views/ops/BatchVerify.vue              # 主页面
frontend/src/components/ops/AssetVerifyReport.vue   # 资产维度报告
frontend/src/components/ops/ProposalPanel.vue       # 变更建议
frontend/src/components/ops/VerifyItemDetail.vue    # 执行项详情
frontend/src/api/assets.ts                          # API 层（含 batch / proposal 端点）
frontend/src/types/api.ts                           # 类型（含 BatchRunRow / ProposalType / ProposalStatus / TERMINAL_BATCH_STATUS_SET）
frontend/src/utils/timezone.ts                      # formatInTz / formatDuration
frontend/src/router/index.ts                        # 路由注册
```

---

投喂时建议强调的 3 个核心心智模型：
1. **三段式生命周期**：Create（一次性）→ Polling（持续 5s tick 到终态）→ Manual（人工处理 proposals）
2. **数据隔离原则**：每个 batch_run_id 独立一份 batch/items/proposals，切换 = 重置
3. **批量 vs 单条对称**：proposal 的 approve / reject / apply 都各有两套入口（单条按钮 + 顶部批量按钮），后端 batch-action 与单端点走同条 service 逻辑
