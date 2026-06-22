import datetime

import types_pb2 as _types_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ImuData(_message.Message):
    __slots__ = ("acc", "gyro", "timestamp")
    ACC_FIELD_NUMBER: _ClassVar[int]
    GYRO_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    acc: _types_pb2.Vector3
    gyro: _types_pb2.Vector3
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, acc: _Optional[_Union[_types_pb2.Vector3, _Mapping]] = ..., gyro: _Optional[_Union[_types_pb2.Vector3, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
