from fastapi import APIRouter, UploadFile, File, HTTPException
import tempfile
import os
from pathlib import Path

from parser.pdf_parser import parse_pdf_to_json

router = APIRouter()

@router.post("/parse-pdf")
async def parse_pdf_endpoint(file: UploadFile = File(...)):
    """
    Endpoint to parse a given PDF file and return the structured JSON.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Create a temporary file to save the uploaded PDF
    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        # Write uploaded file to temp file
        with os.fdopen(fd, 'wb') as temp_file:
            content = await file.read()
            temp_file.write(content)
        
        # Parse the PDF to JSON
        parsed_data = parse_pdf_to_json(Path(temp_path))
        
        return {"filename": file.filename, "data": parsed_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)
