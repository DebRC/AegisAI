"""Protected SSE endpoint for grounded RAG chat."""

from collections.abc import Iterator

from fastapi import APIRouter
from fastapi import Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_rag_chat_service
from app.chat.streaming import stream_chat_sse
from app.schemas.chat import ChatStreamRequest
from app.models.user import User
from app.security.dependencies import require_permission
from app.security.permissions import PermissionCode
from app.security.dependencies import TenantContext, get_current_tenant_context
from app.services.rag_chat_service import RagChatService


router = APIRouter(prefix="/chat", tags=["Chat"])


def chat_event_stream(
    service: RagChatService,
    request: ChatStreamRequest,
    *,
    user_id: int,
    tenant_id: int | None = None,
) -> Iterator[str]:
    """Adapt one chat turn to SSE and always release its provider resources."""
    try:
        stream = service.stream(request, user_id=user_id, tenant_id=tenant_id) if tenant_id is not None else service.stream(request, user_id=user_id)
        yield from stream_chat_sse(stream)
    finally:
        service.close()


@router.post(
    "/stream",
    response_class=StreamingResponse,
    summary="Stream a grounded answer with verified document citations",
)
def stream(
    request: ChatStreamRequest,
    current_user: User = Depends(require_permission(PermissionCode.DOCUMENTS_READ)),
    context: TenantContext = Depends(get_current_tenant_context),
    service: RagChatService = Depends(get_rag_chat_service),
) -> StreamingResponse:
    """Return the Phase 11 SSE contract after existing document-read RBAC passes."""
    return StreamingResponse(
        chat_event_stream(service, request, user_id=current_user.id, tenant_id=context.tenant.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
