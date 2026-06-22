import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
import types_pb2 as _types_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ArmStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[ArmStatus]
    READY: _ClassVar[ArmStatus]
    EXECUTING: _ClassVar[ArmStatus]
    ERROR: _ClassVar[ArmStatus]
    NEED_CALIBRATE: _ClassVar[ArmStatus]

class CommandType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN_COMMAND: _ClassVar[CommandType]
    MOVE_L: _ClassVar[CommandType]
    MOVE_J: _ClassVar[CommandType]
    HOME: _ClassVar[CommandType]
    BRAKE: _ClassVar[CommandType]

class CommandResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN_RESULT: _ClassVar[CommandResult]
    SUCCESS: _ClassVar[CommandResult]
    FAILED: _ClassVar[CommandResult]
    TIMEOUT: _ClassVar[CommandResult]
    REJECTED: _ClassVar[CommandResult]
    DISCONNECTED: _ClassVar[CommandResult]
    IN_PROGRESS: _ClassVar[CommandResult]
UNKNOWN: ArmStatus
READY: ArmStatus
EXECUTING: ArmStatus
ERROR: ArmStatus
NEED_CALIBRATE: ArmStatus
UNKNOWN_COMMAND: CommandType
MOVE_L: CommandType
MOVE_J: CommandType
HOME: CommandType
BRAKE: CommandType
UNKNOWN_RESULT: CommandResult
SUCCESS: CommandResult
FAILED: CommandResult
TIMEOUT: CommandResult
REJECTED: CommandResult
DISCONNECTED: CommandResult
IN_PROGRESS: CommandResult

class ArmState(_message.Message):
    __slots__ = ("id", "current_joints", "current_pose", "status", "timestamp")
    ID_FIELD_NUMBER: _ClassVar[int]
    CURRENT_JOINTS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_POSE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    id: str
    current_joints: JointState
    current_pose: _types_pb2.Pose
    status: ArmStatus
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., current_joints: _Optional[_Union[JointState, _Mapping]] = ..., current_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., status: _Optional[_Union[ArmStatus, str]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class JointState(_message.Message):
    __slots__ = ("joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6")
    JOINT_1_FIELD_NUMBER: _ClassVar[int]
    JOINT_2_FIELD_NUMBER: _ClassVar[int]
    JOINT_3_FIELD_NUMBER: _ClassVar[int]
    JOINT_4_FIELD_NUMBER: _ClassVar[int]
    JOINT_5_FIELD_NUMBER: _ClassVar[int]
    JOINT_6_FIELD_NUMBER: _ClassVar[int]
    joint_1: float
    joint_2: float
    joint_3: float
    joint_4: float
    joint_5: float
    joint_6: float
    def __init__(self, joint_1: _Optional[float] = ..., joint_2: _Optional[float] = ..., joint_3: _Optional[float] = ..., joint_4: _Optional[float] = ..., joint_5: _Optional[float] = ..., joint_6: _Optional[float] = ...) -> None: ...

class MoveLParams(_message.Message):
    __slots__ = ("target_pose", "blocking")
    TARGET_POSE_FIELD_NUMBER: _ClassVar[int]
    BLOCKING_FIELD_NUMBER: _ClassVar[int]
    target_pose: _types_pb2.Pose
    blocking: bool
    def __init__(self, target_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., blocking: bool = ...) -> None: ...

class MoveJParams(_message.Message):
    __slots__ = ("target_joints", "blocking")
    TARGET_JOINTS_FIELD_NUMBER: _ClassVar[int]
    BLOCKING_FIELD_NUMBER: _ClassVar[int]
    target_joints: JointState
    blocking: bool
    def __init__(self, target_joints: _Optional[_Union[JointState, _Mapping]] = ..., blocking: bool = ...) -> None: ...
