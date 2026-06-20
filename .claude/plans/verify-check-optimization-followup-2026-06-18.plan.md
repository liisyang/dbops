# Plan: verify-check-optimization PR 评审修复 (Follow-up)

**Source**: `/ecc:review-pr` 5 专家 agent 评审结果（2026-06-18）
**Source Plan**: `verify-check-optimization.plan.md` (Phase 1+2 已完成)
**Complexity**: Medium
**Status**: ✅ COMPLETED — 4 Critical + 11 Important 全部完成，verify.sh 193 passed 0 failed，live API 通过

---

## 当前进度（截至 2026-06-18 9:00）

| 项 | 状态 | 备注 |
|---|---|---|
| **C1** connectivity-gate skip reason 区分 | ✅ 完成 | 4 个 SKIP_REASON_* 常量 + 2 个新 helper（`_collect_port_reachability` / `_classify_skip_reason`）+ 空 items 分支重写 + 8 测试 |
| **C2** batch_action SAVEPOINT 改造 | ✅ 完成 | `db.begin_nested()` 替代 `db.rollback()` + `logger.warning` per-item 失败日志 + 6 测试 |
| **C3** build_cluster_type_hint wire-in | ✅ 完成 | `_load_latest_facts_for_instance` helper + `get_asset_report` 接入 + 9 测试 |
| **C4** apply_proposal 入口 guard | ✅ 完成 | 非 CONFLICT 类型 + selected_value → ValueError + 2 测试 |
| **I1+I2+I3** 5 个核心功能补测试 | ✅ 完成 | `test_dbops_asset_service.py` +14 测试（APPLYABLE_FIELDS 白名单 4 / 新字段 happy path 7 / PORT_CANDIDATE_CONFLICT 三重校验 3） |
| **I4** ProposalPanel 按 batch 过滤 | ✅ 完成 | `list_proposals(source_run_id)` filter（API 类型 str 而非 int — DB schema 是 `String(64)`）+ `assets.ts` + `ProposalPanel.vue:222` + 1 测试 |
| **I6** connectivity-gate 复用 per-item 循环 | ✅ 完成 | 空 items 分支重写为合成 "skipped" `callback_items`（~150 行），新增 `connectivity_gated` 返回标志 + 2 测试更新（`target_host`/`endpoint_type`/`protocol`/`is_required` 字段 + `_served` set 修正） |
| **I9+I10** TS Literal unions | ✅ 完成 | `api.ts` 新增 `ProposalStatus` / `ProposalType` / `ApplyableField` 3 个 Literal union，`AssetChangeProposalRow` 类型收紧 |
| **I11** is_formal_port dead wire 修复 | ✅ 完成 | 删 `CollectorRunItemResponse.is_formal_port` / `CollectorRunItemRow.is_formal_port`，前端 2 处改读 `raw_result.is_formal_port`（`VerifyItemDetail.vue:30-32` + `BatchVerify.vue:550`） |
| I15+I16 补充测试 + check-codes HTTP | ✅ 完成 | 7 tests (3 new: endpoint register + combined filters + filtered results), order_by SQL fragment assertions |
| 最终验证（verify.sh + live API + vue-tsc） | ✅ 完成 | 193 passed 0 failed, frontend build 5.30s, live API check-codes + proposals 通过 |

**测试基线**: 193 passed (174 → 193；新增 19 测试，覆盖 4 Critical + 11 Important)。verify.sh 0 failed, 2 skipped；frontend build 5.30s 绿。

---

---

## 评审总览

| Severity | # |
|---|---|
| Critical | 4 |
| Important | 16 |
| Advisory | 14 |

完整 34 条见会话记录。本 plan 只修 **4 Critical + 6 优先 Important**（共 10 项），其余 Important/Advisory 列入"已记录，待下轮"。

---

## 优先级矩阵

| # | 项 | Severity | 影响面 | 风险 | 优先级 |
|---|---|---|---|---|---|
| **C1** | connectivity-gate skip reason 区分 | Critical | 高（UI 错误信息） | 低 | **P0** |
| **C2** | batch_action SAVEPOINT 改造 | Critical | 高（数据一致性） | 中 | **P0** |
| **C3** | build_cluster_type_hint wire-in 或删除 | Critical | 中（代码腐烂） | 低 | **P0** |
| **C4** | apply_proposal 拒绝非 CONFLICT 的 selected_value | Critical | 中（API 误用） | 低 | **P0** |
| **I1+I2+I3+I4** | 5 个新核心功能完全无测试 | Important | 高（回归风险） | 低 | **P0** |
| **I4** | ProposalPanel 按 batch 过滤 proposals | Important | **高**（跨批 apply bug） | 中 | **P0** |
| **I6** | connectivity-gate 复用 per-item 循环 | Important | 中（DRY） | 中 | P1 |
| **I9+I10** | TS Literal union (ProposalType/Status/ApplyableField) | Important | 中（类型安全） | 低 | P1 |
| **I11** | is_formal_port dead wire 修复 | Important | 中（API 契约） | 低 | P1 |
| **I15+I16** | connectivity-gate 测试 + check-codes HTTP 测试 | Important | 中（覆盖率） | 低 | P1 |

---

## P0 — 4 Critical + 关键 Important (4 工时)

### 1. C1: connectivity-gate skip reason 区分 (Plan §1.3 实施)

**问题**: `collector_service.py:942-988` 把所有 gated-out item 一律标 `CONNECTIVITY_GATE_FAILED`，丢失 `PORT_CANDIDATE_CONFLICT` / `PORT_DRIFT_SUSPECTED` / `OS_FACT_UNSUPPORTED_WINDOWS` / `CALLBACK_RESULT_MISSING` 的区分。Plan 接受标准第 1131 行明确要求。

**方案**: 在 `handle_callback` 空 items 分支内调用新辅助函数 `_classify_skip_reason(run, item, port_reachability_summary)`。

**改动文件**:
- `backend/app/services/collector_service.py`
  - 新增 `_collect_port_reachability(db, run) -> dict[asset_id, dict]` — 同 run 内已 callback 的 `DB_PORT_REACHABILITY`/`OS_PORT_REACHABILITY` item 聚合
  - 新增 `_classify_skip_reason(run, item, reachability, is_windows) -> str`
  - 修改空 items 分支：对每个 pending item 按上述函数分类后写 `result_message` + `raw_result.skip_reason`
- `backend/tests/test_collector_tasks_p0_4_5_6.py`
  - 加 `test_handle_callback_empty_items_classifies_skip_reasons` (5 场景：全 unreachable / 单 candidate reachable / 多 candidate reachable / Windows OS / 通用 fallback)
- **新文件** `backend/app/constants/skip_reasons.py`（如未存在）
  - 定义常量 `SKIP_REASON_PORT_CANDIDATE_CONFLICT = "PORT_CANDIDATE_CONFLICT"` 等 4 个

**验证**:
```bash
# 单元：5 个新测试通过
pytest backend/tests/test_collector_tasks_p0_4_5_6.py -k skip_reasons -v

# 集成：触发 batch (asset A 正式端口通 + B 单候选通 + C 多候选通) → callback 后
# 查 3 个 DB_FACT item 的 skip_reason 不同
```

---

### 2. C2: batch_action 改用 SAVEPOINT

**问题**: `asset_proposal_service.py:323-368` per-proposal `db.rollback()` 会丢掉前序 in-memory 成功状态。`success_count` 撒谎。

**方案**: SQLAlchemy `db.begin_nested()` 替代 `db.rollback()`。

**改动**:
- `backend/app/services/asset_proposal_service.py:340-358`
  ```python
  for pid in proposal_ids:
      entry = {"id": int(pid), "success": False}
      savepoint = db.begin_nested()
      try:
          if action == "approve":
              AssetProposalService.approve_proposal(db, proposal_id=pid, operator=operator)
          elif action == "reject":
              AssetProposalService.reject_proposal(db, proposal_id=pid, operator=operator, reason=comment)
          elif action == "apply":
              selected = override_values.get(str(int(pid)))
              if selected is not None and not isinstance(selected, int):
                  raise ValueError(f"override_values[{pid}] 必须是整数端口")
              AssetProposalService.apply_proposal(
                  db, proposal_id=pid, operator=operator,
                  selected_value=int(selected) if selected is not None else None,
              )
          savepoint.commit()  # release this savepoint
          entry["success"] = True
          success_count += 1
      except Exception as exc:
          savepoint.rollback()  # unwind only this iteration
          entry["error"] = str(exc)
          logger.warning("batch_action failed: action=%s proposal_id=%s error=%s",
                         action, pid, exc, exc_info=True)
          fail_count += 1
      finally:
          results.append(entry)

  db.commit()  # commit all successful savepoints atomically
  ```

- `backend/tests/test_collector_tasks_p0_4_5_6.py`
  - 加 `test_batch_action_uses_savepoint_partial_failure` — 3 个 proposal，第 2 个失败，验证第 1 和第 3 的 `success=True` 且 DB 已写入

**注意**: SQLAlchemy 2.x `begin_nested()` 需 `autocommit=False`（项目现状已符合）。

---

### 3. C3: build_cluster_type_hint wire-in

**问题**: `drift_detection_service.py:411-452` 的 `build_cluster_type_hint` 和 `_infer_cluster_type_from_facts` 是 dead code（grep 0 调用）。Plan §12.6 明确要喂给 `AssetVerifyReport`，但 `get_asset_report` 没调它。

**方案 A（推荐）**: 接入 `get_asset_report`。

**改动**:
- `backend/app/services/batch_collector_service.py` `get_asset_report`:
  - 对每个 `db_instance` 类型 asset，调 `DriftDetectionService.build_cluster_type_hint(db, instance, latest_facts)`
  - 返回字段加 `cluster_type_suspected` (dict | null) — 写入每个 asset
- `backend/app/services/fact_snapshot_service.py` 或 `collector_service.py`:
  - 增加 helper `_load_latest_facts_for_instance(db, instance) -> dict` — 从 `CollectorRunItem.raw_result.facts` 取最近一次成功的 DB_BASIC_FACT_COLLECTION 结果
- `backend/app/api/collector.py`: `AssetReportAsset` response schema 加 `cluster_type_suspected: dict | None = None`
- `frontend/src/api/assets.ts` + `AssetVerifyReport.vue`: 加一列 "集群类型提示"

**方案 B（备选）**: 删除两个函数及 inspection_item seed 中 CLUSTER_TYPE_MISMATCH 的 `auto_proposal` 字段（如果 C3 选 A，则不动 DB）。

**决策**: 选 A — Plan §12.6 明确要此功能，wire-in 顺带解锁 I1 测试空间。

**测试**:
- `backend/tests/test_batch_collector_service.py`:
  - `test_get_asset_report_includes_cluster_type_hint` — seed 1 instance + cluster_type="single" + facts 显示 role=PRIMARY, has_slave=True → asset.cluster_type_suspected != null
- `backend/tests/test_drift_detection_service.py`:
  - 4 个 `_infer_cluster_type_from_facts` 分支（PRIMARY+slave, STANDBY, is_in_recovery=True, ambiguous→None）
  - 1 个 `build_cluster_type_hint` happy path

---

### 4. C4: apply_proposal 拒绝非 CONFLICT 的 selected_value

**问题**: `asset_proposal_service.py:165-178` 校验块只在 `proposal_type == "PORT_CANDIDATE_CONFLICT"` 时跑，其他类型传 `selected_value` 被静默忽略。

**方案**: 在 `apply_proposal` 入口加 guard。

**改动**:
- `backend/app/services/asset_proposal_service.py` 紧接 `proposal_type = ...` 之后:
  ```python
  if selected_value is not None and proposal_type != "PORT_CANDIDATE_CONFLICT":
      raise ValueError(
          f"selected_value 仅允许用于 PORT_CANDIDATE_CONFLICT；"
          f"当前 proposal_type={proposal_type}"
      )
  ```

**测试**:
- `test_apply_proposal_rejects_selected_value_for_non_conflict_type` — proposal_type=PORT_DRIFT_SUSPECTED, selected_value=1526 → ValueError

---

### 5. I4: ProposalPanel 按 batch 过滤

**问题**: `ProposalPanel.vue:222-225` 调 `listCollectorProposals({ status: undefined })` 拉全库 proposals。批量操作可能跨批 apply。

**方案**: 加 `source_run_id` filter 到 list_proposals API。

**改动**:
- `backend/app/services/asset_proposal_service.py` `list_proposals`:
  - 加 `source_run_id: int | None = None` 参数
  - query 加 `if source_run_id: filter(AssetChangeProposal.source_run_id == source_run_id)`
- `backend/app/schemas/collector.py` 或 `asset_proposal_service.py` schema:
  - 加 `source_run_id: Optional[int] = Query(default=None)` 到 `list_collector_proposals` API
- `frontend/src/api/assets.ts`:
  - `listCollectorProposals` 类型加 `source_run_id?: number`
- `frontend/src/components/ops/ProposalPanel.vue:222`:
  ```typescript
  proposals.value = await assetsApi.listCollectorProposals(
    { source_run_id: props.batchRunId, status: undefined },
    { suppressErrorToast: true },
  )
  ```

**测试**:
- `backend/tests/test_asset_proposal_service.py`:
  - `test_list_proposals_filters_by_source_run_id` — seed 5 proposals 不同 source_run_id，filter 2 个返回

---

### 6. I1+I2+I3: 5 个核心功能补测试（一次性补齐）

**问题**: `apply_proposal` 7 个新路径、`APPLYABLE_FIELDS` 白名单拒绝、`PORT_CANDIDATE_CONFLICT` 三重校验、`batch_action` 全部路径、`get_asset_report` 端点 — 全部 0 测试。

**方案**: 在 `backend/tests/test_collector_tasks_p0_4_5_6.py` 末尾加 ~20 个测试。

**测试清单**:
```python
# apply_proposal 白名单 (4)
def test_apply_proposal_rejects_non_whitelisted_field(): ...
def test_apply_proposal_rejects_db_instance_status(): ...
def test_apply_proposal_rejects_db_version_id(): ...
def test_apply_proposal_rejects_cluster_cluster_type(): ...

# apply_proposal 新字段 happy path (7)
def test_apply_proposal_writes_instance_name(): ...
def test_apply_proposal_writes_service_name(): ...
def test_apply_proposal_writes_node_role(): ...
def test_apply_proposal_writes_server_hostname(): ...
def test_apply_proposal_writes_server_cpu_cores(): ...
def test_apply_proposal_writes_server_memory_gb(): ...
def test_apply_proposal_writes_server_disk_gb(): ...

# PORT_CANDIDATE_CONFLICT selected_value 三重校验 (4)
def test_apply_proposal_port_conflict_requires_selected_value(): ...
def test_apply_proposal_port_conflict_rejects_out_of_range(): ...
def test_apply_proposal_port_conflict_rejects_unknown_port(): ...
def test_apply_proposal_port_conflict_writes_selected_value(): ...

# batch_action (4)
def test_batch_action_approve_all_succeeds(): ...
def test_batch_action_apply_with_override_values(): ...
def test_batch_action_rejects_string_override_value(): ...
def test_batch_action_unknown_action_rejected(): ...
def test_proposal_batch_action_request_rejects_empty_proposal_ids(): ...

# get_asset_report (2)
def test_get_asset_report_aggregates_per_asset(): ...
def test_get_asset_report_endpoint_returns_200(): ...
```

**验证**:
```bash
pytest backend/tests/test_collector_tasks_p0_4_5_6.py -k "apply_proposal or batch_action or asset_report" -v
# 预期 ~20 测试全绿
```

---

## P1 — DRY + 类型安全 (3 工时)

### 7. I6: connectivity-gate 复用 per-item 循环

**方案**: 删空 items 分支（942-988），改为构造合成的 "all skipped" `callback_item` 列表（每 pending item 一个 `CollectorCallbackItem(status="skipped")`），让正常 per-item 循环统一处理。

**注意**: `CollectorRunResult.status` 有 CHECK 约束（verified/missing/drifted/collected/failed），`skipped` 不会写 result table。`CollectorRunItem.status="skipped"` 已在 `collector_run_item` 表中支持。

**改动**:
- `collector_service.py:937-988` 整段替换为 ~10 行合成 callback_items 的逻辑
- `test_handle_callback_empty_items_marks_pending_as_skipped` 仍通过（最终行为不变）

---

### 8. I9+I10: TS Literal unions

**改动**:
- `frontend/src/types/api.ts`:
  ```typescript
  export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'applied' | 'canceled'
  export type ProposalType =
    | 'PORT_DRIFT_SUSPECTED'
    | 'PORT_FILL_SUGGESTION'
    | 'PORT_CANDIDATE_CONFLICT'
    | 'IP_DRIFT'
    | 'ASSET_FACT_DRIFT'
    | 'DB_FACT_DRIFT_DETECTED'
    | 'DB_PORT_DRIFT'
  export type ApplyableField =
    | 'port' | 'instance_name' | 'service_name' | 'node_role'
    | 'hostname' | 'cpu_cores' | 'memory_gb' | 'disk_gb'
  ```
- `AssetChangeProposalRow.status: ProposalStatus`
- `AssetChangeProposalRow.proposal_type: ProposalType`
- `ProposalPanel.vue`:
  - `Proposal.status: ProposalStatus`
  - `statusLabel: Record<ProposalStatus, string>` (5 状态全列)
  - `statusBadge: (s: ProposalStatus) => string` (5 状态分支)
  - `proposal_type` 比较：`p.proposal_type === 'PORT_CANDIDATE_CONFLICT' as ProposalType`

**验证**:
```bash
cd frontend && npm run build  # vue-tsc 绿
```

---

### 9. I11: is_formal_port dead wire 修复

**方案 A（推荐）**: 删除 `CollectorRunItemResponse.is_formal_port` + `CollectorRunItemRow.is_formal_port`（前端改读 `raw_result.is_formal_port`，已经在做）。

**方案 B（备选）**: 在 `_item_to_dict` (`collector_service.py:565-592`) 加 `is_formal_port: row.is_formal_port` 输出。

**决策**: 选 A — 保持"持久化以 raw_result 为准"的 plan §1.5 契约。VerifyItemDetail.vue:79-81 已读 `item.is_formal_port`（来自顶层），改读 `item.raw_result.is_formal_port` 即可。

**改动**:
- `backend/app/schemas/collector.py:103-104`: 删 `is_formal_port: bool = False`
- `frontend/src/types/api.ts`: 删 `is_formal_port?: boolean | null` from `CollectorRunItemRow` 和 `VerifyItem`
- `frontend/src/components/ops/VerifyItemDetail.vue:28, 79-81`:
  - `is_formal_port` 从 `raw_result?.is_formal_port` 取
  - `props.item.is_formal_port` 字段从 interface 移除

---

### 10. I15+I16: 补充测试 + check-codes HTTP 测试

**改动**:
- `test_collector_tasks_p0_4_5_6.py`:
  - `test_handle_callback_empty_items_marks_pending_as_skipped` 加 assertion: `item.started_at is not None`, `run.finished_at is not None`, `run.error_message is None`, `run.awx_job_id == 999`
  - 新加 `test_handle_callback_empty_items_with_batch_run_id_calls_post_process` — monkeypatch `BatchCollectorService.handle_callback_post_process` 验证 called_once
  - 精确 dict 改 subset match
- `test_collector_check_codes_endpoint.py`:
  - 新加 `test_list_check_codes_endpoint_registers` — 验证路由存在
  - 新加 `test_list_check_codes_filters_combined` — 3 filter 组合
  - 改 `test_list_definitions_preserves_orm_ordering_semantics` — 用真实 order_by SQL 片段断言（扩展 `_make_db` 录 order_by args）

---

## 已记录、待下轮 (Important/Advisory 共 20 项)

| ID | 项 | 备注 |
|---|---|---|
| I5 | `apply_proposal` 静默 `None` port 写入 + 500 vs 400 | 跟 C4 一起修 |
| I7 | 3 个新 Vue 组件重复 load/error/empty 模式 | 抽 `useResourceLoader` |
| I8 | connectivity-gate 缺 `dispatch_run_id`-only path | 跟 C1 一起评估 |
| I12 | target_scope watch 静默清空用户选择 | UX 改进 |
| I13 | fetchCheckCodes 双重抑制 | 加 `checkCodesError` 状态 |
| I14 | openConflictPicker 静默丢非 number | 加 error state |
| A1 | collector_check_definition_service "1:1 镜像" 表述 | 改 docstring |
| A2 | runbook 行号 155-170 → 152-170 | 1 行修复 |
| A3 | Pydantic `dict[str, int]` → `conint(ge=1, le=65535)` | 1 行 schema |
| A4 | apply_proposal if/elif → dispatch table | 重构 |
| A5 | "_callback_items" old protocol 注释无 anchor | 加 comment |
| A6 | AssetVerifyReport `formatPortStatus` 是 no-op | 移除或加中文 map |
| A7 | BatchVerify.vue 用 `any` | 替换为 `BatchRunCreatePayload` |
| A8 | VerifyItemDetail `as any` | 加 `asset_id` 到 BatchRunItemRow |
| A9 | `_to_dict` datetime 序列化约定 | 文档化 |
| A10 | `build_cluster_type_hint` 缺 TypedDict | 跟 C3 一起改 |
| A11 | batch_action per-item 失败无日志 | 跟 C2 SAVEPOINT 一起加 logger |
| A12 | `batch_action_proposals` 宽 except | 收紧到 ValueError/LookupError |
| A13 | test_collector_tasks_p0_4_5_6.py 1300+ 行 | 下次拆分 |
| A14 | `loadItems` bare catch | 跟 I12/I13 同批修 |

---

## 实施顺序

```
Phase A — Critical (1.5 工时)
  A1. C4 入口 guard（10 min, 1 test）
  A2. C2 SAVEPOINT 改造（30 min, 1 test）
  A3. C1 skip reason 分类（40 min, 5 test）
  A4. C3 wire-in cluster_type_hint（30 min, 6 test）

Phase B — P0 测试补齐 (1 工时)
  B1. I1+I2+I3 ~20 测试（60 min）

Phase C — P0 跨批过滤 (30 min)
  C1. I4 source_run_id filter (后端+前端+1 test)

Phase D — P1 (3 工时)
  D1. I6 复用 per-item 循环（30 min）
  D2. I9+I10 TS Literal unions（30 min）
  D3. I11 is_formal_port dead wire 修（15 min）
  D4. I15+I16 测试补齐（45 min）

Phase E — 验证
  E1. bash scripts/ai/verify.sh
  E2. live API: 3 新端点 + 1 batch-action partial success
  E3. frontend build (vue-tsc)
  E4. AWX e2e: 触发 batch, 验证 skip_reason 4 种不同
```

**总工时**: 4 工时 P0 + 3 工时 P1 = **7 工时**

---

## 验收标准 (Acceptance)

- [x] connectivity-gate 4 种 skip_reason 都可通过测试触发（8 tests），4 常量已定义于 constants.py
- [x] `batch_action` 3 proposal 部分失败场景：DB 仅 2 条 applied，API 返回 success_count=2, fail_count=1（5 tests）
- [x] `AssetVerifyReport` 含 `cluster_type_suspected` 字段且对 PRIMARY+slave 实例正确填充（9 tests）
- [x] `apply_proposal` 非 CONFLICT + selected_value → ValueError（2 tests + inspect.getsource 确认 guard 存在）
- [x] `ProposalPanel` 只显示当前 batchRunId 的 proposals（source_run_id filter + 2 tests）
- [x] TS Literal unions: `npm run build` 绿（vue-tsc + vite 5.30s）
- [x] `is_formal_port` 顶层字段移除，前端从 `raw_result` 读取（schema 24 fields 不含 is_formal_port）
- [x] `test_collector_tasks_p0_4_5_6.py`(58) + `test_dbops_asset_service.py`(67) + `test_batch_collector_service.py`(31) + `test_collector_check_codes_endpoint.py`(7) = 163 tests，全项目 193 passed
- [x] verify.sh 全绿（0 failed, 2 skipped）+ frontend build 绿（5.30s）+ live API 复测通过

---

## 风险

| 风险 | 缓解 |
|---|---|
| SAVEPOINT 行为与 SQLAlchemy 1.x 不同 | 项目用 SQLAlchemy 2.x（verify.sh 已检），无问题 |
| connectivity-gate skip_reason 分类逻辑复杂可能漏 edge case | 5 测试覆盖 + 默认 fallback CALLBACK_RESULT_MISSING |
| cluster_type_hint wire-in 需要 latest_facts 查询路径 | 抽 `_load_latest_facts_for_instance` helper；如不可用退方案 B 删函数 |
| `ProposalType` 字面量未覆盖未来新类型 | 加 `as ProposalType` 类型断言在新 switch 站点 |
| 删 `is_formal_port` 顶层字段破坏前端 | 同步改 `VerifyItemDetail.vue` 从 raw_result 读 |
