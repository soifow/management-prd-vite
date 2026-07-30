"""WebApi - PyWebView JS 桥接层。

将 Python 后端能力通过 :class:`webview.Window` 的 ``js_api`` 暴露给前端
Vue/Element Plus UI。**所有方法返回值必须是 JSON 可序列化的**（pydantic 模型
调用 ``.model_dump(mode="json")``）。

错误处理约定：
    成功 -> 返回业务数据（dict / list / str / None / bool）
    失败 -> 返回 ``{"success": False, "error": "msg"}`` 统一错误信封

对话框方法（``pick_and_parse_import`` / ``export_project``）需要 ``webview.Window``，
由 :func:`app.run` 在 :func:`webview.create_window` 之后调用
:func:`set_window` 注入。
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import webview

from management_prd.errors import (
    ExportError,
    ManagementPrdError,
    NotFoundError,
    StorageError,
)
from management_prd.models.data import (
    CreateRequirementInput,
    ParsedImport,
    ProjectSummary,
    UpdateRequirementInput,
)
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.services.bootstrap_service import BootstrapService
from management_prd.services.db_service import DbService
from management_prd.services.importer import parse_import
from management_prd.services.project_service import ProjectService
from management_prd.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


def _err(exc: Exception) -> dict[str, object]:
    """构造统一错误信封。"""
    return {"success": False, "error": str(exc)}


class WebApi:
    """暴露给前端的全部方法集合（PyWebView ``js_api``）。"""

    def __init__(
        self,
        project_service: ProjectService | None = None,
        settings_service: SettingsService | None = None,
        bootstrap: BootstrapService | None = None,
    ) -> None:
        if project_service is None:
            db = self._default_db()
            project_service = ProjectService(db)
            if bootstrap is None:
                bootstrap = db.bootstrap
        self._project_service = project_service
        self._settings_service = settings_service or SettingsService(bootstrap)
        self._window: webview.Window | None = None

    @staticmethod
    def _default_db() -> DbService:
        return DbService()

    # ---------- 窗口注入 ----------

    def set_window(self, window: webview.Window) -> None:
        """注入 webview 窗口引用，供对话框方法使用。"""
        self._window = window

    # ---------- 项目 ----------

    def list_projects(self) -> object:
        try:
            settings = self._settings_service.load()
            summaries: list[ProjectSummary] = self._project_service.list_summaries(
                date_mode=settings.project_list_date_mode,
            )
            return [s.model_dump(mode="json") for s in summaries]
        except Exception as exc:
            return _err(exc)

    def get_project(self, project_id: str) -> object:
        try:
            project = self._project_service.get(project_id)
            return project.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def create_project(self, name: str) -> object:
        try:
            summary = self._project_service.create_project(name)
            return summary.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def rename_project(self, project_id: str, name: str) -> object:
        try:
            settings = self._settings_service.load()
            summary = self._project_service.rename_project(
                project_id, name, date_mode=settings.project_list_date_mode
            )
            return summary.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def delete_project(self, project_id: str) -> object:
        try:
            return self._project_service.delete_project(project_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def list_modules(self, project_id: str) -> object:
        try:
            return self._project_service.list_modules(project_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def list_features(self, project_id: str, module: str) -> object:
        try:
            return self._project_service.list_features(project_id, module)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def list_iterations(self, project_id: str, module: str, feature: str) -> object:
        try:
            iters = self._project_service.list_iterations(project_id, module, feature)
            return [it.model_dump(mode="json") for it in iters]
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- 需求 ----------

    def create_requirement(self, project_id: str, input_dict: dict[str, object]) -> object:
        try:
            input_ = self._coerce_create_input(input_dict)
            item: RequirementItem = self._project_service.create_requirement(project_id, input_)
            return item.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def update_requirement(self, item_id: str, patch: dict[str, object]) -> object:
        try:
            input_ = self._coerce_update_input(patch)
            item = self._project_service.update_requirement(item_id, input_)
            return item.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def set_requirement_status(self, item_id: str, status: str) -> object:
        try:
            rs = RequirementStatus(status)
            item = self._project_service.set_status(item_id, rs)
            return item.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def delete_requirement(self, item_id: str) -> object:
        try:
            return self._project_service.delete_requirement(item_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- 待办提醒 ----------

    def get_todo_reminders(self) -> object:
        """跨项目返回待办提醒列表（按剩余天数排序、已逾期置顶、暂缓末尾）。

        阈值与「无时限常驻」开关取自设置，后端单点过滤/排序；前端按返回的
        ``bucket``/``remaining_days`` 分组渲染。
        """
        try:
            settings = self._settings_service.load()
            return self._project_service.list_todo_reminders(
                threshold_days=settings.reminder_threshold_days,
                show_no_deadline=settings.show_no_deadline_in_todo,
            )
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- 导入/导出 ----------

    def pick_and_parse_import(self) -> object:
        """弹打开文件框，解析为 ParsedRequirement 列表。取消返回 None。

        返回 ``{"requirements": [...], "filename": "xxx"}`` 以便前端用文件名推测项目名。
        """
        try:
            picked = self._open_text_file()
            if not picked:
                return None
            path = Path(picked)
            text = path.read_text(encoding="utf-8")
            parsed: ParsedImport = parse_import(text)
            filename_stem = path.stem
            return {
                "requirements": [r.model_dump(mode="json") for r in parsed.requirements],
                "filename": filename_stem,
            }
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def apply_import(self, project_id: str, requirements: list[dict[str, object]]) -> object:
        """应用导入预览结果。"""
        try:
            from management_prd.models.data import ParsedRequirement

            parsed_reqs = [ParsedRequirement.model_validate(r) for r in requirements]
            project = self._project_service.apply_import(project_id, parsed_reqs)
            return project.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def apply_import_as_new_project(
        self, name: str, requirements: list[dict[str, object]]
    ) -> object:
        """新建项目并导入需求（项目名取自导入文件名）。"""
        try:
            from management_prd.models.data import ParsedRequirement

            parsed_reqs = [ParsedRequirement.model_validate(r) for r in requirements]
            project = self._project_service.apply_import_as_new_project(name, parsed_reqs)
            return project.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def export_project(self, project_id: str) -> object:
        """导出项目为 .txt 文件（弹保存对话框）。"""
        try:
            project = self._project_service.get(project_id)
            from management_prd.services.exporter import Exporter

            exporter = Exporter()
            content = exporter.export(project)
            suggested = exporter.suggested_filename(project)
            picked = self._save_dialog(suggested)
            if not picked:
                return None
            target = Path(picked)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info("需求已导出: %s", target)
            return str(target)
        except (ExportError, NotFoundError, StorageError, ValueError) as exc:
            return _err(exc)

    # ---------- 存储位置 ----------

    def get_storage_info(self) -> object:
        """返回当前存储目录信息。"""
        try:
            return self._project_service.get_storage_info()
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def pick_storage_dir(self) -> object:
        """弹文件夹选择对话框，返回所选路径或 None。"""
        try:
            return self._open_folder_dialog()
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def migrate_storage(self, new_dir: str) -> object:
        """迁移存储目录：在 new_dir 下创建 management-prd-storage 子目录并迁入。

        ``new_dir`` 为用户选定的目录（父目录）；实际数据落入其下的
        ``management-prd-storage`` 专属子目录，与所选目录内其他文件隔离。
        """
        try:
            return self._project_service.migrate_storage_dir(new_dir)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- 设置 ----------

    def get_settings(self) -> object:
        """返回应用设置（落盘在 storage_dir/settings.json）。"""
        try:
            return self._settings_service.get_settings_dict()
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def update_settings(self, patch: dict[str, object]) -> object:
        """部分更新设置并落盘。非法值返回错误信封。"""
        try:
            settings = self._settings_service.update_settings(patch)
            return settings.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- 内部工具 ----------

    @staticmethod
    def _coerce_create_input(d: dict[str, object]) -> CreateRequirementInput:
        """把前端传入的 dict 转换为 CreateRequirementInput。"""
        module = d.get("module", "")
        feature = d.get("feature", "")
        content = d.get("content", "")
        if not isinstance(module, str) or not isinstance(content, str):
            raise ValueError("module/content 必须是字符串")
        if not isinstance(feature, str):
            raise ValueError("feature 必须是字符串")
        status_raw = d.get("status", RequirementStatus.TODO.value)
        if not isinstance(status_raw, str):
            raise ValueError("status 必须是字符串")
        status = RequirementStatus(status_raw)
        date_raw = d.get("date")
        if not isinstance(date_raw, str) or not date_raw:
            raise ValueError("date 必填")
        d_val = date.fromisoformat(date_raw)
        deadline_raw = d.get("completion_deadline")
        completion_deadline: date | None = None
        if isinstance(deadline_raw, str) and deadline_raw:
            completion_deadline = date.fromisoformat(deadline_raw)
        return CreateRequirementInput(
            module=module,
            feature=feature,
            content=content,
            status=status,
            date=d_val,
            completion_deadline=completion_deadline,
        )

    @staticmethod
    def _coerce_update_input(d: dict[str, object]) -> UpdateRequirementInput:
        """把前端传入的 dict 转换为 UpdateRequirementInput。"""
        module = d.get("module")
        feature = d.get("feature")
        content = d.get("content")
        status = d.get("status")
        date_raw = d.get("date")
        rs: RequirementStatus | None = None
        if status is not None:
            if not isinstance(status, str):
                raise ValueError("status 必须是字符串")
            rs = RequirementStatus(status)
        d_val: date | None = None
        if date_raw is not None:
            if not isinstance(date_raw, str) or not date_raw:
                raise ValueError("date 必须为非空字符串")
            d_val = date.fromisoformat(date_raw)
        deadline_raw = d.get("completion_deadline")
        cd: date | None = None
        if isinstance(deadline_raw, str) and deadline_raw:
            cd = date.fromisoformat(deadline_raw)
        clear_deadline = bool(d.get("clear_completion_deadline", False))
        return UpdateRequirementInput(
            module=module if isinstance(module, str) else None,
            feature=feature if isinstance(feature, str) else None,
            content=content if isinstance(content, str) else None,
            status=rs,
            date=d_val,
            completion_deadline=cd,
            clear_completion_deadline=clear_deadline,
        )

    def _open_text_file(self) -> str | None:
        """调用 webview 打开文件对话框，返回所选路径或 None。"""
        if self._window is None:
            raise ManagementPrdError("WebApi 窗口未注入，无法弹对话框")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=["文本文件 (*.txt)", "所有文件 (*.*)"],
        )
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    def _save_dialog(self, suggested: str) -> str | None:
        """调用 webview 保存文件对话框，返回所选路径或 None。"""
        if self._window is None:
            raise ManagementPrdError("WebApi 窗口未注入，无法弹对话框")
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested,
            file_types=["文本文件 (*.txt)", "所有文件 (*.*)"],
        )
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    def _open_folder_dialog(self) -> str | None:
        """调用 webview 文件夹选择对话框，返回所选目录或 None。"""
        if self._window is None:
            raise ManagementPrdError("WebApi 窗口未注入，无法弹对话框")
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)
