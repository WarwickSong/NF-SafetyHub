from datetime import UTC, datetime, time, timedelta
import json
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from admin.schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminOperationItem,
    AdminOperationListResponse,
    AdminStatsResponse,
    ApiKeyBulkReplaceItem,
    ApiKeyBulkReplaceRequest,
    ApiKeyBulkReplaceResponse,
    ApiKeyCreateRequest,
    ApiKeyDeleteResponse,
    ApiKeyItem,
    ApiKeyListResponse,
    ApiKeyMutationResponse,
    ApiKeyReplaceRequest,
    ApiKeyRevealResponse,
    ApiKeyUpdateRequest,
    ArchiveDetail,
    ArchiveListResponse,
    ArchiveStatsResponse,
    ArchiveSummary,
    AuditDetail,
    AuditListResponse,
    AuditSummary,
    ImageAssetItem,
    ImageAssetListResponse,
    ObservationItem,
    ObservationListResponse,
    Pagination,
    PlaceholderResponse,
    RuleItem,
    RuleListResponse,
    RuleMutationResponse,
    RulesReloadResponse,
    RuleToggleRequest,
    RuntimeStatusResponse,
    TrendPoint,
)
from config import settings
from governance.api_keys import ApiKeyCreate, ApiKeyService, key_prefix, key_suffix, parse_bulk_replace_csv
from governance.key_provider import KeyProviderError
from middleware.auth import clear_admin_session_cookie, require_admin_access, set_admin_session_cookie, validate_admin_login
from middleware.concurrency_limit import get_v1_concurrency_snapshot
from storage.admin_ops import AdminOperationPayload, AdminOperationQuery, AdminOperationReader, AdminOperationWriter
from storage.archive import ArchiveQuery, ArchiveReader
from storage.audit import AuditQuery, AuditReader
from storage.database import get_session_factory
from storage.image_assets import ImageAssetReader
from storage.models import AdminOperation, ApiKeyRecord, AuditLog, ImageAsset, MessageArchive

router = APIRouter(dependencies=[Depends(require_admin_access)])


@router.post("/login", response_model=AdminLoginResponse)
async def login(request: Request, response: Response, payload: AdminLoginRequest):
    active_settings = getattr(request.app.state, "settings", settings)
    if not validate_admin_login(payload.username, payload.password, active_settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")
    set_admin_session_cookie(response, payload.username, active_settings)
    return AdminLoginResponse(status="ok", message="登录成功")


@router.post("/logout", response_model=AdminLoginResponse)
async def logout(response: Response):
    clear_admin_session_cookie(response)
    return AdminLoginResponse(status="ok", message="已退出登录")


@router.get("/observations/recent", response_model=ObservationListResponse)
async def recent_observations(request: Request, limit: int = Query(default=10, ge=1, le=50)):
    reader = _archive_reader(request)
    archives = await reader.recent(limit)
    return ObservationListResponse(items=[_archive_to_observation(archive) for archive in archives])


@router.get("/archives", response_model=ArchiveListResponse)
async def list_archives(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str | None = None,
    model: str | None = None,
    action_taken: str | None = None,
    is_blocked: bool | None = None,
    keyword: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    page = await _archive_reader(request).list(
        ArchiveQuery(
            limit=limit,
            offset=offset,
            user_id=user_id,
            model=model,
            action_taken=action_taken,
            is_blocked=is_blocked,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
        )
    )
    return ArchiveListResponse(
        items=[_archive_to_summary(item) for item in page.items],
        pagination=Pagination(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.get("/archives/stats", response_model=ArchiveStatsResponse)
async def archive_stats(
    request: Request,
    user_id: str | None = None,
    model: str | None = None,
    action_taken: str | None = None,
    is_blocked: bool | None = None,
    keyword: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    stats = await _archive_reader(request).stats(
        ArchiveQuery(
            user_id=user_id,
            model=model,
            action_taken=action_taken,
            is_blocked=is_blocked,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
        )
    )
    return ArchiveStatsResponse(
        total=stats.total,
        blocked=stats.blocked,
        desensitized=stats.desensitized,
        passed=stats.passed,
        by_action=stats.by_action,
        by_model=stats.by_model,
    )


@router.get("/archives/{archive_id}", response_model=ArchiveDetail)
async def get_archive(request: Request, archive_id: int):
    archive = await _archive_reader(request).get(archive_id)
    if archive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archive not found")
    await _write_admin_operation(request, "archive.view_detail", "archive", str(archive_id))
    return _archive_to_detail(archive)


@router.get("/image-assets", response_model=ImageAssetListResponse)
async def list_image_assets(
    request: Request,
    request_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    assets = await _image_asset_reader(request).list(request_id=request_id, limit=limit, offset=offset)
    await _write_admin_operation(request, "image_asset.list", "image_asset", request_id or "all")
    return ImageAssetListResponse(items=[_image_asset_to_item(asset) for asset in assets])


@router.get("/audits", response_model=AuditListResponse)
async def list_audits(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: str | None = None,
    rule_id: str | None = None,
    rule_level: str | None = None,
    scanner_type: str | None = None,
    action_taken: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
):
    page = await _audit_reader(request).list(
        AuditQuery(
            limit=limit,
            offset=offset,
            user_id=user_id,
            rule_id=rule_id,
            rule_level=rule_level,
            scanner_type=scanner_type,
            action_taken=action_taken,
            start_time=start_time,
            end_time=end_time,
        )
    )
    return AuditListResponse(
        items=[_audit_to_summary(item) for item in page.items],
        pagination=Pagination(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.get("/audits/{audit_id}", response_model=AuditDetail)
async def get_audit(request: Request, audit_id: int):
    audit = await _audit_reader(request).get(audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    await _write_admin_operation(request, "audit.view_detail", "audit", str(audit_id))
    return _audit_to_detail(audit)


@router.get("/admin-ops", response_model=AdminOperationListResponse)
async def list_admin_operations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    operation: str | None = None,
    resource_type: str | None = None,
):
    page = await _admin_operation_reader(request).list(
        AdminOperationQuery(limit=limit, offset=offset, operation=operation, resource_type=resource_type)
    )
    return AdminOperationListResponse(
        items=[_admin_operation_to_item(item) for item in page.items],
        pagination=Pagination(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(request: Request):
    cache = getattr(request.app.state, "admin_stats_cache", None)
    if cache is not None:
        return await cache.get_or_set(lambda: _load_admin_stats(request))
    return await _load_admin_stats(request)


async def _load_admin_stats(request: Request) -> AdminStatsResponse:
    archive_reader = _archive_reader(request)
    audit_reader = _audit_reader(request)
    now = datetime.now(UTC)
    today_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    tomorrow_start = today_start + timedelta(days=1)
    total_archive_stats = await archive_reader.stats()
    today_archive_stats = await archive_reader.stats(ArchiveQuery(start_time=today_start, end_time=tomorrow_start))
    total_hits = await audit_reader.count_between(datetime.min.replace(tzinfo=UTC), now + timedelta(days=1))
    total_blocks = await audit_reader.count_between(datetime.min.replace(tzinfo=UTC), now + timedelta(days=1), "block")
    today_hits = await audit_reader.count_between(today_start, tomorrow_start)
    today_blocks = await audit_reader.count_between(today_start, tomorrow_start, "block")
    trend = []
    for days_ago in range(6, -1, -1):
        day_start = today_start - timedelta(days=days_ago)
        day_end = day_start + timedelta(days=1)
        day_archive_stats = await archive_reader.stats(ArchiveQuery(start_time=day_start, end_time=day_end))
        day_hits = await audit_reader.count_between(day_start, day_end)
        day_blocks = await audit_reader.count_between(day_start, day_end, "block")
        trend.append(TrendPoint(date=day_start.date().isoformat(), requests=day_archive_stats.total, hits=day_hits, blocked=day_blocks))
    return AdminStatsResponse(
        today_requests=today_archive_stats.total,
        today_hits=today_hits,
        today_blocks=today_blocks,
        total_requests=total_archive_stats.total,
        total_hits=total_hits,
        total_blocks=total_blocks,
        recent_trend=trend,
    )


@router.get("/rules", response_model=RuleListResponse)
async def list_rules(request: Request):
    active_settings = getattr(request.app.state, "settings", settings)
    return RuleListResponse(items=_load_rules(active_settings))


@router.patch("/rules/{rule_id}", response_model=RuleMutationResponse)
async def toggle_rule(request: Request, rule_id: str, payload: RuleToggleRequest):
    active_settings = getattr(request.app.state, "settings", settings)
    rule = _set_rule_enabled(rule_id, payload.enabled, active_settings)
    reloaded = await _reload_scanners(request)
    await _write_admin_operation(request, "rule.toggle", "rule", rule_id)
    return RuleMutationResponse(status="ok", rule=rule, reloaded=reloaded)


@router.post("/rules/reload", response_model=RulesReloadResponse)
async def reload_rules(request: Request):
    reloaded = await _reload_scanners(request)
    await _write_admin_operation(request, "rule.reload", "rule", "all")
    return RulesReloadResponse(status="ok", reloaded=reloaded)


@router.get("/health")
async def admin_health():
    return {"status": "ok"}


@router.get("/runtime", response_model=RuntimeStatusResponse)
async def runtime_status(request: Request):
    active_settings = getattr(request.app.state, "settings", settings)
    return RuntimeStatusResponse(
        worker_pid=os.getpid(),
        configured_workers=active_settings.uvicorn_workers,
        v1_concurrency=_v1_concurrency_snapshot(request),
        archive_queue=_archive_queue_snapshot(request),
        upstream={
            "max_connections": active_settings.upstream_max_connections,
            "max_keepalive_connections": active_settings.upstream_max_keepalive_connections,
            "keepalive_expiry": active_settings.upstream_keepalive_expiry,
            "timeout_connect": active_settings.upstream_timeout_connect,
            "timeout_read": active_settings.upstream_timeout_read,
            "timeout_pool": active_settings.upstream_timeout_pool,
        },
        admin={
            "stats_cache_seconds": active_settings.admin_stats_cache_seconds,
            "observations_default_limit": 5,
            "observations_max_limit": 20,
        },
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
):
    page = await _api_key_service(request).list(limit=limit, offset=offset, status=status_filter)
    return ApiKeyListResponse(
        items=[_api_key_to_item(item) for item in page.items],
        pagination=Pagination(total=page.total, limit=page.limit, offset=page.offset),
    )


@router.post("/api-keys", response_model=ApiKeyMutationResponse)
async def create_api_key(request: Request, payload: ApiKeyCreateRequest):
    try:
        result = await _api_key_service(request).create(
            ApiKeyCreate(
                name=payload.name,
                owner_user_id=payload.owner_user_id,
                upstream_key=payload.upstream_key,
                reuse_upstream_key=payload.reuse_upstream_key,
                expires_at=payload.expires_at,
                provider_name=payload.provider_name,
                owner_department=payload.owner_department,
                cost_center=payload.cost_center,
                create_mode=payload.create_mode,
                metadata=payload.metadata,
            )
        )
    except KeyProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _write_admin_operation(request, "api_key.create", "api_key", result.record.id)
    return ApiKeyMutationResponse(status="ok", item=_api_key_to_item(result.record), safetyhub_key=result.safetyhub_key)


@router.get("/api-keys/{api_key_id}", response_model=ApiKeyItem)
async def get_api_key(request: Request, api_key_id: str):
    record = await _api_key_service(request).get(api_key_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APIKey not found")
    await _write_admin_operation(request, "api_key.view_detail", "api_key", api_key_id)
    return _api_key_to_item(record)


@router.patch("/api-keys/{api_key_id}", response_model=ApiKeyMutationResponse)
async def update_api_key(request: Request, api_key_id: str, payload: ApiKeyUpdateRequest):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No editable fields provided")
    try:
        record = await _api_key_service(request).update(api_key_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APIKey not found")
    await _write_admin_operation(request, "api_key.update", "api_key", api_key_id)
    return ApiKeyMutationResponse(status="ok", item=_api_key_to_item(record))


@router.post("/api-keys/{api_key_id}/reveal", response_model=ApiKeyRevealResponse)
async def reveal_api_key(request: Request, response: Response, api_key_id: str):
    raw_key = await _api_key_service(request).reveal_safetyhub_key(api_key_id)
    if raw_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APIKey not found")
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="APIKey secret is not available")
    response.headers["Cache-Control"] = "no-store"
    await _write_admin_operation(request, "api_key.reveal", "api_key", api_key_id)
    return ApiKeyRevealResponse(status="ok", api_key_id=api_key_id, key=raw_key, key_prefix=key_prefix(raw_key), key_suffix=key_suffix(raw_key))


@router.post("/api-keys/{api_key_id}/revoke", response_model=ApiKeyMutationResponse)
async def revoke_api_key(request: Request, api_key_id: str):
    try:
        record = await _api_key_service(request).revoke(api_key_id)
    except KeyProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APIKey not found")
    await _write_admin_operation(request, "api_key.revoke", "api_key", api_key_id)
    return ApiKeyMutationResponse(status="ok", item=_api_key_to_item(record))


@router.delete("/api-keys/{api_key_id}", response_model=ApiKeyDeleteResponse)
async def delete_api_key(request: Request, api_key_id: str):
    try:
        deleted = await _api_key_service(request).delete_revoked(api_key_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APIKey not found")
    await _write_admin_operation(request, "api_key.delete", "api_key", api_key_id)
    return ApiKeyDeleteResponse(status="ok", api_key_id=api_key_id)


@router.post("/api-keys/{api_key_id}/replace-upstream-key", response_model=ApiKeyMutationResponse)
async def replace_upstream_key(request: Request, api_key_id: str, payload: ApiKeyReplaceRequest):
    try:
        record = await _api_key_service(request).replace_upstream_key(api_key_id, payload.new_upstream_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APIKey not found")
    await _write_admin_operation(request, "api_key.replace_upstream_key", "api_key", api_key_id)
    return ApiKeyMutationResponse(status="ok", item=_api_key_to_item(record))


@router.post("/api-keys/bulk-replace-upstream-keys", response_model=ApiKeyBulkReplaceResponse)
async def bulk_replace_upstream_keys(request: Request, payload: ApiKeyBulkReplaceRequest):
    rows = parse_bulk_replace_csv(payload.csv_content)
    results = await _api_key_service(request).bulk_replace(rows)
    await _write_admin_operation(request, "api_key.bulk_replace_upstream_key", "api_key", "bulk")
    return ApiKeyBulkReplaceResponse(
        status="ok",
        items=[ApiKeyBulkReplaceItem(identifier=item.identifier, status=item.status, message=item.message, api_key_id=item.api_key_id) for item in results],
    )


@router.get("/approvals", response_model=PlaceholderResponse)
async def approvals_placeholder():
    return PlaceholderResponse(message="审批链将在阶段 9 启用，当前为只读占位入口")


def _archive_reader(request: Request) -> ArchiveReader:
    return getattr(request.app.state, "archive_reader", None) or ArchiveReader(_session_factory(request))


def _audit_reader(request: Request) -> AuditReader:
    return getattr(request.app.state, "audit_reader", None) or AuditReader(_session_factory(request))


def _admin_operation_reader(request: Request) -> AdminOperationReader:
    return getattr(request.app.state, "admin_operation_reader", None) or AdminOperationReader(_session_factory(request))


def _image_asset_reader(request: Request) -> ImageAssetReader:
    return getattr(request.app.state, "image_asset_reader", None) or ImageAssetReader(_session_factory(request))


def _admin_operation_writer(request: Request) -> AdminOperationWriter:
    return getattr(request.app.state, "admin_operation_writer", None) or AdminOperationWriter(_session_factory(request))


def _api_key_service(request: Request) -> ApiKeyService:
    return getattr(request.app.state, "api_key_service", None) or ApiKeyService(_session_factory(request), key_provider=getattr(request.app.state, "key_provider", None))


def _v1_concurrency_snapshot(request: Request) -> dict[str, Any]:
    snapshot = get_v1_concurrency_snapshot()
    if snapshot is not None:
        return {**snapshot, "snapshot_scope": "worker"}
    active_settings = getattr(request.app.state, "settings", settings)
    return {
        "max_inflight": active_settings.v1_max_inflight,
        "max_queue_size": active_settings.v1_max_queue_size,
        "queue_timeout_seconds": active_settings.v1_queue_timeout_seconds,
        "inflight": None,
        "queue_size": None,
        "snapshot_scope": "configured",
    }


def _archive_queue_snapshot(request: Request) -> dict[str, Any]:
    archive_queue = getattr(request.app.state, "archive_queue", None)
    if archive_queue is None:
        return {
            "queue_size": None,
            "max_size": settings.archive_queue_max_size,
            "dropped": None,
            "processed": None,
            "snapshot_scope": "configured",
        }
    return {**archive_queue.snapshot(), "snapshot_scope": "worker"}


def _session_factory(request: Request):
    return getattr(request.app.state, "session_factory", None) or get_session_factory()


async def _write_admin_operation(request: Request, operation: str, resource_type: str, resource_id: str) -> None:
    try:
        await _admin_operation_writer(request).write(
            AdminOperationPayload(
                request_id=getattr(request.state, "request_id", ""),
                admin_user=getattr(request.state, "admin_user", ""),
                operation=operation,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
    except Exception:
        return


def _archive_to_summary(archive: MessageArchive) -> ArchiveSummary:
    return ArchiveSummary(
        id=archive.id,
        request_id=archive.request_id,
        user_id=archive.user_id,
        api_key_id=archive.api_key_id,
        model=archive.model,
        capability=archive.capability,
        action_taken=archive.action_taken,
        is_stream=archive.is_stream,
        is_blocked=archive.is_blocked,
        is_desensitized=archive.is_desensitized,
        blocked_rule_id=archive.blocked_rule_id,
        matched_rule_ids=_parse_json(archive.matched_rule_ids, []),
        created_at=archive.created_at,
        completed_at=archive.completed_at,
        latency_ms=archive.latency_ms,
    )


def _archive_to_detail(archive: MessageArchive) -> ArchiveDetail:
    summary = _archive_to_summary(archive).model_dump()
    return ArchiveDetail(
        **summary,
        messages_original=_parse_json(archive.prompt_original, []),
        messages_desensitized=_parse_json(archive.prompt_desensitized, []),
        response=_normalize_archive_response(archive.response),
        image_metadata=_parse_json(archive.image_metadata, {}),
        prompt_tokens=archive.prompt_tokens,
        completion_tokens=archive.completion_tokens,
    )


def _archive_to_observation(archive: MessageArchive) -> ObservationItem:
    return ObservationItem(**_archive_to_detail(archive).model_dump())


def _audit_to_summary(audit: AuditLog) -> AuditSummary:
    return AuditSummary(
        id=audit.id,
        request_id=audit.request_id,
        user_id=audit.user_id,
        rule_id=audit.rule_id,
        rule_name=audit.rule_name,
        rule_level=audit.rule_level,
        scanner_type=audit.scanner_type,
        action_taken=audit.action_taken,
        created_at=audit.created_at,
    )


def _audit_to_detail(audit: AuditLog) -> AuditDetail:
    summary = _audit_to_summary(audit).model_dump()
    return AuditDetail(
        **summary,
        matched_snippet=audit.matched_snippet,
        full_text_hash=audit.full_text_hash,
        approval_id=audit.approval_id,
        security_policy_id=audit.security_policy_id,
    )


def _admin_operation_to_item(operation: AdminOperation) -> AdminOperationItem:
    return AdminOperationItem(
        id=operation.id,
        request_id=operation.request_id,
        admin_user=operation.admin_user,
        operation=operation.operation,
        resource_type=operation.resource_type,
        resource_id=operation.resource_id,
        created_at=operation.created_at,
    )


def _image_asset_to_item(asset: ImageAsset) -> ImageAssetItem:
    return ImageAssetItem(
        id=asset.id,
        request_id=asset.request_id,
        source_index=asset.source_index,
        source_type=asset.source_type,
        source_url=asset.source_url or "",
        status=asset.status,
        local_path=asset.local_path or "",
        sha256=asset.sha256 or "",
        mime_type=asset.mime_type or "",
        size_bytes=asset.size_bytes or 0,
        error=asset.error or "",
        created_at=asset.created_at,
        completed_at=asset.completed_at,
    )


def _api_key_to_item(record: ApiKeyRecord) -> ApiKeyItem:
    return ApiKeyItem(
        id=record.id,
        name=record.name,
        owner_user_id=record.owner_user_id,
        owner_department=record.owner_department,
        cost_center=record.cost_center,
        key_prefix=record.key_prefix,
        key_suffix=record.key_suffix,
        upstream_key_prefix=record.upstream_key_prefix,
        provider_name=record.provider_name,
        status=record.status,
        is_decoupled=record.is_decoupled,
        created_at=record.created_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
    )


async def _reload_scanners(request: Request) -> bool:
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        return False
    await scanner.reload_all()
    return True


def _set_rule_enabled(rule_id: str, enabled: bool, active_settings) -> RuleItem:
    data = _load_rules_config(active_settings)
    for section, rule_type in (("keyword_rules", "keyword"), ("regex_rules", "regex")):
        for rule in data.get(section, []) or []:
            if str(rule.get("id", "")) != rule_id:
                continue
            rule["enabled"] = enabled
            _write_rules_config(data, active_settings)
            return _rule_to_item(rule, rule_type)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")


def _load_rules(active_settings) -> list[RuleItem]:
    data = _load_rules_config(active_settings)
    items = []
    for rule in data.get("keyword_rules", []) or []:
        items.append(_rule_to_item(rule, "keyword"))
    for rule in data.get("regex_rules", []) or []:
        items.append(_rule_to_item(rule, "regex"))
    return items


def _rule_to_item(rule: dict[str, Any], rule_type: str) -> RuleItem:
    return RuleItem(
        id=str(rule.get("id", "")),
        name=str(rule.get("name", "")),
        type=rule_type,
        level=str(rule.get("level", "")),
        enabled=bool(rule.get("enabled", False)),
        description=str(rule.get("description", "")),
    )


def _load_rules_config(active_settings) -> dict[str, Any]:
    rules_path = Path(active_settings.rules_config_path)
    if not rules_path.exists():
        return {}
    with rules_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _write_rules_config(data: dict[str, Any], active_settings) -> None:
    rules_path = Path(active_settings.rules_config_path)
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    with rules_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)


def _normalize_archive_response(value: str) -> Any:
    response = _parse_json(value, value)
    if not isinstance(response, dict):
        return response
    content = response.get("content")
    if not isinstance(content, str):
        return response
    parsed_content = _parse_json(content, None)
    if parsed_content is None:
        return response
    normalized = dict(response)
    normalized["raw_content"] = content
    normalized["content"] = parsed_content
    return normalized


def _parse_json(value: str, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
