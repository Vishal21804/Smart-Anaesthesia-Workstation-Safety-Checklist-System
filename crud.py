from sqlalchemy.orm import Session
from models import User


def authenticate_user(db: Session, email: str, password: str):
    return db.query(User).filter(
        User.email == email,
        User.password == password,
        User.status == 1
    ).first()


def get_users_by_hospital(db: Session, hospital_id: int):
    return db.query(User).filter(
        User.hospital_id == hospital_id,
        User.role != "HM"
    ).all()


def update_user_status(db: Session, user_id: int, status: int):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return None

    user.status = status
    db.commit()
    db.refresh(user)
    return user


def get_user_profile(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, request, creator_id: int, hospital_id: int):

    existing = db.query(User).filter(
        User.email == request.email
    ).first()

    if existing:
        return None

    # get hospital default settings
    settings = db.query(ChecklistSettings).filter(
        ChecklistSettings.hospital_id == hospital_id
    ).first()

    # decide password based on role
    if request.role == "AT" and settings:
        password = settings.default_at_password
    elif request.role == "BMET" and settings:
        password = settings.default_bmet_password
    else:
        password = request.password

    new_user = User(
        name=request.name,
        email=request.email,
        password=password,
        role=request.role,
        employee_id=request.employee_id,
        status=1,
        created_by=creator_id,
        hospital_id=hospital_id
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user
