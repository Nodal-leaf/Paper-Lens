from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship, backref

Base = declarative_base()

class Section(Base):
    __tablename__ = 'sections'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    number = Column(String(50), nullable=True)
    page_number = Column(Integer, nullable=True)
    content = Column(Text, nullable=False, default='')
    position = Column(Integer, nullable=False)

    # Stores the list of extracted AI/ML terms for this section's content.
    # Shape: [{"term": str, "context_definition": str, "general_definition": str, "occurrences": [str]}]
    extracted_terms = Column(JSON, nullable=True, default=None)

    parent_id = Column(Integer, ForeignKey('sections.id'), nullable=True)

    # Self-referential relationship to hold subsections
    subsections = relationship(
        'Section',
        backref=backref('parent', remote_side=[id]),
        cascade='all, delete-orphan',
        order_by='Section.position'
    )

