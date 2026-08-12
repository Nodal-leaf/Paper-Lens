from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Any, Dict, List
import tempfile
import os
from pathlib import Path

from parser.pdf_parser import parse_pdf_to_json
from agents.pipeline import run_pipeline

router = APIRouter()


@router.post("/parse-pdf")
async def parse_pdf_endpoint(file: UploadFile = File(...)):
    """
    Parses a PDF and returns its structured section hierarchy as JSON.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, 'wb') as temp_file:
            content = await file.read()
            temp_file.write(content)

        parsed_data = parse_pdf_to_json(Path(temp_path))
        return {"filename": file.filename, "data": parsed_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/analyze")
async def analyze_endpoint(sections: List[Dict[str, Any]]):
    """
    Runs the two-agent pipeline on a parsed paper JSON.

    Accepts the output of /api/parse-pdf (the `data` array) as the request body.
    Returns a glossary of AI/ML terms with in-context and general definitions.
    """
    if not sections:
        raise HTTPException(status_code=400, detail="sections list must not be empty")
    try:
        result = run_pipeline(sections)
        return result
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.post("/parse-and-analyze")
async def parse_and_analyze_endpoint(file: UploadFile = File(...)):
    """
    One-shot endpoint: parses a PDF and immediately runs the agentic pipeline.
    Returns structured sections + full AI/ML glossary in a single response.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, 'wb') as temp_file:
            content = await file.read()
            temp_file.write(content)

        parsed_data = parse_pdf_to_json(Path(temp_path))
        pdf_name = Path(file.filename).stem
        analysis = run_pipeline(parsed_data, pdf_name=pdf_name)

        return {
            "filename": file.filename,
            "sections": parsed_data,
            **analysis,
        }
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
