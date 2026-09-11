"""Accept file payloads over either transport.

The FreeBuff brief specifies **base64 JSON** for the internal service
(``{"image_b64": "..."}``). OpenCode's backend scaffolding sends **multipart
form uploads** instead. Rather than making one side change, the file endpoints
accept both:

* ``application/json`` — ``{image_b64 | audio_b64: "<base64>"}``;
* ``multipart/form-data`` — a file part, or a base64 string part.

Multipart file bytes are base64-encoded here, so every service downstream sees
exactly one internal representation and no model code needs to know which
transport the caller used.

Field names are accepted generously because the calling code is written by
another agent: ``/ocr`` takes ``file`` (OpenCode's name) or ``image``;
``/tumor-predict`` takes ``dicom_file``; ``/faceid/embed`` takes ``image``;
``/stt`` takes ``audio_file``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Sequence

from fastapi import Request

from utils.errors import ModelServiceError

#: Content types Starlette parses into a form.
FORM_CONTENT_TYPES = ("multipart/form-data", "application/x-www-form-urlencoded")

_TRUE = {"1", "true", "yes", "y", "on"}


@dataclass
class Payload:
    """A base64 payload plus any other scalar fields the caller sent."""

    value: str
    fields: dict[str, Any] = field(default_factory=dict)

    def flag(self, name: str, default: bool = False) -> bool:
        """Read a boolean sibling field, accepting JSON and form spellings."""
        value = self.fields.get(name)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _TRUE


def _missing(label: str, accepted: Sequence[str]) -> ModelServiceError:
    return ModelServiceError(
        "missing_payload",
        f"no {label} payload found; send JSON {{'{label}_b64': '...'}} or a "
        f"multipart form-data part named one of {list(accepted)}",
        422,
    )


async def read_payload(
    request: Request,
    *,
    json_fields: Sequence[str],
    form_fields: Sequence[str],
    label: str,
) -> Payload:
    """Return a base64 payload from a JSON body or a multipart form.

    Raises :class:`ModelServiceError` with a 422 when nothing usable is present,
    so the error shape stays consistent with the rest of the service.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith(FORM_CONTENT_TYPES):
        return await _from_form(request, form_fields, label)
    return await _from_json(request, json_fields, label)


async def _from_json(request: Request, fields: Sequence[str], label: str) -> Payload:
    """Pull a base64 string, and any siblings, out of a JSON body."""
    try:
        body: Any = await request.json()
    except Exception as exc:  # noqa: BLE001 - malformed JSON is the caller's fault
        raise ModelServiceError(
            "invalid_body", f"request body is not valid JSON: {exc}", 400
        ) from exc

    if isinstance(body, dict):
        for name in fields:
            value = body.get(name)
            if isinstance(value, str) and value.strip():
                siblings = {key: item for key, item in body.items() if key != name}
                return Payload(value=value, fields=siblings)
    raise _missing(label, fields)


async def _from_form(request: Request, fields: Sequence[str], label: str) -> Payload:
    """Pull a file or base64 string, and any siblings, out of a multipart form."""
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001
        raise ModelServiceError(
            "invalid_body", f"multipart body could not be parsed: {exc}", 400
        ) from exc

    scalars = {
        key: value
        for key, value in form.multi_items()
        if isinstance(value, str)
    }

    for name in fields:
        value = form.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                # Some clients put base64 in a form field rather than a file part.
                return Payload(value=value, fields={k: v for k, v in scalars.items() if k != name})
            continue

        # Starlette's UploadFile: read once and normalise to base64.
        try:
            data = await value.read()
        except Exception as exc:  # noqa: BLE001
            raise ModelServiceError(
                "invalid_body", f"could not read uploaded part {name!r}: {exc}", 400
            ) from exc
        if data:
            return Payload(
                value=base64.b64encode(data).decode("ascii"),
                fields={k: v for k, v in scalars.items() if k != name},
            )

    raise _missing(label, fields)


def base64_body_schema(field_name: str, label: str, file_field: str) -> dict[str, Any]:
    """``openapi_extra`` describing both accepted request shapes.

    Routes read the raw request to support two transports, which costs FastAPI's
    automatic body schema; supplying it explicitly keeps /docs accurate instead
    of showing a bodiless endpoint.
    """
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            field_name: {
                                "type": "string",
                                "description": f"Base64-encoded {label}",
                            }
                        },
                        "required": [field_name],
                    }
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            file_field: {
                                "type": "string",
                                "format": "binary",
                                "description": f"{label.capitalize()} file upload",
                            }
                        },
                    }
                },
            },
        }
    }


#: Prebuilt OpenAPI bodies for the endpoints that take a file.
IMAGE_BODY = base64_body_schema("image_b64", "image", "file")
AUDIO_BODY = base64_body_schema("audio_b64", "audio", "audio_file")

#: Accepted field names per endpoint: JSON key, then multipart aliases.
OCR_FIELDS = ("image_b64",)
OCR_FORM_FIELDS = ("file", "image", "image_b64", "upload")

TUMOR_FIELDS = ("image_b64",)
TUMOR_FORM_FIELDS = ("dicom_file", "file", "image", "image_b64", "upload")

FACEID_FIELDS = ("image_b64",)
FACEID_FORM_FIELDS = ("image", "file", "image_b64", "upload")

STT_FIELDS = ("audio_b64",)
STT_FORM_FIELDS = ("audio_file", "audio", "file", "audio_b64", "upload")
