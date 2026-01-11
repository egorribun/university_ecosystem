from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

DESCRIPTOR: _descriptor.FileDescriptor

class ProcessFileRequest(_message.Message):
    __slots__ = ["callback_url", "dest_key", "id", "options", "source_key", "type"]

    class OptionsEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

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
    def __init__(
        self,
        id: str | None = ...,
        type: str | None = ...,
        source_key: str | None = ...,
        dest_key: str | None = ...,
        options: _Mapping[str, str] | None = ...,
        callback_url: str | None = ...,
    ) -> None: ...

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
    def __init__(
        self,
        job_id: str | None = ...,
        success: bool = ...,
        dest_key: str | None = ...,
        error: str | None = ...,
        duration_ms: int | None = ...,
    ) -> None: ...
