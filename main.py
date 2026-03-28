from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from database import SessionLocal, engine, get_db
import models
import crud
import schemas
from models import Machine, MachineInspection
from fastapi.staticfiles import StaticFiles
import os
import shutil
from datetime import datetime, date
from models import ChecklistSettings
import time
from datetime import datetime
import pytz
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

IST = pytz.timezone("Asia/Kolkata")

# ================= SMTP CONFIGURATION =================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "vishal21804@gmail.com"  # 🔴 CHANGE THIS
SMTP_PASSWORD = "vckjrhryfkdvolvx"  # 🔴 CHANGE THIS (Use App Password)

def send_otp_email(receiver_email: str, otp: str):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = receiver_email
        msg['Subject'] = "Your OTP for Password Reset"

        body = f"Hello,\n\nYour OTP for resetting your password is: {otp}\n\nThis OTP is valid for a single session. Please do not share it with anyone."
        msg.attach(MIMEText(body, 'plain'))

        # Use standard SMTP for Port 587
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Required for Port 587
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"SMTP Error: {str(e)}")
        return False



def get_current_user(db: Session = Depends(get_db)):
    # TEMP VERSION (for testing)
    user = db.query(models.User).first()
    return user

def get_current_hm(
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "HM":
        raise HTTPException(
            status_code=403,
            detail="Only Hospital Manager (HM) allowed"
        )
    return current_user

UPLOAD_DIR = "uploads/profile_pics"
os.makedirs(UPLOAD_DIR, exist_ok=True)

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for uploads so the Android app can download images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ================= DATABASE SESSION =================

@app.get("/")
def root():
    return {"message": "API running"}

# ================= HM REGISTRATION =================
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import re
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)


# ================= LOGIN =================
@app.post("/login")
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):

    user = crud.authenticate_user(db, request.email, request.password)

    if not user:
        return {
            "status": False,
            "message": "Invalid email or password"
        }

    # UPDATE LAST LOGIN
    user.last_login = datetime.now(IST)
    db.commit()

    return {
        "status": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "hospital_id": user.hospital_id,
            "profile_pic": user.profile_picture,
            "force_password_change": user.force_password_change 
        }
    }


# ================= CREATE USER (HM ONLY) =================
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
import re

def calculate_age(dob: date):
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )

@app.post("/create_user")
def create_user(
    request: schemas.CreateUserRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # -------- VALIDATE CREATOR --------
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM can create users")

    # -------- NAME VALIDATION --------
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")

    if not re.match(r"^[A-Za-z][A-Za-z .'-]*$", request.name.strip()):
        raise HTTPException(status_code=400, detail="Name must contain only alphabets")

    # -------- EMAIL VALIDATION --------
    if not request.email or not request.email.strip():
        raise HTTPException(status_code=400, detail="Email is required")

    existing_email = db.query(models.User).filter(
        models.User.email == request.email
    ).first()

    if existing_email:
        raise HTTPException(status_code=400, detail="Email already exists")

    # -------- DOB VALIDATION --------
    if not request.dob:
        raise HTTPException(status_code=400, detail="Date of Birth is required")

    age = calculate_age(request.dob)

    if age < 18:
        raise HTTPException(status_code=400, detail="User must be at least 18 years old")

    # -------- EMPLOYEE ID CHECK --------
    existing_emp = db.query(models.User).filter(
        models.User.employee_id == request.employee_id
    ).first()

    if existing_emp:
        raise HTTPException(status_code=400, detail="Employee ID already exists")

    # -------- CREATE USER --------
    user = models.User(
        name=request.name.strip(),
        email=request.email.strip(),
        password=request.password,
        role=request.role,
        employee_id=request.employee_id,
        dob=request.dob,
        hospital_id=creator.hospital_id,
        created_by=creator.id,
        status=1,
        force_password_change=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": True,
        "message": "User created successfully"
    }


@app.get("/api/users")
def get_users(
    creator_id: int,
    search: str = None,
    role: str = None,
    db: Session = Depends(get_db)
):
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(models.User).filter(
        models.User.hospital_id == creator.hospital_id,
        models.User.role != "HM"
    )

    if search:
        query = query.filter(models.User.name.ilike(f"%{search}%"))

    if role:
        query = query.filter(models.User.role == role)

    users = query.all()

    user_list = []

    for user in users:
        ot_count = db.query(models.OTAssignment).filter(
            models.OTAssignment.user_id == user.id
        ).count()

        user_list.append({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "employee_id": user.employee_id,
            "profile_pic": user.profile_picture,

            # ✅ FIXED DOB
            "dob": str(user.dob) if user.dob else None,

            "assigned_ots": ot_count,
            "last_login": str(user.last_login) if user.last_login else None
        })

    return {
        "status": True,
        "data": user_list
    }



@app.get("/get_users")
def get_users(
    creator_id: int,
    db: Session = Depends(get_db)
):
    # ---------------- VALIDATE CREATOR ----------------
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    # ---------------- GET USERS ----------------
    users = db.query(models.User).filter(
        models.User.hospital_id == creator.hospital_id,
        models.User.role != "HM"
    ).all()

    data = []

    for u in users:

    # 🔥 COUNT ASSIGNED OTs (CORRECT TABLE)
        ot_count = db.query(models.OTAssignment).filter(
            models.OTAssignment.user_id == u.id
            ).count()

        data.append({
            "id": u.id,
            "name": u.name,
            "email": getattr(u, "email", ""),
            "role": getattr(u, "role", ""),
            "status": getattr(u, "status", 1),
            "employee_id": getattr(u, "employee_id", ""),
            "profile_pic": getattr(u, "profile_picture", None),
            "last_login": u.last_login.date() if getattr(u, "last_login", None) else None,
            "dob": str(u.dob) if getattr(u, "dob", None) else None,
            # ✅ ADD THIS
            "assigned_ots": ot_count
        })

    return {
        "status": True,
        "data": data
    }


from datetime import datetime

@app.put("/hospital/settings")
def update_hospital_settings(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    from datetime import datetime

    print("Hospital ID:", current_user.hospital_id)
    print("Incoming:", data)

    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User has no hospital")

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == current_user.hospital_id
    ).first()

    # create if not exists
    if not settings:
        settings = models.ChecklistSettings(
            hospital_id=current_user.hospital_id
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    # update values
    settings.reset_time = datetime.strptime(
        data["reset_time"], "%H:%M:%S"
    ).time()

    settings.default_at_password = data["default_at_password"]
    settings.default_bmet_password = data["default_bmet_password"]

    db.commit()
    db.refresh(settings)

    return {
        "status": True,
        "message": "Settings updated successfully"
    }


@app.get("/default-password/{role}")
def get_default_password(role: str, hospital_id: int, db: Session = Depends(get_db)):

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == hospital_id
    ).first()

    if not settings:
        return {"password": ""}

    password_map = {
        "AT": settings.default_at_password,
        "BMET": settings.default_bmet_password
    }

    return {"password": password_map.get(role, "")}

# ================= UPDATE USER STATUS (HM ONLY - SAME HOSPITAL) =================
@app.put("/update_user_status")
def update_user_status(
    request: schemas.UpdateUserStatusRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Access denied")

    user = db.query(models.User).filter(
        models.User.id == request.user_id,
        models.User.hospital_id == creator.hospital_id,
        models.User.role != "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.status = request.status
    db.commit()

    return {
        "status": True,
        "message": "User status updated successfully"
    }


# ================= UPDATE USER DETAILS =================
@app.put("/api/user/update")
def update_user_details(
    request: schemas.UpdateUserRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # -------- VALIDATE CREATOR --------
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM can update users")

    # -------- GET USER --------
    user = db.query(models.User).filter(
        models.User.id == request.user_id,
        models.User.hospital_id == creator.hospital_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # -------- NAME VALIDATION --------
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")

    if not re.match(r"^[A-Za-z][A-Za-z .'-]*$", request.name.strip()):
        raise HTTPException(status_code=400, detail="Name must contain only alphabets")

    # -------- EMAIL VALIDATION --------
    existing = db.query(models.User).filter(
        models.User.email == request.email,
        models.User.id != request.user_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    # -------- DOB VALIDATION --------
    if not request.dob:
        raise HTTPException(status_code=400, detail="Date of Birth is required")

    age = calculate_age(request.dob)

    if age < 18:
        raise HTTPException(status_code=400, detail="User must be at least 18 years old")

    # -------- UPDATE --------
    user.name = request.name.strip()
    user.email = request.email.strip()
    user.employee_id = request.employee_id
    user.dob = request.dob

    db.commit()
    db.refresh(user)

    return {
        "status": True,
        "message": "User updated successfully"
    }


# ================= GET PROFILE =================
@app.get("/profile/{user_id}")
def get_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    BASE_URL = "http://localhost:8000/"

    return {
    "status": True,
    "data": {
        "id": user.id,
        "name": user.name or "",
        "email": user.email or "",
        "mobile": user.mobile or "",
        "role": user.role or "",
        "employee_id": user.employee_id or "",
        "dob": str(user.dob) if user.dob else None,  # ✅ ADD
        "last_login": str(user.last_login) if user.last_login else None,  # ✅ ADD
        "hospital_name": hospital.hospital_name if hospital else "",
        "profile_pic": BASE_URL + user.profile_picture if user.profile_picture else None,
        "created_at": user.created_at
    }
}


@app.put("/api/user/update-profile/{user_id}")
async def update_profile(
    user_id: int,
    mobile: str = Form(...),
    profile_pic: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update mobile
    user.mobile = mobile

    # Handle profile picture
    if profile_pic:
        file_extension = profile_pic.filename.split(".")[-1]
        filename = f"user_{user_id}_{int(time.time())}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_pic.file, buffer)

        user.profile_picture = f"uploads/profile_pics/{filename}"

    db.commit()

    return {
        "status": True,
        "message": "Profile updated successfully",
        "profile_picture": user.profile_picture
    }


# ================= OT MANAGEMENT =================


@app.post("/api/ot/add")
def add_ot(
    request: schemas.OTCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):
    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check duplicate OT Code
    existing = db.query(models.OTRoom).filter(
        models.OTRoom.ot_code == request.ot_code
    ).first()

    if existing:
        return {
            "status": False,
            "message": "OT Code already exists"
        }

    # Create OT linked to hospital
    new_ot = models.OTRoom(
        ot_name=request.ot_name,
        ot_code=request.ot_code,
        location=request.location,
        ot_type=request.ot_type,
        description=request.description,
        hospital_id=creator.hospital_id,
        creator_id=creator_id,
        machines_assigned=0,
        issues_count=0,
        status="Operational"
    )

    db.add(new_ot)
    db.commit()

    return {
        "status": True,
        "message": "OT Room created successfully"
    }


@app.get("/api/ot/list")
def get_ot_list(
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get OTs for creator's hospital
    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    data = []

    for ot in ots:

        machine_count = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.ot_id == ot.id
        ).count()

        issue_count = db.query(models.Machine).join(
            models.OTMachineAssignment,
            models.Machine.id == models.OTMachineAssignment.machine_id
        ).filter(
            models.OTMachineAssignment.ot_id == ot.id,
            models.Machine.status == "Not Working"
        ).count()

        data.append({
            "id": ot.id,
            "ot_name": ot.ot_name,
            "ot_code": ot.ot_code,
            "location": ot.location,
            "ot_type": ot.ot_type,
            "machines_assigned": machine_count,
            "issues_count": issue_count,
            "status": ot.status,
            "description": ot.description
        })

    return {
        "status": True,
        "data": data
    }


@app.put("/api/ot/update/{id}")
def update_ot(
    id: int,
    request: schemas.OTCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == id,
        models.OTRoom.hospital_id == creator.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")

    # Check duplicate OT code
    existing = db.query(models.OTRoom).filter(
        models.OTRoom.ot_code == request.ot_code,
        models.OTRoom.id != id
    ).first()

    if existing:
        return {
            "status": False,
            "message": "OT Code already exists"
        }

    ot.ot_name = request.ot_name
    ot.ot_code = request.ot_code
    ot.location = request.location
    ot.ot_type = request.ot_type
    ot.description = request.description

    db.commit()

    return {
        "status": True,
        "message": "OT Room updated successfully"
    }



@app.get("/api/ots")
def get_ots(
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get OTs for the creator's hospital
    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    result = []

    for ot in ots:

        machine_count = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.ot_id == ot.id
        ).count()

        result.append({
            "id": ot.id,
            "name": ot.ot_name,
            "type": ot.ot_type,
            "machine_count": machine_count
        })

    return {
        "status": True,
        "data": result
    }

@app.delete("/api/ot/delete/{id}")
def delete_ot(
    id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == id,
        models.OTRoom.hospital_id == creator.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")

    db.delete(ot)
    db.commit()

    return {
        "status": True,
        "message": "OT Room deleted successfully"
    }


@app.get("/api/ot/user_assignments")
def get_user_assignments(
    creator_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get assignments only from same hospital
    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.hospital_id == creator.hospital_id
    ).all()

    data = []

    for a in assignments:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == a.ot_id,
            models.OTRoom.hospital_id == creator.hospital_id
        ).first()

        if ot:
            data.append({
                "id": ot.id,
                "ot_name": ot.ot_name,
                "ot_code": ot.ot_code,
                "location": ot.location
            })

    return {
        "status": True,
        "data": data
    }


@app.get("/api/ot/assignment_counts")
def get_ot_assignment_counts(
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    data = []

    for ot in ots:

        assignment_count = db.query(models.OTAssignment).filter(
            models.OTAssignment.ot_id == ot.id
        ).count()

        data.append({
            "ot_id": ot.id,
            "assignment_count": assignment_count
        })

    return {
        "status": True,
        "data": data
    }


@app.get("/api/ot/available")
def get_available_ots(
    creator_id: int,
    user_role: str,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get all users of SAME ROLE in this hospital
    same_role_users = db.query(models.User).filter(
        models.User.hospital_id == creator.hospital_id,
        models.User.role == user_role
    ).all()

    same_role_ids = [u.id for u in same_role_users]

    # Get OTs assigned to users of SAME ROLE only
    assigned_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id.in_(same_role_ids)
    ).all()

    assigned_ids = [a[0] for a in assigned_ids]

    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id,
        ~models.OTRoom.id.in_(assigned_ids)
    ).all()

    data = []

    for ot in ots:
        data.append({
            "id": ot.id,
            "ot_name": ot.ot_name,
            "ot_code": ot.ot_code,
            "location": ot.location
        })

    return {
        "status": True,
        "data": data
    }

@app.get("/api/ot/{ot_id}")
def get_ot_details(
    ot_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == ot_id,
        models.OTRoom.hospital_id == user.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")

    return {
        "status": True,
        "data": {
            "id": ot.id,
            "ot_name": ot.ot_name,
            "ot_code": ot.ot_code,
            "location": ot.location,
            "ot_type": ot.ot_type,
            "description": ot.description,
            "status": ot.status
        }
    }




@app.get("/api/machine/types")
def get_machine_types(db: Session = Depends(get_db)):

    types = db.query(models.MachineType).all()

    data = []
    for t in types:
        data.append({
            "id": t.id,
            "type_name": t.type_name
        })

    return {
        "status": True,
        "data": data
    }


@app.post("/api/machine/add")
def add_machine(
    request: schemas.MachineCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    template = models.MachineTemplate(
        machine_name=request.machine_name,
        machine_type_id=request.machine_type_id,
        hospital_id=creator.hospital_id
    )

    db.add(template)
    db.commit()

    return {
        "status": True,
        "message": "Machine template added successfully"
    }


@app.get("/api/machine/list")
def get_machine_list(
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == creator.hospital_id
    ).all()

    data = []

    for m in machines:

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == m.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        assignments = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == m.id
        ).all()

        ot_names = []

        for a in assignments:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == a.ot_id
            ).first()

            if ot:
                ot_names.append(ot.ot_name)

        data.append({
            "id": m.id,
            "machine_name": machine_name,
            "serial_number": m.serial_number,
            "status": m.status,
            "assigned_ots": ot_names
        })

    return {
        "status": True,
        "data": data
    }



@app.post("/api/ot/assign")
def assign_ot(
    request: schemas.AssignOTRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # ---------------- GET USER ----------------
    assigned_user = db.query(models.User).filter(
        models.User.id == request.user_id,
        models.User.status == 1
    ).first()

    if not assigned_user:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    # ---------------- GET OT ----------------
    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == request.ot_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT not found")

    # ---------------- PREVENT SAME USER DUPLICATE ----------------
    existing_same = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == request.user_id,
        models.OTAssignment.ot_id == request.ot_id,
        models.OTAssignment.is_active == True
    ).first()

    if existing_same:
        return {
            "status": False,
            "message": "User already assigned to this OT"
        }

    # ---------------- ROLE-BASED CONTROL ----------------
    # Prevent multiple AT OR multiple BMET for same OT
    existing_same_role = db.query(models.OTAssignment).join(models.User).filter(
        models.OTAssignment.ot_id == request.ot_id,
        models.OTAssignment.is_active == True,
        models.User.role == assigned_user.role
    ).first()

    if existing_same_role:
        return {
            "status": False,
            "message": f"{assigned_user.role} already assigned to this OT"
        }

    # ---------------- DEACTIVATE OLD ASSIGNMENT FOR USER ----------------
    old_assignment = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == request.user_id,
        models.OTAssignment.is_active == True
    ).first()

    if old_assignment:
        old_assignment.is_active = False

    # ---------------- CREATE NEW ASSIGNMENT ----------------
    new_assignment = models.OTAssignment(
        user_id=request.user_id,
        ot_id=request.ot_id,
        hospital_id=assigned_user.hospital_id,
        is_active=True
    )

    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)

    return {
        "status": True,
        "message": "OT assigned successfully",
        "data": {
            "user_id": assigned_user.id,
            "role": assigned_user.role,
            "ot_id": request.ot_id
        }
    }




@app.get("/users/technicians")
def get_technicians(hospital_id: int, db: Session = Depends(get_db)):

    users = db.query(models.User).filter(
        models.User.hospital_id == hospital_id,
        models.User.role == "AT"
    ).all()

    data = []

    for user in users:
        data.append({
            "id": user.id,
            "name": user.name,
            "employee_id": user.employee_id
        })

    return {"status": True, "data": data}






@app.delete("/api/ot/unassign")
def unassign_ot(
    user_id: int,
    ot_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    assignment = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.ot_id == ot_id
    ).first()

    if not assignment:
        return {
            "status": False,
            "message": "Assignment not found"
        }

    db.delete(assignment)
    db.commit()

    return {
        "status": True,
        "message": "OT unassigned successfully"
    }


@app.post("/api/machine/assign")
def assign_machine(
    creator_id: int,
    ot_id: int,
    template_id: int,
    serial_number: str,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # check serial duplicate
    existing = db.query(models.Machine).filter(
        models.Machine.serial_number == serial_number
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Serial already exists")

    # create machine
    machine = models.Machine(
        template_id=template_id,
        serial_number=serial_number,
        hospital_id=user.hospital_id,
        status="Working"
    )

    db.add(machine)
    db.commit()
    db.refresh(machine)

    # assign machine to OT
    assignment = models.OTMachineAssignment(
        ot_id=ot_id,
        machine_id=machine.id,
        hospital_id=user.hospital_id
    )

    db.add(assignment)
    db.commit()

    return {
        "status": True,
        "machine_id": machine.id,
        "message": "Machine assigned successfully"
    }




@app.get("/api/machines/list")
def get_machines_list_simple(db: Session = Depends(get_db)):
    machines = db.query(models.Machine).all()
    data = []
    for m in machines:
        template = db.query(models.MachineTemplate).filter(models.MachineTemplate.id == m.template_id).first()
        data.append({
            "id": m.id,
            "machine_name": template.machine_name if template else f"Machine {m.id}",
            "serial_number": m.serial_number
        })
    return {"status": True, "data": data}

@app.post("/api/ot/assign-machine")
def assign_machine_to_ot(request: schemas.AssignMachineToOTRequest, db: Session = Depends(get_db)):
    # Check if assignment already exists
    existing = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.ot_id == request.ot_id,
        models.OTMachineAssignment.machine_id == request.machine_id
    ).first()
    
    if existing:
        return {"status": False, "message": "Machine already assigned to this OT"}
    
    # Get hospital_id from OT
    ot = db.query(models.OTRoom).filter(models.OTRoom.id == request.ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")
        
    new_assignment = models.OTMachineAssignment(
        ot_id=request.ot_id,
        machine_id=request.machine_id,
        hospital_id=ot.hospital_id
    )
    db.add(new_assignment)
    db.commit()
    
    return {"status": True, "message": "Machine assigned successfully"}




@app.get("/api/machine/available")
def get_available_machines(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    templates = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.hospital_id == user.hospital_id
    ).all()

    data = []

    for t in templates:
        data.append({
            "id": t.id,
            "machine_name": t.machine_name
        })

    return {
        "status": True,
        "data": data
    }

@app.get("/api/user/{user_id}/assigned-ots")
def get_user_assigned_ots(
    user_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.hospital_id == creator.hospital_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [a.ot_id for a in assignments]

    if not ot_ids:
        return {"status": True, "data": []}

    ots = db.query(models.OTRoom).filter(
        models.OTRoom.id.in_(ot_ids)
    ).all()

    today_start = datetime.combine(date.today(), datetime.min.time())

    data = []

    for ot in ots:

        # Total machines in OT
        machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
            models.OTMachineAssignment.ot_id == ot.id
        ).all()

        machine_ids = [m[0] for m in machine_ids]

        total_machines = len(machine_ids)

        # Machines inspected today
        completed_ids = db.query(
            models.MachineInspection.machine_id
        ).filter(
            models.MachineInspection.machine_id.in_(machine_ids),
            models.MachineInspection.created_at >= today_start
        ).distinct().all()

        completed_count = len(completed_ids)

        data.append({
            "id": ot.id,
            "ot_name": ot.ot_name,
            "location": ot.location,
            "ot_type": ot.ot_type,
            "machine_count": total_machines,
            "completed_count": completed_count
        })

    return {
        "status": True,
        "data": data
    }

from datetime import datetime

from pydantic import BaseModel

class InspectMachineRequest(BaseModel):
    machine_id: int
    user_id: int
    status: str
    remarks: str = None
    priority: str = None

from datetime import datetime, date, timedelta
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

@app.post("/api/machine/inspect")
def inspect_machine(
    machine_id: int,
    creator_id: int,
    status: str,
    remarks: str = "",
    priority: str = None,
    db: Session = Depends(get_db)
):

    from datetime import datetime, date
    import pytz

    IST = pytz.timezone("Asia/Kolkata")

    def get_ist_time():
        return datetime.now(IST)

    # Validate user
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid user")

    # Validate machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == user.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # PRIORITY VALIDATION
    allowed_priorities = ["Critical", "Medium", "Low"]

    if priority:
        priority = priority.capitalize()
        if priority not in allowed_priorities:
            raise HTTPException(
                status_code=400,
                detail="Invalid priority. Allowed values: Critical, Medium, Low"
            )
    else:
        priority = "Low"

    today = date.today()

    existing = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id,
        models.MachineInspection.check_date == today
    ).first()

    if existing:
        existing.status = status
        existing.remarks = remarks
        existing.priority = priority
        existing.created_at = datetime.now(IST)   # 🔥 FIXED

    else:
        inspection = models.MachineInspection(
            machine_id=machine_id,
            user_id=creator_id,
            status=status,
            remarks=remarks,
            priority=priority,
            check_date=today,
            created_at=datetime.now(IST)   # 🔥 FIXED
        )
        db.add(inspection)

    machine.status = status
    machine.last_checked = datetime.now(IST)   # 🔥 FIXED

    db.commit()

    return {
        "status": True,
        "message": "Inspection submitted successfully"
    }

@app.get("/api/machine/history")
def get_resolved_machine_history(
    creator_id: int,
    status: str = None,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    data = []

    # ================= GET MACHINE IDS =================

    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user.id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [a.ot_id for a in assignments]

    if not ot_ids:
        return {"status": True, "total": 0, "data": []}

    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {"status": True, "total": 0, "data": []}

    # ================= GET RESOLVED RECORDS =================

    resolved_records = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.status == "Resolved"
    ).order_by(models.MachineInspection.created_at.desc()).all()

    for resolved in resolved_records:

        machine = db.query(models.Machine).filter(
            models.Machine.id == resolved.machine_id
        ).first()

        if not machine:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        # ================= GET AT ISSUE =================

        issue = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id,
            models.MachineInspection.status == "Not Working"
        ).order_by(models.MachineInspection.created_at.desc()).first()

        at_issue = issue.remarks if issue else "No issue details provided"

        # ================= OT NAME =================

        assignment = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).order_by(models.OTMachineAssignment.id.desc()).first()

        ot_name = "Unknown OT"

        if assignment:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == assignment.ot_id
            ).first()

            if ot and ot.ot_name:
                ot_name = ot.ot_name

        # ================= MAINTENANCE NOTES =================

        maintenance_notes = resolved.remarks if resolved.remarks else "No maintenance notes"

        data.append({
    "id": resolved.id,   # 🔥 THIS LINE FIXES EVERYTHING

    "machine_id": machine.id,
    "machine_name": machine_name,
    "serial_number": machine.serial_number,
    "ot_name": ot_name,
    "at_issue": at_issue,
    "maintenance_notes": maintenance_notes,
    "resolved_time": resolved.created_at.strftime("%b %d, %Y • %I:%M %p")
})

    return {
        "status": True,
        "total": len(data),
        "data": data
    }


@app.get("/api/machine/templates")
def get_machine_templates(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    templates = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.hospital_id == user.hospital_id
    ).all()

    data = []

    for t in templates:
        machine_type = db.query(models.MachineType).filter(
            models.MachineType.id == t.machine_type_id
        ).first()

        data.append({
            "id": t.id,
            "machine_name": t.machine_name,
            "machine_type_id": t.machine_type_id,
            "machine_type_name": machine_type.type_name if machine_type else ""  # ✅ FIXED
        })

    return {
        "status": True,
        "data": data
    }



from typing import Optional

@app.put("/api/machine/update/{machine_id}")
def update_machine(
    machine_id: int,
    request: schemas.UpdateMachineRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # -------- Validate creator --------
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # -------- Get machine --------
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # -------- Validate machine type (ONLY if provided) --------
    if request.machine_type_id is not None:
        machine_type = db.query(models.MachineType).filter(
            models.MachineType.id == request.machine_type_id
        ).first()

        if not machine_type:
            raise HTTPException(status_code=400, detail="Invalid machine type")

    # -------- Validate serial number (ONLY if provided) --------
    if request.serial_number is not None:
        if not request.serial_number.strip():
            raise HTTPException(status_code=400, detail="Serial number required")

        # Check duplicate serial number
        duplicate = db.query(models.Machine).filter(
            models.Machine.serial_number == request.serial_number,
            models.Machine.hospital_id == creator.hospital_id,
            models.Machine.id != machine_id
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="Serial number already exists"
            )

    # -------- Validate machine name (ONLY if provided) --------
    if request.machine_name is not None:
        if not request.machine_name.strip():
            raise HTTPException(status_code=400, detail="Machine name required")

    # -------- Update ONLY provided fields --------
    if request.machine_name is not None:
        machine.machine_name = request.machine_name.strip()

    if request.machine_type_id is not None:
        machine.machine_type_id = request.machine_type_id

    if request.serial_number is not None:
        machine.serial_number = request.serial_number.strip()

    db.commit()
    db.refresh(machine)

    return {
        "status": True,
        "message": "Machine updated successfully",
        "data": {
            "id": machine.id,
            "serial_number": machine.serial_number
        }
    }


@app.put("/api/machine/update-template/{machine_id}")
def update_machine_template(
    machine_id: int,
    request: schemas.MachineCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM can edit machine templates")

    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine_id,
        models.MachineTemplate.hospital_id == creator.hospital_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    machine_type = db.query(models.MachineType).filter(
        models.MachineType.id == request.machine_type_id
    ).first()

    if not machine_type:
        raise HTTPException(status_code=400, detail="Invalid machine type")

    template.machine_name = request.machine_name.strip()
    template.machine_type_id = request.machine_type_id

    db.commit()

    return {
        "status": True,
        "message": "Machine template updated successfully"
    }



@app.get("/api/machine/{machine_id}")
def get_machine_details(
    machine_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine.template_id
        ).first()
    machine_name = template.machine_name if template else "Unknown"
    return {
        "status": True,
        "data": {
            "id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "last_checked": machine.last_checked
            }
            }


@app.delete("/api/machine/delete/{machine_id}")
def delete_machine(
    machine_id: int,
    db: Session = Depends(get_db)
):
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # 🔥 Optional: delete related inspections first (avoid FK error)
    db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id
    ).delete()

    # 🔥 Optional: delete OT assignment
    db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.machine_id == machine_id
    ).delete()

    db.delete(machine)
    db.commit()

    return {
        "status": True,
        "message": "Machine deleted successfully"
    }


# ================= ISSUE PAGE APIs =================

@app.get("/api/issues/ots")
def get_issue_ots(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "BMET",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid BMET user")

    # ✅ ONLY ACTIVE OTs
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == creator_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {"status": True, "data": []}

    machines = db.query(models.Machine).join(
        models.OTMachineAssignment,
        models.Machine.id == models.OTMachineAssignment.machine_id
    ).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids),
        models.Machine.status == "Not Working"
    ).all()

    ot_issue_map = {}

    for machine in machines:

        assignment = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        if not assignment:
            continue

        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == assignment.ot_id
        ).first()

        if not ot:
            continue

        if ot.id not in ot_issue_map:
            ot_issue_map[ot.id] = {
                "id": ot.id,
                "ot_name": ot.ot_name,
                "machine_count": 0
            }

        ot_issue_map[ot.id]["machine_count"] += 1

    return {
        "status": True,
        "data": list(ot_issue_map.values())
    }


@app.get("/api/issues/machines")
def get_issue_machines(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "BMET",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid BMET user")

    # ✅ ONLY ACTIVE OTs
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == user.id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {"status": True, "total": 0, "data": []}

    # ✅ Machines only inside BMET OTs
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {"status": True, "total": 0, "data": []}

    data = []

    for machine_id in machine_ids:

        machine = db.query(models.Machine).filter(
            models.Machine.id == machine_id
        ).first()

        if not machine:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        latest = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id
        ).order_by(models.MachineInspection.created_at.desc()).first()

        if not latest or latest.status != "Not Working":
            continue

        # OT Name
        ot_assign = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        ot_name = "Unknown"
        if ot_assign:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == ot_assign.ot_id
            ).first()
            if ot:
                ot_name = ot.ot_name

        # Technician
        checked_by = "System"
        if latest.user_id:
            tech = db.query(models.User).filter(
                models.User.id == latest.user_id
            ).first()
            if tech:
                checked_by = tech.name

        data.append({
            "machine_id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "location": ot_name,
            "priority": latest.priority if latest.priority else "Low",
            "remarks": latest.remarks,
            "reported_at": latest.created_at.strftime("%b %d, %Y • %I:%M %p"),
            "checked_by": checked_by
        })

    return {
        "status": True,
        "total": len(data),
        "data": data
    }


# ================= ISSUE DETAILS API =================

@app.get("/api/issues/{machine_id}")
def get_issue_details(
    machine_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate user
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Get machine template
    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine.template_id
    ).first()

    machine_name = template.machine_name if template else "Unknown"

    # Get latest inspection
    latest = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine.id
    ).order_by(models.MachineInspection.created_at.desc()).first()

    # Technician name
    checked_by = "Unknown"

    if latest and latest.user_id:
        tech = db.query(models.User).filter(
            models.User.id == latest.user_id
        ).first()

        if tech and tech.name:
            checked_by = tech.name

    # OT Location
    ot_name = ""

    assignment = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.machine_id == machine.id
    ).first()

    if assignment:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == assignment.ot_id
        ).first()

        if ot:
            ot_name = ot.ot_name

    # Format inspection time
    reported_time = None

    if latest and latest.created_at:
        reported_time = latest.created_at.strftime("%b %d, %Y • %I:%M %p")

    # Priority
    priority = "Low"
    if latest and latest.priority:
        priority = latest.priority

    # Remarks
    remarks = ""
    if latest and latest.remarks:
        remarks = latest.remarks

    return {
        "status": True,
        "data": {
            "machine_id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "priority": priority,
            "remarks": remarks,
            "reported_at": reported_time,
            "ot_name": ot_name,
            "checked_by": checked_by
        }
    }


from datetime import datetime, date

from fastapi import Query

@app.post("/api/issues/resolve/{machine_id}")
def resolve_issue(
    machine_id: int,
    creator_id: int = Query(...),
    maintenance_notes: str = Query(...),
    db: Session = Depends(get_db)
):

    # Require maintenance notes
    if not maintenance_notes or maintenance_notes.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="Maintenance notes are required to resolve the issue"
        )

    # Validate user
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == user.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Verify there is an active issue inspection
    latest = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id
    ).order_by(models.MachineInspection.created_at.desc()).first()

    if not latest or latest.status != "Not Working":
        raise HTTPException(
            status_code=400,
            detail="No active issue to resolve"
        )

    # Create RESOLVED inspection record
    resolved_record = models.MachineInspection(
        machine_id=machine_id,
        user_id=creator_id,
        status="Resolved",
        remarks=maintenance_notes.strip(),
        priority=None,
        check_date=date.today(),
        created_at=datetime.now(IST)
    )

    db.add(resolved_record)

    # Update machine status
    machine.status = "Working"
    machine.last_checked = datetime.now(IST)

    db.commit()

    return {
        "status": True,
        "message": "Issue resolved successfully",
        "data": {
            "machine_id": machine_id,
            "resolved_by": user.name if hasattr(user, "name") else user.email,
            "resolved_at": datetime.now(IST).strftime("%b %d, %Y • %I:%M %p")
        }
    }


@app.get("/api/history/machines")
def get_at_history_machines(
    creator_id: int,
    status: str | None = None,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid user")

    # 🔥 STEP 1: Machines touched by AT
    at_machine_ids = db.query(models.MachineInspection.machine_id).filter(
        models.MachineInspection.user_id == creator_id
    ).distinct().all()

    at_machine_ids = [m[0] for m in at_machine_ids]

    if not at_machine_ids:
        return {"status": True, "total": 0, "data": []}

    # 🔥 STEP 2: Get latest inspections (ANY USER)
    inspections = db.query(models.MachineInspection).join(
        models.Machine,
        models.Machine.id == models.MachineInspection.machine_id
    ).filter(
        models.Machine.hospital_id == user.hospital_id,
        models.MachineInspection.machine_id.in_(at_machine_ids)
    ).order_by(
        models.MachineInspection.created_at.desc()
    ).all()

    result = []
    seen_machine_ids = set()

    for insp in inspections:

        if insp.machine_id in seen_machine_ids:
            continue

        seen_machine_ids.add(insp.machine_id)

        if status and insp.status.lower() != status.lower():
            continue

        machine = db.query(models.Machine).filter(
            models.Machine.id == insp.machine_id
        ).first()

        if not machine:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        # Machine Type
        machine_type = "Unknown"
        if template:
            type_obj = db.query(models.MachineType).filter(
                models.MachineType.id == template.machine_type_id
            ).first()
            if type_obj:
                machine_type = type_obj.type_name

        # OT Name
        ot_name = "Assign"
        ot_assign = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        if ot_assign:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == ot_assign.ot_id
            ).first()
            if ot:
                ot_name = ot.ot_name

        # Checked By
        inspector = db.query(models.User).filter(
            models.User.id == insp.user_id
        ).first()

        checked_by = inspector.name if inspector else "Technician"

        result.append({
            "id": insp.id,
            "machine_id": machine.id,
            "machine_name": template.machine_name if template else "Unknown",
            "machine_type": machine_type,
            "serial_number": machine.serial_number,
            "ot_name": ot_name,
            "status": insp.status,   # 🔥 NOW CORRECT
            "priority": insp.priority,
            "remarks": insp.remarks,
            "checked_at": insp.created_at,
            "checked_by": checked_by
        })

    return {
        "status": True,
        "total": len(result),
        "data": result
    }


from datetime import datetime, date

from sqlalchemy import func

@app.get("/api/dashboard/at/{user_id}")
def get_at_dashboard(user_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "AT",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid AT user")

    today = date.today()

    # ===== GET OTs ASSIGNED TO THIS AT =====
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {"status": True, "checked": 0, "issues": 0, "pending": 0}

    # ===== GET MACHINES INSIDE THOSE OTs =====
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {"status": True, "checked": 0, "issues": 0, "pending": 0}

    total_machines = len(machine_ids)

    # ===== GET TODAY'S INSPECTIONS =====
    inspections = db.query(
        models.MachineInspection.machine_id,
        models.MachineInspection.status
    ).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.user_id == user_id,
        models.MachineInspection.check_date == today
    ).all()

    checked = 0
    issues = 0
    inspected_machine_ids = set()

    for machine_id, status in inspections:

        # count each machine only once
        if machine_id not in inspected_machine_ids:
            inspected_machine_ids.add(machine_id)
            checked += 1

        # count issues
        if status == "Not Working":
            issues += 1

    pending = total_machines - checked

    if pending < 0:
        pending = 0

    return {
        "status": True,
        "checked": checked,
        "issues": issues,
        "pending": pending
    }



@app.get("/api/checklist/machines/{user_id}")
def get_checklist_machines(user_id: int, ot_id: int = None, db: Session = Depends(get_db)):

    # ---------------- USER VALIDATION ----------------
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "AT",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid AT user")

    # ---------------- GET ASSIGNED OTs ----------------
    if ot_id:
        ot_ids = [ot_id]
    else:
        ot_ids = [
    o[0] for o in db.query(models.OTAssignment.ot_id)
    .filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.is_active == True   # 🔥 THIS LINE
    )
    .all()
]

    if not ot_ids:
        return {"status": True, "pending": [], "completed": []}

    # ---------------- GET MACHINES ----------------
    machines = db.query(
        models.Machine.id,
        models.Machine.serial_number,
        models.MachineTemplate.machine_name,
        models.OTRoom.ot_name
    ).join(
        models.MachineTemplate,
        models.Machine.template_id == models.MachineTemplate.id
    ).join(
        models.OTMachineAssignment,
        models.Machine.id == models.OTMachineAssignment.machine_id
    ).outerjoin(
        models.OTRoom,
        models.OTRoom.id == models.OTMachineAssignment.ot_id
    ).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    if not machines:
        return {"status": True, "pending": [], "completed": []}

    today = date.today()
    machine_ids = [m.id for m in machines]

    # ---------------- GET TODAY'S AT INSPECTIONS ----------------
    inspections_today = db.query(
        models.MachineInspection.machine_id
    ).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.user_id == user_id,
        models.MachineInspection.check_date == today
    ).all()

    inspected_ids = set(i.machine_id for i in inspections_today)

    # ---------------- GET LATEST INSPECTIONS (ANY USER) ----------------
    latest_inspections = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id.in_(machine_ids)
    ).order_by(
        models.MachineInspection.machine_id,
        models.MachineInspection.created_at.desc()
    ).all()

    latest_map = {}
    for insp in latest_inspections:
        if insp.machine_id not in latest_map:
            latest_map[insp.machine_id] = insp

    # ---------------- BUILD RESPONSE ----------------
    pending = []
    completed = []

    for machine in machines:

        latest = latest_map.get(machine.id)

        machine_status = latest.status if latest else "Unknown"
        last_checked = latest.created_at if latest else None

        machine_data = {
            "id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "status": machine_status,   # ✅ ALWAYS CORRECT NOW
            "last_checked": last_checked,
            "ot_name": machine.ot_name
        }

        if machine.id in inspected_ids:
            completed.append(machine_data)
        else:
            pending.append(machine_data)

    return {
        "status": True,
        "pending": pending,
        "completed": completed
    }

@app.post("/api/checklist/reset-time")
def set_reset_time(
    request: schemas.ResetTimeRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Only HM can set reset time")

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == user.hospital_id
    ).first()

    if settings:
        settings.reset_time = request.reset_time
    else:
        settings = models.ChecklistSettings(
            hospital_id=user.hospital_id,
            reset_time=request.reset_time
        )
        db.add(settings)

    db.commit()

    return {
        "status": True,
        "message": "Reset time updated successfully"
    }



from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

@app.get("/api/dashboard/hm/{user_id}")
def get_hm_dashboard(user_id: int, db: Session = Depends(get_db)):

    # -------- VALIDATE HM USER --------
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    hospital_id = user.hospital_id

    # -------- TOTAL OTs --------
    total_ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == hospital_id
    ).count()

    # -------- TOTAL MACHINES --------
    total_machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == hospital_id
    ).count()

    # -------- TECHNICIANS (AT + BMET) --------
    technicians = db.query(models.User).filter(
        models.User.hospital_id == hospital_id,
        models.User.role.in_(["AT", "BMET"]),
        models.User.status == 1
    ).count()

    # -------- MACHINES WITH ISSUES --------
    machines_with_issues = db.query(models.Machine).filter(
        models.Machine.hospital_id == hospital_id,
        models.Machine.status == "Not Working"
    ).count()

    # -------- OPTIONAL: TOTAL REPORTS (for clarity) --------
    total_reports = db.query(models.MachineInspection).join(
        models.Machine,
        models.MachineInspection.machine_id == models.Machine.id
    ).filter(
        models.Machine.hospital_id == hospital_id
    ).count()

    return {
        "status": True,
        "data": {
            "total_ots": total_ots,
            "total_machines": total_machines,  # 🔥 THIS IS CORRECT MACHINE COUNT
            "technicians": technicians,
            "machines_with_issues": machines_with_issues,
            "total_reports": total_reports  # 👈 Added to avoid confusion
        }
    }
# ================= HM REGISTRATION =================
@app.post("/api/register")
def register_hospital_and_hm(
    request: schemas.HMRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        # -------- VALIDATION --------
        if not request.hospital_name or not request.hm_name or not request.hm_email or not request.password:
            raise HTTPException(status_code=400, detail="All fields are required")

        # -------- CHECK EMAIL EXISTS --------
        existing_user = db.query(models.User).filter(
            models.User.email == request.hm_email.strip()
        ).first()

        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")

        # -------- CREATE HOSPITAL --------
        hospital = models.Hospital(
            hospital_name=request.hospital_name.strip()
        )

        db.add(hospital)
        db.commit()
        db.refresh(hospital)

        if not hospital.id:
            raise HTTPException(status_code=500, detail="Hospital creation failed")

        # -------- CREATE HM USER --------
        hm_user = models.User(
            name=request.hm_name.strip(),
            email=request.hm_email.strip(),
            password = request.password,  # 🔥 MUST hash
            role="HM",
            employee_id=f"HM{hospital.id}",
            hospital_id=hospital.id,   # 🔥 LINK HERE
            status=1
        )

        db.add(hm_user)
        db.commit()
        db.refresh(hm_user)

        return {
            "status": True,
            "message": "Registration successful",
            "hospital_id": hospital.id,
            "user_id": hm_user.id
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Database error")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ================= LOGIN =================
@app.post("/login")
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):

    user = crud.authenticate_user(db, request.email, request.password)

    if not user:
        return {
            "status": False,
            "message": "Invalid email or password"
        }

    # UPDATE LAST LOGIN
    user.last_login = datetime.now(IST)
    db.commit()

    return {
        "status": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "hospital_id": user.hospital_id,
            "profile_pic": user.profile_picture,
            "force_password_change": user.force_password_change 
        }
    }


# ================= CREATE USER (HM ONLY) =================
@app.post("/create_user")
def create_user(
    request: schemas.CreateUserRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM can create users")

    # 🔥 NAME VALIDATION (ADD THIS)
    if not re.match(r"^[A-Za-z][A-Za-z .'-]*$", request.name.strip()):
        raise HTTPException(
            status_code=400,
            detail="Name must contain only alphabets"
        )

    existing_email = db.query(models.User).filter(
        models.User.email == request.email
    ).first()

    if existing_email:
        return {
            "status": False,
            "message": "Email already exists"
        }

    user = models.User(
        name=request.name.strip(),  # 🔥 trim spaces
        email=request.email,
        password=request.password,
        role=request.role,
        employee_id=request.employee_id,
        dob=request.dob,
        hospital_id=creator.hospital_id,
        created_by=creator.id,
        status=1,
        force_password_change=True
    )

    db.add(user)
    db.commit()

    return {
        "status": True,
        "message": "User created successfully"
    }




@app.put("/hospital/settings")
def update_hospital_settings(
    data: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    print("User hospital_id:", current_user.hospital_id)
    print("Incoming data:", data)

    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="Invalid hospital")

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == current_user.hospital_id
    ).first()

    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    # update safely
    settings.reset_time = datetime.strptime(
        data["reset_time"], "%H:%M:%S"
    ).time()

    settings.default_at_password = data["default_at_password"]
    settings.default_bmet_password = data["default_bmet_password"]

    db.commit()
    db.refresh(settings)

    print("Updated AT password:", settings.default_at_password)

    return {
        "status": True,
        "message": "Settings updated successfully"
    }

# ================= UPDATE USER STATUS (HM ONLY - SAME HOSPITAL) =================
@app.put("/update_user_status")
def update_user_status(
    request: schemas.UpdateUserStatusRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Access denied")

    user = db.query(models.User).filter(
        models.User.id == request.user_id,
        models.User.hospital_id == creator.hospital_id,
        models.User.role != "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.status = request.status
    db.commit()

    return {
        "status": True,
        "message": "User status updated successfully"
    }


# ================= UPDATE USER DETAILS =================
@app.put("/api/user/update")
def update_user_details(
    request: schemas.UpdateUserRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM can update users")

    user = db.query(models.User).filter(
        models.User.id == request.user_id,
        models.User.hospital_id == creator.hospital_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check duplicate email
    existing = db.query(models.User).filter(
        models.User.email == request.email,
        models.User.id != request.user_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user.name = request.name
    user.email = request.email
    user.employee_id = request.employee_id
    user.dob = request.dob   # 🔥 THIS LINE IS MANDATORY

    db.commit()

    return {
        "status": True,
        "message": "User updated successfully"
    }


# ================= GET PROFILE =================
@app.get("/profile/{user_id}")
def get_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    BASE_URL = "http://localhost:8000/"

    return {
    "status": True,
    "data": {
        "id": user.id,
        "name": user.name or "",
        "email": user.email or "",
        "mobile": user.mobile or "",
        "role": user.role or "",
        "employee_id": user.employee_id or "",
        "dob": str(user.dob) if user.dob else None,  # ✅ ADD
        "last_login": str(user.last_login) if user.last_login else None,  # ✅ ADD
        "hospital_name": hospital.hospital_name if hospital else "",
        "profile_pic": BASE_URL + user.profile_picture if user.profile_picture else None,
        "created_at": user.created_at
    }
}


@app.put("/api/user/update-profile/{user_id}")
async def update_profile(
    user_id: int,
    mobile: str = Form(...),
    profile_pic: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update mobile
    user.mobile = mobile

    # Handle profile picture
    if profile_pic:
        file_extension = profile_pic.filename.split(".")[-1]
        filename = f"user_{user_id}_{int(time.time())}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_pic.file, buffer)

        user.profile_picture = f"uploads/profile_pics/{filename}"

    db.commit()

    return {
        "status": True,
        "message": "Profile updated successfully",
        "profile_picture": user.profile_picture
    }

@app.get("/api/profile")
def get_profile(user_id: int, db: Session = Depends(get_db)):

    print("Fetching user ID:", user_id)  # 🔥 DEBUG

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    BASE_URL = "http://127.0.0.1:8000/"

    return {
        "status": True,
        "data": {
            "id": user.id,
            "name": user.name or "",
            "email": user.email or "",
            "mobile": user.mobile or "",
            "role": user.role or "",
            "employee_id": user.employee_id or "",
            "dob": str(user.dob) if user.dob else None,
            "last_login": str(user.last_login) if user.last_login else None,
            "hospital_name": hospital.hospital_name if hospital else "",
            "profile_pic": BASE_URL + user.profile_picture if user.profile_picture else None,
            "created_at": str(user.created_at)
        }
    }

def get_current_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

def get_current_hm(
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "HM":
        raise HTTPException(
            status_code=403,
            detail="Only Hospital Manager (HM) allowed"
        )

    return current_user


@app.put("/api/profile")
def update_profile(
    user_id: int,   # 🔥 TAKE DIRECTLY
    request: schemas.UpdateHMProfileRequest,
    db: Session = Depends(get_db)
):

    print("Updating user ID:", user_id)  # DEBUG

    # -------- GET USER --------
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔥 ENSURE ONLY HM
    if user.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM allowed")

    # -------- UPDATE ONLY NON-EMPTY FIELDS --------

    if request.name is not None and request.name.strip():
        user.name = request.name.strip()

    if request.email is not None and request.email.strip():

        existing = db.query(models.User).filter(
            models.User.email == request.email,
            models.User.id != user.id
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        user.email = request.email.strip()

    if request.mobile is not None and request.mobile.strip():
        user.mobile = request.mobile.strip()

    if request.employee_id is not None and request.employee_id.strip():
        user.employee_id = request.employee_id.strip()

    if request.dob is not None:
        user.dob = request.dob

    db.commit()
    db.refresh(user)

    return {
        "status": True,
        "message": "HM profile updated successfully",
        "data": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "mobile": user.mobile,
            "employee_id": user.employee_id,
            "dob": str(user.dob) if user.dob else None
        }
    }

# ================= OT MANAGEMENT =================


@app.post("/api/ot/add")
def add_ot(
    request: schemas.OTCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):
    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check duplicate OT Code
    existing = db.query(models.OTRoom).filter(
        models.OTRoom.ot_code == request.ot_code
    ).first()

    if existing:
        return {
            "status": False,
            "message": "OT Code already exists"
        }

    # Create OT linked to hospital
    new_ot = models.OTRoom(
        ot_name=request.ot_name,
        ot_code=request.ot_code,
        location=request.location,
        ot_type=request.ot_type,
        description=request.description,
        hospital_id=creator.hospital_id,
        creator_id=creator_id,
        machines_assigned=0,
        issues_count=0,
        status="Operational"
    )

    db.add(new_ot)
    db.commit()

    return {
        "status": True,
        "message": "OT Room created successfully"
    }


@app.get("/api/ot/list")
def get_ot_list(
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get OTs for creator's hospital
    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    data = []

    for ot in ots:

        machine_count = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.ot_id == ot.id
        ).count()

        issue_count = db.query(models.Machine).join(
            models.OTMachineAssignment,
            models.Machine.id == models.OTMachineAssignment.machine_id
        ).filter(
            models.OTMachineAssignment.ot_id == ot.id,
            models.Machine.status == "Not Working"
        ).count()

        data.append({
            "id": ot.id,
            "ot_name": ot.ot_name,
            "ot_code": ot.ot_code,
            "location": ot.location,
            "ot_type": ot.ot_type,
            "machines_assigned": machine_count,
            "issues_count": issue_count,
            "status": ot.status,
            "description": ot.description
        })

    return {
        "status": True,
        "data": data
    }


@app.put("/api/ot/update/{id}")
def update_ot(
    id: int,
    request: schemas.OTCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == id,
        models.OTRoom.hospital_id == creator.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")

    # Check duplicate OT code
    existing = db.query(models.OTRoom).filter(
        models.OTRoom.ot_code == request.ot_code,
        models.OTRoom.id != id
    ).first()

    if existing:
        return {
            "status": False,
            "message": "OT Code already exists"
        }

    ot.ot_name = request.ot_name
    ot.ot_code = request.ot_code
    ot.location = request.location
    ot.ot_type = request.ot_type
    ot.description = request.description

    db.commit()

    return {
        "status": True,
        "message": "OT Room updated successfully"
    }



@app.get("/api/ots")
def get_ots(
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get OTs for the creator's hospital
    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    result = []

    for ot in ots:

        machine_count = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.ot_id == ot.id
        ).count()

        result.append({
            "id": ot.id,
            "name": ot.ot_name,
            "type": ot.ot_type,
            "machine_count": machine_count
        })

    return {
        "status": True,
        "data": result
    }

@app.delete("/api/ot/delete/{id}")
def delete_ot(
    id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == id,
        models.OTRoom.hospital_id == creator.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")

    db.delete(ot)
    db.commit()

    return {
        "status": True,
        "message": "OT Room deleted successfully"
    }


@app.get("/api/ot/user_assignments")
def get_user_assignments(
    creator_id: int,
    user_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get assignments only from same hospital
    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.hospital_id == creator.hospital_id
    ).all()

    data = []

    for a in assignments:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == a.ot_id,
            models.OTRoom.hospital_id == creator.hospital_id
        ).first()

        if ot:
            data.append({
                "id": ot.id,
                "ot_name": ot.ot_name,
                "ot_code": ot.ot_code,
                "location": ot.location
            })

    return {
        "status": True,
        "data": data
    }


@app.get("/api/ot/assignment_counts")
def get_ot_assignment_counts(
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    data = []

    for ot in ots:

        assignment_count = db.query(models.OTAssignment).filter(
            models.OTAssignment.ot_id == ot.id
        ).count()

        data.append({
            "ot_id": ot.id,
            "assignment_count": assignment_count
        })

    return {
        "status": True,
        "data": data
    }


@app.get("/api/ot/available")
def get_available_ots(
    creator_id: int,
    user_role: str,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get all users of SAME ROLE in this hospital
    same_role_users = db.query(models.User).filter(
        models.User.hospital_id == creator.hospital_id,
        models.User.role == user_role
    ).all()

    same_role_ids = [u.id for u in same_role_users]

    # Get OTs assigned to users of SAME ROLE only
    assigned_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id.in_(same_role_ids)
    ).all()

    assigned_ids = [a[0] for a in assigned_ids]

    ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id,
        ~models.OTRoom.id.in_(assigned_ids)
    ).all()

    data = []

    for ot in ots:
        data.append({
            "id": ot.id,
            "ot_name": ot.ot_name,
            "ot_code": ot.ot_code,
            "location": ot.location
        })

    return {
        "status": True,
        "data": data
    }

@app.get("/api/ot/{ot_id}")
def get_ot_details(
    ot_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == ot_id,
        models.OTRoom.hospital_id == user.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")

    return {
        "status": True,
        "data": {
            "id": ot.id,
            "ot_name": ot.ot_name,
            "ot_code": ot.ot_code,
            "location": ot.location,
            "ot_type": ot.ot_type,
            "description": ot.description,
            "status": ot.status
        }
    }


@app.get("/api/ot/{ot_id}/machines")
def get_ot_machines(
    ot_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # ---------------- VALIDATE USER ----------------
    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    # ---------------- VALIDATE OT ----------------
    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == ot_id,
        models.OTRoom.hospital_id == user.hospital_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT not found")

    # ---------------- JOIN QUERY (FAST + CORRECT) ----------------
    machines = db.query(
        models.Machine.id,
        models.Machine.serial_number,
        models.Machine.status,
        models.Machine.last_checked,
        models.MachineTemplate.machine_name,
        models.MachineType.type_name
    ).join(
        models.OTMachineAssignment,
        models.OTMachineAssignment.machine_id == models.Machine.id
    ).join(
        models.MachineTemplate,
        models.Machine.template_id == models.MachineTemplate.id
    ).join(
        models.MachineType,
        models.MachineTemplate.machine_type_id == models.MachineType.id
    ).filter(
        models.OTMachineAssignment.ot_id == ot_id
    ).all()

    # ---------------- FORMAT RESPONSE ----------------
    result = []

    for m in machines:
        result.append({
            "id": m.id,
            "machine_name": m.machine_name,
            "machine_type": m.type_name,
            "serial_number": m.serial_number,
            "status": m.status,
            "last_checked": str(m.last_checked) if m.last_checked else None
        })

    return {
        "status": True,
        "data": result
    }


@app.get("/api/machine/types")
def get_machine_types(db: Session = Depends(get_db)):

    types = db.query(models.MachineType).all()

    data = []
    for t in types:
        data.append({
            "id": t.id,
            "type_name": t.type_name
        })

    return {
        "status": True,
        "data": data
    }


@app.post("/api/machine/add")
def add_machine(
    request: schemas.MachineCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    template = models.MachineTemplate(
        machine_name=request.machine_name,
        machine_type_id=request.machine_type_id,
        hospital_id=creator.hospital_id
    )

    db.add(template)
    db.commit()

    return {
        "status": True,
        "message": "Machine template added successfully"
    }


@app.get("/api/machine/list")
def get_machine_list(
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == creator.hospital_id
    ).all()

    data = []

    for m in machines:

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == m.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        assignments = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == m.id
        ).all()

        ot_names = []

        for a in assignments:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == a.ot_id
            ).first()

            if ot:
                ot_names.append(ot.ot_name)

        data.append({
            "id": m.id,
            "machine_name": machine_name,
            "serial_number": m.serial_number,
            "status": m.status,
            "assigned_ots": ot_names
        })

    return {
        "status": True,
        "data": data
    }



@app.post("/api/ot/assign")
def assign_ot(
    request: schemas.AssignOTRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):

    assigned_user = db.query(models.User).filter(
        models.User.id == request.user_id
    ).first()

    if not assigned_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔴 Prevent duplicate active assignment
    existing_same = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == request.user_id,
        models.OTAssignment.ot_id == request.ot_id,
        models.OTAssignment.is_active == True
    ).first()

    if existing_same:
        return {
            "status": False,
            "message": "User already assigned to this OT"
        }

    # 🔥 BMET RULE → deactivate old, don’t delete
    if assigned_user.role == "BMET":

        existing_bmet = db.query(models.OTAssignment).join(models.User).filter(
            models.OTAssignment.ot_id == request.ot_id,
            models.OTAssignment.is_active == True,
            models.User.role == "BMET"
        ).first()

        if existing_bmet:
            existing_bmet.is_active = False   # 🔥 IMPORTANT
            db.commit()

    # ✅ create new active assignment
    new_assignment = models.OTAssignment(
        user_id=request.user_id,
        ot_id=request.ot_id,
        hospital_id=assigned_user.hospital_id,
        is_active=True
    )

    db.add(new_assignment)
    db.commit()

    return {
        "status": True,
        "message": "OT reassigned successfully"
    }




@app.get("/users/technicians")
def get_technicians(hospital_id: int, db: Session = Depends(get_db)):

    users = db.query(models.User).filter(
        models.User.hospital_id == hospital_id,
        models.User.role == "AT"
    ).all()

    data = []

    for user in users:
        data.append({
            "id": user.id,
            "name": user.name,
            "employee_id": user.employee_id
        })

    return {"status": True, "data": data}






@app.delete("/api/ot/unassign")
def unassign_ot(
    user_id: int,
    ot_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    assignment = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.ot_id == ot_id
    ).first()

    if not assignment:
        return {
            "status": False,
            "message": "Assignment not found"
        }

    db.delete(assignment)
    db.commit()

    return {
        "status": True,
        "message": "OT unassigned successfully"
    }


@app.post("/api/machine/assign")
def assign_machine(
    creator_id: int,
    ot_id: int,
    template_id: int,
    serial_number: str,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # check serial duplicate
    existing = db.query(models.Machine).filter(
        models.Machine.serial_number == serial_number
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Serial already exists")

    # create machine
    machine = models.Machine(
        template_id=template_id,
        serial_number=serial_number,
        hospital_id=user.hospital_id,
        status="Working"
    )

    db.add(machine)
    db.commit()
    db.refresh(machine)

    # assign machine to OT
    assignment = models.OTMachineAssignment(
        ot_id=ot_id,
        machine_id=machine.id,
        hospital_id=user.hospital_id
    )

    db.add(assignment)
    db.commit()

    return {
        "status": True,
        "machine_id": machine.id,
        "message": "Machine assigned successfully"
    }




@app.get("/api/machines/list")
def get_machines_list_simple(db: Session = Depends(get_db)):
    machines = db.query(models.Machine).all()
    data = []
    for m in machines:
        template = db.query(models.MachineTemplate).filter(models.MachineTemplate.id == m.template_id).first()
        data.append({
            "id": m.id,
            "machine_name": template.machine_name if template else f"Machine {m.id}",
            "serial_number": m.serial_number
        })
    return {"status": True, "data": data}

@app.post("/api/ot/assign-machine")
def assign_machine_to_ot(request: schemas.AssignMachineToOTRequest, db: Session = Depends(get_db)):
    # Check if assignment already exists
    existing = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.ot_id == request.ot_id,
        models.OTMachineAssignment.machine_id == request.machine_id
    ).first()
    
    if existing:
        return {"status": False, "message": "Machine already assigned to this OT"}
    
    # Get hospital_id from OT
    ot = db.query(models.OTRoom).filter(models.OTRoom.id == request.ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT Room not found")
        
    new_assignment = models.OTMachineAssignment(
        ot_id=request.ot_id,
        machine_id=request.machine_id,
        hospital_id=ot.hospital_id
    )
    db.add(new_assignment)
    db.commit()
    
    return {"status": True, "message": "Machine assigned successfully"}




@app.get("/api/machine/available")
def get_available_machines(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    templates = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.hospital_id == user.hospital_id
    ).all()

    data = []

    for t in templates:
        data.append({
            "id": t.id,
            "machine_name": t.machine_name
        })

    return {
        "status": True,
        "data": data
    }

@app.get("/api/user/{user_id}/assigned-ots")
def get_user_assigned_ots(
    user_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.hospital_id == creator.hospital_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [a.ot_id for a in assignments]

    if not ot_ids:
        return {"status": True, "data": []}

    ots = db.query(models.OTRoom).filter(
        models.OTRoom.id.in_(ot_ids)
    ).all()

    today_start = datetime.combine(date.today(), datetime.min.time())

    data = []

    for ot in ots:

        # Total machines in OT
        machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
            models.OTMachineAssignment.ot_id == ot.id
        ).all()

        machine_ids = [m[0] for m in machine_ids]

        total_machines = len(machine_ids)

        # Machines inspected today
        completed_ids = db.query(
            models.MachineInspection.machine_id
        ).filter(
            models.MachineInspection.machine_id.in_(machine_ids),
            models.MachineInspection.created_at >= today_start
        ).distinct().all()

        completed_count = len(completed_ids)

        data.append({
            "id": ot.id,
            "ot_name": ot.ot_name,
            "location": ot.location,
            "ot_type": ot.ot_type,
            "machine_count": total_machines,
            "completed_count": completed_count
        })

    return {
        "status": True,
        "data": data
    }

from datetime import datetime

from pydantic import BaseModel

class InspectMachineRequest(BaseModel):
    machine_id: int
    user_id: int
    status: str
    remarks: str = None
    priority: str = None

from datetime import datetime, date, timedelta
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

@app.post("/api/machine/inspect")
def inspect_machine(
    machine_id: int,
    creator_id: int,
    status: str,
    remarks: str = "",
    priority: str = None,
    db: Session = Depends(get_db)
):

    from datetime import datetime, date
    import pytz

    IST = pytz.timezone("Asia/Kolkata")

    def get_ist_time():
        return datetime.now(IST)

    # Validate user
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid user")

    # Validate machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == user.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # PRIORITY VALIDATION
    allowed_priorities = ["Critical", "Medium", "Low"]

    if priority:
        priority = priority.capitalize()
        if priority not in allowed_priorities:
            raise HTTPException(
                status_code=400,
                detail="Invalid priority. Allowed values: Critical, Medium, Low"
            )
    else:
        priority = "Low"

    today = date.today()

    existing = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id,
        models.MachineInspection.check_date == today
    ).first()

    if existing:
        existing.status = status
        existing.remarks = remarks
        existing.priority = priority
        existing.created_at = datetime.now(IST)   # 🔥 FIXED

    else:
        inspection = models.MachineInspection(
            machine_id=machine_id,
            user_id=creator_id,
            status=status,
            remarks=remarks,
            priority=priority,
            check_date=today,
            created_at=datetime.now(IST)   # 🔥 FIXED
        )
        db.add(inspection)

    machine.status = status
    machine.last_checked = datetime.now(IST)   # 🔥 FIXED

    db.commit()

    return {
        "status": True,
        "message": "Inspection submitted successfully"
    }

@app.get("/api/machine/history")
def get_resolved_machine_history(
    creator_id: int,
    status: str = None,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    data = []

    # ================= GET MACHINE IDS =================

    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user.id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [a.ot_id for a in assignments]

    if not ot_ids:
        return {"status": True, "total": 0, "data": []}

    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {"status": True, "total": 0, "data": []}

    # ================= GET RESOLVED RECORDS =================

    resolved_records = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.status == "Resolved"
    ).order_by(models.MachineInspection.created_at.desc()).all()

    for resolved in resolved_records:

        machine = db.query(models.Machine).filter(
            models.Machine.id == resolved.machine_id
        ).first()

        if not machine:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        # ================= GET AT ISSUE =================

        issue = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id,
            models.MachineInspection.status == "Not Working"
        ).order_by(models.MachineInspection.created_at.desc()).first()

        at_issue = issue.remarks if issue else "No issue details provided"

        # ================= OT NAME =================

        assignment = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).order_by(models.OTMachineAssignment.id.desc()).first()

        ot_name = "Unknown OT"

        if assignment:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == assignment.ot_id
            ).first()

            if ot and ot.ot_name:
                ot_name = ot.ot_name

        # ================= MAINTENANCE NOTES =================

        maintenance_notes = resolved.remarks if resolved.remarks else "No maintenance notes"

        data.append({
    "id": resolved.id,   # 🔥 THIS LINE FIXES EVERYTHING

    "machine_id": machine.id,
    "machine_name": machine_name,
    "serial_number": machine.serial_number,
    "ot_name": ot_name,
    "at_issue": at_issue,
    "maintenance_notes": maintenance_notes,
    "resolved_time": resolved.created_at.strftime("%b %d, %Y • %I:%M %p")
})

    return {
        "status": True,
        "total": len(data),
        "data": data
    }








@app.get("/api/machine/{machine_id}")
def get_machine_details(
    machine_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine.template_id
        ).first()
    machine_name = template.machine_name if template else "Unknown"
    return {
        "status": True,
        "data": {
            "id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "last_checked": machine.last_checked
            }
            }


@app.delete("/api/machine/delete/{machine_id}")
def delete_machine(
    machine_id: int,
    db: Session = Depends(get_db)
):
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # 🔥 Optional: delete related inspections first (avoid FK error)
    db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id
    ).delete()

    # 🔥 Optional: delete OT assignment
    db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.machine_id == machine_id
    ).delete()

    db.delete(machine)
    db.commit()

    return {
        "status": True,
        "message": "Machine deleted successfully"
    }


# ================= ISSUE PAGE APIs =================

@app.get("/api/issues/ots")
def get_issue_ots(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "BMET",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid BMET user")

    # ✅ ONLY ACTIVE OTs
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == creator_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {"status": True, "data": []}

    machines = db.query(models.Machine).join(
        models.OTMachineAssignment,
        models.Machine.id == models.OTMachineAssignment.machine_id
    ).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids),
        models.Machine.status == "Not Working"
    ).all()

    ot_issue_map = {}

    for machine in machines:

        assignment = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        if not assignment:
            continue

        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == assignment.ot_id
        ).first()

        if not ot:
            continue

        if ot.id not in ot_issue_map:
            ot_issue_map[ot.id] = {
                "id": ot.id,
                "ot_name": ot.ot_name,
                "machine_count": 0
            }

        ot_issue_map[ot.id]["machine_count"] += 1

    return {
        "status": True,
        "data": list(ot_issue_map.values())
    }


@app.get("/api/issues/machines")
def get_issue_machines(
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "BMET",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid BMET user")

    # ✅ ONLY ACTIVE OTs
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == user.id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {"status": True, "total": 0, "data": []}

    # ✅ Machines only inside BMET OTs
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {"status": True, "total": 0, "data": []}

    data = []

    for machine_id in machine_ids:

        machine = db.query(models.Machine).filter(
            models.Machine.id == machine_id
        ).first()

        if not machine:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        latest = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id
        ).order_by(models.MachineInspection.created_at.desc()).first()

        if not latest or latest.status != "Not Working":
            continue

        # OT Name
        ot_assign = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        ot_name = "Unknown"
        if ot_assign:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == ot_assign.ot_id
            ).first()
            if ot:
                ot_name = ot.ot_name

        # Technician
        checked_by = "System"
        if latest.user_id:
            tech = db.query(models.User).filter(
                models.User.id == latest.user_id
            ).first()
            if tech:
                checked_by = tech.name

        data.append({
            "machine_id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "location": ot_name,
            "priority": latest.priority if latest.priority else "Low",
            "remarks": latest.remarks,
            "reported_at": latest.created_at.strftime("%b %d, %Y • %I:%M %p"),
            "checked_by": checked_by
        })

    return {
        "status": True,
        "total": len(data),
        "data": data
    }


# ================= ISSUE DETAILS API =================

@app.get("/api/issues/{machine_id}")
def get_issue_details(
    machine_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate user
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Get machine template
    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine.template_id
    ).first()

    machine_name = template.machine_name if template else "Unknown"

    # Get latest inspection
    latest = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine.id
    ).order_by(models.MachineInspection.created_at.desc()).first()

    # Technician name
    checked_by = "Unknown"

    if latest and latest.user_id:
        tech = db.query(models.User).filter(
            models.User.id == latest.user_id
        ).first()

        if tech and tech.name:
            checked_by = tech.name

    # OT Location
    ot_name = ""

    assignment = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.machine_id == machine.id
    ).first()

    if assignment:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == assignment.ot_id
        ).first()

        if ot:
            ot_name = ot.ot_name

    # Format inspection time
    reported_time = None

    if latest and latest.created_at:
        reported_time = latest.created_at.strftime("%b %d, %Y • %I:%M %p")

    # Priority
    priority = "Low"
    if latest and latest.priority:
        priority = latest.priority

    # Remarks
    remarks = ""
    if latest and latest.remarks:
        remarks = latest.remarks

    return {
        "status": True,
        "data": {
            "machine_id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "priority": priority,
            "remarks": remarks,
            "reported_at": reported_time,
            "ot_name": ot_name,
            "checked_by": checked_by
        }
    }


from datetime import datetime, date

from fastapi import Query

@app.post("/api/issues/resolve/{machine_id}")
def resolve_issue(
    machine_id: int,
    creator_id: int = Query(...),
    maintenance_notes: str = Query(...),
    db: Session = Depends(get_db)
):

    # Require maintenance notes
    if not maintenance_notes or maintenance_notes.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="Maintenance notes are required to resolve the issue"
        )

    # Validate user
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == user.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Verify there is an active issue inspection
    latest = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id
    ).order_by(models.MachineInspection.created_at.desc()).first()

    if not latest or latest.status != "Not Working":
        raise HTTPException(
            status_code=400,
            detail="No active issue to resolve"
        )

    # Create RESOLVED inspection record
    resolved_record = models.MachineInspection(
        machine_id=machine_id,
        user_id=creator_id,
        status="Resolved",
        remarks=maintenance_notes.strip(),
        priority=None,
        check_date=date.today(),
        created_at=datetime.now(IST)
    )

    db.add(resolved_record)

    # Update machine status
    machine.status = "Working"
    machine.last_checked = datetime.now(IST)

    db.commit()

    return {
        "status": True,
        "message": "Issue resolved successfully",
        "data": {
            "machine_id": machine_id,
            "resolved_by": user.name if hasattr(user, "name") else user.email,
            "resolved_at": datetime.now(IST).strftime("%b %d, %Y • %I:%M %p")
        }
    }


@app.get("/api/history/machines")
def get_at_history_machines(
    creator_id: int,
    status: str | None = None,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid user")

    # 🔥 STEP 1: Machines touched by AT
    at_machine_ids = db.query(models.MachineInspection.machine_id).filter(
        models.MachineInspection.user_id == creator_id
    ).distinct().all()

    at_machine_ids = [m[0] for m in at_machine_ids]

    if not at_machine_ids:
        return {"status": True, "total": 0, "data": []}

    # 🔥 STEP 2: Get latest inspections (ANY USER)
    inspections = db.query(models.MachineInspection).join(
        models.Machine,
        models.Machine.id == models.MachineInspection.machine_id
    ).filter(
        models.Machine.hospital_id == user.hospital_id,
        models.MachineInspection.machine_id.in_(at_machine_ids)
    ).order_by(
        models.MachineInspection.created_at.desc()
    ).all()

    result = []
    seen_machine_ids = set()

    for insp in inspections:

        if insp.machine_id in seen_machine_ids:
            continue

        seen_machine_ids.add(insp.machine_id)

        if status and insp.status.lower() != status.lower():
            continue

        machine = db.query(models.Machine).filter(
            models.Machine.id == insp.machine_id
        ).first()

        if not machine:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        # Machine Type
        machine_type = "Unknown"
        if template:
            type_obj = db.query(models.MachineType).filter(
                models.MachineType.id == template.machine_type_id
            ).first()
            if type_obj:
                machine_type = type_obj.type_name

        # OT Name
        ot_name = "Assign"
        ot_assign = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        if ot_assign:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == ot_assign.ot_id
            ).first()
            if ot:
                ot_name = ot.ot_name

        # Checked By
        inspector = db.query(models.User).filter(
            models.User.id == insp.user_id
        ).first()

        checked_by = inspector.name if inspector else "Technician"

        result.append({
            "id": insp.id,
            "machine_id": machine.id,
            "machine_name": template.machine_name if template else "Unknown",
            "machine_type": machine_type,
            "serial_number": machine.serial_number,
            "ot_name": ot_name,
            "status": insp.status,   # 🔥 NOW CORRECT
            "priority": insp.priority,
            "remarks": insp.remarks,
            "checked_at": insp.created_at,
            "checked_by": checked_by
        })

    return {
        "status": True,
        "total": len(result),
        "data": result
    }


from datetime import datetime, date

from sqlalchemy import func

@app.get("/api/dashboard/at/{user_id}")
def get_at_dashboard(user_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "AT",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid AT user")

    today = date.today()

    # ===== GET OTs ASSIGNED TO THIS AT =====
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {"status": True, "checked": 0, "issues": 0, "pending": 0}

    # ===== GET MACHINES INSIDE THOSE OTs =====
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {"status": True, "checked": 0, "issues": 0, "pending": 0}

    total_machines = len(machine_ids)

    # ===== GET TODAY'S INSPECTIONS =====
    inspections = db.query(
        models.MachineInspection.machine_id,
        models.MachineInspection.status
    ).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.user_id == user_id,
        models.MachineInspection.check_date == today
    ).all()

    checked = 0
    issues = 0
    inspected_machine_ids = set()

    for machine_id, status in inspections:

        # count each machine only once
        if machine_id not in inspected_machine_ids:
            inspected_machine_ids.add(machine_id)
            checked += 1

        # count issues
        if status == "Not Working":
            issues += 1

    pending = total_machines - checked

    if pending < 0:
        pending = 0

    return {
        "status": True,
        "checked": checked,
        "issues": issues,
        "pending": pending
    }



@app.get("/api/checklist/machines/{user_id}")
def get_checklist_machines(user_id: int, ot_id: int = None, db: Session = Depends(get_db)):

    # ---------------- USER VALIDATION ----------------
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "AT",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid AT user")

    # ---------------- GET ASSIGNED OTs ----------------
    if ot_id:
        ot_ids = [ot_id]
    else:
        ot_ids = [
    o[0] for o in db.query(models.OTAssignment.ot_id)
    .filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.is_active == True   # 🔥 THIS LINE
    )
    .all()
]

    if not ot_ids:
        return {"status": True, "pending": [], "completed": []}

    # ---------------- GET MACHINES ----------------
    machines = db.query(
        models.Machine.id,
        models.Machine.serial_number,
        models.MachineTemplate.machine_name,
        models.OTRoom.ot_name
    ).join(
        models.MachineTemplate,
        models.Machine.template_id == models.MachineTemplate.id
    ).join(
        models.OTMachineAssignment,
        models.Machine.id == models.OTMachineAssignment.machine_id
    ).outerjoin(
        models.OTRoom,
        models.OTRoom.id == models.OTMachineAssignment.ot_id
    ).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    if not machines:
        return {"status": True, "pending": [], "completed": []}

    today = date.today()
    machine_ids = [m.id for m in machines]

    # ---------------- GET TODAY'S AT INSPECTIONS ----------------
    inspections_today = db.query(
        models.MachineInspection.machine_id
    ).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.user_id == user_id,
        models.MachineInspection.check_date == today
    ).all()

    inspected_ids = set(i.machine_id for i in inspections_today)

    # ---------------- GET LATEST INSPECTIONS (ANY USER) ----------------
    latest_inspections = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id.in_(machine_ids)
    ).order_by(
        models.MachineInspection.machine_id,
        models.MachineInspection.created_at.desc()
    ).all()

    latest_map = {}
    for insp in latest_inspections:
        if insp.machine_id not in latest_map:
            latest_map[insp.machine_id] = insp

    # ---------------- BUILD RESPONSE ----------------
    pending = []
    completed = []

    for machine in machines:

        latest = latest_map.get(machine.id)

        machine_status = latest.status if latest else "Unknown"
        last_checked = latest.created_at if latest else None

        machine_data = {
            "id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "status": machine_status,   # ✅ ALWAYS CORRECT NOW
            "last_checked": last_checked,
            "ot_name": machine.ot_name
        }

        if machine.id in inspected_ids:
            completed.append(machine_data)
        else:
            pending.append(machine_data)

    return {
        "status": True,
        "pending": pending,
        "completed": completed
    }

@app.post("/api/checklist/reset-time")
def set_reset_time(
    request: schemas.ResetTimeRequest,
    creator_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Only HM can set reset time")

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == user.hospital_id
    ).first()

    if settings:
        settings.reset_time = request.reset_time
    else:
        settings = models.ChecklistSettings(
            hospital_id=user.hospital_id,
            reset_time=request.reset_time
        )
        db.add(settings)

    db.commit()

    return {
        "status": True,
        "message": "Reset time updated successfully"
    }


@app.get("/api/inspection/details/{inspection_id}")
def get_inspection_details(
    inspection_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # ---------------- USER VALIDATION ----------------
    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    # ---------------- CURRENT INSPECTION ----------------
    current = db.query(models.MachineInspection).filter(
        models.MachineInspection.id == inspection_id
    ).first()

    if not current:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # ---------------- MACHINE ----------------
    machine_obj = db.query(models.Machine).filter(
        models.Machine.id == current.machine_id
    ).first()

    if not machine_obj:
        raise HTTPException(status_code=404, detail="Machine not found")

    # ---------------- HM ACCESS CHECK (CRITICAL FIX) ----------------
    if user.role == "HM":
        if machine_obj.hospital_id != user.hospital_id:
            raise HTTPException(status_code=403, detail="Access denied")

    # ---------------- MACHINE INFO ----------------
    machine = db.query(
        models.Machine.id,
        models.Machine.serial_number,
        models.MachineTemplate.machine_name,
        models.OTRoom.ot_name
    ).join(
        models.MachineTemplate,
        models.Machine.template_id == models.MachineTemplate.id
    ).outerjoin(
        models.OTMachineAssignment,
        models.Machine.id == models.OTMachineAssignment.machine_id
    ).outerjoin(
        models.OTRoom,
        models.OTRoom.id == models.OTMachineAssignment.ot_id
    ).filter(
        models.Machine.id == current.machine_id
    ).first()

    # ---------------- FIND RELATED ISSUE ----------------
    issue = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == current.machine_id,
        models.MachineInspection.status == "Not Working",
        models.MachineInspection.created_at <= current.created_at
    ).order_by(models.MachineInspection.created_at.desc()).first()

    # ---------------- AT USER ----------------
    at_user = None
    if issue:
        at_user = db.query(models.User).filter(
            models.User.id == issue.user_id
        ).first()

    # ---------------- LIFECYCLE ----------------
    lifecycle = []

    lifecycle.append({
        "event": "Checklist Completed",
        "time": issue.created_at if issue else current.created_at,
        "checked_by": at_user.name if at_user else "Technician"
    })

    if issue:
        lifecycle.append({
            "event": "Issue Reported",
            "time": issue.created_at,
            "remarks": issue.remarks if issue.remarks else "Not Working"
        })

    if current.status == "Resolved":
        resolver = db.query(models.User).filter(
            models.User.id == current.user_id
        ).first()

        lifecycle.append({
            "event": "Resolved",
            "time": current.created_at,
            "resolved_by": resolver.name if resolver else "BMET",
            "resolution_notes": current.remarks if current.remarks else "Resolved"
        })

    # ---------------- RESPONSE ----------------
    return {
        "status": True,
        "data": {
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "ot_name": machine.ot_name if machine.ot_name else "Unknown",
            "machine_status": current.status,
            "inspection_time": current.created_at,
            "lifecycle": lifecycle,
            "issues": []
        }
    }


@app.get("/api/dashboard/hm/{user_id}")
def get_hm_dashboard(user_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    hospital_id = user.hospital_id

    total_ots = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == hospital_id
    ).count()

    total_machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == hospital_id
    ).count()

    technicians = db.query(models.User).filter(
        models.User.hospital_id == hospital_id,
        models.User.role.in_(["AT", "BMET"]),
        models.User.status == 1
    ).count()

    machines_with_issues = db.query(models.Machine).filter(
        models.Machine.hospital_id == hospital_id,
        models.Machine.status == "Not Working"
    ).count()

    return {
        "status": True,
        "data": {
            "total_ots": total_ots,
            "total_machines": total_machines,
            "technicians": technicians,
            "machines_with_issues": machines_with_issues
        }
    }


@app.get("/api/dashboard/bmet/{user_id}")
def get_bmet_dashboard(user_id: int, db: Session = Depends(get_db)):

    # ---------------- VALIDATE USER ----------------
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "BMET",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid BMET user")

    # ---------------- GET ACTIVE OTs ----------------
    ot_ids = db.query(models.OTAssignment.ot_id).filter(
        models.OTAssignment.user_id == user_id,
        models.OTAssignment.is_active == True
    ).all()

    ot_ids = [o[0] for o in ot_ids]

    if not ot_ids:
        return {
            "status": True,
            "issues": 0,
            "critical": 0,
            "done": 0,
            "data": {
                "issues": 0,
                "critical": 0,
                "done": 0
            }
        }

    # ---------------- GET MACHINES ----------------
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).distinct().all()

    machine_ids = [m[0] for m in machine_ids]

    if not machine_ids:
        return {
            "status": True,
            "issues": 0,
            "critical": 0,
            "done": 0,
            "data": {
                "issues": 0,
                "critical": 0,
                "done": 0
            }
        }

    # ---------------- GET LATEST INSPECTIONS ----------------
    inspections = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id.in_(machine_ids)
    ).order_by(
        models.MachineInspection.machine_id,
        models.MachineInspection.created_at.desc()
    ).all()

    latest_map = {}

    for insp in inspections:
        if insp.machine_id not in latest_map:
            latest_map[insp.machine_id] = insp

    # ---------------- COUNT ----------------
    issues = 0
    critical = 0
    done = 0
    
    for machine_id in machine_ids:
        latest = latest_map.get(machine_id)
        if not latest:
            continue

        # DONE
        # DONE → ONLY resolved
        if latest.status == "Resolved":
            done += 1

        # ISSUES
        elif latest.status == "Not Working":
            issues += 1

    if latest.priority == "Critical":
        critical += 1

    # ---------------- RESPONSE ----------------
    return {
        "status": True,
        "issues": issues,
        "critical": critical,
        "done": done,
        "data": {
            "issues": issues,
            "critical": critical,
            "done": done
        }
    }

@app.get("/api/reports/history")
def get_report_history(
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Get all machines of hospital
    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == creator.hospital_id
    ).all()

    data = []

    for machine in machines:

        # ✅ Get latest inspection
        latest_insp = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id
        ).order_by(models.MachineInspection.created_at.desc()).first()

        if not latest_insp:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        user = db.query(models.User).filter(
            models.User.id == latest_insp.user_id
        ).first()

        # ✅ OT Name
        assignment = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        ot_name = ""

        if assignment:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == assignment.ot_id
            ).first()

            if ot:
                ot_name = ot.ot_name

        # ✅ DERIVE STATUS
        if latest_insp.status == "Working":
            final_status = "Working"
        elif latest_insp.status == "Not Working":
            final_status = "Not Working"
        elif latest_insp.status == "Resolved":
            final_status = "Resolved"
        else:
            final_status = latest_insp.status

        data.append({
            "inspection_id": latest_insp.id,
            "machine_id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "status": final_status,
            "remarks": latest_insp.remarks,
            "priority": latest_insp.priority,
            "checked_by": user.name if user else "",
            "role": user.role if user else "",
            "date": latest_insp.created_at,
            "ot_name": ot_name
        })

    return {
        "status": True,
        "total": len(data),
        "data": data
    }

@app.post("/api/machine/template/add")
def add_machine_template(
    machine_name: str,
    machine_type_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Only HM can add templates")

    template = models.MachineTemplate(
        machine_name=machine_name,
        machine_type_id=machine_type_id,
        hospital_id=user.hospital_id
    )

    db.add(template)
    db.commit()

    return {
        "status": True,
        "message": "Machine template added"
    }

@app.get("/hospital/settings")
def get_hospital_settings(db: Session = Depends(get_db)):

    hospital = db.query(models.Hospital).first()
    settings = db.query(models.ChecklistSettings).first()

    hospital_name = None
    reset_time = None
    default_at_password = None
    default_bmet_password = None

    if hospital:
        hospital_name = getattr(hospital, "hospital_name", None)

    if settings:
        reset_time = settings.reset_time
        default_at_password = settings.default_at_password
        default_bmet_password = settings.default_bmet_password

    return {
        "hospital_name": hospital_name,
        "reset_time": reset_time,
        "default_at_password": default_at_password,
        "default_bmet_password": default_bmet_password
    }

@app.put("/api/hospital/update")
def update_hospital(
    creator_id: int,
    hospital_name: str,
    machine_reset_time: str,
    db: Session = Depends(get_db)
):

    # ---------------- VALIDATE USER ----------------
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    # ---------------- GET HOSPITAL ----------------
    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    # ---------------- UPDATE ----------------
    hospital.hospital_name = hospital_name
    hospital.machine_reset_time = machine_reset_time

    db.commit()

    return {
        "status": True,
        "message": "Hospital settings updated successfully"
    }

@app.get("/api/default-passwords")
def get_default_passwords(creator_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == user.hospital_id
    ).first()

    if not settings:
        return {
            "status": True,
            "data": {
                "default_at_password": "",
                "default_bmet_password": ""
            }
        }

    return {
        "status": True,
        "data": {
            "default_at_password": settings.default_at_password,
            "default_bmet_password": settings.default_bmet_password
        }
    }

    
@app.delete("/api/user/delete/{user_id}")
def delete_user(
    user_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Unauthorized")

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.hospital_id == creator.hospital_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == creator_id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")

    # 🔥 REAL DELETE
    db.delete(user)
    db.commit()

    return {
        "status": True,
        "message": "User permanently deleted"
    }

@app.put("/api/hospital/network-restriction")
def update_network_restriction(
    creator_id: int,
    enabled: bool,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    hospital.network_restriction = enabled

    db.commit()

    return {
        "status": True,
        "message": "Network restriction updated"
    }

@app.get("/api/hospital/networks")
def get_allowed_networks(
    creator_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    networks = db.query(models.AllowedNetwork).filter(
        models.AllowedNetwork.hospital_id == user.hospital_id
    ).all()

    return {
        "status": True,
        "data": [
            {
                "id": net.id,
                "ssid": net.ssid,
                "domain": net.domain
            }
            for net in networks
        ]
    }

@app.post("/api/hospital/networks")
def add_network(
    request: schemas.NetworkSaveRequest,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == request.creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_network = models.AllowedNetwork(
        hospital_id=user.hospital_id,
        ssid=request.ssid,
        domain=request.domain
    )

    db.add(new_network)
    db.commit()

    return {
        "status": True,
        "message": "Network added successfully"
    }

@app.put("/api/user/force-change-password")
def force_change_password(
    user_id: int,
    new_password: str,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    import re

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if not re.search(r"[A-Z]", new_password):
        raise HTTPException(status_code=400, detail="Must contain uppercase")

    if not re.search(r"[a-z]", new_password):
        raise HTTPException(status_code=400, detail="Must contain lowercase")

    if not re.search(r"[0-9]", new_password):
        raise HTTPException(status_code=400, detail="Must contain number")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):
        raise HTTPException(status_code=400, detail="Must contain special character")

    # 🔥 UPDATE PASSWORD
    user.password = new_password

    # 🔥 THIS IS THE LINE YOU ARE ASKING ABOUT
    user.force_password_change = False

    db.commit()

    return {
        "status": True,
        "message": "Password updated successfully"
    }

@app.put("/api/user/update-mobile")
def update_mobile(user_id: int, mobile: str, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.mobile = mobile
    db.commit()

    return {
        "status": True,
        "message": "Mobile updated successfully"
    }

@app.post("/api/user/send-otp")
def send_otp(user_id: int, mobile: str, db: Session = Depends(get_db)):

    import random

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp = str(random.randint(100000, 999999))

    user.mobile = mobile
    user.otp = otp   # add column in DB
    db.commit()

    print("OTP:", otp)  # for testing

    return {
        "status": True,
        "message": "OTP sent"
    }


@app.post("/api/user/verify-otp")
def verify_otp(user_id: int, otp: str, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    user.otp = None
    db.commit()

    return {
        "status": True,
        "message": "OTP verified"
    }


@app.put("/api/user/forgot-password/reset")
def reset_password(
    email: str = None,
    mobile: str = None,
    new_password: str = None,
    db: Session = Depends(get_db)
):

    user = None

    if email:
        user = db.query(models.User).filter(models.User.email == email).first()
    elif mobile:
        user = db.query(models.User).filter(models.User.mobile == mobile).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = new_password
    user.force_password_change = False  # optional
    db.commit()

    return {
        "status": True,
        "message": "Password reset successful"
    }

from fastapi.responses import FileResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import os
from datetime import datetime
from calendar import monthrange

@app.get("/api/report/monthly")
def generate_monthly_report(
    machine_id: int,
    month: int,
    year: int,
    db: Session = Depends(get_db)
):

    # ===== VALIDATION =====
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == machine.hospital_id
    ).first()

    # ===== MACHINE NAME =====
    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine.template_id
    ).first()

    machine_name = template.machine_name if template else "Unknown Machine"

    # ===== OT NAME =====
    assignment = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.machine_id == machine.id
    ).first()

    ot_name = "Unknown OT"

    if assignment:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == assignment.ot_id
        ).first()

        if ot:
            ot_name = ot.ot_name

    # ===== DATE RANGE FIX =====
    last_day = monthrange(year, month)[1]

    records = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id,
        models.MachineInspection.check_date.between(
            f"{year}-{month:02d}-01",
            f"{year}-{month:02d}-{last_day}"
        )
    ).order_by(models.MachineInspection.check_date.asc()).all()

    # ===== FILE SETUP =====
    os.makedirs("reports", exist_ok=True)
    file_path = f"reports/report_{machine_id}_{month}_{year}.pdf"

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()
    elements = []

    # ===== HEADER =====
    elements.append(Paragraph(
        f"<b>{hospital.hospital_name if hospital else ''}</b>",
        styles['Title']
    ))
    elements.append(Paragraph(f"{ot_name}", styles['Normal']))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        f"<b>Anaesthesia Workstation Checklist ({machine_name})</b>",
        styles['Heading2']
    ))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        f"<b>{datetime(year, month, 1).strftime('%B %Y')}</b>",
        styles['Normal']
    ))
    elements.append(Spacer(1, 15))

    if not records:
        elements.append(Paragraph("No records available for this period", styles['Normal']))
        elements.append(Spacer(1, 10))

    # ===== TABLE =====
    table_data = [["Date", "Working", "Remarks (BMET)", "Checked By"]]

    for record in records:
        user = db.query(models.User).filter(
            models.User.id == record.user_id
        ).first()

        checked_by = user.name if user else "Unknown"

        table_data.append([
            record.check_date.strftime("%d-%m-%Y"),
            "Working" if record.status == "Working" else "Not Working",
            record.remarks or "-",
            checked_by
        ])

    table = Table(table_data)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # ===== FOOTER =====
    elements.append(Paragraph(
        "Generated by Smart Anaesthesia Workstation System",
        styles['Italic']
    ))

    doc.build(elements)

    return FileResponse(
        path=file_path,
        media_type='application/pdf',
        filename=f"Report_{month}_{year}.pdf"
    )


@app.get("/api/reports/history")
def get_report_history(
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # ✅ Get all machines of hospital
    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == creator.hospital_id
    ).all()

    data = []

    for machine in machines:

        # ✅ Get latest inspection
        latest_insp = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id
        ).order_by(models.MachineInspection.created_at.desc()).first()

        if not latest_insp:
            continue

        template = db.query(models.MachineTemplate).filter(
            models.MachineTemplate.id == machine.template_id
        ).first()

        machine_name = template.machine_name if template else "Unknown"

        user = db.query(models.User).filter(
            models.User.id == latest_insp.user_id
        ).first()

        # ✅ OT Name
        assignment = db.query(models.OTMachineAssignment).filter(
            models.OTMachineAssignment.machine_id == machine.id
        ).first()

        ot_name = ""

        if assignment:
            ot = db.query(models.OTRoom).filter(
                models.OTRoom.id == assignment.ot_id
            ).first()

            if ot:
                ot_name = ot.ot_name

        # ✅ DERIVE STATUS
        if latest_insp.status == "Working":
            final_status = "Working"
        elif latest_insp.status == "Not Working":
            final_status = "Not Working"
        elif latest_insp.status == "Resolved":
            final_status = "Resolved"
        else:
            final_status = latest_insp.status

        data.append({
            "inspection_id": latest_insp.id,
            "machine_id": machine.id,
            "machine_name": machine_name,
            "serial_number": machine.serial_number,
            "status": final_status,
            "remarks": latest_insp.remarks,
            "priority": latest_insp.priority,
            "checked_by": user.name if user else "",
            "role": user.role if user else "",
            "date": latest_insp.created_at,
            "ot_name": ot_name
        })

    return {
        "status": True,
        "total": len(data),
        "data": data
    }

@app.post("/api/machine/template/add")
def add_machine_template(
    machine_name: str,
    machine_type_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Only HM can add templates")

    template = models.MachineTemplate(
        machine_name=machine_name,
        machine_type_id=machine_type_id,
        hospital_id=user.hospital_id
    )

    db.add(template)
    db.commit()

    return {
        "status": True,
        "message": "Machine template added"
    }

@app.get("/hospital/settings")
def get_hospital_settings(db: Session = Depends(get_db)):

    hospital = db.query(models.Hospital).first()
    settings = db.query(models.ChecklistSettings).first()

    hospital_name = None
    reset_time = None
    default_at_password = None
    default_bmet_password = None

    if hospital:
        hospital_name = getattr(hospital, "hospital_name", None)

    if settings:
        reset_time = settings.reset_time
        default_at_password = settings.default_at_password
        default_bmet_password = settings.default_bmet_password

    return {
        "hospital_name": hospital_name,
        "reset_time": reset_time,
        "default_at_password": default_at_password,
        "default_bmet_password": default_bmet_password
    }

from datetime import datetime

@app.put("/api/hospital/update")
def update_hospital(
    creator_id: int,
    hospital_name: str,
    machine_reset_time: str,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    # 🔥 CONVERT STRING → TIME
    try:
        parsed_time = datetime.strptime(machine_reset_time, "%H:%M:%S").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format (HH:MM:SS required)")

    hospital.hospital_name = hospital_name
    hospital.machine_reset_time = parsed_time

    db.commit()
    db.refresh(hospital)

    return {
        "status": True,
        "message": "Hospital settings updated successfully"
    }

@app.get("/api/default-passwords")
def get_default_passwords(creator_id: int, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == user.hospital_id
    ).first()

    if not settings:
        return {
            "status": True,
            "data": {
                "default_at_password": "",
                "default_bmet_password": ""
            }
        }

    return {
        "status": True,
        "data": {
            "default_at_password": settings.default_at_password,
            "default_bmet_password": settings.default_bmet_password
        }
    }

    
@app.delete("/api/user/delete/{user_id}")
def delete_user(
    user_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Unauthorized")

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.hospital_id == creator.hospital_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == creator_id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")

    # 🔥 REAL DELETE
    db.delete(user)
    db.commit()

    return {
        "status": True,
        "message": "User permanently deleted"
    }

@app.put("/api/hospital/network-restriction")
def update_network_restriction(
    creator_id: int,
    enabled: bool,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == creator_id,
        models.User.role == "HM"
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    hospital.network_restriction = enabled

    db.commit()

    return {
        "status": True,
        "message": "Network restriction updated"
    }

@app.put("/api/user/force-change-password")
def force_change_password(
    user_id: int,
    new_password: str,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    import re

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if not re.search(r"[A-Z]", new_password):
        raise HTTPException(status_code=400, detail="Must contain uppercase")

    if not re.search(r"[a-z]", new_password):
        raise HTTPException(status_code=400, detail="Must contain lowercase")

    if not re.search(r"[0-9]", new_password):
        raise HTTPException(status_code=400, detail="Must contain number")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):
        raise HTTPException(status_code=400, detail="Must contain special character")

    # 🔥 UPDATE PASSWORD
    user.password = new_password

    # 🔥 THIS IS THE LINE YOU ARE ASKING ABOUT
    user.force_password_change = False

    db.commit()

    return {
        "status": True,
        "message": "Password updated successfully"
    }

@app.put("/api/user/update-mobile")
def update_mobile(user_id: int, mobile: str, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.mobile = mobile
    db.commit()

    return {
        "status": True,
        "message": "Mobile updated successfully"
    }

@app.post("/api/user/send-otp")
def send_otp(user_id: int, mobile: str, db: Session = Depends(get_db)):

    import random

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp = str(random.randint(100000, 999999))

    user.mobile = mobile
    user.otp = otp   # add column in DB
    db.commit()

    print("OTP:", otp)  # for testing

    return {
        "status": True,
        "message": "OTP sent"
    }


@app.post("/api/user/verify-otp")
def verify_otp(user_id: int, otp: str, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    user.otp = None
    db.commit()

    return {
        "status": True,
        "message": "OTP verified"
    }


@app.put("/api/user/forgot-password/reset")
def reset_password(
    email: str = None,
    mobile: str = None,
    new_password: str = None,
    db: Session = Depends(get_db)
):

    user = None

    if email:
        user = db.query(models.User).filter(models.User.email == email).first()
    elif mobile:
        user = db.query(models.User).filter(models.User.mobile == mobile).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = new_password
    user.force_password_change = False  # optional
    db.commit()

    return {
        "status": True,
        "message": "Password reset successful"
    }

from fastapi.responses import FileResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import os
from datetime import datetime
from calendar import monthrange

@app.get("/api/report/monthly")
def generate_monthly_report(
    machine_id: int,
    month: int,
    year: int,
    db: Session = Depends(get_db)
):

    # ===== VALIDATION =====
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == machine.hospital_id
    ).first()

    # ===== MACHINE NAME =====
    template = db.query(models.MachineTemplate).filter(
        models.MachineTemplate.id == machine.template_id
    ).first()

    machine_name = template.machine_name if template else "Unknown Machine"

    # ===== OT NAME =====
    assignment = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.machine_id == machine.id
    ).first()

    ot_name = "Unknown OT"

    if assignment:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == assignment.ot_id
        ).first()

        if ot:
            ot_name = ot.ot_name

    # ===== DATE RANGE FIX =====
    last_day = monthrange(year, month)[1]

    records = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id,
        models.MachineInspection.check_date.between(
            f"{year}-{month:02d}-01",
            f"{year}-{month:02d}-{last_day}"
        )
    ).order_by(models.MachineInspection.check_date.asc()).all()

    # ===== FILE SETUP =====
    os.makedirs("reports", exist_ok=True)
    file_path = f"reports/report_{machine_id}_{month}_{year}.pdf"

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()
    elements = []

    # ===== HEADER =====
    elements.append(Paragraph(
        f"<b>{hospital.hospital_name if hospital else ''}</b>",
        styles['Title']
    ))
    elements.append(Paragraph(f"{ot_name}", styles['Normal']))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        f"<b>Anaesthesia Workstation Checklist ({machine_name})</b>",
        styles['Heading2']
    ))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        f"<b>{datetime(year, month, 1).strftime('%B %Y')}</b>",
        styles['Normal']
    ))
    elements.append(Spacer(1, 15))

    if not records:
        elements.append(Paragraph("No records available for this period", styles['Normal']))
        elements.append(Spacer(1, 10))

    # ===== TABLE =====
    table_data = [["Date", "Working", "Remarks (BMET)", "Checked By"]]

    for record in records:
        user = db.query(models.User).filter(
            models.User.id == record.user_id
        ).first()

        checked_by = user.name if user else "Unknown"

        table_data.append([
            record.check_date.strftime("%d-%m-%Y"),
            "Working" if record.status == "Working" else "Not Working",
            record.remarks or "-",
            checked_by
        ])

    table = Table(table_data)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # ===== FOOTER =====
    elements.append(Paragraph(
        "Generated by Smart Anaesthesia Workstation System",
        styles['Italic']
    ))

    doc.build(elements)

    return FileResponse(
        path=file_path,
        media_type='application/pdf',
        filename=f"Report_{month}_{year}.pdf"
    )

@app.post("/api/machine/type/add")
def add_machine_type(
    request: schemas.MachineTypeCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):
    # -------- VALIDATE USER --------
    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    hospital_id = user.hospital_id

    # -------- PREVENT DUPLICATE (PER HOSPITAL) --------
    existing = db.query(models.MachineType).filter(
        models.MachineType.type_name.ilike(request.type_name.strip()),
        models.MachineType.hospital_id == hospital_id
    ).first()

    if existing:
        return {
            "status": False,
            "message": "Machine type already exists in this hospital"
        }

    # -------- CREATE TYPE --------
    new_type = models.MachineType(
        type_name=request.type_name.strip(),
        hospital_id=hospital_id   # 🔥 IMPORTANT FIX
    )

    db.add(new_type)
    db.commit()
    db.refresh(new_type)

    return {
        "status": True,
        "message": "Machine type added successfully",
        "id": new_type.id
    }
# ================= FORGOT PASSWORD (REAL TIME MAIL OTP) =================

from datetime import datetime, timedelta

@app.post("/api/user/forgot-password/send-otp")
def forgot_password_otp(request: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.email == request.email).first()
    
    if not user:
        return {"status": False, "message": "Email not found"}

    # 🔥 Generate OTP
    otp = ''.join(random.choices(string.digits, k=6))

    # 🔥 SET EXPIRY (YOU MISSED THIS)
    expiry_time = datetime.utcnow() + timedelta(minutes=2)

    user.otp = otp
    user.otp_expiry = expiry_time

    db.commit()

    if send_otp_email(user.email, otp):
        return {"status": True, "message": f"OTP sent to {user.email}"}
    else:
        return {"status": False, "message": "Email sending failed"}

from datetime import datetime
from fastapi import HTTPException

@app.post("/api/user/forgot-password/verify-otp")
def verify_otp_endpoint(request: schemas.VerifyOTPRequest, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.email == request.email
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    print("DB OTP:", user.otp)
    print("Entered OTP:", request.otp)

    if not user.otp:
        raise HTTPException(status_code=400, detail="No OTP found")

    # 🔥 FORCE STRING + STRIP
    if str(user.otp).strip() != str(request.otp).strip():
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if not user.otp_expiry or datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP expired")

    # invalidate
    user.otp = None
    user.otp_expiry = None
    db.commit()

    return {"status": True, "message": "OTP verified"}

@app.post("/api/user/forgot-password/reset-password")
def reset_password_endpoint(
    request: schemas.ResetPasswordRequest,
    db: Session = Depends(get_db)
):

    # -------- PASSWORD MATCH CHECK --------
    if request.new_password != request.confirm_password:
        return {"status": False, "message": "Passwords do not match"}

    # -------- GET USER --------
    user = db.query(models.User).filter(
        models.User.email == request.email
    ).first()

    if not user:
        return {"status": False, "message": "User not found"}

    # 🔥 DO NOT CHECK OTP HERE

    # -------- UPDATE PASSWORD --------
    user.password = request.new_password

    # OPTIONAL: clear OTP
    user.otp = None

    db.commit()

    return {
        "status": True,
        "message": "Password changed successfully"
    }


import random
from datetime import datetime, timedelta

@app.post("/api/resend-otp")
def resend_otp(email: str, db: Session = Depends(get_db)):

    user = db.query(models.User).filter(
        models.User.email == email
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔥 Generate new OTP
    new_otp = str(random.randint(100000, 999999))

    # 🔥 Set new expiry (e.g., 2 mins)
    expiry_time = datetime.utcnow() + timedelta(minutes=2)

    # 🔥 Overwrite old OTP (this auto-expires previous)
    user.otp = new_otp
    user.otp_expiry = expiry_time

    db.commit()

    # TODO: Send OTP (email/sms)

    return {
        "status": True,
        "message": "OTP resent successfully"
    }


    # main.py

# main.py

import random
from datetime import datetime, timedelta
from fastapi import HTTPException

@app.post("/api/register/send-otp")
def send_register_otp(request: schemas.HMRegisterRequest, db: Session = Depends(get_db)):

    # -------- VALIDATION --------
    if not request.hm_name or not request.hm_email or not request.password or not request.hospital_name:
        raise HTTPException(status_code=400, detail="All fields are required")

    # -------- CHECK EXISTING USER --------
    existing_user = db.query(models.User).filter(
        models.User.email == request.hm_email.strip()
    ).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    # -------- DELETE OLD TEMP USER (IMPORTANT) --------
    db.query(models.TempUser).filter(
        models.TempUser.email == request.hm_email.strip()
    ).delete()

    # -------- GENERATE OTP --------
    import random
    from datetime import datetime, timedelta

    otp = str(random.randint(100000, 999999))
    expiry_time = datetime.utcnow() + timedelta(minutes=5)

    # -------- CREATE TEMP USER --------
    temp_user = models.TempUser(
        name=request.hm_name.strip(),
        email=request.hm_email.strip(),
        password=request.password,  # will hash later
        hospital_name=request.hospital_name.strip(),  # 🔥 CRITICAL
        otp=otp,
        otp_expiry=expiry_time
    )

    db.add(temp_user)
    db.commit()

    print("OTP:", otp)  # for testing

    return {
        "status": True,
        "message": "OTP sent successfully"
    }


@app.post("/api/register/verify-otp")
def verify_register_otp(request: schemas.VerifyOTPRequest, db: Session = Depends(get_db)):

    from datetime import datetime

    # -------- GET LATEST TEMP USER --------
    temp_user = db.query(models.TempUser).filter(
        models.TempUser.email == request.email
    ).order_by(models.TempUser.id.desc()).first()

    if not temp_user:
        raise HTTPException(status_code=404, detail="No registration found")

    print("Stored OTP:", temp_user.otp)
    print("Entered OTP:", request.otp)
    print("Hospital:", temp_user.hospital_name)

    # -------- VALIDATE OTP --------
    if str(temp_user.otp) != str(request.otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # -------- CHECK EXPIRY --------
    if not temp_user.otp_expiry or datetime.utcnow() > temp_user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP expired")

    # -------- VALIDATE HOSPITAL NAME --------
    if not temp_user.hospital_name:
        raise HTTPException(status_code=400, detail="Hospital name missing")

    # -------- CREATE HOSPITAL --------
    hospital = models.Hospital(
        hospital_name=temp_user.hospital_name.strip()
    )

    db.add(hospital)
    db.commit()
    db.refresh(hospital)

    print("Created Hospital ID:", hospital.id)

    # -------- CREATE HM USER --------
    new_user = models.User(
        name=temp_user.name.strip(),
        email=temp_user.email.strip(),
        password=temp_user.password,  # 🔥 SECURE
        role="HM",
        employee_id=f"HM{hospital.id}",
        hospital_id=hospital.id,
        status=1
    )

    db.add(new_user)

    # -------- DELETE TEMP USER --------
    db.delete(temp_user)

    db.commit()
    db.refresh(new_user)

    return {
        "status": True,
        "message": "Registration successful",
        "hospital_id": hospital.id,
        "user_id": new_user.id
    }


@app.post("/api/register/resend-otp")
def resend_register_otp(email: str, db: Session = Depends(get_db)):

    temp_user = db.query(models.TempUser).filter(
        models.TempUser.email == email
    ).first()

    if not temp_user:
        raise HTTPException(status_code=404, detail="No registration found")

    # 🔥 Generate new OTP
    new_otp = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=2)

    temp_user.otp = new_otp
    temp_user.otp_expiry = expiry

    db.commit()

    send_otp_email(email, new_otp)

    return {
        "status": True,
        "message": "OTP resent successfully"
    }