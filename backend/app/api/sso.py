import base64
import hashlib

import httpx

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse

from app.api.dependencies import get_sso_account_service
from app.api.dependencies import get_sso_provider_factory
from app.api.dependencies import get_sso_transaction_manager
from app.core.exceptions import SsoAccountResolutionError
from app.core.exceptions import SsoEmailVerificationError
from app.core.exceptions import SsoProviderConfigurationError
from app.core.exceptions import SsoProviderError
from app.core.exceptions import SsoTransactionError
from app.core.logging import logger
from app.core.config import settings
from app.integrations.sso.factory import SsoProviderFactory
from app.integrations.sso.models import ProviderName
from app.schemas.sso import SsoCallbackResponse
from app.security.sso_transactions import SsoTransactionManager
from app.services.auth_service import AuthService
from app.services.sso_account_service import SsoAccountService
from app.api.dependencies import get_auth_service
from app.core.exceptions import AuthenticationError
from app.models.audit_event import AuditEventType


router = APIRouter(prefix="/auth/sso", tags=["Single sign-on"])


@router.get("/{provider}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def begin_sso(
    provider: ProviderName,
    factory: SsoProviderFactory = Depends(get_sso_provider_factory),
    transactions: SsoTransactionManager = Depends(get_sso_transaction_manager),
) -> RedirectResponse:
    try:
        transaction = transactions.create(provider)
        with httpx.Client(timeout=10.0) as http_client:
            oauth_provider = factory.create(provider, http_client)
            authorization_url = oauth_provider.build_authorization_url(
                transaction.state,
                _code_challenge(transaction.code_verifier),
                transaction.nonce,
            )
    except SsoProviderConfigurationError as error:
        return _error_response(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))

    response = RedirectResponse(
        authorization_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    response.set_cookie(
        key=transactions.cookie_name(provider),
        value=transactions.encode(transaction),
        max_age=transactions.expires_in_minutes * 60,
        httponly=True,
        secure=transactions.secure_cookie,
        samesite="lax",
        path=transactions.callback_path(provider),
    )
    return response


@router.get("/{provider}/callback", response_model=SsoCallbackResponse)
def complete_sso(
    provider: ProviderName,
    request: Request,
    state: str,
    code: str | None = None,
    error: str | None = None,
    factory: SsoProviderFactory = Depends(get_sso_provider_factory),
    transactions: SsoTransactionManager = Depends(get_sso_transaction_manager),
    accounts: SsoAccountService = Depends(get_sso_account_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    cookie_name = transactions.cookie_name(provider)
    transaction_cookie = request.cookies.get(cookie_name)

    if error or not code:
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_400_BAD_REQUEST,
            "SSO authorization was not completed",
            "authorization_not_completed",
        )

    try:
        transaction = transactions.validate(transaction_cookie, provider, state)
        with httpx.Client(timeout=10.0) as http_client:
            oauth_provider = factory.create(provider, http_client)
            tokens = oauth_provider.exchange_code(code, transaction.code_verifier)
            identity = oauth_provider.get_identity(tokens, transaction.nonce)
        user = accounts.resolve_identity(identity)
        session = auth_service.issue_session(
            user,
            success_event_type=AuditEventType.AUTH_SSO_SUCCEEDED,
            failure_event_type=AuditEventType.AUTH_SSO_FAILED,
            metadata={"provider": provider.value},
        )
    except SsoTransactionError as error:
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_400_BAD_REQUEST,
            str(error),
            "invalid_transaction",
        )
    except SsoProviderConfigurationError as error:
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            str(error),
            "provider_configuration",
        )
    except SsoProviderError as error:
        logger.warning("%s SSO provider verification failed: %s", provider.value, error)
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_502_BAD_GATEWAY,
            "SSO provider verification failed",
            "provider_rejected",
        )
    except SsoEmailVerificationError:
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A verified email address is required to create or link an account",
            "email_unverified",
        )
    except SsoAccountResolutionError:
        logger.warning("%s SSO account linking conflict", provider.value)
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_409_CONFLICT,
            "SSO account linking conflict; retry sign-in",
            "account_resolution",
        )
    except AuthenticationError:
        return _callback_error(
            provider,
            transactions,
            auth_service,
            status.HTTP_401_UNAUTHORIZED,
            "Inactive user",
            "inactive_user",
            record_audit=False,
        )

    if settings.SSO_FRONTEND_REDIRECT_URL:
        response = RedirectResponse(
            f"{settings.SSO_FRONTEND_REDIRECT_URL.rstrip('/')}/login?provider={provider.value}",
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
        cookie_options = {
            "httponly": True,
            "secure": transactions.secure_cookie,
            "samesite": "lax",
            "path": "/",
        }
        response.set_cookie(
            key="aegis_access_token",
            value=session.access_token,
            max_age=session.expires_in,
            **cookie_options,
        )
        response.set_cookie(
            key="aegis_refresh_token",
            value=session.refresh_token,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            **cookie_options,
        )
    else:
        response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=SsoCallbackResponse(
            **session.model_dump(mode="json", exclude_none=True),
            provider=provider,
        ).model_dump(mode="json", exclude_none=True),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
    _clear_transaction_cookie(response, provider, transactions)
    return response


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _callback_error(
    provider: ProviderName,
    transactions: SsoTransactionManager,
    auth_service: AuthService,
    status_code: int,
    detail: str,
    failure_category: str,
    record_audit: bool = True,
) -> JSONResponse:
    if record_audit:
        auth_service.record_sso_failure(
            provider=provider.value,
            failure_category=failure_category,
        )
    response = _error_response(status_code, detail)
    _clear_transaction_cookie(response, provider, transactions)
    return response


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _clear_transaction_cookie(
    response: JSONResponse,
    provider: ProviderName,
    transactions: SsoTransactionManager,
) -> None:
    response.delete_cookie(
        key=transactions.cookie_name(provider),
        path=transactions.callback_path(provider),
    )
