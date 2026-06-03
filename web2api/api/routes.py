"""FastAPI HTTP endpoints - HTTP接口层

提供:
- /                        Web UI 管理面板
- /v1/chat/completions     OpenAI 兼容接口 (支持 SSE 流式)
- /api/v1/message          原生接口
- /api/v1/stats            统计信息
- /health                  健康检查
"""

import json
import time
import uuid
from pathlib import Path
from typing import Optional, AsyncGenerator
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from loguru import logger

from web2api.config import config
from web2api.core.gateway import APIGateway
from web2api.platforms import resolve_platform, PLATFORMS, MODEL_TO_PLATFORM

DASHBOARD_PATH = Path(__file__).parent.parent / "web" / "dashboard.html"


# ========== Pydantic Models ==========

class MessageRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    account_id: str
    platform: str = "gemini"  # gemini / chatgpt / claude / deepseek / kimi / qwen


class CompletionRequest(BaseModel):
    model: str = "gemini-2.0-flash"
    messages: list
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    user: Optional[str] = None  # 用于携带 account_id 或 API key


class CompletionChoice(BaseModel):
    index: int = 0
    message: dict
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ========== FastAPI App ==========

app = FastAPI(
    title="web2api",
    description="AI Web Interface to OpenAI API Gateway",
    version="1.3.0",
)

gateway: APIGateway = None


@app.on_event("startup")
async def startup_event():
    global gateway
    gateway = APIGateway(config)
    await gateway.initialize()
    logger.info("🚀 Web2API Gateway started")


@app.on_event("shutdown")
async def shutdown_event():
    if gateway:
        await gateway.shutdown()
    logger.info("🛑 Web2API Gateway stopped")


# ========== Health ==========

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.3.0"}


@app.get("/v1/models")
async def list_models():
    """OpenAI兼容的模型列表端点"""
    models = []
    seen = set()
    for model_name, platform in MODEL_TO_PLATFORM.items():
        if model_name not in seen:
            seen.add(model_name)
            models.append({
                "id": model_name,
                "object": "model",
                "created": 1780462878,
                "owned_by": platform,
            })
    return {"object": "list", "data": models}


@app.get("/api/v1/platforms")
async def list_platforms():
    """列出所有支持的平台"""
    from web2api.platforms import PLATFORMS
    platforms = {}
    for name, cls in PLATFORMS.items():
        platforms[name] = {
            "name": name,
            "requires_login": cls.REQUIRES_LOGIN,
            "supports_guest": cls.SUPPORTS_GUEST,
            "base_url": cls.URLS.get("base", ""),
        }
    return {"status": "ok", "platforms": platforms, "total": len(platforms)}


# ========== Dashboard ==========

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Web UI 管理面板"""
    try:
        return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


# ========== Native API ==========

@app.post("/api/v1/message")
async def send_message(req: MessageRequest):
    try:
        result = await gateway.handle_message(
            req.conversation_id, req.message, req.account_id, req.platform
        )

        if result["status"] == "error":
            raise HTTPException(
                status_code=result.get("http_status", 500),
                detail=result["error"],
            )
        elif result["status"] == "rate_limited":
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in send_message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== OpenAI-Compatible API ==========

def _extract_account_id(req: CompletionRequest, x_api_key: Optional[str]) -> str:
    """从请求中提取 account_id"""
    if req.user:
        return req.user
    if x_api_key:
        return x_api_key
    return "account_01"


def _build_openai_response(result: dict, model: str) -> dict:
    """将内部结果转换为 OpenAI 格式"""
    return {
        "id": f"chatcmpl-{result.get('conversation_id', uuid.uuid4().hex[:8])}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["response"],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.get("interaction_count", 0),
            "completion_tokens": len(result.get("response", "").split()),
            "total_tokens": result.get("interaction_count", 0) + len(result.get("response", "").split()),
        },
    }


def _build_sse_chunk(delta_content: str, conv_id: str, model: str, finish_reason: str = None) -> str:
    """构建单个 SSE chunk"""
    chunk = {
        "id": f"chatcmpl-{conv_id}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": delta_content} if delta_content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


async def _stream_response(
    conversation_id: Optional[str],
    message: str,
    account_id: str,
    model: str,
    platform: str = "gemini",
) -> AsyncGenerator[str, None]:
    """SSE 流式响应生成器"""
    try:
        result = await gateway.handle_message(conversation_id, message, account_id, platform)

        if result["status"] == "error":
            error_chunk = {
                "error": {
                    "message": result["error"],
                    "type": "server_error",
                    "code": result.get("http_status", 500),
                }
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            return

        if result["status"] == "rate_limited":
            error_chunk = {
                "error": {
                    "message": "Rate limit exceeded",
                    "type": "rate_limit_error",
                    "code": 429,
                }
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            return

        response_text = result.get("response", "")
        conv_id = result.get("conversation_id", "")

        # 模拟流式输出：逐段发送
        chunk_size = 20
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i : i + chunk_size]
            yield _build_sse_chunk(chunk, conv_id, model)
            # 微延迟模拟流式
            import asyncio
            await asyncio.sleep(0.02)

        # 发送最终 chunk
        yield _build_sse_chunk("", conv_id, model, finish_reason="stop")

        # 在 stream 结束后携带 conversation_id
        yield f"data: {json.dumps({'conversation_id': conv_id})}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'server_error'}})}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def openai_chat_completions(
    req: CompletionRequest,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
):
    """
    OpenAI兼容的chat completions API

    支持:
    - 流式 (stream=true) 和非流式响应
    - 多轮对话 (通过 messages 数组或 user 字段传递 conversation_id)
    """
    try:
        # 从 messages 中提取用户消息
        user_message = ""
        for msg in reversed(req.messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        if not user_message:
            raise HTTPException(status_code=400, detail="No user message found")

        account_id = _extract_account_id(req, x_api_key)
        platform = resolve_platform(req.model)

        # 尝试从 user 字段提取 conversation_id（约定格式: "account_id:conversation_id"）
        conversation_id = None
        if req.user and ":" in req.user:
            parts = req.user.split(":", 1)
            account_id = parts[0]
            conversation_id = parts[1]
        elif req.user:
            account_id = req.user

        if req.stream:
            return StreamingResponse(
                _stream_response(conversation_id, user_message, account_id, req.model, platform),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # 非流式
        result = await gateway.handle_message(conversation_id, user_message, account_id, platform)

        if result["status"] == "error":
            raise HTTPException(status_code=result.get("http_status", 500), detail=result["error"])
        if result["status"] == "rate_limited":
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        return _build_openai_response(result, req.model)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in openai_chat_completions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Management ==========

@app.get("/api/v1/stats")
async def get_stats():
    try:
        stats = gateway.get_gateway_stats()
        return {"status": "ok", "data": stats}
    except Exception as e:
        logger.error(f"Error in get_stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/quota/reset/{account_id}")
async def reset_account_quota(account_id: str):
    try:
        if not gateway.quota_engine:
            raise HTTPException(status_code=503, detail="Quota engine unavailable (no Redis)")
        await gateway.quota_engine.reset_account(account_id)
        return {"status": "ok", "message": f"Account {account_id} quota reset"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting quota: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/quota/status")
async def get_all_quota_status():
    try:
        if not gateway.quota_engine:
            return {"status": "ok", "data": {}, "message": "Quota engine unavailable (no Redis)"}
        status = await gateway.quota_engine.get_all_account_status()
        return {"status": "ok", "data": status}
    except Exception as e:
        logger.error(f"Error getting quota status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/accounts")
async def get_account_pool_status():
    """获取账号池状态"""
    try:
        stats = gateway.account_pool.get_pool_stats()
        accounts = {
            aid: acc.to_dict()
            for aid, acc in gateway.account_pool.accounts.items()
        }
        return {"status": "ok", "pool_stats": stats, "accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/accounts/{account_id}/cooldown")
async def force_cooldown(account_id: str, minutes: int = 90):
    """手动将账号切入冷却"""
    acc = gateway.account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    acc.set_cooldown(minutes)
    return {"status": "ok", "message": f"Account {account_id} set to cooldown for {minutes}min"}


@app.get("/api/v1/admin/sessions")
async def list_sessions():
    """列出所有会话（用于 Dashboard）"""
    try:
        if gateway.session_router:
            sessions = await gateway.session_router.list_all_sessions()
        elif gateway.db:
            sessions = gateway.db.get_all_sessions()
        else:
            sessions = []
        return {"status": "ok", "sessions": sessions, "total": len(sessions)}
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/workers/{worker_id}/kill")
async def kill_worker(worker_id: str):
    """强制终止指定 Worker"""
    try:
        if worker_id not in gateway.browser_pool.workers:
            raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")
        await gateway.browser_pool.kill_worker(worker_id)
        return {"status": "ok", "message": f"Worker {worker_id} killed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error killing worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/logs")
async def list_logs(limit: int = 50):
    """获取操作日志"""
    try:
        if gateway.db:
            logs = gateway.db.get_recent_logs(limit)
        else:
            logs = []
        return {"status": "ok", "logs": logs, "total": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Account CRUD ==========

@app.post("/api/v1/admin/accounts/add")
async def add_account(account_id: str, platform: str = "gemini", display_name: str = ""):
    """添加新账号"""
    try:
        if gateway.account_pool.get_account(account_id):
            raise HTTPException(status_code=409, detail=f"Account {account_id} already exists")
        acc = gateway.account_pool.add_account(account_id, platform, display_name)
        if gateway.db:
            gateway.db.save_account(account_id, "Idle")
            gateway.db.log_event("info", account_id, "account_added", f"Added {platform} account {account_id}")
        return {"status": "ok", "message": f"Account {account_id} ({platform}) added", "account": acc.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/accounts/batch-add")
async def batch_add_accounts(platform: str, count: int = 5, prefix: str = ""):
    """批量添加账号"""
    try:
        if count < 1 or count > 50:
            raise HTTPException(status_code=400, detail="Count must be 1-50")
        added = gateway.account_pool.batch_add_accounts(platform, count, prefix)
        for acc in added:
            if gateway.db:
                gateway.db.save_account(acc.account_id, "Idle")
        return {"status": "ok", "message": f"Added {len(added)} {platform} accounts", "accounts": [a.account_id for a in added]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/admin/accounts/{account_id}")
async def delete_account(account_id: str):
    """删除账号"""
    try:
        acc = gateway.account_pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        if acc.status.value == "busy":
            raise HTTPException(status_code=409, detail="Cannot delete busy account")
        del gateway.account_pool.accounts[account_id]
        if gateway.db:
            gateway.db.log_event("warn", account_id, "account_deleted", f"Deleted account {account_id}")
        return {"status": "ok", "message": f"Account {account_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/admin/accounts/{account_id}/reset")
async def reset_account(account_id: str):
    """重置账号状态为 Idle"""
    try:
        acc = gateway.account_pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        acc.set_idle()
        gateway._persist_account(account_id)
        return {"status": "ok", "message": f"Account {account_id} reset to Idle"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Session CRUD ==========

@app.delete("/api/v1/admin/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    try:
        if gateway.session_router:
            await gateway.session_router.delete_session(session_id)
        elif gateway.db:
            gateway.db.update_session(session_id, status="deleted")
        else:
            raise HTTPException(status_code=503, detail="No storage backend")
        return {"status": "ok", "message": f"Session {session_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/admin/sessions")
async def clear_all_sessions():
    """清空所有会话"""
    try:
        if gateway.db:
            conn = gateway.db._get_conn()
            conn.execute("UPDATE sessions SET status='deleted'")
            conn.commit()
        return {"status": "ok", "message": "All sessions cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Worker CRUD ==========

@app.get("/api/v1/admin/workers")
async def list_workers():
    """列出所有 Worker 详情"""
    try:
        workers = {}
        for wid, w in gateway.browser_pool.workers.items():
            workers[wid] = {
                "id": wid,
                "status": w.status.value,
                "account_id": w.account_id,
                "memory_mb": round(w.memory_usage_mb, 1),
                "pid": w.pid,
                "created_at": w.created_at,
                "last_used": w.last_used_time,
            }
        return {"status": "ok", "workers": workers, "total": len(workers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "Internal server error",
            "detail": str(exc) if config.debug else None,
        },
    )
