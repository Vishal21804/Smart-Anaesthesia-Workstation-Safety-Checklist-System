from pydantic import BaseModel, EmailStr
from typing import Optional, List


class HMRegisterRequest(BaseModel):
    hospital_name: str
    hm_name: str
    hm_email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


from datetime import date

class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    employee_id: str
    dob: Optional[date] = None


class UpdateUserStatusRequest(BaseModel):
    user_id: int
    status: int


class GenericResponse(BaseModel):
    status: bool
    message: str


class UserListItem(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: int


class UserListResponse(BaseModel):
    status: bool
    total_users: int
    active_users: int
    disabled_users: int
    users: List[UserListItem]

class OTCreate(BaseModel):
    ot_name: str
    ot_code: str
    location: Optional[str] = None
    ot_type: str
    description: Optional[str] = None


class OTResponse(BaseModel):
    id: int
    ot_name: str
    ot_code: str
    location: Optional[str]
    ot_type: str
    machines_assigned: int
    issues_count: int
    status: str
    
class MachineCreate(BaseModel):
    machine_name: str
    machine_type_id: int


class MachineResponse(BaseModel):
    id: int
    machine_name: str
    serial_number: str
    machine_type: str
    status: str

class AssignOTRequest(BaseModel):
    user_id: int
    ot_id: int

from datetime import time

class ResetTimeRequest(BaseModel):
    reset_time: time


from typing import Optional

class UpdateMachineRequest(BaseModel):
    machine_name: Optional[str] = None
    machine_type_id: Optional[int] = None
    serial_number: Optional[str] = None

from typing import Optional
from datetime import date

class UpdateUserRequest(BaseModel):
    user_id: int
    name: str
    email: EmailStr
    employee_id: Optional[str] = None
    dob: Optional[date] = None   # ✅ ADD THISfrom pydantic import BaseModel
from typing import Optional

class NetworkSaveRequest(BaseModel):
    creator_id: int
    ssid: str
    domain: Optional[str] = None

class HospitalSettingsUpdate(BaseModel):
    hospital_id: int
    reset_time: str
    default_at_password: str
    default_bmet_password: str

class MachineTypeCreate(BaseModel):
    type_name: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str
    confirm_password: str

from pydantic import BaseModel

class AssignMachineToOTRequest(BaseModel):
    machine_id: int
    ot_id: int

    # schemas.py

from pydantic import BaseModel

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class VerifyOTPRequest(BaseModel):
    email: str
    otp: str


from typing import Optional
from pydantic import BaseModel
from datetime import date

class UpdateHMProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    employee_id: Optional[str] = None
    dob: Optional[date] = None