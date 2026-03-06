from pydantic import BaseModel, EmailStr
from typing import Optional, List


class HMRegisterRequest(BaseModel):
    hospital_name: str
    hospital_email: EmailStr
    hm_name: str
    hm_email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    employee_id: str


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

class ResetTimeRequest(BaseModel):
    reset_time: str

class UpdateMachineRequest(BaseModel):
    machine_name: str
    machine_type_id: int
    serial_number: str

class UpdateUserRequest(BaseModel):
    user_id: int
    name: str
    email: EmailStr
