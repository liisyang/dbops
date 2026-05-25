"""
服务器资产 API v3.0
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, Literal, Optional, List

from app.services.asset_event_history_service import event_to_dict
from app.services.dbops_asset_service import DbopsAssetService
from app.services.dbops_contact_service import DbopsContactService
from app.services.dbops_import_service import DbopsImportService
from app.services.dbops_stats_service import DbopsStatsService
from app.models.user import User
from app.api.deps import get_current_user, get_db

router = APIRouter()


class BusinessLifecycleRequest(BaseModel):
    action: Literal["building", "pending", "active", "retired"]
    reason: Optional[str] = None
    remark: Optional[str] = None
    lifecycle_context: dict[str, Any] = Field(default_factory=dict)


class ContactUpsertRequest(BaseModel):
    employee_no: Optional[str] = None
    contact_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    dept: Optional[str] = None
    remark: Optional[str] = None


class BusinessSystemUpsertRequest(BaseModel):
    system_name: str
    business_unit: Optional[str] = None
    department: Optional[str] = None
    service_scope: Optional[str] = None
    biz_level: Optional[str] = None
    remark: Optional[str] = None
    system_group_id: Optional[int] = None


class BusinessContactLinkRequest(BaseModel):
    contact_id: int
    role_code: str
    remark: Optional[str] = None


class ClusterUpsertRequest(BaseModel):
    cluster_name: str
    business_system_id: int
    db_type_id: int
    cluster_type: str
    status: Optional[str] = None
    remark: Optional[str] = None
    vip_addresses: list[str] = []


class DbInstanceUpsertRequest(BaseModel):
    instance_name: str
    cluster_id: int
    db_type_id: int
    server_id: int
    db_version_id: Optional[int] = None
    node_role: str
    service_name: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


# ---------- 实例管理 ----------

@router.get("/instances")
async def list_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=2000),
    search: str = "",
    db_type: Optional[str] = None,
    bia_level: Optional[str] = None,
    cluster_role: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取实例列表"""
    rows = DbopsAssetService.list_instances(db=db)
    if search:
        search_lower = search.lower()
        rows = [
            row for row in rows
            if search_lower in str(row.get("instance_name", "")).lower()
            or search_lower in str(row.get("cluster_code", "")).lower()
            or search_lower in str(row.get("server_ip", "")).lower()
        ]
    if db_type:
        rows = [row for row in rows if row.get("db_type") == db_type]
    if cluster_role:
        rows = [row for row in rows if row.get("node_role") == cluster_role]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    start = (page - 1) * page_size
    end = start + page_size
    return {"total": len(rows), "page": page, "page_size": page_size, "items": rows[start:end]}


@router.get("/instances/{instance_id}")
async def get_instance(
    instance_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取实例详情"""
    data = DbopsAssetService.get_instance_detail(db=db, instance_id=int(instance_id))
    if not data:
        raise HTTPException(status_code=404, detail="实例不存在")
    return data


# ---------- 服务器管理 ----------

@router.get("/servers")
async def list_servers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=2000),
    search: str = "",
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取服务器列表"""
    rows = DbopsAssetService.list_servers(db=db)
    if search:
        search_lower = search.lower()
        rows = [
            row for row in rows
            if search_lower in str(row.get("hostname", "")).lower()
            or search_lower in str(row.get("ip_address", "")).lower()
        ]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    start = (page - 1) * page_size
    end = start + page_size
    return {"total": len(rows), "page": page, "page_size": page_size, "items": rows[start:end]}


@router.get("/servers/{server_id}")
async def get_server(
    server_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取服务器详情"""
    data = DbopsAssetService.get_server_detail(db=db, server_id=int(server_id))
    if not data:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return data


@router.post("/servers")
async def create_server(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建服务器"""
    if not data.get("ip") and not data.get("ip_address"):
        raise HTTPException(status_code=400, detail="IP地址不能为空")
    server_id = DbopsAssetService.create_server(db=db, data=data)
    return {"id": server_id}, 201


@router.put("/servers/{server_id}")
async def update_server(
    server_id: str,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新服务器"""
    updated = DbopsAssetService.update_server(db=db, server_id=int(server_id), data=data)
    if not updated:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return {"message": "更新成功"}


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除服务器"""
    deleted = DbopsAssetService.delete_server(db=db, server_id=int(server_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="服务器不存在")
    return {"message": "删除成功"}


@router.post("/servers/batch-delete")
async def batch_delete_servers(
    ids: List[str] = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批量删除服务器"""
    deleted = 0
    for sid in ids:
        try:
            DbopsAssetService.delete_server(db=db, server_id=int(sid))
            deleted += 1
        except Exception:
            pass
    return {"deleted": deleted, "total": len(ids)}


# ---------- 联系人管理 ----------

@router.get("/contacts")
async def list_contacts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取联系人列表"""
    return DbopsContactService.list_contacts(db=db)


@router.post("/contacts")
async def create_contact(
    payload: ContactUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建联系人"""
    contact = DbopsContactService.upsert_contact(db=db, payload=payload.model_dump())
    return {"id": contact.id}, 201


@router.put("/contacts/{contact_id}")
async def update_contact(
    contact_id: int,
    payload: ContactUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新联系人"""
    contact = DbopsContactService.upsert_contact(
        db=db,
        payload=payload.model_dump(),
        contact_id=contact_id,
    )
    return {"id": contact.id}


@router.delete("/contacts/{contact_id}")
async def delete_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除联系人"""
    DbopsContactService.delete_contact(db=db, contact_id=contact_id)
    return {"message": "删除成功"}


# ---------- 字典数据 ----------

@router.get("/business-services")
async def list_business_services(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取业务系统及其 DB 绑定关系"""
    return DbopsAssetService.list_business_systems(db=db)


@router.post("/business-services")
async def create_business_service(
    payload: BusinessSystemUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建业务系统"""
    system = DbopsAssetService.upsert_business_system(db=db, fields=payload.model_dump())
    return {"id": system.id}, 201


@router.put("/business-services/{system_id}")
async def update_business_service(
    system_id: int,
    payload: BusinessSystemUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新业务系统"""
    system = DbopsAssetService.upsert_business_system(
        db=db,
        fields=payload.model_dump(),
        system_id=system_id,
    )
    return {"id": system.id}


@router.get("/business-services/{system_id}")
async def get_business_service_detail(
    system_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取业务系统详情"""
    data = DbopsAssetService.get_business_system_detail(db=db, system_id=system_id)
    if not data:
        raise HTTPException(status_code=404, detail="业务系统不存在")
    return data


@router.get("/business-services/{system_id}/lifecycle/history")
async def list_business_service_lifecycle_history(
    system_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取业务系统生命周期历史"""
    history = DbopsAssetService.list_business_lifecycle_history(db=db, system_id=system_id)
    return [event_to_dict(item) for item in history]


@router.post("/business-services/{system_id}/lifecycle")
async def change_business_service_lifecycle(
    system_id: int,
    payload: BusinessLifecycleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """变更业务系统生命周期状态"""
    try:
        result = DbopsAssetService.change_business_status(
            db=db,
            system_id=system_id,
            action=payload.action,
            reason=payload.reason,
            remark=payload.remark,
            operator=current_user.username,
            lifecycle_context=payload.lifecycle_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not result:
        raise HTTPException(status_code=404, detail="业务系统不存在")

    history = result["history"]
    business_system = result["business_system"]
    return {
        "id": business_system.id,
        "status": business_system.status,
        "history_id": history.id,
        "history": event_to_dict(history),
    }


@router.post("/business-services/{system_id}/contacts")
async def add_business_service_contact(
    system_id: int,
    payload: BusinessContactLinkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """给业务系统绑定联系人"""
    link = DbopsAssetService.upsert_business_contact_link(
        db=db,
        business_system_id=system_id,
        contact_id=payload.contact_id,
        role_code=payload.role_code,
        remark=payload.remark,
    )
    return {"id": link.id}, 201


@router.delete("/business-services/{system_id}/contacts/{contact_id}/{role_code}")
async def delete_business_service_contact(
    system_id: int,
    contact_id: int,
    role_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解绑业务系统联系人"""
    deleted = DbopsAssetService.delete_business_contact_link(
        db=db,
        business_system_id=system_id,
        contact_id=contact_id,
        role_code=role_code,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="业务联系人关系不存在")
    return {"message": "删除成功"}


# ---------- 统计 ----------

@router.get("/stats/dashboard")
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取仪表板统计"""
    return DbopsStatsService.dashboard(db=db)


@router.get("/stats/by-country")
async def stats_by_country(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按国家分组统计"""
    return DbopsStatsService.by_country(db=db)


@router.get("/stats/by-factory")
async def stats_by_factory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按厂区分组统计"""
    return DbopsStatsService.by_factory(db=db)


@router.get("/stats/by-cluster")
async def stats_by_cluster(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按集群分组统计"""
    return {"groups": DbopsAssetService.list_clusters(db=db)}


@router.get("/stats/by-deploy-type")
async def stats_by_deploy_type(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按部署类型分组统计"""
    return DbopsStatsService.by_deploy_type(db=db)


@router.get("/stats/by-provider")
async def stats_by_provider(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按资源提供方分组统计"""
    return DbopsStatsService.by_provider(db=db)


@router.get("/stats/summary-by-type")
async def stats_summary_by_type(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """总览按 DB 类型分组统计"""
    return DbopsStatsService.by_db_type(db=db)


@router.get("/stats/by-system-group")
async def stats_by_system_group(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按业务大类分组统计"""
    return DbopsStatsService.by_system_group(db=db)


# ---------- 集群管理 ----------

@router.get("/clusters/{cluster_id}/instances")
async def get_cluster_instances(
    cluster_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定集群下的所有实例"""
    return DbopsAssetService.list_instances_by_cluster(db=db, cluster_id=cluster_id)


@router.get("/clusters")
async def list_clusters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取集群列表"""
    return DbopsAssetService.list_clusters(db=db)


@router.get("/clusters/{cluster_id}")
async def get_cluster_detail(
    cluster_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取集群详情"""
    data = DbopsAssetService.get_cluster_detail(db=db, cluster_id=cluster_id)
    if not data:
        raise HTTPException(status_code=404, detail="集群不存在")
    return data


@router.get("/dicts/db-types")
async def list_db_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取数据库类型列表"""
    return DbopsAssetService.list_db_types(db=db)


@router.get("/dicts/servers-dropdown")
async def list_servers_dropdown(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取服务器下拉列表（仅 hostname，不含 IP）"""
    return DbopsAssetService.list_servers_for_dropdown(db=db)


@router.post("/clusters")
async def create_cluster(
    payload: ClusterUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建集群"""
    try:
        cluster = DbopsAssetService.upsert_cluster(db=db, fields=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": cluster.id}, 201


@router.put("/clusters/{cluster_id}")
async def update_cluster(
    cluster_id: int,
    payload: ClusterUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新集群"""
    try:
        cluster = DbopsAssetService.upsert_cluster(db=db, fields=payload.model_dump(), cluster_id=cluster_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": cluster.id}


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(
    cluster_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除集群"""
    try:
        deleted = DbopsAssetService.delete_cluster(db=db, cluster_id=cluster_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="集群不存在")
    return {"message": "删除成功"}


@router.post("/dbinstances")
async def create_dbinstance(
    payload: DbInstanceUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建数据库实例"""
    try:
        instance = DbopsAssetService.upsert_dbinstance(db=db, fields=payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": instance.id}, 201


@router.put("/dbinstances/{instance_id}")
async def update_dbinstance(
    instance_id: int,
    payload: DbInstanceUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新数据库实例"""
    try:
        instance = DbopsAssetService.upsert_dbinstance(db=db, fields=payload.model_dump(), instance_id=instance_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": instance.id}


@router.delete("/dbinstances/{instance_id}")
async def delete_dbinstance(
    instance_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除数据库实例"""
    deleted = DbopsAssetService.delete_dbinstance(db=db, instance_id=instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="实例不存在")
    return {"message": "删除成功"}


# ---------- 导入相关 ----------

@router.post("/imports/preview")
async def preview_import(
    file: UploadFile = File(...),
    mode: str = Form("新增"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """预览导入"""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式")
    try:
        content = await file.read()
        from io import BytesIO
        result = DbopsImportService.preview_import(BytesIO(content), file.filename, db=db, import_mode=mode)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {str(e)}")


@router.post("/imports/execute")
async def execute_import(
    file: UploadFile = File(...),
    mode: str = Form("新增"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """执行导入"""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式")
    try:
        content = await file.read()
        from io import BytesIO
        result = DbopsImportService.execute_import(
            BytesIO(content),
            file.filename,
            current_user.username,
            db,
            import_mode=mode,
        )
        return {
            "import_batch_id": result.get("import_batch_id"),
            "success": result["success"],
            "updated": result.get("updated", 0),
            "error": result["error"],
            "error_count": result["error"],
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
            "warning_count": result.get("warning_count", 0),
            "issue_groups": result.get("issue_groups", []),
            "conflict_count": result.get("conflict_count", 0),
            "import_mode": result.get("import_mode", mode),
            "stage": result.get("stage", "completed"),
            "stage_label": result.get("stage_label", "导入完成"),
            "progress": result.get("progress", 100),
            "message": f"导入完成: 新增 {result['success']} 条, 更新 {result.get('updated', 0)} 条, 失败 {result['error']} 条",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/imports/batches")
async def list_import_batches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取导入批次列表"""
    # 普通用户只看自己的导入记录，admin/dba 看所有
    if current_user.role in ('admin', 'dba'):
        return DbopsImportService.list_import_batches(db)
    else:
        return DbopsImportService.list_import_batches(db, uploaded_by=current_user.username)
