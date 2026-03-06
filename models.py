from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Time, Text, Boolean, Date
from sqlalchemy.sql import func
from database import Base
from datetime import datetime
from sqlalchemy import DateTime


# ================= HOSPITAL =================
class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    hospital_name = Column(String(150), nullable=False)
    hospital_email = Column(String(150), unique=True)
    created_at = Column(DateTime, server_default=func.now())


# ================= USER =================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    mobile = Column(String(20), nullable=True)
    profile_picture = Column(String(255), nullable=True)
    password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    employee_id = Column(String(30))
    status = Column(Integer, default=1)
    created_by = Column(Integer)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    # NEW COLUMN
    last_login = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


# ================= OT ROOM =================
class OTRoom(Base):
    __tablename__ = "ot_rooms"

    id = Column(Integer, primary_key=True, index=True)
    ot_name = Column(String(100), nullable=False)
    ot_code = Column(String(50), unique=True, nullable=False)
    location = Column(String(150))
    ot_type = Column(String(100), nullable=False)
    machines_assigned = Column(Integer, default=0)
    issues_count = Column(Integer, default=0)
    status = Column(String(20), default="Operational")
    description = Column(Text)

    # 🔴 IMPORTANT: Link OT to hospital
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    created_at = Column(DateTime, server_default=func.now())

# ================= MACHINE TYPE =================
class MachineType(Base):
    __tablename__ = "machine_types"

    id = Column(Integer, primary_key=True, index=True)
    type_name = Column(String(100), unique=True, nullable=False)



# ================= OT ASSIGNMENT =================
class OTAssignment(Base):
    __tablename__ = "ot_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ot_id = Column(Integer, ForeignKey("ot_rooms.id"), nullable=False, unique=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())

# ================= OT MACHINE ASSIGNMENT =================
class OTMachineAssignment(Base):
    __tablename__ = "ot_machine_assignments"

    id = Column(Integer, primary_key=True, index=True)
    ot_id = Column(Integer, ForeignKey("ot_rooms.id"), nullable=False)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())


# ================= MACHINE =================

class Machine(Base):
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, index=True)
    machine_name = Column(String(100))
    serial_number = Column(String(100), nullable=True)
    status = Column(String(50))
    last_checked = Column(DateTime, nullable=True)
    machine_type_id = Column(Integer, ForeignKey("machine_types.id"))
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))

class MachineInspection(Base):
    from sqlalchemy import Date
    check_date = Column(Date, nullable=False)
    __tablename__ = "machine_inspections"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(50))
    remarks = Column(Text)
    priority = Column(String(20))   # 🔥 ADD THIS
    created_at = Column(DateTime, default=datetime.utcnow)

class ChecklistSettings(Base):
    __tablename__ = "checklist_settings"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, unique=True)
    reset_time = Column(Time, nullable=False)
    created_at = Column(DateTime, server_default=func.now())