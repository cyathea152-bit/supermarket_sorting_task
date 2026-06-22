import arm_control_pb2 as _arm_control_pb2
import gripper_2f_pb2 as _gripper_2f_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CommandRequest(_message.Message):
    __slots__ = ("header_id", "wait_for_completion", "arm_command_type", "gripper_command_type", "move_l_target", "move_j_target", "close_force_control", "close_position_control", "close_joint_control")
    HEADER_ID_FIELD_NUMBER: _ClassVar[int]
    WAIT_FOR_COMPLETION_FIELD_NUMBER: _ClassVar[int]
    ARM_COMMAND_TYPE_FIELD_NUMBER: _ClassVar[int]
    GRIPPER_COMMAND_TYPE_FIELD_NUMBER: _ClassVar[int]
    MOVE_L_TARGET_FIELD_NUMBER: _ClassVar[int]
    MOVE_J_TARGET_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FORCE_CONTROL_FIELD_NUMBER: _ClassVar[int]
    CLOSE_POSITION_CONTROL_FIELD_NUMBER: _ClassVar[int]
    CLOSE_JOINT_CONTROL_FIELD_NUMBER: _ClassVar[int]
    header_id: str
    wait_for_completion: bool
    arm_command_type: _arm_control_pb2.CommandType
    gripper_command_type: _gripper_2f_pb2.CommandType
    move_l_target: _arm_control_pb2.MoveLParams
    move_j_target: _arm_control_pb2.MoveJParams
    close_force_control: _gripper_2f_pb2.CloseForceControl
    close_position_control: _gripper_2f_pb2.ClosePositionControl
    close_joint_control: _gripper_2f_pb2.CloseJointControl
    def __init__(self, header_id: _Optional[str] = ..., wait_for_completion: bool = ..., arm_command_type: _Optional[_Union[_arm_control_pb2.CommandType, str]] = ..., gripper_command_type: _Optional[_Union[_gripper_2f_pb2.CommandType, str]] = ..., move_l_target: _Optional[_Union[_arm_control_pb2.MoveLParams, _Mapping]] = ..., move_j_target: _Optional[_Union[_arm_control_pb2.MoveJParams, _Mapping]] = ..., close_force_control: _Optional[_Union[_gripper_2f_pb2.CloseForceControl, _Mapping]] = ..., close_position_control: _Optional[_Union[_gripper_2f_pb2.ClosePositionControl, _Mapping]] = ..., close_joint_control: _Optional[_Union[_gripper_2f_pb2.CloseJointControl, _Mapping]] = ...) -> None: ...

class CommandResponse(_message.Message):
    __slots__ = ("header_id", "arm_result", "gripper_result")
    HEADER_ID_FIELD_NUMBER: _ClassVar[int]
    ARM_RESULT_FIELD_NUMBER: _ClassVar[int]
    GRIPPER_RESULT_FIELD_NUMBER: _ClassVar[int]
    header_id: str
    arm_result: _arm_control_pb2.CommandResult
    gripper_result: _gripper_2f_pb2.CommandResult
    def __init__(self, header_id: _Optional[str] = ..., arm_result: _Optional[_Union[_arm_control_pb2.CommandResult, str]] = ..., gripper_result: _Optional[_Union[_gripper_2f_pb2.CommandResult, str]] = ...) -> None: ...
