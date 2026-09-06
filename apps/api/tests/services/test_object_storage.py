"""Tests for server-generated object-storage keys."""

from uuid import UUID

from app.services.object_storage import candidate_document_object_key


def test_candidate_document_key_is_deterministic_and_contains_no_filename() -> None:
    """Verify candidate document keys are deterministic and filename-independent."""
    key = candidate_document_object_key(
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        candidate_id=UUID("22222222-2222-2222-2222-222222222222"),
        document_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    assert key == (
        "v1/tenants/11111111-1111-1111-1111-111111111111/"
        "candidates/22222222-2222-2222-2222-222222222222/"
        "documents/33333333-3333-3333-3333-333333333333/content"
    )
