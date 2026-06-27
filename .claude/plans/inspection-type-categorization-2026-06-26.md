# Plan: 巡检类型 (inspection_type) 分组与筛选

**Date**: 2026-06-26
**Branch**: feature/phase-3.5-db-readonly-sql-exec
**Complexity**: Medium

## Context

当前在 `/inspection/tasks` 创建巡检任务时，巡检项以扁平 checkbox 列表展示，无分组。用户每次需要手动逐个勾选大量巡检项，效率低。用户希望：
1. 将自定义巡检项归类为"Oracle基础巡检项"和"SQL Server基础巡检项"
2. 新增 `inspection_type` 字段作为巡检类型/分组标签
3. 创建任务时按巡检类型分组展示，支持按组一键全选/取消
4. 巡检项管理页支持按巡检类型筛选

## 关键发现

- `inspection_item` 表已有 `category`（VARCHAR(50)）字段，语义为检查类别（info/state/capacity/performance），不用于业务分组
- 已有 `db_type_code` 字段区分 Oracle/SQLServer，但它是 DB 引擎类型而非巡检业务分组
- 前端 Types 中 **尚未包含** `category` 字段；后端有但前端未使用
- 新建 `inspection_type` 独立于 `category` 和 `db_type_code`，语义更清晰

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| DDL migration | `backend/db/dbops_phase3_5_inspection_item_dbtype.sql` | `ALTER TABLE ADD COLUMN IF NOT EXISTS` + partial index + COMMENT |
| ORM column | `dbops_assets.py:754` (`category = Column(String(50))`) | `Column(String(100))` after `category` |
| Pydantic field | `schemas/inspection.py:30` (`category: Optional[str] = None`) | `Optional[str] = None` in create/update/response |
| Service filter | `inspection_service.py:275-276` (`db_type_code` filter) | `query.filter(InspectionItem.inspection_type == value)` |
| Snapshot copy | `inspection_service.py:727` (`category=item.category`) | `inspection_type=item.inspection_type` in task_item creation |
| Frontend filter dropdown | `Items.vue:19-25` (dbTypeFilter select) | `<select v-model>` + `@change="loadItems"` |
| API query param | `api/inspection.py:37-45` (existing Query params) | `Optional[str] = Query(default=None)` |

## Files to Change

| File | Action | Why |
|---|---|---|
| `backend/db/dbops_inspection_v5_2_inspection_type.sql` | **CREATE** | DDL migration: ADD COLUMN + index on `inspection_item` and `inspection_task_item` |
| `backend/db/rollback_inspection_v5_2_inspection_type.sql` | **CREATE** | Rollback script |
| `backend/app/models/dbops_assets.py` | UPDATE | Add `inspection_type = Column(String(100))` to `InspectionItem` (after L754) and `InspectionTaskItem` (after L879) |
| `backend/app/schemas/inspection.py` | UPDATE | Add `inspection_type: Optional[str] = None` to `InspectionItemCreateRequest`(L30), `InspectionItemUpdateRequest`(L48), `InspectionItemResponse`(L68) |
| `backend/app/services/inspection_service.py` | UPDATE | Add to `_item_to_dict`(L167), `_result_to_dict`(L235), `list_items` filter(L276), `create_task` snapshot(L727), new `list_inspection_types()` |
| `backend/app/api/inspection.py` | UPDATE | Add `inspection_type` query param to GET `/inspection/items`, add GET `/inspection/types` |
| `frontend/src/types/api.ts` | UPDATE | Add `inspection_type?: string \| null` to `InspectionItemRow`, `InspectionItemCreatePayload`, `InspectionItemUpdatePayload` |
| `frontend/src/api/assets.ts` | UPDATE | Add `inspection_type` param to `listInspectionItems`, add `listInspectionTypes` method |
| `frontend/src/views/inspection/Tasks.vue` | UPDATE | Replace flat checkbox list with grouped layout + group toggle |
| `frontend/src/views/inspection/Items.vue` | UPDATE | Add `inspection_type` filter dropdown, add field to create/edit form |

## Tasks

### Task 1: Database Migration
- **Action**: Create `dbops_inspection_v5_2_inspection_type.sql` with `ALTER TABLE dbops.inspection_item ADD COLUMN IF NOT EXISTS inspection_type VARCHAR(100)` and same for `inspection_task_item`, plus partial index. Create rollback script.
- **Mirror**: `dbops_phase3_5_inspection_item_dbtype.sql`
- **Validate**: Run migration against dev DB, verify columns exist

### Task 2: ORM Models
- **Action**: Add `inspection_type = Column(String(100))` to `InspectionItem` (after `category` L754) and `InspectionTaskItem` (after `category` L879) in `dbops_assets.py`
- **Mirror**: existing `category = Column(String(50))` pattern
- **Validate**: `python -c "from app.models.dbops_assets import InspectionItem; print('OK')"`

### Task 3: Pydantic Schemas
- **Action**: Add `inspection_type: Optional[str] = None` to `InspectionItemCreateRequest`(after L30), `InspectionItemUpdateRequest`(after L48), `InspectionItemResponse`(after L68)
- **Mirror**: existing `category: Optional[str] = None` pattern
- **Validate**: Schema imports without error

### Task 4: Service Layer
- **Action**:
  1. `_item_to_dict()`: add `"inspection_type": item.inspection_type` after L167
  2. `_result_to_dict()`: add `"inspection_type": item.inspection_type if item else None` after L235
  3. `list_items()`: add `inspection_type: str | None = None` param and filter after L276
  4. `create_task()`: add `inspection_type=item.inspection_type` to `InspectionTaskItem(...)` after L727
  5. Add `list_inspection_types(db)` static method returning distinct non-null inspection_type values
- **Mirror**: existing `category` handling in same methods
- **Validate**: pytest on inspection service tests

### Task 5: API Routes
- **Action**:
  1. Add `inspection_type: Optional[str] = Query(default=None)` to `list_inspection_items`
  2. Add `GET /inspection/types` endpoint calling `InspectionService.list_inspection_types(db)`
- **Mirror**: existing query params on `list_inspection_items`
- **Validate**: `curl -s localhost:60801/v1/inspection/types | jq`

### Task 6: Frontend Types
- **Action**: Add `inspection_type?: string | null` to `InspectionItemRow`, `InspectionItemCreatePayload`, `InspectionItemUpdatePayload` in `api.ts`
- **Mirror**: existing `db_type_code?: string | null` pattern
- **Validate**: `npx vue-tsc --noEmit` no new errors

### Task 7: Frontend API
- **Action**:
  1. Add `inspection_type?: string` to `listInspectionItems` params
  2. Add `listInspectionTypes: (): Promise<string[]> => request.get('/v1/inspection/types')`
- **Mirror**: existing `listInspectionItems` pattern
- **Validate**: vue-tsc passes

### Task 8: Tasks.vue — Grouped Item Selection
- **Action**: Replace the flat checkbox list (L33-45) with a grouped layout:
  1. Add `groupedItems` computed: groups `selectableItems` by `inspection_type || '未分类'`
  2. Add `isGroupSelected(key)`, `isGroupIndeterminate(key)`, `toggleGroup(key)` functions
  3. Template: for each group, render a group header checkbox (with indeterminate support) + individual item checkboxes indented below
  4. Group checkbox: checked = all items selected, indeterminate = some selected, click toggles all
- **Mirror**: existing `selectableItems` computed pattern, form styles from existing checkboxes
- **Validate**: Visual check on `/inspection/tasks` — items grouped, group toggle works, individual toggle works

### Task 9: Items.vue — Inspection Type Filter + Form Field
- **Action**:
  1. Add `inspection_type` filter dropdown to `OpsFilterBar #tools` slot (alongside source/dbType filters)
  2. Load inspection types on mount via `listInspectionTypes()`
  3. Add `inspectionTypeFilter` ref, wire to `loadItems` params
  4. Update `@reset` to clear `inspectionTypeFilter`
  5. Add `inspection_type` field to create/edit form (dropdown selecting from `inspectionTypes`)
  6. Update `ItemForm` interface, `form` reactive, `resetForm()`
- **Mirror**: existing `dbTypeFilter` pattern on same page
- **Validate**: Visual check on `/inspection/items` — filter dropdown populated, filtering works, form has inspection_type field

## Verification

```bash
# 1. Backend tests
cd backend && python -m pytest tests/test_inspection_service.py -v -x

# 2. Schema import check
python -c "from app.schemas.inspection import InspectionItemCreateRequest, InspectionItemResponse; print('OK')"

# 3. Frontend type check
cd frontend && npx vue-tsc --noEmit

# 4. Full verify
bash scripts/ai/verify.sh

# 5. Live API smoke test
curl -s http://localhost:60801/v1/inspection/types | jq
curl -s "http://localhost:60801/v1/inspection/items?inspection_type=Oracle%E5%9F%BA%E7%A1%80%E5%B7%A1%E6%A3%80" | jq '.[].item_code'
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Existing items have NULL inspection_type → all land in "未分类" | High | Accept as designed; user can edit items to assign types |
| Frontend checkbox list gets very tall with grouping | Low | Groups are visually separated; most users will have 2-3 groups |
| `list_inspection_types` returns empty initially | Medium | Accept; dropdown shows "全部巡检类型" default; populate after user assigns types |

## Acceptance

- [ ] DDL migration applies cleanly to dev DB
- [ ] Backend CRUD includes `inspection_type` field throughout
- [ ] GET `/inspection/types` returns distinct type list
- [ ] GET `/inspection/items?inspection_type=X` filters correctly
- [ ] Tasks.vue shows items grouped by inspection_type with group-level checkboxes
- [ ] Group toggle selects/deselects all items in that group
- [ ] Items.vue has inspection_type filter and form field
- [ ] verify.sh passes (pytest + vue-tsc)
- [ ] Backward compatible: NULL inspection_type items work (show as "未分类")
