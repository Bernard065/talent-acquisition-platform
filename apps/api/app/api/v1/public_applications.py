"""Anonymous public job application HTTP endpoints."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.api.dependencies import (
    enforce_public_application_body_limit,
    get_db_session,
    get_malware_scanner,
    get_object_storage,
    get_public_application_abuse_guard,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.public_applications import (
    PublicApplicationAcceptedResponse,
    PublicApplicationResumeScanResponse,
    SubmitPublicApplicationRequest,
)
from app.core.authorization import TenantContext
from app.domains.documents.enums import MalwareScanVerdict
from app.services.abuse_control import (
    PublicApplicationAbuseCheck,
    PublicApplicationAbuseGuard,
)
from app.services.idempotency import (
    IdempotencyResult,
    execute_idempotently,
    get_idempotent_replay,
    hash_idempotency_key,
)
from app.services.malware_scanner import MalwareScannerError
from app.services.object_storage import ObjectStorage, public_application_resume_scan_object_key
from app.services.outbox import enqueue_outbox_event
from app.services.public_application_errors import (
    PublicApplicationResumeRejectedError,
    PublicApplicationScanUnavailableError,
)
from app.services.public_applications import (
    SubmitPublicApplicationCommand,
    resolve_public_application_tenant,
    submit_public_application,
)

router = APIRouter(prefix="/public", tags=["Public applications"])
_MAX_RESUME_BYTES = 10 * 1024 * 1024
_RESUME_SCAN_PROOF_LIFETIME = timedelta(hours=2)
_RESUME_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
AbuseGuard = Annotated[
    PublicApplicationAbuseGuard,
    Depends(get_public_application_abuse_guard),
]


@router.post(
    "/jobs/{public_job_id}/resume-scans",
    response_model=PublicApplicationResumeScanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_public_application_body_limit)],
    summary="Upload and scan a résumé before submitting an application",
)
async def scan_public_application_resume_endpoint(
    public_job_id: UUID,
    request: Request,
    session: DatabaseSession,
    abuse_guard: AbuseGuard,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Scan the uploaded bytes and issue a short-lived, single-use proof token."""
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload a résumé file to scan.",
        )
    form = await request.form()
    if set(form.keys()) != {"resume", "challenge_token"} or any(
        len(form.getlist(key)) != 1 for key in form.keys()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid résumé scan request.",
        )

    upload = form.get("resume")
    challenge_token = form.get("challenge_token")
    if not isinstance(upload, UploadFile) or not upload.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a PDF or Word résumé to scan.",
        )
    if not isinstance(challenge_token, str):
        challenge_token = None

    content = await upload.read(_MAX_RESUME_BYTES + 1)
    await upload.close()
    if not 0 < len(content) <= _MAX_RESUME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Résumé must not exceed 10 MiB.",
        )
    if (
        len(upload.filename) > 255
        or "/" in upload.filename
        or "\\" in upload.filename
        or any(ord(character) < 32 for character in upload.filename)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Résumé filename is invalid.",
        )

    content_type = upload.content_type
    if not content_type:
        content_type = (
            "application/pdf"
            if upload.filename.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if upload.filename.lower().endswith(".docx")
            else None
        )
    if content_type not in _RESUME_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Résumé must be a PDF or Word document.",
        )
    valid_signature = (
        content_type == "application/pdf" and content.startswith(b"%PDF-")
    ) or (
        content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        and content.startswith(b"PK\x03\x04")
    )
    if not valid_signature:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Résumé file type does not match its contents.",
        )

    tenant_id = await resolve_public_application_tenant(
        session,
        public_job_id=public_job_id,
    )
    context = TenantContext(
        tenant_id=tenant_id,
        subject="public:job-application-resume-scan",
        roles=frozenset(),
        request_id=request.headers.get("X-Request-ID", "unknown"),
    )
    content_digest = sha256(content).hexdigest()
    scan_payload = {
        "public_job_id": str(public_job_id),
        "content_sha256": content_digest,
        "content_type": content_type,
        "byte_size": len(content),
    }
    replay = await get_idempotent_replay(
        session,
        context=context,
        key=idempotency_key,
        operation_name="public_application.resume_scan",
        payload=scan_payload,
    )
    if replay is not None:
        response = JSONResponse(
            status_code=replay.status_code,
            content=PublicApplicationResumeScanResponse(
                scan_token=idempotency_key.strip(),
                expires_at=replay.body["scan_expires_at"],
            ).model_dump(mode="json"),
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    await session.rollback()

    await abuse_guard.verify(
        PublicApplicationAbuseCheck(
            public_job_id=public_job_id,
            idempotency_key=idempotency_key,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            challenge_token=challenge_token,
        )
    )
    scanner = await get_malware_scanner(request)
    try:
        scan_result = await scanner.scan_content(
            content=content,
            content_type=content_type,
        )
    except MalwareScannerError as error:
        raise PublicApplicationScanUnavailableError(
            "Résumé could not be scanned before submission."
        ) from error
    if scan_result.verdict is MalwareScanVerdict.INFECTED:
        raise PublicApplicationResumeRejectedError(
            "Résumé did not pass the security scan. Upload a different file."
        )

    scan_id = uuid4()
    expires_at = datetime.now(UTC) + _RESUME_SCAN_PROOF_LIFETIME
    object_key = public_application_resume_scan_object_key(
        tenant_id=tenant_id,
        scan_id=scan_id,
    )

    async def store_scan_proof() -> tuple[int, dict[str, Any]]:
        proof = {
            "resume_scan_id": str(scan_id),
            "public_job_id": str(public_job_id),
            "content_sha256": content_digest,
            "content_type": content_type,
            "byte_size": len(content),
            "scanner_name": scan_result.scanner_name,
            "scan_expires_at": expires_at.isoformat(),
            "object_key": object_key,
        }
        cleanup_event = enqueue_outbox_event(
            session,
            context=context,
            event_type="public_application_resume.cleanup_requested",
            aggregate_type="public_application_resume_scan",
            aggregate_id=str(scan_id),
            deduplication_key=f"public_application_resume.cleanup_requested:{scan_id}",
            payload={
                "scan_id": str(scan_id),
                "scan_token_hash": hash_idempotency_key(idempotency_key.strip()),
            },
        )
        cleanup_event.next_attempt_at = expires_at
        return status.HTTP_201_CREATED, proof

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="public_application.resume_scan",
        payload=scan_payload,
        operation=store_scan_proof,
    )
    await session.commit()
    response = JSONResponse(
        status_code=result.status_code,
        content=PublicApplicationResumeScanResponse(
            scan_token=idempotency_key.strip(),
            expires_at=result.body["scan_expires_at"],
        ).model_dump(mode="json"),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post(
    "/jobs/{public_job_id}/applications",
    response_model=PublicApplicationAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_public_application_body_limit)],
    summary="Submit a public job application",
)
async def submit_public_application_endpoint(
    public_job_id: UUID,
    request: Request,
    session: DatabaseSession,
    abuse_guard: AbuseGuard,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Accept an application without exposing candidate or job state."""
    resume: UploadFile | None = None
    resume_scan_token_value: str | None = None
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        allowed_fields = {
            "full_name",
            "email",
            "phone",
            "location",
            "source_reference",
            "privacy_consent",
            "challenge_token",
            "resume",
            "resume_scan_token",
        }
        if set(form.keys()) - allowed_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid application submission.",
            )
        if any(len(form.getlist(key)) != 1 for key in form.keys()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid application submission.",
            )
        raw_scan_token = form.get("resume_scan_token")
        if raw_scan_token is not None:
            if not isinstance(raw_scan_token, str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Invalid application submission.",
                )
            resume_scan_token_value = raw_scan_token
        values: dict[str, object] = {
            key: form.get(key)
            for key in allowed_fields - {"resume", "resume_scan_token"}
            if form.get(key) is not None
        }
        if values.get("privacy_consent") == "true":
            values["privacy_consent"] = True
        candidate_resume = form.get("resume")
        if isinstance(candidate_resume, UploadFile):
            resume = candidate_resume
        try:
            payload = SubmitPublicApplicationRequest.model_validate(values)
        except ValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid application submission.",
            ) from error
    else:
        try:
            payload = SubmitPublicApplicationRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid application submission.",
            ) from error

    resume_content: bytes | None = None
    if resume is not None:
        resume_content = await resume.read(_MAX_RESUME_BYTES + 1)
        await resume.close()
        if not 0 < len(resume_content) <= _MAX_RESUME_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Résumé must not exceed 10 MiB.",
            )
        if not resume.filename or len(resume.filename) > 255:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Résumé filename is invalid.",
            )
        if "/" in resume.filename or "\\" in resume.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Résumé filename is invalid.",
            )
        if any(ord(character) < 32 for character in resume.filename):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Résumé filename is invalid.",
            )

    resume_content_type = resume.content_type if resume else None
    if resume is not None and not resume_content_type:
        resume_content_type = (
            "application/pdf"
            if resume.filename and resume.filename.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if resume.filename and resume.filename.lower().endswith(".docx")
            else None
        )
    if resume is not None and resume_content_type not in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Résumé must be a PDF or Word document.",
        )
    if resume_content is not None and resume_content_type is not None:
        has_valid_signature = (
            resume_content_type == "application/pdf" and resume_content.startswith(b"%PDF-")
        ) or (
            resume_content_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            and resume_content.startswith(b"PK\x03\x04")
        )
        if not has_valid_signature:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Résumé file type does not match its contents.",
            )

    tenant_id = await resolve_public_application_tenant(
        session,
        public_job_id=public_job_id,
    )
    context = TenantContext(
        tenant_id=tenant_id,
        subject="public:job-application",
        roles=frozenset(),
        request_id=request.headers.get("X-Request-ID", "unknown"),
    )

    idempotency_payload = {
        "public_job_id": str(public_job_id),
        **payload.model_dump(mode="json"),
        **(
            {
                "resume_filename": resume.filename,
                "resume_content_type": resume_content_type,
                "resume_sha256": sha256(resume_content).hexdigest(),
                "resume_size": len(resume_content),
                "resume_scan_token_hash": hash_idempotency_key(
                    resume_scan_token_value or ""
                ),
            }
            if resume is not None and resume_content is not None
            else {}
        ),
    }
    replay = await get_idempotent_replay(
        session,
        context=context,
        key=idempotency_key,
        operation_name="public_application.submit",
        payload=idempotency_payload,
    )
    if replay is not None:
        response = idempotency_response(replay)
        response.headers["Cache-Control"] = "no-store"
        return response
    await session.rollback()

    if resume is not None and not resume_scan_token_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Scan the résumé before submitting your application.",
        )
    if resume is None and resume_scan_token_value is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A résumé scan token was provided without a résumé file.",
        )
    if resume is None:
        await abuse_guard.verify(
            PublicApplicationAbuseCheck(
                public_job_id=public_job_id,
                idempotency_key=idempotency_key,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
                challenge_token=payload.challenge_token,
            )
        )

    storage: ObjectStorage | None = None
    if resume_content is not None and resume_content_type is not None:
        storage = await get_object_storage(request)

    async def operation() -> tuple[int, dict[str, Any]]:
        await submit_public_application(
            session,
            context=context,
            public_job_id=public_job_id,
            command=SubmitPublicApplicationCommand(
                full_name=payload.full_name,
                email=payload.email,
                phone=payload.phone,
                location=payload.location,
                source_reference=payload.source_reference,
                resume_filename=resume.filename if resume else None,
                resume_content_type=resume_content_type,
                resume_content=resume_content,
                resume_scan_token=resume_scan_token_value,
            ),
            storage=storage,
        )
        return (
            status.HTTP_202_ACCEPTED,
            PublicApplicationAcceptedResponse().model_dump(mode="json"),
        )

    result: IdempotencyResult = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="public_application.submit",
        payload=idempotency_payload,
        operation=operation,
    )
    await session.commit()

    response = idempotency_response(result)
    response.headers["Cache-Control"] = "no-store"
    return response
