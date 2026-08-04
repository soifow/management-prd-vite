"""自定义异常类。

所有项目内的业务异常统一继承自 :class:`ManagementPrdError`。
"""

from __future__ import annotations


class ManagementPrdError(Exception):
    """项目基础异常类。"""


class StorageError(ManagementPrdError):
    """存储读写错误。"""


class NotFoundError(ManagementPrdError):
    """资源未找到（项目/需求不存在）。"""


class ImportParseError(ManagementPrdError):
    """导入解析错误。"""


class ExportError(ManagementPrdError):
    """导出序列化错误。"""


class ImportFormatError(ManagementPrdError):
    """导入格式错误（format_version 不兼容等）。"""


class LlmError(ManagementPrdError):
    """LLM 调用错误。"""


class BackupError(ManagementPrdError):
    """备份/回滚操作错误。"""
