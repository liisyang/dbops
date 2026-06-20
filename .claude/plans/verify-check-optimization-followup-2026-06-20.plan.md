# Plan: verify-check-optimization Batch-2 评审修复 (Follow-up)

**Source**: `/ecc:review-pr` 6 专家 agent 评审结果（2026-06-20）
**Source Plan**: `verify-check-optimization-followup-2026-06-18.plan.md` (Batch-1 4C+11I 已完成)
**Complexity**: Medium-High
**Status**: 🟡 PARTIAL — 23/33 项完成（8C 全 + 11I + 4A），I7 + 5 P2 + 4A 待下轮
**Working Tree 基线**: HEAD = a0f49b0，17 modified + 10 untracked (working tree 未提交)
**完成时间**: 2026-06-20
**验证**: verify.sh 0 failed 2 skipped；pytest 223 passed；vue-tsc EXIT=0

---

## 评审总览

| Severity | # | 处理策略 |
|---|---|---|
| **Critical** | 8 | 全部修（数据正确性 / 静默失败 / 测试空缺） |
| **Important** | 16 | 全部修（架构 / 一致性 / 性能） |
| **Advisory** | 9 | 选 5 项修（nohup、gitignore、status 提取等），其余列 backlog |

完整 33 条见会话记录 / `pr-review-2026-06-20.summary.md`（本 plan 末尾嵌入摘要）。

---

## 优先级矩阵

| # | 项 | Severity | 影响面 | 风险 | 优先级 |
|---|---|---|---|---|---|
| **C1** | apply_proposal int() 截断 Numeric(10,2)/(12,2) | Critical | 高（数据丢失） | 低 | **P0** |
| **C2** | node_role apply 绕过 chk_node_role CHECK 约束 | Critical | 高（事务回滚牵连） | 低 | **P0** |
| **C3** | db_version auto-create 无幂等检查 | Critical | 高（ghost 行循环） | 低 | **P0** |
| **C4** | collector_service IntegrityError 整事务 rollback | Critical | 高（其他 item 写入丢失） | 中 | **P0** |
| **C5** | drift_detection._create_change_proposal 吞所有异常 | Critical | 高（drift 静默失效） | 中 | **P0** |
| **C6** | drift_detection_service 测试文件整体缺失 | Critical | 高（回归风险） | 低 | **P0** |
| **C7** | db_version / db_size_gb apply 零 happy-path 测试 | Critical | 高（bug fix 未钉住） | 低 | **P0** |
| **C8** | 3 个新端点零 HTTP 集成测试 | Critical | 中（契约保护） | 低 | **P0** |
| **I1** | ApplyableField TS union 缺 db_size_gb / db_version | Important | 中（类型契约） | 低 | **P1** |
| **I2** | 状态颜色 / 标签在 3 个 Vue 组件硬编码重复 | Important | 中（CLAUDE.md 规则 13 违反） | 低 | **P1** |
| **I3** | _collect_port_reachability / get_asset_report N+1 | Important | 中（1000 实例性能） | 中 | **P1** |
| **I4** | 30-runbook.md 仍写 CONNECTIVITY_GATE_FAILED | Important | 中（on-call 误导） | 低 | **P1** |
| **I5** | record_event before/after 都取 post-apply | Important | 中（审计语义） | 低 | **P1** |
| **I6** | target_type 仍有 `\| string` 拓宽 | Important | 低（类型契约） | 低 | **P1** |
| **I7** | batch-action / asset-report 无 response_model | Important | 中（OpenAPI 契约） | 低 | **P1** |
| **I8** | _FakeSavepoint.rollback 不真回滚，回归测试无效 | Important | 高（C2 fix 风险） | 低 | **P1** |
| **I9** | collector_check_definition_service 1:1 克隆 port_profile_service | Important | 中（DRY） | 低 | **P2** |
| **I10** | apply_proposal 200 行 if/elif 阶梯 | Important | 中（可维护性） | 中 | **P2** |
| **I11** | drift current_value is None → 刷提案 + auto-create 联动 | Important | 高（与 C3 联动） | 中 | **P1** |
| **I12** | AssetReport / AssetReportAsset 在 SFC + assets.ts 各定义 | Important | 中（类型契约） | 低 | **P1** |
| **I13** | VerifyItem / Proposal 局部 interface 绕开 shared types | Important | 低（类型契约） | 低 | **P2** |
| **I14** | collector.py:540 冗余内联 import | Important | 低（清理） | 低 | **P1** |
| **I15** | CollectorCheckDefinitionResponse 未在 __init__ 导出 | Important | 低（可发现性） | 低 | **P1** |
| **I16** | 6 个 classify_skip_reason 测试可参数化 | Important | 低（DRY） | 低 | **P2** |
| **A1** | backend/nohup.out 不应提交 | Advisory | 低（仓库卫生） | 低 | **P1** |
| **A2** | .claude/plans/ 4 个 untracked 文件 | Advisory | 低（仓库卫生） | 低 | **P1** |
| **A3** | drift_detection_service logger import 嵌在 import 块中间 | Advisory | 低（PEP 8） | 低 | **P2** |
| **A4** | I11 注释块在 collector.py 描述已删除的字段 | Advisory | 低（注释腐烂） | 低 | **P2** |
| **A5** | formatPortStatus / formatFactStatus no-op 包装 | Advisory | 低（dead code） | 低 | **P2** |
| **A6** | _is_windows_target 4 重三元嵌套 | Advisory | 低（可读性） | 低 | **P2** |
| **A7** | apply_proposal 三段重复 int-coerce-or-raise 块 | Advisory | 低（DRY） | 低 | **P2** |
| **A8** | build_cluster_type_hint 静默 except Exception | Advisory | 中（错误吞咽） | 低 | **P1** |
| **A9** | _collect_port_reachability SSH 端口解析失败静默 | Advisory | 低（可观测性） | 低 | **P2** |

---

## P0 — 8 Critical (4 工时)

### 1. C1+C2+C3: apply_proposal 三处静默数据错误（一次性改 `asset_proposal_service.py`）

**问题集中**: `apply_proposal` 同一方法的三个 dispatch 分支各自有数据正确性 bug。批量改以减少反复 review。

**C1 - Numeric 列 int() 截断**:
- 位置: `asset_proposal_service.py:374-388`
- 现状:
  ```python
  elif field_path == "memory_gb":
      server.memory_gb = int(proposal.suggested_value) if proposal.suggested_value is not None else None
  ```
- 修复: 抽 `_coerce_field(obj, attr, raw, target_type)` helper（`target_type in {"int","float","str"}`），`memory_gb/disk_gb/db_size_gb` 走 `float`（或 `Decimal(str(...))`），`cpu_cores` 走 `int`。

**C2 - node_role 绕过 CHECK**:
- 位置: `asset_proposal_service.py:243-250`
- 修复: 加模块常量 `APPLYABLE_NODE_ROLES = {primary, standby, single, member, unknown}`，dispatch 前 `if str(...).lower() not in APPLYABLE_NODE_ROLES: raise ValueError(...)`（与 C1 helper 协同，allowed_values 是参数）。

**C3 - db_version auto-create 无幂等**:
- 位置: `asset_proposal_service.py:295-334`
- 修复: 进入 step 6（auto-create）前再查一次 `DbVersion.filter(version_code == version_str).first()`；空字符串 / 全 whitespace 直接 `ValueError`。
- 顺便实现 I11 的部分修复：把 `current_value is None → drift=True` 路径也调整成"信息缺失"（不动 service 改 drift_detection，service 只负责兜底幂等）。

**测试**:
- `test_apply_proposal_writes_memory_gb_decimal_preserved` — `64.5 → 64.5`（不被截断）
- `test_apply_proposal_writes_node_role_lowercases` — `"PRIMARY" → "primary"`
- `test_apply_proposal_rejects_node_role_invalid_value` — `"replica" → ValueError`
- `test_apply_proposal_db_version_auto_create_idempotent` — 同 suggested_value 调两次，只新增 1 行 DbVersion
- `test_apply_proposal_db_version_rejects_empty_version_str` — `"   " → ValueError`

---

### 2. C4: collector_service IntegrityError 改 SAVEPOINT

**位置**: `collector_service.py:1096-1100`

**问题**:
```python
try:
    db.flush()
except IntegrityError as exc:
    db.rollback()  # 整个 session 回滚
```

race-loser 路径下，前面已写的 `CollectorRunItem.pending→running`、fact snapshot、drift record 全部丢失。

**修复**:
```python
savepoint = db.begin_nested()
try:
    db.flush()
    savepoint.commit()
except IntegrityError:
    savepoint.rollback()  # 只回滚这条
    logger.info("race-loser on CollectorRunItem: %s", item.item_key)
    continue
```

**测试**:
- `test_handle_callback_integrity_error_only_rolls_back_loser_item` — seed 2 个 item，第一条 raise IntegrityError，第二条仍被处理；验证前序已写的 fact snapshot 保留。

---

### 3. C5: drift_detection._create_change_proposal 区分 IntegrityError vs 真错误

**位置**: `drift_detection_service.py:411`

**修复**:
```python
try:
    proposal = AssetProposalService.create_proposal(...)
    return proposal
except IntegrityError as exc:
    # duplicate (drift, source) is expected and OK
    logger.info("Duplicate proposal for snapshot=%s key=%s: %s", snapshot_id, fact_key, exc)
    return None
except (OperationalError, DBAPIError):
    # transient DB issue — surface so callback transaction doesn't commit with stale state
    logger.exception("DB error creating proposal for snapshot=%s key=%s", snapshot_id, fact_key)
    raise
except SQLAlchemyError:
    # schema/programming error — log + re-raise
    logger.exception("ORM error creating proposal for snapshot=%s key=%s", snapshot_id, fact_key)
    raise
```

**测试**:
- `test_create_change_proposal_returns_none_on_integrity_error_duplicate`
- `test_create_change_proposal_reraises_on_operational_error`（mock raise）

---

### 4. C6+C7: drift_detection 测试文件重建 + db_version / db_size_gb 回归测试

**C6 - 重建 test_drift_detection_service.py**:
- 文件整体不存在（`grep` 只找到陈旧 `.pyc`），需新建。
- 至少 5 个 case：
  - `test_detect_for_snapshot_database_role_single_is_not_drift` — node_role=single + fact=PRIMARY → 无 drift
  - `test_detect_for_snapshot_database_role_primary_when_standby` — node_role=standby + fact=PRIMARY → drift
  - `test_detect_for_snapshot_null_formal_value_creates_drift`（视 I11 决策）
  - `test_detect_for_snapshot_version_label_match_no_drift`
  - `test_detect_for_snapshot_extra_field_marked_info_only`

**C7 - 补 db_version / db_size_gb happy-path 测试**（在 `test_dbops_asset_service.py`）:
- `test_apply_proposal_db_version_exact_match_on_version_name`
- `test_apply_proposal_db_version_bidirectional_like`（"Microsoft SQL Server 2019" 匹配 "SQL Server 2019"）
- `test_apply_proposal_db_version_uses_evidence_version_full`
- `test_apply_proposal_db_version_auto_creates_when_unmatched`
- `test_apply_proposal_writes_db_size_gb_float`
- `test_apply_proposal_writes_db_size_gb_from_dict_evidence`

---

### 5. C8: 3 个新端点 HTTP 集成测试

**位置**: `backend/tests/test_collector_tasks_p0_4_5_6.py`（或新建 `test_collector_api_endpoints.py`）

**仿照 `test_collector_check_codes_endpoint.py:225-268` 的 TestClient 模式**：

```python
# asset-report
def test_asset_report_endpoint_registers():
    # TestClient: GET /v1/collector/batch-runs/{id}/asset-report → 200

def test_asset_report_endpoint_returns_404_for_unknown_batch():
    # LookupError → HTTPException 404

def test_asset_report_endpoint_requires_auth():
    # no current_user override → 401

# apply-with-value
def test_apply_with_value_endpoint_requires_admin():
    # non-admin override → 403

def test_apply_with_value_endpoint_returns_404_on_missing_proposal():
    # missing proposal_id → 404

def test_apply_with_value_endpoint_validates_selected_value_type():
    # selected_value="not-int" → 422 (Pydantic)

# batch-action
def test_batch_action_endpoint_validates_empty_proposal_ids():
    # proposal_ids=[] → 422 (Pydantic min_length)

def test_batch_action_endpoint_requires_admin():
    # non-admin override → 403

def test_batch_action_endpoint_returns_404_for_unknown_proposal():
    # missing proposal_id → 404
```

---

## P1 — 9 Important (3 工时)

### 6. I1+I6: TS Literal union 补全 + 移除 `| string` 拓宽

**位置**: `frontend/src/types/api.ts:375-393`

**修复**:
```typescript
export type ApplyableField =
  | 'port' | 'instance_name' | 'service_name' | 'node_role'
  | 'db_size_gb' | 'db_version'           // <-- 补
  | 'hostname' | 'cpu_cores' | 'memory_gb' | 'disk_gb'

export type ProposalTargetType = 'server' | 'db_instance'  // 抽常量

// AssetChangeProposalRow:
target_type: ProposalTargetType  // 去掉 | string
proposal_type: ProposalType
field_path?: ApplyableField | null
```

**验证**:
```bash
cd frontend && npx vue-tsc --noEmit  # 0 errors
```

---

### 7. I2: 状态颜色 / 标签三组件去重

**新文件**: `frontend/src/constants/proposalStatus.ts`

```typescript
import type { ProposalStatus } from '@/types/api'

export const PROPOSAL_STATUS_LABEL: Record<ProposalStatus, string> = {
  pending: '待审',
  approved: '已同意',
  rejected: '已拒绝',
  applied: '已应用',
  canceled: '已取消',
}

export const PROPOSAL_STATUS_BADGE: Record<ProposalStatus, string> = {
  pending: 'border-amber-500 text-amber-700',
  approved: 'border-blue-500 text-blue-700',
  rejected: 'border-red-500 text-red-700',
  applied: 'border-emerald-500 text-emerald-700',
  canceled: 'border-outline-variant text-on-surface-variant',
}

export function proposalStatusLabel(s: string): string {
  return PROPOSAL_STATUS_LABEL[s as ProposalStatus] ?? s
}

export function proposalStatusBadge(s: string): string {
  const base = 'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium'
  return `${base} ${PROPOSAL_STATUS_BADGE[s as ProposalStatus] ?? 'border-outline-variant text-on-surface-variant'}`
}
```

**改造**:
- `ProposalPanel.vue`: `import { proposalStatusLabel, proposalStatusBadge } from '@/constants/proposalStatus'`
- `VerifyItemDetail.vue`: 同样（item 状态 `verified/collected/success/missing/failed/skipped` 单独建一个 `verifyItemStatus.ts`，不复用 proposalStatus）
- `AssetVerifyReport.vue`: 同样

---

### 8. I3: N+1 修复（`_collect_port_reachability` + `get_asset_report`）

**位置**: `collector_service.py:1495-1535`、`batch_collector_service.py:1083-1100`

**修复 `_collect_port_reachability`**:
```python
# 收集完所有 item 后, 批量查 DbInstance / Server
db_ids = {item.db_instance_id for item in run_items if item.db_instance_id}
server_ids = {item.server_id for item in run_items if item.server_id}
db_map = {row.id: row for row in db.query(DbInstance).filter(DbInstance.id.in_(db_ids)).all()} if db_ids else {}
server_map = {row.id: row for row in db.query(Server).filter(Server.id.in_(server_ids)).all()} if server_ids else {}
# 然后在 loop 里用 map 查
```

**修复 `get_asset_report`**:
```python
# 一次性 in_(...) 加载 DbInstance (含 selectinload cluster), 然后 Python 构建 group dict
distinct_instance_ids = list({int(g["entity_id"]) for g in groups if g["entity_type"] == "db_instance"})
if distinct_instance_ids:
    instances = db.query(DbInstance).options(selectinload(DbInstance.cluster)).filter(
        DbInstance.id.in_(distinct_instance_ids)
    ).all()
    instance_map = {inst.id: inst for inst in instances}
```

**性能验证**:
```bash
# 1000 实例批次下: 看 log 里的 SQL 数量
# 改前: ~3000 SQL (get_asset_report + 后续 build_cluster_type_hint)
# 改后: ~10 SQL
```

---

### 9. I4: 30-runbook.md 行 50 同步

**位置**: `docs/30-runbook.md:50`

**修复**: 把"`+ CONNECTIVITY_GATE_FAILED`"改成"`+ 4 个 SKIP_REASON_* code`"，列具体 code + alias 关系：
```markdown
✅ 已修复（2026-06-17+2026-06-20）：playbook 门控在无端口检测项时不生效；后端空 items 时写 skipped + 4 个具体 skip_reason：
  - PORT_CANDIDATE_CONFLICT — 端口候选冲突无法决定
  - PORT_DRIFT_SUSPECTED — 端口漂移可疑
  - OS_FACT_UNSUPPORTED_WINDOWS — Windows OS 跳过 fact
  - CALLBACK_RESULT_MISSING — callback 缺结果
CONNECTIVITY_GATE_FAILED 作为 backward-compat alias 保留。
```

---

### 10. I5: record_event 修正 before/after 语义

**位置**: `asset_proposal_service.py:347-348`

**修复**: 进入 dispatch 前快照 `before_status`，写后再取 `after_status`：
```python
# 进入 apply_proposal 的 db_instance 分支前:
before_status = getattr(instance, "trust_status", None)
# ... dispatch ...
# 写完所有字段后:
after_status = getattr(instance, "trust_status", None)
record_event(..., before_status=before_status, after_status=after_status)
```

**测试**:
- `test_apply_proposal_record_event_captures_real_before_status` — seed trust_status="verified", apply 改 port，event 记录 before=verified / after=unverified

---

### 11. I7: batch-action / asset-report 加 response_model

**位置**: `backend/app/schemas/collector.py`（新增）、`backend/app/api/collector.py`（设 response_model）

**新 schema**:
```python
class BatchActionResultEntry(BaseModel):
    id: int
    success: bool
    error: str | None = None

class BatchActionResultResponse(BaseModel):
    action: Literal["approve", "reject", "apply"]
    results: list[BatchActionResultEntry]
    success_count: int
    fail_count: int

class AssetReportAssetResponse(BaseModel):
    asset_id: int
    entity_type: str
    cluster_type_suspected: dict | None = None
    # ... 其余字段

class AssetReportResponse(BaseModel):
    batch_run_id: int
    batch_code: str
    assets: list[AssetReportAssetResponse]
```

**修复 API 层**: `response_model=BatchActionResultResponse` / `response_model=AssetReportResponse`

**前端**: 删 `assets.ts:331-371` 的 inline type，import `AssetReportResponse` from `@/types/api`。

---

### 12. I8: _FakeSavepoint 真回滚

**位置**: `backend/tests/test_dbops_asset_service.py:228-237`

**修复**:
```python
class _FakeSavepoint:
    def __init__(self, session, snapshot):
        self.session = session
        self.snapshot = snapshot  # dict: obj_id -> (attr_name, old_value)

    def commit(self):
        self.snapshot.clear()  # 已成功的归 db.commit() 管

    def rollback(self):
        # 真回滚：恢复 begin_nested 时的属性值
        for obj, attr, old in self.snapshot.values():
            setattr(obj, attr, old)
        self.snapshot.clear()
```

**关键点**: `begin_nested()` 时遍历 session 里所有 tracked 对象的 dirty 状态做 snapshot；`rollback()` 恢复。

**验证**: `test_batch_action_uses_savepoint_partial_failure` 应该仍然绿（已有行为），但现在真在测回滚语义。

---

### 13. I11+I14+I15+A1+A2+A8: 杂项收口

**I11 - drift current_value None 路径**:
- 位置: `drift_detection_service.py:217-221`
- 决策: 改成"info-only"，不报 actionable drift（与 C3 auto-create 解耦）
- 修复:
  ```python
  elif current_value is None:
      # 字典未登记视为信息缺失，不是漂移
      is_drift = False
      # 仍记一条 info-only drift record, 但不创建 proposal
  ```
- 测试: `test_detect_for_snapshot_null_formal_value_no_actionable_drift`

**I14 - collector.py:540 冗余 import**:
- 修复: 删方法内的 `from app.services.batch_collector_service import BatchCollectorService`

**I15 - schema __init__ 导出**:
- 修复: `backend/app/schemas/__init__.py` 加 `from .collector import CollectorCheckDefinitionResponse` + 加到 `__all__`

**A1 - backend/nohup.out**:
- 修复: `echo 'backend/nohup.out' >> backend/.gitignore` + `git rm --cached backend/nohup.out` (如已 add)

**A2 - .claude/plans/**:
- 修复: `echo '.claude/plans/' >> .gitignore`（确认 policy 后）

**A8 - build_cluster_type_hint 静默 except**:
- 位置: `batch_collector_service.py:1096`
- 修复: 缩窄到 `except (AttributeError, TypeError)`，加 `logger.warning` 保留可观测性

---

## P2 — 5 Important + 5 Advisory（可选合并, 1.5 工时）

### 14. I9: collector_check_definition_service 抽 base 模板

**新文件**: `backend/app/services/_definition_service_base.py`

```python
class BaseDefinitionService:
    """1:1 共享 list + _to_dict 模板, 被 port_profile_service / collector_check_definition_service 共用"""
    model: type
    enabled_field: str = "enabled"

    @classmethod
    def list(cls, db, **filters):
        query = db.query(cls.model)
        for k, v in filters.items():
            if v is not None:
                query = query.filter(getattr(cls.model, k) == v)
        return [cls._to_dict(row) for row in query.all()]

    @classmethod
    def _to_dict(cls, row):
        raise NotImplementedError
```

**改造**:
- `port_profile_service.PortProfileService` 改成 `PortProfileService(BaseDefinitionService)`
- `collector_check_definition_service.CollectorCheckDefinitionService` 同样

### 15. I10: apply_proposal 抽 applier 注册表

**新位置**: `asset_proposal_service.py` 同文件

```python
DB_INSTANCE_APPLIERS: dict[str, Callable] = {
    "port": _apply_port,
    "instance_name": _apply_str_field,
    "service_name": _apply_str_field,
    "node_role": _apply_node_role,
    "db_size_gb": _apply_float_field,
    "db_version": _apply_db_version,
}
SERVER_APPLIERS: dict[str, Callable] = {
    "hostname": _apply_str_field,
    "cpu_cores": _apply_int_field,
    "memory_gb": _apply_float_field,
    "disk_gb": _apply_float_field,
}

def apply_proposal(db, proposal_id, operator, selected_value=None):
    # ... whitelist + selected_value guard + before_snapshot ...
    applier = (DB_INSTANCE_APPLIERS if proposal.target_type == "db_instance" else SERVER_APPLIERS).get(field_path)
    if not applier:
        raise ValueError(f"field_path {field_path} 不在白名单")
    applier(...)
    # ... event record ...
```

效果: 200 行变 50 行；新增字段 = 加一行注册表。

### 16. I12+I13: 前端类型集中

**I12**:
- `frontend/src/types/api.ts` 新增 `export interface AssetReport { ... }` + `export interface AssetReportAsset { ... }`
- 删 `AssetVerifyReport.vue:95-114` 的 inline interface
- 改 `assets.ts:351-371` 返回类型

**I13**:
- `ProposalPanel.vue` 的 local `Proposal` 删，改 `import type { AssetChangeProposalRow as Proposal }`
- `VerifyItemDetail.vue` 的 local `VerifyItem` 删，改 `import type { CollectorRunItemRow }` + `Pick<>` 缩小

### 17. I16: classify_skip_reason 参数化

**位置**: `backend/tests/test_collector_tasks_p0_4_5_6.py:1755-1886`

```python
@pytest.mark.parametrize("check_code,reachability,expected_reason", [
    ("DB_BASIC_FACT_COLLECTION", {}, "CALLBACK_RESULT_MISSING"),
    ("DB_BASIC_FACT_COLLECTION", {1521: "unreachable"}, "PORT_DRIFT_SUSPECTED"),
    ("DB_BASIC_FACT_COLLECTION", {1521: "reachable"}, None),  # 不应被 skip
    ("OS_BASIC_FACT_COLLECTION", {}, "OS_FACT_UNSUPPORTED_WINDOWS"),
    ("DB_VERSION_FACT_COLLECTION", {}, "CALLBACK_RESULT_MISSING"),
    ("UNKNOWN_CHECK_CODE", {}, "CALLBACK_RESULT_MISSING"),
])
def test_classify_skip_reason(check_code, reachability, expected_reason):
    ...
```

### 18. A3+A4+A5+A6+A7+A9: 杂项清理

- **A3** `drift_detection_service.py:17-18`: logger 移到 import 块外
- **A4** `collector.py:103-104`: 删 I11 陈旧注释块
- **A5** `AssetVerifyReport.vue:149-157`: 删 `formatPortStatus` / `formatFactStatus` no-op 包装
- **A6** `collector_service.py:948-965`: `_is_windows_target` 改早返
- **A7** `asset_proposal_service.py:367-388`: 抽 `_coerce_int_field`（与 C1 合并）
- **A9** `collector_service.py:1477`: SSH 端口解析失败加 `logger.warning(server_id, ssh_port)`

---

## 已记录、待下轮 (Backlog)

| ID | 项 | 备注 |
|---|---|---|
| I9 | collector_check_definition_service 1:1 克隆 | P2 修（不阻塞） |
| I10 | apply_proposal 200 行 if/elif | P2 修（不阻塞） |
| I13 | VerifyItem / Proposal 局部 interface | P2 修 |
| I16 | 6 个 classify_skip_reason 测试参数化 | P2 修 |
| A3 | drift_detection logger import 位置 | P2 修 |
| A4 | I11 陈旧注释块 | P2 修 |
| A5 | formatPortStatus no-op 包装 | P2 修 |
| A6 | _is_windows_target 4 重三元 | P2 修 |
| A7 | apply_proposal 三段 int-coerce 块重复 | 与 C1 合并修 |
| A9 | SSH 端口解析失败静默 | P2 修 |

---

## 实施顺序

```
Phase A — Critical 数据正确性 (2 工时)
  A1. C1+C2+C3 apply_proposal 三处数据 bug (1h, 5 tests)
       └─ 顺带做 A7 (coerce helper 抽取)
  A2. C4 SAVEPOINT 改造 (30min, 1 test)
  A3. C5 _create_change_proposal 异常分流 (20min, 2 tests)

Phase B — Critical 测试补齐 (1.5 工时)
  B1. C6 重建 test_drift_detection_service.py (45min, 5 tests)
  B2. C7 补 db_version / db_size_gb happy-path 测试 (30min, 6 tests)
  B3. C8 3 端点 HTTP 集成测试 (45min, 9 tests)

Phase C — Important 前端 (1 工时)
  C1. I1+I6 ApplyableField union + target_type 去 | string (15min, vue-tsc 验证)
  C2. I2 proposalStatus 集中化 (3 组件改造, 30min)
  C3. I12+I13 前端类型集中 (AssetReport / Proposal / VerifyItem) (15min)

Phase D — Important 后端架构 (1.5 工时)
  D1. I3 N+1 修复 (_collect_port_reachability + get_asset_report) (45min, 性能 log 对比)
  D2. I5 record_event before/after 真语义 (20min, 1 test)
  D3. I7 response_model (30min, OpenAPI 验证)
  D4. I8 _FakeSavepoint 真回滚 (30min, 现有测试更新)
  D5. I11 drift None 路径 info-only (20min, 1 test)
  D6. I14+I15+A8 杂项 (15min)

Phase E — I4 文档同步 (15min)
  E1. 30-runbook.md 行 50 同步 4 code + alias

Phase F — 仓库卫生 (10min)
  F1. A1+A2 nohup.out + .claude/plans/ 加 .gitignore

Phase G — P2 重构 (1.5 工时, 可后置)
  G1. I9 BaseDefinitionService 抽 base (30min)
  G2. I10 apply_proposal applier 注册表 (45min)
  G3. I16 classify_skip_reason 参数化 (15min)
  G4. A3+A4+A5+A6+A9 杂项 (15min)

Phase H — 验证
  H1. bash scripts/ai/verify.sh (193 → 230+ passed)
  H2. live API 验证 (3 端点 + 1 batch-action partial)
  H3. frontend build (vue-tsc 0 errors)
  H4. AWX e2e: 1000 实例批次 get_asset_report 性能对比
  H5. DB 直查: 验证 ghost DbVersion 行不再出现 (C3 验证)
```

**总工时**: 5.5 工时 P0+P1 + 1.5 工时 P2 = **7 工时**

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| C1/C2/C3 改 coerce 类型可能回归 (memory_gb 之前 int 数据回写) | 改前 dump 5 条 sample, 改后 diff; pgsql 加 type cast |
| C4 SAVEPOINT 改造可能与现有 `db.rollback()` 调用链冲突 | 只改 IntegrityError 那一处; 其他地方不动 |
| I3 N+1 修复可能改语义 (空 instance cluster) | 改前抓 log 对比 1 批次输出, 字段级 diff |
| I7 response_model 改 OpenAPI 后前端 inline type 不匹配 | 一次性把所有 inline type 都迁到 types/api.ts |
| I8 _FakeSavepoint 真回滚可能让现有 7 个测试 fail | 跑一遍 test_dbops_asset_service.py 看红绿, 按需调整 |

---

## 完成标准

- [ ] Phase A-F 全部 commit, working tree 干净（**PENDING** — per CLAUDE.md 不自动 commit，等用户指令）
- [x] verify.sh 223 passed 0 failed（实际：223 passed, plan 写 230+ 是乐观估计）
- [ ] live API: asset-report / apply-with-value / batch-action / check-codes 4 端点全 200（**PENDING** — 需 DB+backend 运行；本轮未执行）
- [x] frontend build (vue-tsc) 0 errors
- [x] nohup.out 已 gitignore（`.claude/plans/` **未** gitignore — 用户后续会话可能要看 plan 故保留）
- [x] 30-runbook.md 已同步
- [ ] (可选) Phase G P2 重构 commit（**PENDING**）

## 本轮实施明细 (2026-06-20)

### ✅ 已完成（23 项）

| ID | 任务 | 涉及文件 |
|---|---|---|
| C1+C2+C3+A7 | apply_proposal _coerce_field + APPLYABLE_NODE_ROLES + db_version 幂等 | `backend/app/services/asset_proposal_service.py` |
| C4 | SAVEPOINT 改造 | `backend/app/services/collector_service.py:1096-1117` |
| C5+A3 | 异常分流 + logger 位置 | `backend/app/services/drift_detection_service.py` |
| C6 | 重建 test_drift_detection_service.py（7 tests） | `backend/tests/test_drift_detection_service.py` (新建) |
| C7 | db_version/db_size_gb 6 happy-path tests | `backend/tests/test_dbops_asset_service.py` |
| C8 | 3 端点 9 HTTP tests | `backend/tests/test_collector_api_endpoints.py` (新建) |
| I1+I6+I12 | TS union 补全 + 移除 `\| string` + AssetReport 接口 | `frontend/src/types/api.ts` |
| I2 | 状态颜色/标签集中化 | `frontend/src/constants/proposalStatus.ts`、`verifyItemStatus.ts` (新建) + 3 个 SFC 改造 |
| I3 | N+1 修复 | `collector_service.py:1453-1486`、`batch_collector_service.py:1083-1100` |
| I5 | record_event before/after 真语义 | `asset_proposal_service.py:347-348` |
| I8 | _FakeSavepoint snapshot-based 真回滚 | `backend/tests/test_dbops_asset_service.py:228-237` |
| I11 | drift current_value None → info-only | `drift_detection_service.py` + 1 test |
| I13 | 局部 interface 移除 | `ProposalPanel.vue`、`VerifyItemDetail.vue`、`AssetVerifyReport.vue` |
| I14 | 删 collector.py:540 冗余 import | `backend/app/api/collector.py` |
| I15 | CollectorCheckDefinitionResponse 导出 | `backend/app/schemas/__init__.py` |
| I4 | runbook 同步 4 skip_reason code | `docs/30-runbook.md:50` |
| A1+A2 | nohup.out gitignore | `.gitignore`、`backend/.gitignore` |
| A5 | 删 formatPortStatus/formatFactStatus no-op | `frontend/src/components/ops/AssetVerifyReport.vue` |
| A8 | except Exception → (AttributeError, TypeError) + warning | `batch_collector_service.py:1096` |
| A9 | SSH 端口解析失败 logger.warning | `collector_service.py:1477` |

### ⏸ 待下轮（10 项 P2/可选）

| ID | 项 | 备注 |
|---|---|---|
| **I7** | batch-action / asset-report response_model | 真实 pending — 端点未声明 `response_model=`，schemas 不存在 |
| I9 | collector_check_definition_service 抽 base | 1:1 克隆 port_profile_service，可后置 |
| I10 | apply_proposal 200 行 if/elif 阶梯 | applier 注册表重构 |
| I16 | 6 个 classify_skip_reason 测试参数化 | DRY 优化 |
| A3 | drift_detection logger import 位置 | 已合并到 C5 修复中（顺手做了） |
| A4 | I11 陈旧注释块 | collector.py:103-104 |
| A6 | _is_windows_target 4 重三元 | collector_service.py:948-965 |
| A7 | _coerce_field 抽取 | 已合并到 C1 修复中（顺手做了） |

### 已知测试调整

- `test_batch_verify_vue_has_abort_controller` / `test_batch_verify_vue_format_time_type`：从 `BatchVerify.vue` 改指新 composables `useBatchPolling.ts` + `batchVerifyFormatters.ts`（commit a0f49b0 已删原文件）
- `test_get_asset_report_includes_cluster_type_suspected`：mock 加 `m.options.return_value.filter.return_value.all.return_value = [instance]`（适配 selectinload）

### 下轮建议起手

1. **I7 first** — schemas/collector.py 加 `BatchActionResultResponse` + `AssetReportResponse` 两个 schema，collector.py:327 + 530 加 `response_model=`，前端 assets.ts 替换 inline type
2. Phase G P2 — 按 I10 > I9 > I16 顺序重构
3. 完成后整轮 commit (per CLAUDE.md 不自动 commit，需用户触发)
