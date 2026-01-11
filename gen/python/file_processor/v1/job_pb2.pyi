from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ProcessFileRequest(_message.Message):
    __slots__ = ["callback_url", "dest_key", "id", "options", "source_key", "type"]
    class OptionsEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CALLBACK_URL_FIELD_NUMBER: _ClassVar[int]
    DEST_KEY_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_KEY_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    callback_url: str
    dest_key: str
    id: str
    options: _containers.ScalarMap[str, str]
    source_key: str
    type: str
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., source_key: _Optional[str] = ..., dest_key: _Optional[str] = ..., options: _Optional[_Mapping[str, str]] = ..., callback_url: _Optional[str] = ...) -> None: ...

class ProcessFileResponse(_message.Message):
    __slots__ = ["dest_key", "duration_ms", "error", "job_id", "success"]
    DEST_KEY_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    dest_key: str
    duration_ms: int
    error: str
    job_id: str
    success: bool
    def __init__(self, job_id: _Optional[str] = ..., success: bool = ..., dest_key: _Optional[str] = ..., error: _Optional[str] = ..., duration_ms: _Optional[int] = ...) -> None: ...
