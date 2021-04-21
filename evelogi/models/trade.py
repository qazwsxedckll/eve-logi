from sqlalchemy.sql.expression import update
from evelogi.extensions import db

class HistoryVolume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type_id = db.Column(db.Integer, nullable=False)
    region_id = db.Column(db.Integer, nullable=False)
    volume = db.Column(db.Integer, nullable=False)
    update_time = db.Column(db.Date, nullable=False)