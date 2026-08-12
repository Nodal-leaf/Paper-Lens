from pathlib import Path
from typing import Any, Dict, List, Optional
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


def save_document_sections(
    session: Session,
    sections_json: List[Dict[str, Any]],
    terms_by_title: Optional[Dict[str, List[Dict[str, Any]]]] = None,
):
    """
    Recursively saves hierarchical sections JSON to the database.

    Args:
        session: Active SQLAlchemy session.
        sections_json: Nested section list from parse_pdf_to_json().
        terms_by_title: Optional mapping of section title → list of extracted
                        term dicts to persist alongside the section content.
    """
    terms_by_title = terms_by_title or {}

    def _create_sections(
        section_dicts: List[Dict[str, Any]],
        parent_id: int = None,
    ) -> List[Section]:
        sections = []
        for idx, sec_dict in enumerate(section_dicts):
            title = sec_dict.get('title', '')
            section = Section(
                title=title,
                number=sec_dict.get('number'),
                page_number=sec_dict.get('page_number'),
                content=sec_dict.get('content', ''),
                position=idx,
                parent_id=parent_id,
                extracted_terms=terms_by_title.get(title),  # None if not analysed yet
            )
            sections.append(section)

            subsections_dict = sec_dict.get('subsections', [])
            if subsections_dict:
                section.subsections = _create_sections(subsections_dict)

        return sections

    db_sections = _create_sections(sections_json)
    session.add_all(db_sections)
    session.commit()


def update_section_terms(
    session: Session,
    section_title: str,
    terms: List[Dict[str, Any]],
):
    """
    Updates the extracted_terms column for all sections matching the given title.

    Args:
        session: Active SQLAlchemy session.
        section_title: Title of the section to update.
        terms: List of explained term dicts from TermExplainerAgent.
    """
    rows = session.query(Section).filter(Section.title == section_title).all()
    for row in rows:
        row.extracted_terms = terms
    session.commit()
