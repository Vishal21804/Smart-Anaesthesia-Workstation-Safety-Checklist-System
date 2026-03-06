from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database import SessionLocal, engine
import models
import crud
import schemas
from fastapi import HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends
from models import Machine, MachineInspection
from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File, Form
import os
import shutil

UPLOAD_DIR = "uploads/profile_pics"
os.makedirs(UPLOAD_DIR, exist_ok=True)

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Serve static files for uploads so the Android app can download images
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ================= DATABASE SESSION =================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ================= HM REGISTRATION =================
@app.post("/register_hm")
def register_hm(
    request: schemas.HMRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        existing_hospital = db.query(models.Hospital).filter(
            models.Hospital.hospital_name == request.hospital_name
        ).first()

        if existing_hospital:
            existing_hm = db.query(models.User).filter(
                models.User.hospital_id == existing_hospital.id,
                models.User.role == "HM"
            ).first()

            if existing_hm:
                return {
                    "status": False,
                    "message": "This hospital already has a Hospital Manager"
                }

            hospital = existing_hospital

        else:
            hospital = models.Hospital(
                hospital_name=request.hospital_name,
                hospital_email=request.hospital_email
            )
            db.add(hospital)
            db.flush()

        hm_user = models.User(
            name=request.hm_name,
            email=request.hm_email,
            password=request.password,
            role="HM",
            employee_id="HM001",
            hospital_id=hospital.id,
            status=1
        )

        db.add(hm_user)
        db.commit()

        return {
            "status": True,
            "message": "Hospital and HM registered successfully"
        }

    except IntegrityError:
        db.rollback()
        return {
            "status": False,
            "message": "Email already exists"
        }


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
    user.last_login = datetime.utcnow()
    db.commit()

    return {
        "status": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "hospital_id": user.hospital_id,
            "profile_pic": user.profile_picture
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

    existing_email = db.query(models.User).filter(
        models.User.email == request.email
    ).first()

    if existing_email:
        return {
            "status": False,
            "message": "Email already exists"
        }

    user = models.User(
        name=request.name,
        email=request.email,
        password=request.password,
        role=request.role,
        employee_id=request.employee_id,
        hospital_id=creator.hospital_id,
        created_by=creator.id,
        status=1
    )

    db.add(user)
    db.commit()

    return {
        "status": True,
        "message": "User created successfully"
    }


# ================= GET USERS (HM ONLY - FILTERED BY HOSPITAL) =================
@app.get("/get_users")
def get_users(
    creator_id: int,
    search: str = None,
    role: str = None,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Access denied")

    query = db.query(models.User).filter(
        models.User.hospital_id == creator.hospital_id,
        models.User.role != "HM"
    )

    if search:
        query = query.filter(
            models.User.name.ilike(f"%{search}%")
        )

    if role:
        query = query.filter(
            models.User.role == role
        )

    users = query.all()

    user_list = []

    for user in users:

        assigned_ot_count = db.query(models.OTAssignment).filter(
            models.OTAssignment.user_id == user.id
        ).count()

        user_list.append({
    "id": user.id,
    "name": user.name,
    "email": user.email,
    "role": user.role,
    "status": user.status,
    "profile_pic": user.profile_picture,
    "assigned_ot_count": assigned_ot_count,
    "last_login": user.last_login.date() if user.last_login else None
})

    return {
        "status": True,
        "total_users": len(user_list),
        "active_users": len([u for u in user_list if u["status"] == 1]),
        "disabled_users": len([u for u in user_list if u["status"] == 0]),
        "users": user_list
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

    db.commit()

    return {
        "status": True,
        "message": "User updated successfully"
    }


# ================= GET PROFILE =================
@app.get("/profile/{user_id}")
def get_profile(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hospital = db.query(models.Hospital).filter(
        models.Hospital.id == user.hospital_id
    ).first()

    hospital_name = hospital.hospital_name if hospital else ""

    return {
        "status": True,
        "data": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "mobile": user.mobile,
            "role": user.role,
            "employee_id": user.employee_id,
            "hospital_id": user.hospital_id,
            "hospital_name": hospital_name,
            "status": user.status,
            "profile_pic": user.profile_picture,
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
        filename = f"user_{user_id}.{file_extension}"
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
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    ot_rooms = db.query(models.OTRoom).filter(
        models.OTRoom.hospital_id == creator.hospital_id
    ).all()

    data = []

    for ot in ot_rooms:

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

    machine = models.Machine(
        machine_name=request.machine_name,
        machine_type_id=request.machine_type_id,
        hospital_id=creator.hospital_id,
        status="Working",
        serial_number=None  # 🔥 default null
    )

    db.add(machine)
    db.commit()
    db.refresh(machine)

    return {
        "status": True,
        "message": "Machine template added successfully"
    }


    # Create machine object
    machine = models.Machine(
        machine_name=request.machine_name,
        model=request.model,
        serial_number=request.serial_number,
        hospital_id=creator.hospital_id,
        machine_type_id=request.machine_type_id,
        status="Active"
    )

    print("Machine name:", request.machine_name)
    print("Model:", request.model)
    print("Serial number:", request.serial_number)
    print("Machine type ID:", request.machine_type_id)
    print("Connected DB URL:", db.bind.url)
    
    db.add(machine)
    db.commit()
    db.refresh(machine)
    print("Machine inserted successfully with ID:", machine.id)

    print("----- END ADD MACHINE -----")

    return {
        "status": True,
        "message": "Machine added successfully"
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

        machine_type = db.query(models.MachineType).filter(
            models.MachineType.id == m.machine_type_id
        ).first()

        # Get all OT assignments for this machine
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
            "machine_name": m.machine_name,
            "serial_number": m.serial_number,
            "machine_type": machine_type.type_name if machine_type else "",
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

    # Get all assignments for this OT
    existing_assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.ot_id == request.ot_id
    ).all()

    for assignment in existing_assignments:
        user = db.query(models.User).filter(
            models.User.id == assignment.user_id
        ).first()

        if user and user.role == assigned_user.role:
            return {
                "status": False,
                "message": "This OT is already assigned to same role"
            }

    new_assignment = models.OTAssignment(
        user_id=request.user_id,
        ot_id=request.ot_id,
        hospital_id=assigned_user.hospital_id
    )

    db.add(new_assignment)
    db.commit()

    return {
        "status": True,
        "message": "OT assigned successfully"
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

@app.get("/api/ot/user_assignments")
def get_user_assignments(
    user_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id
    ).all()

    data = []

    for a in assignments:
        ot = db.query(models.OTRoom).filter(
            models.OTRoom.id == a.ot_id
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
    machine_id: int,
    serial_number: str,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    if not serial_number:
        raise HTTPException(status_code=400, detail="Serial number required")

    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == ot_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT not found")

    # DO NOT block reuse
    assignment = models.OTMachineAssignment(
        machine_id=machine_id,
        ot_id=ot_id,
        hospital_id=creator.hospital_id
    )

    db.add(assignment)

    # store serial on assignment level
    machine.serial_number = serial_number

    db.commit()

    return {
        "status": True,
        "message": "Machine assigned successfully"
    }

@app.get("/api/ot/{ot_id}/machines")
def get_ot_machines(
    ot_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):
    # Validate user
    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate OT exists
    ot = db.query(models.OTRoom).filter(
        models.OTRoom.id == ot_id
    ).first()

    if not ot:
        raise HTTPException(status_code=404, detail="OT not found")

    # Fetch assignments ONLY by OT
    assignments = db.query(models.OTMachineAssignment).filter(
        models.OTMachineAssignment.ot_id == ot_id
    ).all()

    result = []

    for assignment in assignments:
        machine = db.query(models.Machine).filter(
            models.Machine.id == assignment.machine_id
        ).first()

        if machine:
            result.append({
                "id": machine.id,
                "machine_name": machine.machine_name,
                "machine_type_id": machine.machine_type_id,
                "serial_number": machine.serial_number,
                "status": machine.status
            })

    return {
        "status": True,
        "data": result
    }


@app.get("/api/machine/available")
def get_available_machines(
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
        data.append({
            "id": m.id,
            "machine_name": m.machine_name,
            "machine_type_id": m.machine_type_id,
            "serial_number": m.serial_number,
            "status": m.status
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
        models.OTAssignment.hospital_id == creator.hospital_id
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
    request: InspectMachineRequest,
    db: Session = Depends(get_db)
):

    # Validate machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == request.machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Validate user
    user = db.query(models.User).filter(
        models.User.id == request.user_id,
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role != "AT":
        raise HTTPException(status_code=403, detail="Only AT can inspect machines")

    # Get hospital reset time
    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == user.hospital_id
    ).first()

    if not settings:
        raise HTTPException(
            status_code=400,
            detail="Checklist reset time not configured"
        )

    reset_time = settings.reset_time
    now = datetime.now()

    reset_datetime_today = datetime.combine(date.today(), reset_time)

    if now < reset_datetime_today:
        checklist_date = date.today() - timedelta(days=1)
    else:
        checklist_date = date.today()

    # DEBUG PRINTS
    print("Current time:", datetime.now())
    print("Reset time:", reset_time)
    print("Checklist date:", checklist_date)
    print("Machine ID:", request.machine_id)
    print("==========================")

    # Validate Not Working logic
    if request.status == "Not Working":
        if not request.remarks:
            raise HTTPException(status_code=400, detail="Remark is required")
        if not request.priority:
            raise HTTPException(status_code=400, detail="Priority is required")

    # Insert with strict DB protection
    try:
        inspection = models.MachineInspection(
            machine_id=request.machine_id,
            user_id=request.user_id,
            status=request.status,
            remarks=request.remarks,
            priority=request.priority,
            check_date=checklist_date,
            created_at=datetime.utcnow()
        )

        db.add(inspection)

        machine.status = request.status
        machine.last_checked = datetime.utcnow()

        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Machine already inspected for this checklist day"
        )

    return {
        "status": True,
        "message": "Inspection recorded successfully"
    }

@app.get("/api/machine/history")
def get_machine_history(
    creator_id: int,
    status: str = None,
    db: Session = Depends(get_db)
):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get machines of this hospital
    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == creator.hospital_id
    ).all()

    data = []

    for machine in machines:

        # Get latest inspection
        latest = db.query(models.MachineInspection).filter(
            models.MachineInspection.machine_id == machine.id,
            models.MachineInspection.user_id == creator.id
        ).order_by(models.MachineInspection.created_at.desc()).first()

        if not latest:
            continue

        if status and latest.status.lower() != status.lower():
            continue

        user = db.query(models.User).filter(
            models.User.id == latest.user_id
        ).first()

        # Get OT assignment
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

        data.append({
            "machine_id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "location": ot_name,
            "inspection_date": latest.created_at,
            "status": latest.status,
            "checked_by": user.name if user else ""
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

    return {
        "status": True,
        "data": {
            "id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "last_checked": machine.last_checked
        }
    }


@app.put("/api/machine/update/{machine_id}")
def update_machine(
    machine_id: int,
    request: schemas.UpdateMachineRequest,
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

    # ---------- Validation ----------
    if not request.machine_name.strip():
        raise HTTPException(status_code=400, detail="Machine name required")

    if not request.serial_number.strip():
        raise HTTPException(status_code=400, detail="Serial number required")

    # Validate machine type
    print("Machine Type Received:", request.machine_type_id)
    machine_type = db.query(models.MachineType).filter(
        models.MachineType.id == request.machine_type_id
    ).first()

    if not machine_type:
        raise HTTPException(status_code=400, detail="Invalid machine type")

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

    # ---------- Update ----------
    machine.machine_name = request.machine_name
    machine.machine_type_id = request.machine_type_id
    machine.serial_number = request.serial_number

    db.commit()

    return {
        "status": True,
        "message": "Machine updated successfully"
    }

@app.put("/api/machine/update-template/{machine_id}")
def update_machine_template(
    machine_id: int,
    request: schemas.MachineCreate,
    creator_id: int,
    db: Session = Depends(get_db)
):

    # Validate creator
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator or creator.role != "HM":
        raise HTTPException(status_code=403, detail="Only HM can edit machine templates")

    # Get machine
    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    # Validate machine type
    machine_type = db.query(models.MachineType).filter(
        models.MachineType.id == request.machine_type_id
    ).first()

    if not machine_type:
        raise HTTPException(status_code=400, detail="Invalid machine type")

    # Update only template fields
    machine.machine_name = request.machine_name
    machine.machine_type_id = request.machine_type_id

    db.commit()

    return {
        "status": True,
        "message": "Machine template updated successfully"
    }

# ================= ISSUE PAGE APIs =================

@app.get("/api/issues/ots")
def get_issue_ots(
    creator_id: int,
    db: Session = Depends(get_db)
):
    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == creator.hospital_id,
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
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    machines = db.query(models.Machine).filter(
        models.Machine.hospital_id == user.hospital_id,
        models.Machine.status == "Not Working"
    ).all()

    data = []

    for machine in machines:

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

        data.append({
            "machine_id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "ot_name": ot_name
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

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == creator.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    if machine.status != "Not Working":
        raise HTTPException(status_code=404, detail="No active issue")

    # Get latest inspection for details only
    latest = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine.id
    ).order_by(models.MachineInspection.created_at.desc()).first()

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

    return {
        "status": True,
        "data": {
            "machine_id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "remarks": latest.remarks if latest else "",
            "reported_at": latest.created_at if latest else None,
            "ot_name": ot_name
        }
    }



@app.post("/api/issues/resolve/{machine_id}")
def resolve_issue(
    machine_id: int,
    creator_id: int,
    maintenance_notes: str = None,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id,
        models.Machine.hospital_id == user.hospital_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    latest = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id
    ).order_by(models.MachineInspection.created_at.desc()).first()

    if not latest or latest.status != "Not Working":
        return {
            "status": False,
            "message": "No active issue"
        }

    # Update machine
    machine.status = "Working"
    machine.last_checked = datetime.utcnow()

    # Insert resolved record
    inspection = models.MachineInspection(
        machine_id=machine_id,
        user_id=user.id,
        status="Resolved",
        remarks=maintenance_notes,
        priority=None,
        created_at=datetime.utcnow()
    )

    db.add(inspection)
    db.commit()

    return {
        "status": True,
        "message": "Issue resolved successfully"
    }


@app.get("/api/history/machines")
def get_bmet_history(creator_id: int, db: Session = Depends(get_db)):

    creator = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not creator:
        raise HTTPException(status_code=403, detail="Access denied")

    inspections = db.query(models.MachineInspection)\
        .join(models.Machine, models.Machine.id == models.MachineInspection.machine_id)\
        .filter(
            models.Machine.hospital_id == creator.hospital_id,
            models.MachineInspection.status == "Resolved",
            models.MachineInspection.user_id == creator.id
        )\
        .order_by(models.MachineInspection.created_at.desc())\
        .all()

    result = []

    for insp in inspections:
        machine = db.query(models.Machine)\
            .filter(models.Machine.id == insp.machine_id)\
            .first()

        if machine:
            result.append({
                "machine_id": machine.id,
                "machine_name": machine.machine_name,
                "serial_number": machine.serial_number,
                "resolved_at": insp.created_at
            })

    return {
        "status": True,
        "data": result
    }

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from datetime import datetime, date

from sqlalchemy import func

@app.get("/api/dashboard/at/{user_id}")
def get_at_dashboard(user_id: int, db: Session = Depends(get_db)):

    # Validate AT
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "AT",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid AT user")

    # Get assigned OTs
    assignments = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id
    ).all()

    if not assignments:
        return {"status": True, "checked": 0, "issues": 0, "pending": 0}

    ot_ids = [a.ot_id for a in assignments]

    # Get machine IDs in those OTs
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = list(set([m[0] for m in machine_ids]))

    if not machine_ids:
        return {"status": True, "checked": 0, "issues": 0, "pending": 0}

    today_start = datetime.combine(date.today(), datetime.min.time())

    # Machines inspected TODAY by this AT
    inspected_today_ids = db.query(
        models.MachineInspection.machine_id
    ).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.user_id == user_id,
        models.MachineInspection.created_at >= today_start
    ).distinct().all()

    inspected_today_ids = [m[0] for m in inspected_today_ids]

    checked = len(inspected_today_ids)

    # Issues = machines currently Not Working
    issues = db.query(func.count(models.Machine.id)).filter(
        models.Machine.id.in_(machine_ids),
        models.Machine.status == "Not Working"
    ).scalar()

    # Pending = machines NOT inspected today
    pending = len(machine_ids) - checked

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

    # Validate AT
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "AT",
        models.User.status == 1
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Invalid AT user")

    # Get reset time
    settings = db.query(models.ChecklistSettings).filter(
        models.ChecklistSettings.hospital_id == user.hospital_id
    ).first()

    if not settings:
        raise HTTPException(status_code=400, detail="Reset time not configured")

    reset_time = settings.reset_time
    now = datetime.now()
    reset_datetime_today = datetime.combine(date.today(), reset_time)

    if now < reset_datetime_today:
        checklist_date = date.today() - timedelta(days=1)
    else:
        checklist_date = date.today()

    # Get assigned OTs
    query = db.query(models.OTAssignment).filter(
        models.OTAssignment.user_id == user_id
    )
    
    if ot_id:
        query = query.filter(models.OTAssignment.ot_id == ot_id)
        
    assignments = query.all()

    ot_ids = [a.ot_id for a in assignments]

    if not ot_ids:
        return {"status": True, "pending": [], "completed": []}

    # Get machine IDs
    machine_ids = db.query(models.OTMachineAssignment.machine_id).filter(
        models.OTMachineAssignment.ot_id.in_(ot_ids)
    ).all()

    machine_ids = list(set([m[0] for m in machine_ids]))

    machines = db.query(models.Machine).filter(
        models.Machine.id.in_(machine_ids)
    ).all()

    # Completed today
    completed_ids = db.query(models.MachineInspection.machine_id).filter(
        models.MachineInspection.machine_id.in_(machine_ids),
        models.MachineInspection.check_date == checklist_date
    ).distinct().all()

    completed_ids = [m[0] for m in completed_ids]

    pending = []
    completed = []

    for machine in machines:

        machine_data = {
            "id": machine.id,
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "status": machine.status,
            "last_checked": machine.last_checked
        }

        if machine.id in completed_ids:
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

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/api/inspection/details/{machine_id}")
def get_inspection_details(
    machine_id: int,
    creator_id: int,
    db: Session = Depends(get_db)
):

    user = db.query(models.User).filter(
        models.User.id == creator_id
    ).first()

    if not user:
        raise HTTPException(status_code=403, detail="Access denied")

    machine = db.query(models.Machine).filter(
        models.Machine.id == machine_id
    ).first()

    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    inspections = db.query(models.MachineInspection).filter(
        models.MachineInspection.machine_id == machine_id
    ).order_by(models.MachineInspection.created_at.asc()).all()

    lifecycle = []
    issues = []

    checklist_event = None
    issue_event = None
    resolved_event = None

    for i in inspections:

        inspector = db.query(models.User).filter(
            models.User.id == i.user_id
        ).first()

        inspector_name = inspector.name if inspector else ""

        if i.status == "Working":

            checklist_event = {
                "event": "Checklist Completed",
                "time": i.created_at,
                "checked_by": inspector_name
            }

        elif i.status == "Not Working":

            issue_event = {
                "event": "Issue Reported",
                "time": i.created_at,
                "remarks": i.remarks
            }

            issues.append({
                "title": i.remarks if i.remarks else "Issue reported",
                "description": i.remarks if i.remarks else ""
            })

        elif i.status == "Resolved":

            resolved_event = {
                "event": "Resolved",
                "time": i.created_at,
                "resolved_by": inspector_name,
                "resolution_notes": i.remarks
            }

    # Always show checklist
    if checklist_event:
        lifecycle.append(checklist_event)

    # Only show issue if machine currently not working
    if machine.status == "Not Working" and issue_event:
        lifecycle.append(issue_event)

    # Show full lifecycle if resolved
    if resolved_event:
        lifecycle.append(issue_event)
        lifecycle.append(resolved_event)

    # If machine working → clear issues
    if machine.status == "Working":
        issues = []

    return {
        "status": True,
        "data": {
            "machine_name": machine.machine_name,
            "serial_number": machine.serial_number,
            "machine_status": machine.status,
            "lifecycle": lifecycle,
            "issues": issues
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

    inspections = db.query(models.MachineInspection)\
        .order_by(models.MachineInspection.created_at.desc())\
        .limit(200)\
        .all()

    data = []

    for insp in inspections:

        machine = db.query(models.Machine).filter(
            models.Machine.id == insp.machine_id
        ).first()

        if not machine:
            continue

        if machine.hospital_id != creator.hospital_id:
            continue

        user = db.query(models.User).filter(
            models.User.id == insp.user_id
        ).first()

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

        data.append({
    "machine_id": machine.id,
    "machine_name": machine.machine_name,
    "serial_number": machine.serial_number,
    "status": insp.status,
    "remarks": insp.remarks,
    "priority": insp.priority,
    "checked_by": user.name if user else "",
    "role": user.role if user else "",
    "date": insp.created_at,
    "ot_name": ot_name
})

    return {
        "status": True,
        "total": len(data),
        "data": data
    }