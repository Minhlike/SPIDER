from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pathlib import Path
from spider.cli.main import get_service

router = APIRouter(prefix="/explain", tags=["Explain & Evidence"])

@router.get("/{assertion_id}", response_model=Dict[str, Any])
async def explain_assertion(assertion_id: str):
    service = get_service()
    await service.start()
    try:
        explanation = await service.explain_assertion(assertion_id)
        if not explanation:
            raise HTTPException(status_code=404, detail="Assertion not found")
        return explanation
    finally:
        await service.stop()

@router.get("/artifact/{artifact_sha256}")
async def view_raw_artifact(artifact_sha256: str):
    runs_dir = Path("data/runs")
    for raw_file in runs_dir.glob("*/*.raw"):
        if artifact_sha256[:8] in raw_file.name:
            content = raw_file.read_text(encoding="utf-8", errors="replace")
            # Limit preview size to 50KB to protect client
            preview = content[:50000]
            return {
                "file_name": raw_file.name,
                "sha256": artifact_sha256,
                "byte_size": raw_file.stat().st_size,
                "content_preview": preview
            }
    raise HTTPException(status_code=404, detail="Artifact file not found on disk")
