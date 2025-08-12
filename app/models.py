from app import db
from datetime import datetime

class Lead(db.Model):
    __tablename__ = 'leads'
    
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, unique=True, nullable=False)
    stage_id = db.Column(db.String(50), nullable=False)
    stage_label = db.Column(db.String(100), nullable=False)
    operator_id = db.Column(db.Integer, nullable=False)
    operator_name = db.Column(db.String(100), nullable=False)
    modified_date = db.Column(db.DateTime, nullable=False)
    created_date = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.Index('idx_lead_stage', 'stage_id'),
        db.Index('idx_lead_modified', 'modified_date'),
        db.Index('idx_lead_operator', 'operator_id'),
    )

    def __repr__(self):
        return f'<Lead {self.lead_id} - {self.stage_label}>'
