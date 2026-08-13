from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import Any, Dict, List
import tempfile
import os
import time
import uuid
from pathlib import Path

from src.parser.pdf_parser import parse_pdf_to_json
from src.agents.pipeline import run_pipeline
from src.monitoring.logger import monitor_logger

router = APIRouter()

LOG_FILE_PATH = "src/monitoring/logs/paper_lens_monitoring.jsonl"


@router.post("/parse-pdf")
async def parse_pdf_endpoint(file: UploadFile = File(...)):
    """
    Parses a PDF and returns its structured section hierarchy as JSON.
    """
    t0 = time.time()
    req_id = f"req_{uuid.uuid4().hex[:10]}"
    error_msg = None
    parsed_data = []

    if not file.filename.endswith(".pdf"):
        error_msg = "Only PDF files are supported"
        monitor_logger.log(
            level="ERROR",
            endpoint="/api/parse-pdf",
            agent_invoked="FastAPI",
            cached=False,
            input_data={"filename": file.filename},
            latency_ms=(time.time() - t0) * 1000.0,
            errors=error_msg,
            request_id=req_id,
        )
        raise HTTPException(status_code=400, detail=error_msg)

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, 'wb') as temp_file:
            content = await file.read()
            temp_file.write(content)

        parsed_data = parse_pdf_to_json(Path(temp_path))
        return {
            "request_id": req_id,
            "filename": file.filename,
            "monitoring_log": LOG_FILE_PATH,
            "data": parsed_data,
        }
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        latency_ms = (time.time() - t0) * 1000.0
        monitor_logger.log(
            level="ERROR" if error_msg else "INFO",
            endpoint="/api/parse-pdf",
            agent_invoked="PyMuPDFParser",
            cached=False,
            input_data={"filename": file.filename},
            output_data={"top_level_sections_count": len(parsed_data)},
            latency_ms=latency_ms,
            errors=error_msg,
            request_id=req_id,
        )


@router.post("/analyze")
async def analyze_endpoint(
    sections: List[Dict[str, Any]],
    pdf_name: str = Query("paper", help="Name of PDF file for output caching"),
    force_rerun: bool = Query(False, help="Force re-run LLM pipeline bypassing cache"),
):
    """
    Runs the two-agent pipeline on a parsed paper JSON with smart output caching.

    Accepts the output of /api/parse-pdf (the `data` array) as the request body.
    Returns a glossary of AI/ML terms with in-context and general definitions.
    """
    t0 = time.time()
    req_id = f"req_{uuid.uuid4().hex[:10]}"
    error_msg = None
    result = {}

    if not sections:
        error_msg = "sections list must not be empty"
        monitor_logger.log(
            level="ERROR",
            endpoint="/api/analyze",
            agent_invoked="FastAPI",
            cached=False,
            input_data={"sections_count": 0},
            latency_ms=(time.time() - t0) * 1000.0,
            errors=error_msg,
            request_id=req_id,
        )
        raise HTTPException(status_code=400, detail=error_msg)
    try:
        result = run_pipeline(sections, pdf_name=pdf_name, request_id=req_id, force_rerun=force_rerun)
        result["monitoring_log"] = LOG_FILE_PATH
        return result
    except EnvironmentError as e:
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        error_msg = f"Pipeline error: {str(e)}"
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        latency_ms = (time.time() - t0) * 1000.0
        monitor_logger.log(
            level="ERROR" if error_msg else "INFO",
            endpoint="/api/analyze",
            agent_invoked="FastAPI_AnalyzeRoute",
            cached=result.get("cached", False),
            input_data={"sections_count": len(sections), "pdf_name": pdf_name, "force_rerun": force_rerun},
            latency_ms=latency_ms,
            errors=error_msg,
            request_id=req_id,
        )


@router.post("/parse-and-analyze")
async def parse_and_analyze_endpoint(
    file: UploadFile = File(...),
    force_rerun: bool = Query(False, help="Force re-run LLM pipeline bypassing cache"),
):
    """
    One-shot endpoint: parses a PDF and immediately runs the agentic pipeline with smart caching.
    Returns structured sections + full AI/ML glossary in a single response.
    """
    t0 = time.time()
    req_id = f"req_{uuid.uuid4().hex[:10]}"
    error_msg = None
    analysis = {}

    if not file.filename.endswith(".pdf"):
        error_msg = "Only PDF files are supported"
        monitor_logger.log(
            level="ERROR",
            endpoint="/api/parse-and-analyze",
            agent_invoked="FastAPI",
            cached=False,
            input_data={"filename": file.filename},
            latency_ms=(time.time() - t0) * 1000.0,
            errors=error_msg,
            request_id=req_id,
        )
        raise HTTPException(status_code=400, detail=error_msg)

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, 'wb') as temp_file:
            content = await file.read()
            temp_file.write(content)

        parsed_data = parse_pdf_to_json(Path(temp_path))
        pdf_name = Path(file.filename).stem
        analysis = run_pipeline(parsed_data, pdf_name=pdf_name, request_id=req_id, force_rerun=force_rerun)

        return {
            "request_id": req_id,
            "filename": file.filename,
            "monitoring_log": LOG_FILE_PATH,
            "sections": parsed_data,
            **analysis,
        }
    except EnvironmentError as e:
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        latency_ms = (time.time() - t0) * 1000.0
        monitor_logger.log(
            level="ERROR" if error_msg else "INFO",
            endpoint="/api/parse-and-analyze",
            agent_invoked="FastAPI_ParseAndAnalyzeRoute",
            cached=analysis.get("cached", False),
            input_data={"filename": file.filename, "force_rerun": force_rerun},
            latency_ms=latency_ms,
            errors=error_msg,
            request_id=req_id,
        )
