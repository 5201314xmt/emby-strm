"""
扫描源管理 API 路由 —— CRUD 操作 + 连通性检查

替代旧版的 scan_paths JSON 字符串，每个扫描源独立记录。
"""
import os
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.source import Source
from ..schemas.source import SourceCreate, SourceUpdate, CheckPathRequest
from ..utils.helpers import make_response, now_str
from .deps import get_current_user

router = APIRouter(prefix="/api/sources", tags=["扫描源"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_sources(db: AsyncSession = Depends(get_db)):
    """获取所有扫描源列表"""
    result = await db.execute(select(Source).order_by(Source.id))
    sources = result.scalars().all()

    items = []
    for s in sources:
        items.append({
            "id": s.id,
            "name": s.name,
            "path": s.path,
            "type": s.type,
            "enabled": s.enabled,
            "emby_url": s.emby_url,
            "last_scan_at": s.last_scan_at.strftime("%Y-%m-%d %H:%M:%S") if s.last_scan_at else None,
            "last_scan_status": s.last_scan_status,
            "last_error": s.last_error,
            "show_count": s.show_count,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
        })

    return make_response(True, data={"total": len(items), "items": items})


@router.post("")
async def create_source(
    body: SourceCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加扫描源"""
    # 检查路径是否存在（filesystem 类型）
    if body.type == "filesystem" and not os.path.isdir(body.path):
        return make_response(False, message=f"目录不存在: {body.path}")

    source = Source(
        name=body.name,
        path=body.path,
        type=body.type,
        enabled=True,
        emby_url=body.emby_url,
        emby_api_key=body.emby_api_key,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    return make_response(True, data={"id": source.id}, message=f"已添加扫描源「{body.name}」")


@router.put("/{source_id}")
async def update_source(
    source_id: int,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """修改扫描源"""
    source = await db.get(Source, source_id)
    if not source:
        return make_response(False, message="扫描源不存在")

    # 只更新传入的字段
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(source, key, value)

    await db.commit()
    return make_response(True, message="已更新")


@router.delete("/{source_id}")
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除扫描源"""
    source = await db.get(Source, source_id)
    if not source:
        return make_response(False, message="扫描源不存在")

    await db.delete(source)
    await db.commit()
    return make_response(True, message="已删除")


@router.post("/{source_id}/check")
async def check_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """测试扫描源连通性"""
    source = await db.get(Source, source_id)
    if not source:
        return make_response(False, message="扫描源不存在")

    if source.type == "filesystem":
        if os.path.isdir(source.path):
            try:
                items = os.listdir(source.path)
                return make_response(True, message=f"目录可用，包含 {len(items)} 个文件/文件夹")
            except PermissionError:
                return make_response(False, message="目录存在但没有读取权限")
        else:
            return make_response(False, message=f"目录不存在: {source.path}")
    elif source.type == "emby":
        if not source.emby_url or not source.emby_api_key:
            return make_response(False, message="Emby 地址或 API Key 未填写")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{source.emby_url.rstrip('/')}/emby/System/Info",
                    headers={"X-Emby-Token": source.emby_api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    server_name = data.get("ServerName", "未知服务器")
                    version = data.get("Version", "")
                    return make_response(True, message=f"Emby 连接成功（{server_name} v{version}）")
                return make_response(False, message=f"Emby 返回异常状态码：{resp.status_code}")
        except Exception as e:
            return make_response(False, message=f"Emby 连接失败：{e}")

    return make_response(False, message="未知的源类型")


@router.post("/check-path")
async def check_path(body: CheckPathRequest):
    """
    检查指定路径是否存在（安装向导用）

    输入的是容器内路径（docker-compose 里挂载的 /media 等）。
    """
    path = body.path.strip()
    if not path:
        return make_response(False, message="路径不能为空")

    if not os.path.isdir(path):
        return make_response(False, message=f"目录不存在: {path}")

    try:
        items = os.listdir(path)
        if not items:
            return make_response(True, message=f"目录存在，但里面是空的")
        return make_response(True, message=f"目录可用，包含 {len(items)} 个文件/文件夹")
    except PermissionError:
        return make_response(False, message="目录存在但没有读取权限")
