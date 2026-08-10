from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from database.models import Base, Section

def init_db(db_path: Path) -> sessionmaker:
    """Initializes the SQLite database and returns a SQLAlchemy sessionmaker."""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

def clear_sections(session: Session):
    """Deletes all existing sections from the database."""
    session.query(Section).delete()
    session.commit()

def save_document_sections(session: Session, sections_json: List[Dict[str, Any]]):
    """
    Recursively saves hierarchical sections JSON to the database.
    """
    def _create_sections(section_dicts: List[Dict[str, Any]], parent_id: int = None) -> List[Section]:
        sections = []
        for idx, sec_dict in enumerate(section_dicts):
            section = Section(
                title=sec_dict.get('title', ''),
                number=sec_dict.get('number'),
                page_number=sec_dict.get('page_number'),
                content=sec_dict.get('content', ''),
                position=idx,
                parent_id=parent_id
            )
            sections.append(section)
            
            # Since we are using SQLAlchemy relationships, we can nest subsections easily, 
            # but to be safe with parent_id assignment we can add to session first or use the relation directly.
            # Let's use the relation directly.
            
            subsections_dict = sec_dict.get('subsections', [])
            if subsections_dict:
                section.subsections = _create_sections(subsections_dict)
                
        return sections

    db_sections = _create_sections(sections_json)
    session.add_all(db_sections)
    session.commit()
