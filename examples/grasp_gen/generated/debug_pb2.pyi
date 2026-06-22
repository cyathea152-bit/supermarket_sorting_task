from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DebugPose(_message.Message):
    __slots__ = ("x", "y", "z", "qw", "qx", "qy", "qz")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    QW_FIELD_NUMBER: _ClassVar[int]
    QX_FIELD_NUMBER: _ClassVar[int]
    QY_FIELD_NUMBER: _ClassVar[int]
    QZ_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    qw: float
    qx: float
    qy: float
    qz: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ..., qw: _Optional[float] = ..., qx: _Optional[float] = ..., qy: _Optional[float] = ..., qz: _Optional[float] = ...) -> None: ...

class DebugGraspList(_message.Message):
    __slots__ = ("action_id", "grasps")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    GRASPS_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    grasps: _containers.RepeatedCompositeFieldContainer[DebugPose]
    def __init__(self, action_id: _Optional[str] = ..., grasps: _Optional[_Iterable[_Union[DebugPose, _Mapping]]] = ...) -> None: ...

class DebugTrajectory(_message.Message):
    __slots__ = ("flat_points", "dof", "steps")
    FLAT_POINTS_FIELD_NUMBER: _ClassVar[int]
    DOF_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    flat_points: _containers.RepeatedScalarFieldContainer[float]
    dof: int
    steps: int
    def __init__(self, flat_points: _Optional[_Iterable[float]] = ..., dof: _Optional[int] = ..., steps: _Optional[int] = ...) -> None: ...

class DebugPlanList(_message.Message):
    __slots__ = ("action_id", "plans")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    PLANS_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    plans: _containers.RepeatedCompositeFieldContainer[DebugTrajectory]
    def __init__(self, action_id: _Optional[str] = ..., plans: _Optional[_Iterable[_Union[DebugTrajectory, _Mapping]]] = ...) -> None: ...
