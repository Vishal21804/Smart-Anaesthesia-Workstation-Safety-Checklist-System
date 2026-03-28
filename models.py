from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Time, Text, Boolean, Date
from sqlalchemy.sql import func
from database import Base
from datetime import datetime
from sqlalchemy import DateTime
from sqlalchemy import Column, Integer, String, Time


# ================= HOSPITAL =================
class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    hospital_name = Column(String(150), nullable=False)
    hospital_email = Column(String(150), unique=True)
    created_at = Column(DateTime, server_default=func.now())
    network_restriction = Column(Boolean, default=False)


# ================= USER =================
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func

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
    dob = Column(Date, nullable=True)
    status = Column(Integer, default=1)
    created_by = Column(Integer)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    force_password_change = Column(Boolean, default=True)

    # 🔥 OTP SYSTEM (FIXED)
    otp = Column(String, nullable=True)
    otp_expiry = Column(DateTime, nullable=True)

    # OTHER
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
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

# ================= MACHINE TYPE =================
class MachineType(Base):
    __tablename__ = "machine_types"

    id = Column(Integer, primary_key=True, index=True)
    type_name = Column(String(100), unique=True, nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))



# ================= OT ASSIGNMENT =================
class OTAssignment(Base):
    __tablename__ = "ot_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ot_id = Column(Integer, ForeignKey("ot_rooms.id"), nullable=False, unique=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())
    is_active = Column(Boolean, default=True)

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

    template_id = Column(Integer, ForeignKey("machine_templates.id"))

    serial_number = Column(String(100), unique=True, nullable=False)

    status = Column(String(50), default="Working")

    last_checked = Column(DateTime, nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"))

    created_at = Column(DateTime, server_default=func.now())


class MachineInspection(Base):
    __tablename__ = "machine_inspections"

    id = Column(Integer, primary_key=True, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(50))
    remarks = Column(Text)
    priority = Column(String(20))
    check_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChecklistSettings(Base):
    __tablename__ = "checklist_settings"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer)
    reset_time = Column(Time)
    default_at_password = Column(String(255))
    default_bmet_password = Column(String(255))

class MachineTemplate(Base):
    __tablename__ = "machine_templates"

    id = Column(Integer, primary_key=True, index=True)
    machine_name = Column(String(100), nullable=False)
    machine_type_id = Column(Integer, ForeignKey("machine_types.id"))
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    created_at = Column(DateTime, server_default=func.now())

class UserPermission(Base):
    __tablename__ = "user_permissions"

    id = Column(Integer, primary_key=True)
    hospital_id = Column(Integer)
    role = Column(String)
    default_password = Column(String)

class AllowedNetwork(Base):
    __tablename__ = "allowed_networks"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer)
    ssid = Column(String(100))      # ✅ FIXED
    domain = Column(String(255), nullable=True)  # ✅ FIXED


    # models.py

# models.py

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base

class TempUser(Base):
    __tablename__ = "temp_users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    hospital_name = Column(String, nullable=False)
    otp = Column(String(6), nullable=True)  # ✅ FIXED
    otp_expiry = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())