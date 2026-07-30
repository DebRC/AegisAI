import base64
import hashlib

import httpx

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse

from app.api.dependencies import get_sso_provider_factory
from app.api.dependencies import get_sso_transaction_manager
from app.core.exceptions import SsoProviderConfigurationError
from app.core.exceptions import SsoProviderError
from app.core.exceptions import SsoTransactionError
from app.core.logging import logger
from app.integrations.sso.factory import SsoProviderFactory
from app.integrations.sso.models import ProviderName
from app.schemas.sso import SsoCallbackResponse
from app.security.sso_transactions import SsoTransactionManager


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
) -> JSONResponse:
    cookie_name = transactions.cookie_name(provider)
    transaction_cookie = request.cookies.get(cookie_name)

    if error or not code:
        return _callback_error(
            provider,
            transactions,
            status.HTTP_400_BAD_REQUEST,
            "SSO authorization was not completed",
        )

    try:
        transaction = transactions.validate(transaction_cookie, provider, state)
        with httpx.Client(timeout=10.0) as http_client:
            oauth_provider = factory.create(provider, http_client)
            tokens = oauth_provider.exchange_code(code, transaction.code_verifier)
            oauth_provider.get_identity(tokens, transaction.nonce)
    except SsoTransactionError as error:
        return _callback_error(
            provider,
            transactions,
            status.HTTP_400_BAD_REQUEST,
            str(error),
        )
    except SsoProviderConfigurationError as error:
        return _callback_error(
            provider,
            transactions,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            str(error),
        )
    except SsoProviderError as error:
        logger.warning("%s SSO provider verification failed: %s", provider.value, error)
        return _callback_error(
            provider,
            transactions,
            status.HTTP_502_BAD_GATEWAY,
            "SSO provider verification failed",
        )

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=SsoCallbackResponse(
            message="External identity verified",
            provider=provider,
        ).model_dump(mode="json"),
    )
    _clear_transaction_cookie(response, provider, transactions)
    return response


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _callback_error(
    provider: ProviderName,
    transactions: SsoTransactionManager,
    status_code: int,
    detail: str,
) -> JSONResponse:
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
