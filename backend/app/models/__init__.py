from app.database import Base, engine, SessionLocal, get_db
from app.models.user import User
from app.models.dbops_assets import (
    DbopsAssetBase, SystemGroup, BusinessSystem, Contact,
    BusinessSystemContact, AssetEventHistory, Site, OsVersion, DbType,
    DbVersion, Server, Cluster, ClusterVip, DbInstance, TopologyRelation,
    CollectorBatchRun, CollectorDispatchRun,
    CollectorRun, CollectorRunItem, CollectorRunResult, CollectorCheckDefinition,
    PortProfile, AssetEndpoint, AssetChangeProposal,
    Tag, ResourceTag, BackupPolicy, InstanceBackupPolicy,
    InspectionItem, InspectionTask, InspectionResult,
    BizScoreRule, BizScoreResult, BizScoreResultDetail, StagingExcelImport,
)
# Phase 3.6 AI Copilot models (C2 范围：chat)
from app.models.ai import AiChatSession, AiChatMessage

db = SessionLocal

__all__ = [
    'Base', 'engine', 'SessionLocal', 'get_db',
    'User',
    'DbopsAssetBase', 'SystemGroup', 'BusinessSystem', 'Contact',
    'BusinessSystemContact', 'AssetEventHistory', 'Site', 'OsVersion', 'DbType',
    'DbVersion', 'Server', 'Cluster', 'ClusterVip', 'DbInstance',
    'CollectorBatchRun', 'CollectorDispatchRun',
    'CollectorRun', 'CollectorRunItem', 'CollectorRunResult', 'CollectorCheckDefinition',
    'PortProfile', 'AssetEndpoint', 'AssetChangeProposal',
    'TopologyRelation', 'Tag', 'ResourceTag', 'BackupPolicy',
    'InstanceBackupPolicy', 'InspectionItem', 'InspectionTask',
    'InspectionResult', 'BizScoreRule', 'BizScoreResult',
    'BizScoreResultDetail', 'StagingExcelImport',
    # Phase 3.6 AI Copilot
    'AiChatSession', 'AiChatMessage',
]
