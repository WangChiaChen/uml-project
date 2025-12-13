from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
db = SQLAlchemy()

class Role:
    USER = "user"
    ADMIN = "admin"
    UNIT = "unit"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.String(32), unique=True, nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(128), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), default=Role.USER)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)


class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_name = db.Column(db.String(128), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class CaseStatus:
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    location_text = db.Column(db.String(256))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    incident_time = db.Column(db.DateTime)
    report_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(32), default=CaseStatus.DRAFT)
    event_type = db.Column(db.String(64))
    attribute_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_unit_id = db.Column(db.Integer, db.ForeignKey('unit.id'))
    is_fake = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref='cases')
    assigned_unit = db.relationship('Unit')

class MediaFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False)
    file_path = db.Column(db.String(256), nullable=False)
    file_type = db.Column(db.String(32))
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    case = db.relationship('Case', backref='media_files')

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False)
    rating = db.Column(db.Integer)
    comments = db.Column(db.Text)
    submission_time = db.Column(db.DateTime, default=datetime.utcnow)
    case = db.relationship('Case', backref='feedbacks')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(256))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(32))
    user = db.relationship('User', backref='notifications')

class TaskAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.String(20), unique=True)
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=False)
    creation_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(32), default="assigned")
    assigned_personnel = db.Column(db.String(128))
    notes = db.Column(db.Text)
    case = db.relationship('Case', backref='assignments')
