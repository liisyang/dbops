/// <reference types="vite/client" />

import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'

// Type declaration for window.__VITE_ROUTER__
declare global {
  interface Window {
    __VITE_ROUTER__?: ReturnType<typeof createRouter>
  }
}
import Login from '@/views/Login.vue'
import Layout from '@/views/Layout.vue'
import Dashboard from '@/views/Dashboard.vue'
import Inventory from '@/views/Inventory.vue'
import Servers from '@/views/Servers.vue'
import Assets from '@/views/Assets.vue'
import Contacts from '@/views/Contacts.vue'
import Import from '@/views/Import.vue'
import Stats from '@/views/Stats.vue'
import Clusters from '@/views/Clusters.vue'
import Instances from '@/views/Instances.vue'
import InstanceDetail from '@/views/InstanceDetail.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresAuth: false, title: '登录' }
  },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    children: [
      // 仪表盘
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: Dashboard,
        meta: { title: '仪表盘' }
      },
      // 自动化运维
      {
        path: 'ops/inventory',
        name: 'OpsInventory',
        component: Inventory,
        meta: { title: '主机清单', parent: '自动化运维' }
      },
      {
        path: 'ops/tasks',
        name: 'OpsTasks',
        component: () => import('@/views/ops/Tasks.vue'),
        meta: { title: '作业执行', parent: '自动化运维' }
      },
      // 资产管理
      {
        path: 'assets/servers',
        name: 'AssetServers',
        component: Servers,
        meta: { title: '服务器', parent: '资产管理' }
      },
      {
        path: 'assets/servers/new',
        name: 'AssetServerCreate',
        component: Servers,
        meta: { title: '新增服务器', parent: '资产管理' }
      },
      {
        path: 'assets/servers/:id',
        name: 'AssetServerDetail',
        component: Servers,
        meta: { title: '服务器详情', parent: '资产管理' }
      },
      {
        path: 'assets/instances',
        name: 'AssetInstances',
        component: Instances,
        meta: { title: '数据库实例', parent: '资产管理' }
      },
      {
        path: 'assets/instances/:id',
        name: 'AssetInstanceDetail',
        component: InstanceDetail,
        meta: { title: '实例详情', parent: '资产管理' }
      },
      {
        path: 'assets/import',
        name: 'AssetImport',
        component: Import,
        meta: { title: '导入', parent: '资产管理' }
      },
      {
        path: 'assets/stats',
        name: 'AssetStats',
        component: Stats,
        meta: { title: '资产统计', parent: '资产管理' }
      },
      {
        path: 'assets/clusters',
        name: 'AssetClusters',
        component: Clusters,
        meta: { title: '集群', parent: '资产管理' }
      },
      {
        path: 'assets/businesses',
        name: 'AssetBusinesses',
        component: Assets,
        meta: { title: '业务', parent: '资产管理' }
      },
      {
        path: 'assets/contacts',
        name: 'AssetContacts',
        component: Contacts,
        meta: { title: '联系人', parent: '资产管理' }
      },
      {
        path: 'assets/businesses/:id',
        name: 'AssetBusinessDetail',
        component: () => import('@/views/BusinessSystemDetail.vue'),
        meta: { title: '业务详情', parent: '资产管理' }
      },
      {
        path: 'assets/clusters/:clusterCode',
        name: 'AssetClusterDetail',
        component: () => import('@/views/ClusterDetail.vue'),
        meta: { title: '集群详情', parent: '资产管理' }
      },
      // 备份与恢复
      {
        path: 'backup/policies',
        name: 'BackupPolicies',
        component: () => import('@/views/backup/Policies.vue'),
        meta: { title: '备份策略', parent: '备份与恢复' }
      },
      {
        path: 'backup/jobs',
        name: 'BackupJobs',
        component: () => import('@/views/backup/Jobs.vue'),
        meta: { title: '备份作业', parent: '备份与恢复' }
      },
      {
        path: 'backup/restore',
        name: 'BackupRestore',
        component: () => import('@/views/backup/Restore.vue'),
        meta: { title: '恢复中心', parent: '备份与恢复' }
      },
      // SQL分析
      {
        path: 'sql/audit',
        name: 'SqlAudit',
        component: () => import('@/views/sql/Audit.vue'),
        meta: { title: 'SQL审计', parent: 'SQL分析' }
      },
      {
        path: 'sql/slow',
        name: 'SqlSlow',
        component: () => import('@/views/sql/SlowQuery.vue'),
        meta: { title: '慢查询', parent: 'SQL分析' }
      },
      {
        path: 'sql/top',
        name: 'SqlTop',
        component: () => import('@/views/sql/TopSql.vue'),
        meta: { title: 'TOP SQL', parent: 'SQL分析' }
      },
      // 巡检与健康
      {
        path: 'inspection/reports',
        name: 'InspectionReports',
        component: () => import('@/views/inspection/Reports.vue'),
        meta: { title: '巡检报告', parent: '巡检与健康' }
      },
      {
        path: 'inspection/health',
        name: 'InspectionHealth',
        component: () => import('@/views/inspection/Health.vue'),
        meta: { title: '健康检查', parent: '巡检与健康' }
      },
      // 审计与安全
      {
        path: 'audit/operations',
        name: 'AuditOperations',
        component: () => import('@/views/audit/Operations.vue'),
        meta: { title: '操作日志', parent: '审计与安全' }
      },
      {
        path: 'audit/login',
        name: 'AuditLogin',
        component: () => import('@/views/audit/LoginLogs.vue'),
        meta: { title: '登录日志', parent: '审计与安全' }
      },
      {
        path: 'audit/sensitive',
        name: 'AuditSensitive',
        component: () => import('@/views/audit/Sensitive.vue'),
        meta: { title: '敏感操作', parent: '审计与安全' }
      },
      // 凭证中心
      {
        path: 'credentials/ssh',
        name: 'CredentialsSsh',
        component: () => import('@/views/credentials/Ssh.vue'),
        meta: { title: 'SSH凭证', parent: '凭证中心' }
      },
      {
        path: 'credentials/db',
        name: 'CredentialsDb',
        component: () => import('@/views/credentials/Db.vue'),
        meta: { title: '数据库凭证', parent: '凭证中心' }
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/knowledge/Index.vue'),
        meta: { title: '知识库' }
      },
      {
        path: 'ui-preview/assets',
        name: 'UiPreviewAssets',
        component: () => import('@/views/ui-preview/AssetsPreview.vue'),
        meta: { title: 'UI 预览-资产', parent: '开发预览' }
      },
      {
        path: 'ui-preview/instances.vue',
        name: 'UiPreviewInstances',
        component: () => import('@/views/ui-preview/instances.vue'),
        meta: { title: 'UI 预览-实例', parent: '开发预览' }
      },
      {
        path: 'ui-preview/servers.vue',
        name: 'UiPreviewServers',
        component: () => import('@/views/ui-preview/servers.vue'),
        meta: { title: 'UI 预览-服务器', parent: '开发预览' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 挂载 router 到 window 供 request.js 等模块使用
window.__VITE_ROUTER__ = router

// 路由守卫
router.beforeEach((to, _from, next) => {
  if (to.meta.requiresAuth !== false) {
    const token = localStorage.getItem('token')
    if (!token) {
      next('/login')
      return
    }
  }
  next()
})

export default router
