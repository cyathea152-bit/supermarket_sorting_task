import types_pb2 as _types_pb2
import arm_control_pb2 as _arm_control_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MotionGoal(_message.Message):
    __slots__ = ("action_id", "target_pose", "speed_scale", "allow_approximate_solution", "ignore_j6")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_POSE_FIELD_NUMBER: _ClassVar[int]
    SPEED_SCALE_FIELD_NUMBER: _ClassVar[int]
    ALLOW_APPROXIMATE_SOLUTION_FIELD_NUMBER: _ClassVar[int]
    IGNORE_J6_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    target_pose: _types_pb2.Pose
    speed_scale: float
    allow_approximate_solution: bool
    ignore_j6: bool
    def __init__(self, action_id: _Optional[str] = ..., target_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., speed_scale: _Optional[float] = ..., allow_approximate_solution: bool = ..., ignore_j6: bool = ...) -> None: ...

class MotionFeedback(_message.Message):
    __slots__ = ("action_id", "progress_percent", "distance_to_goal", "current_step", "total_steps", "state")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_PERCENT_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_TO_GOAL_FIELD_NUMBER: _ClassVar[int]
    CURRENT_STEP_FIELD_NUMBER: _ClassVar[int]
    TOTAL_STEPS_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    progress_percent: float
    distance_to_goal: float
    current_step: int
    total_steps: int
    state: str
    def __init__(self, action_id: _Optional[str] = ..., progress_percent: _Optional[float] = ..., distance_to_goal: _Optional[float] = ..., current_step: _Optional[int] = ..., total_steps: _Optional[int] = ..., state: _Optional[str] = ...) -> None: ...

class MotionResult(_message.Message):
    __slots__ = ("action_id", "status", "message", "execution_duration")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_DURATION_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    status: _arm_control_pb2.CommandResult
    message: str
    execution_duration: float
    def __init__(self, action_id: _Optional[str] = ..., status: _Optional[_Union[_arm_control_pb2.CommandResult, str]] = ..., message: _Optional[str] = ..., execution_duration: _Optional[float] = ...) -> None: ...

class GraspGoal(_message.Message):
    __slots__ = ("action_id", "mask_pc", "place_pose", "initial_approach_pose", "retract_pose", "approach_dist", "retract_dist", "hover_dist", "max_attempt")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    MASK_PC_FIELD_NUMBER: _ClassVar[int]
    PLACE_POSE_FIELD_NUMBER: _ClassVar[int]
    INITIAL_APPROACH_POSE_FIELD_NUMBER: _ClassVar[int]
    RETRACT_POSE_FIELD_NUMBER: _ClassVar[int]
    APPROACH_DIST_FIELD_NUMBER: _ClassVar[int]
    RETRACT_DIST_FIELD_NUMBER: _ClassVar[int]
    HOVER_DIST_FIELD_NUMBER: _ClassVar[int]
    MAX_ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    mask_pc: bytes
    place_pose: _types_pb2.Pose
    initial_approach_pose: _types_pb2.Pose
    retract_pose: _types_pb2.Pose
    approach_dist: float
    retract_dist: float
    hover_dist: float
    max_attempt: int
    def __init__(self, action_id: _Optional[str] = ..., mask_pc: _Optional[bytes] = ..., place_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., initial_approach_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., retract_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., approach_dist: _Optional[float] = ..., retract_dist: _Optional[float] = ..., hover_dist: _Optional[float] = ..., max_attempt: _Optional[int] = ...) -> None: ...

class GraspFeedback(_message.Message):
    __slots__ = ("action_id", "stage", "raw_candidates", "valid_candidates", "status_message")
    class GraspStage(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        IDLE: _ClassVar[GraspFeedback.GraspStage]
        GENERATING_GRASPS: _ClassVar[GraspFeedback.GraspStage]
        FILTERING_GRASPS: _ClassVar[GraspFeedback.GraspStage]
        PLANNING_GRASPS: _ClassVar[GraspFeedback.GraspStage]
        APPROACHING: _ClassVar[GraspFeedback.GraspStage]
        GRIPPING: _ClassVar[GraspFeedback.GraspStage]
        LIFTING: _ClassVar[GraspFeedback.GraspStage]
        RETRACTING: _ClassVar[GraspFeedback.GraspStage]
        PLACING: _ClassVar[GraspFeedback.GraspStage]
        RESETING: _ClassVar[GraspFeedback.GraspStage]
    IDLE: GraspFeedback.GraspStage
    GENERATING_GRASPS: GraspFeedback.GraspStage
    FILTERING_GRASPS: GraspFeedback.GraspStage
    PLANNING_GRASPS: GraspFeedback.GraspStage
    APPROACHING: GraspFeedback.GraspStage
    GRIPPING: GraspFeedback.GraspStage
    LIFTING: GraspFeedback.GraspStage
    RETRACTING: GraspFeedback.GraspStage
    PLACING: GraspFeedback.GraspStage
    RESETING: GraspFeedback.GraspStage
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    STAGE_FIELD_NUMBER: _ClassVar[int]
    RAW_CANDIDATES_FIELD_NUMBER: _ClassVar[int]
    VALID_CANDIDATES_FIELD_NUMBER: _ClassVar[int]
    STATUS_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    stage: GraspFeedback.GraspStage
    raw_candidates: _containers.RepeatedCompositeFieldContainer[_types_pb2.Pose]
    valid_candidates: _containers.RepeatedCompositeFieldContainer[_types_pb2.Pose]
    status_message: str
    def __init__(self, action_id: _Optional[str] = ..., stage: _Optional[_Union[GraspFeedback.GraspStage, str]] = ..., raw_candidates: _Optional[_Iterable[_Union[_types_pb2.Pose, _Mapping]]] = ..., valid_candidates: _Optional[_Iterable[_Union[_types_pb2.Pose, _Mapping]]] = ..., status_message: _Optional[str] = ...) -> None: ...

class GraspResult(_message.Message):
    __slots__ = ("action_id", "status", "executed_grasp_pose", "message")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    EXECUTED_GRASP_POSE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    status: _arm_control_pb2.CommandResult
    executed_grasp_pose: _types_pb2.Pose
    message: str
    def __init__(self, action_id: _Optional[str] = ..., status: _Optional[_Union[_arm_control_pb2.CommandResult, str]] = ..., executed_grasp_pose: _Optional[_Union[_types_pb2.Pose, _Mapping]] = ..., message: _Optional[str] = ...) -> None: ...
