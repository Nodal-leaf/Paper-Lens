import argparse
import sqlite3
from pathlib import Path
from parser.pdf_parser import parse_pdf_to_json

def setup_database(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(255) NOT NULL,
            number VARCHAR(50),
            page_number INTEGER,
            content TEXT NOT NULL,
            position INTEGER NOT NULL,
            parent_id INTEGER
        )
    ''')
    conn.commit()
    return conn

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
    
    conn = setup_database(db_path)
    cursor = conn.cursor()
    
    # Clear old sections if re-parsing
    cursor.execute("DELETE FROM sections")
    
    for idx, sec in enumerate(sections):
        cursor.execute('''
            INSERT INTO sections (title, number, page_number, content, position, parent_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            sec.get('title', ''), 
            sec.get('number'), 
            sec.get('page_number'), 
            sec.get('content', ''), 
            idx, 
            None # parent_id not computed currently by parse_pdf_to_json outputting flat list
        ))
        
    conn.commit()
    conn.close()
    print(f"Database saved to {db_path}")

if __name__ == "__main__":
    main()
