"""Helper that wraps successful payloads in the standard {"success": true, "data": ...} envelope."""
from pydantic import BaseModel


def ok(data: BaseModel) -> dict:
    return {"success": True, "data": data.model_dump(mode="json")}
