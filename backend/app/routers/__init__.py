"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import external_label, resource

# external_label 含 /api/compliance_check/scan_reports 等静态路径，
# 必须先于通用资源路由注册，避免被 /{module}/{entry_id} 抢先匹配。
ROUTERS = [external_label, resource]
