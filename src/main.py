import argparse
from pathlib import Path
from parser.pdf_parser import parse_pdf_to_json
from database.repository import init_db, clear_sections, save_document_sections

def main():
    parser = argparse.ArgumentParser(description="Parse research paper PDF and store output.")
    parser.add_argument("pdf", type=str, help="Path to the PDF file to parse")
    parser.add_argument("out_dir", type=str, help="Directory where the JSON output will be stored")
    parser.add_argument(
        "--db", 
        type=str, 
        default="data", 
        help="Directory where the SQLite database will be stored (default: data)"
    )
    
    args = parser.parse_args()
    
    pdf_path = Path(args.pdf)
    out_dir = Path(args.out_dir)
    db_dir = Path(args.db)
    
    if not pdf_path.exists():
        print(f"Error: PDF file {pdf_path} does not exist.")
        return
        
    out_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)
    
    json_path = out_dir / f"{pdf_path.stem}.json"
    db_path = db_dir / f"{pdf_path.stem}.db"
    
    print(f"Parsing {pdf_path}...")
    sections = parse_pdf_to_json(pdf_path, json_path)
    
    print(f"JSON output saved to {json_path}")
    
    SessionLocal = init_db(db_path)
    with SessionLocal() as session:
        # Clear old sections if re-parsing
        clear_sections(session)
        
        # Save new sections hierarchically
        save_document_sections(session, sections)
    
    print(f"Database saved to {db_path}")

if __name__ == "__main__":
    main()
