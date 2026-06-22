import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GripperStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[GripperStatus]
    IDLE: _ClassVar[GripperStatus]
    MOVING: _ClassVar[GripperStatus]
    GRIPPING: _ClassVar[GripperStatus]
    ERROR: _ClassVar[GripperStatus]

class CommandType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NO_COMMAND: _ClassVar[CommandType]
    OPEN: _ClassVar[CommandType]
    CLOSE: _ClassVar[CommandType]
    WAIT_OPEN: _ClassVar[CommandType]
    WAIT_CLOSE: _ClassVar[CommandType]
    SET_POSITION: _ClassVar[CommandType]

class CommandResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN_RESULT: _ClassVar[CommandResult]
    SUCCESS: _ClassVar[CommandResult]
    FAILED: _ClassVar[CommandResult]
    TIMEOUT: _ClassVar[CommandResult]
    REJECTED: _ClassVar[CommandResult]
    DISCONNECTED: _ClassVar[CommandResult]
    IN_PROGRESS: _ClassVar[CommandResult]
UNKNOWN: GripperStatus
IDLE: GripperStatus
MOVING: GripperStatus
GRIPPING: GripperStatus
ERROR: GripperStatus
NO_COMMAND: CommandType
OPEN: CommandType
CLOSE: CommandType
WAIT_OPEN: CommandType
WAIT_CLOSE: CommandType
SET_POSITION: CommandType
UNKNOWN_RESULT: CommandResult
SUCCESS: CommandResult
FAILED: CommandResult
TIMEOUT: CommandResult
REJECTED: CommandResult
DISCONNECTED: CommandResult
IN_PROGRESS: CommandResult

class Gripper2FState(_message.Message):
    __slots__ = ("id", "status", "position", "finger_force", "timestamp")
    ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    FINGER_FORCE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    id: str
    status: GripperStatus
    position: float
    finger_force: float
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., status: _Optional[_Union[GripperStatus, str]] = ..., position: _Optional[float] = ..., finger_force: _Optional[float] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ClosePositionControl(_message.Message):
    __slots__ = ("position",)
    POSITION_FIELD_NUMBER: _ClassVar[int]
    position: float
    def __init__(self, position: _Optional[float] = ...) -> None: ...

class CloseJointControl(_message.Message):
    __slots__ = ("joint_angle",)
    JOINT_ANGLE_FIELD_NUMBER: _ClassVar[int]
    joint_angle: float
    def __init__(self, joint_angle: _Optional[float] = ...) -> None: ...

class CloseForceControl(_message.Message):
    __slots__ = ("force",)
    FORCE_FIELD_NUMBER: _ClassVar[int]
    force: float
    def __init__(self, force: _Optional[float] = ...) -> None: ...
