from typing import Annotated, Sequence, List, Type, Optional
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, File, UploadFile, APIRouter, HTTPException, status
from uuid import UUID
from fastapi import (
    Depends,
    Security,
    HTTPException,
    status,
    Query,
    Body,
    Form,
    Path,
    Response,
)

from print_service import PrintServiceManager, PrintJob
from config import Config
from log import get_logger
from db import get_session

config = Config()
log = get_logger()


fast_api_router: APIRouter = APIRouter()


@fast_api_router.post("/print/png")
async def print_png(file: Annotated[bytes, File()]):
    worker_status = PrintServiceManager().get_worker_status()
    if worker_status.status != "running":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Printing service not running.",
        )
    with get_session() as session:
        PrintJob()
        stmt = (
            select(PrintJob)
            .where(is_(PrintJob.started_at, None))
            .order_by(PrintJob.created_at)
        )
        return session.exec(stmt).first()
    return {"message": "Hello World"}
