from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.api.dependencies import get_admin_processing_job_service
from app.core.exceptions import ProcessingJobNotFoundError, ProcessingJobStateError
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.user import User
from app.schemas.document import ProcessingJobResponse
from app.security.dependencies import require_administration_permission
from app.security.permissions import PermissionCode
from app.services.admin_processing_job_service import AdminProcessingJobService

router = APIRouter(prefix="/admin/processing-jobs", tags=["Administration"])
def _error(error):
    if isinstance(error, ProcessingJobNotFoundError): return HTTPException(404, "Processing job not found")
    return HTTPException(status.HTTP_409_CONFLICT, "Processing job operation cannot be completed")
@router.get("", response_model=list[ProcessingJobResponse])
def list_jobs(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), status_filter: ProcessingJobStatus | None = Query(None, alias="status"), service: AdminProcessingJobService = Depends(get_admin_processing_job_service), _: User = Depends(require_administration_permission(PermissionCode.DOCUMENTS_MANAGE))):
    return service.list_jobs(offset=offset, limit=limit, status=status_filter).items
@router.post("/{job_id}/retry", response_model=ProcessingJobResponse)
def retry_job(job_id: int, service: AdminProcessingJobService = Depends(get_admin_processing_job_service), _: User = Depends(require_administration_permission(PermissionCode.DOCUMENTS_MANAGE))):
    try: return service.retry_job(job_id)
    except (ProcessingJobNotFoundError, ProcessingJobStateError) as error: raise _error(error)
@router.post("/{job_id}/cancel", response_model=ProcessingJobResponse)
def cancel_job(job_id: int, service: AdminProcessingJobService = Depends(get_admin_processing_job_service), _: User = Depends(require_administration_permission(PermissionCode.DOCUMENTS_MANAGE))):
    try: return service.cancel_job(job_id)
    except (ProcessingJobNotFoundError, ProcessingJobStateError) as error: raise _error(error)
