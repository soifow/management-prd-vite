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
    LlmError,
    ManagementPrdError,
    NotFoundError,
    StorageError,
)
from management_prd.models.bug import BugLevel, BugStatus, CreateBugInput, UpdateBugInput
from management_prd.models.data import (
    CreateRequirementInput,
    ParsedImport,
    ProjectSummary,
    UpdateRequirementInput,
)
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.models.subitem import CreateSubitemInput, UpdateSubitemInput
from management_prd.services.bootstrap_service import BootstrapService
from management_prd.services.bug_service import BugService
from management_prd.services.db_service import DbService
from management_prd.services.importer import parse_import
from management_prd.services.module_service import ModuleService
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
        bug_service: BugService | None = None,
        settings_service: SettingsService | None = None,
        bootstrap: BootstrapService | None = None,
        module_service: ModuleService | None = None,
    ) -> None:
        if project_service is None:
            db = self._default_db()
            project_service = ProjectService(db)
            if bootstrap is None:
                bootstrap = db.bootstrap
        else:
            # 外部注入 project_service 时需自带 db 以便复用给 bug_service。
            db = project_service._db
        self._project_service = project_service
        self._bug_service = bug_service or BugService(db)
        self._settings_service = settings_service or SettingsService(bootstrap)
        self._module_service = module_service or ModuleService(db)
        self._db = db  # 供头像缓存等直接访问 storage_dir
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
            modules = self._module_service.list_modules(project_id)
            return [m.model_dump(mode="json") for m in modules]
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def create_module(self, project_id: str, name: str) -> object:
        try:
            module = self._project_service.create_module(project_id, name)
            return module.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def delete_module(self, module_id: str) -> object:
        try:
            return self._module_service.delete_module(module_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def list_features(self, project_id: str) -> object:
        try:
            return self._project_service.list_features(project_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def list_iterations(self, project_id: str, feature: str) -> object:
        try:
            iters = self._project_service.list_iterations(project_id, feature)
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

    # ---------- 迭代级子需求 ----------

    def list_subitems(self, iteration_id: str) -> object:
        try:
            subitems = self._project_service.list_subitems(iteration_id)
            return [s.model_dump(mode="json") for s in subitems]
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def create_subitem(self, iteration_id: str, input_dict: dict[str, object]) -> object:
        try:
            input_ = self._coerce_create_subitem_input(iteration_id, input_dict)
            subitem = self._project_service.create_subitem(input_)
            return subitem.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def update_subitem(self, subitem_id: str, patch: dict[str, object]) -> object:
        try:
            input_ = self._coerce_update_subitem_input(patch)
            subitem = self._project_service.update_subitem(subitem_id, input_)
            return subitem.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def set_subitem_status(self, subitem_id: str, status: str) -> object:
        try:
            rs = RequirementStatus(status)
            subitem = self._project_service.set_subitem_status(subitem_id, rs)
            return subitem.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def delete_subitem(self, subitem_id: str) -> object:
        try:
            return self._project_service.delete_subitem(subitem_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- Bug ----------

    def list_bugs(self, project_id: str) -> object:
        try:
            bugs = self._bug_service.list_bugs(project_id)
            return [b.model_dump(mode="json") for b in bugs]
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def create_bug(self, project_id: str, input_dict: dict[str, object]) -> object:
        try:
            input_ = self._coerce_create_bug_input(input_dict)
            bug = self._bug_service.create_bug(project_id, input_)
            return bug.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def update_bug(self, bug_id: str, patch: dict[str, object]) -> object:
        try:
            input_ = self._coerce_update_bug_input(patch)
            bug = self._bug_service.update_bug(bug_id, input_)
            return bug.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def delete_bug(self, bug_id: str) -> object:
        try:
            return self._bug_service.delete_bug(bug_id)
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def set_bug_status(self, bug_id: str, status: str) -> object:
        try:
            bs = BugStatus(status)
            bug = self._bug_service.set_bug_status(bug_id, bs)
            return bug.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def resolve_bug_link(self, linked_iteration_id: str) -> object:
        """解析 bug 关联的需求迭代，返回跳转信息或 None（关联已失效）。"""
        try:
            return self._bug_service.resolve_bug_link(linked_iteration_id)
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

    def parse_md_import(self) -> object:
        """弹打开文件框，解析 .md 双轨格式为 ParsedProject。

        返回 ``{"parsed": {...}, "filename": "xxx"}`` 以便前端用文件名推测项目名。
        取消返回 None。
        """
        try:
            from management_prd.services.importer import parse_import_md

            picked = self._open_md_file()
            if not picked:
                return None
            path = Path(picked)
            text = path.read_text(encoding="utf-8")
            parsed = parse_import_md(text)
            return {
                "parsed": parsed.model_dump(mode="json"),
                "filename": path.stem,
            }
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def apply_full_import(self, target: dict[str, object], parsed: dict[str, object]) -> object:
        """应用完整导入（基础/智能共用统一写入路径）。

        ``target`` 形如 ``{"project_id": "..."}``（已有项目）或 ``{"name": "..."}``
        （新建项目）。``reuse_id`` 由 parsed 中的来源标记决定：基础导入 True、智能导入
        False（智能导入数据无原始 ID，全新建）。
        """
        try:
            from management_prd.models.data import ParsedProject
            from management_prd.services.project_service import ProjectTarget

            parsed_obj = ParsedProject.model_validate(parsed)
            raw_pid = target.get("project_id")
            raw_name = target.get("name")
            target_obj = ProjectTarget(
                project_id=str(raw_pid) if isinstance(raw_pid, str) and raw_pid else None,
                name=str(raw_name) if isinstance(raw_name, str) else None,
            )
            # 智能导入数据无原始 ID（reuse_id=False）；基础导入有（reuse_id=True）。
            reuse_id = bool(parsed.get("reuse_id", True))
            project = self._project_service.apply_full_import(
                target_obj, parsed_obj, reuse_id=reuse_id
            )
            return project.model_dump(mode="json")
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    def export_project(self, project_id: str) -> object:
        """[旧版 .txt 导出] 导出项目为 .txt 文件（弹保存对话框）。

        .. deprecated::
            新版导出走 :meth:`export_project_md`（.md 双轨格式）。本方法保留至
            第 7 步清理旧代码时移除，此处仅保持向后兼容的最小实现。
        """
        try:
            project = self._project_service.get(project_id)
            from management_prd.services.exporter import Exporter

            exporter = Exporter()
            # 旧 .txt 格式已废弃：这里复用快照导出 .md 文本作为最小兼容实现。
            snapshot = self._project_service.get_full_snapshot(project_id)
            content = exporter.export(snapshot)
            suggested = exporter.suggested_filename(project.name)
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

    def export_project_md(self, project_id: str, include_bug: bool = True) -> object:
        """导出项目为 .md 双轨格式文件（弹保存对话框）。

        先装配完整快照（``get_full_snapshot``），再由 :class:`Exporter` 生成
        YAML frontmatter + 正文渲染。``include_bug`` 决定是否包含 bug 段。
        """
        try:
            from management_prd.services.exporter import Exporter

            snapshot = self._project_service.get_full_snapshot(project_id)
            exporter = Exporter()
            content = exporter.export(snapshot, include_bug=include_bug)
            suggested = exporter.suggested_filename(snapshot.name)
            picked = self._save_dialog_md(suggested)
            if not picked:
                return None
            target = Path(picked)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            logger.info("需求已导出(.md): %s", target)
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

    def test_llm(self, config: dict[str, object] | None = None) -> object:
        """测试 LLM 连接（轻量 chat 请求，验证凭据/模型/网络）。

        ``config`` 可选覆盖当前设置（表单草稿未保存时用前端传入值测试）。形如
        ``{"base_url": "...", "api_key": "...", "model": "...", "timeout": 120}``。
        缺省字段回退到已落盘的设置。
        """
        try:
            from management_prd.llm.client import LlmClient

            settings = self._settings_service.load()
            cfg = config or {}
            base_url = str(cfg.get("base_url") or settings.llm_base_url)
            api_key = str(cfg.get("api_key") or settings.llm_api_key)
            model = str(cfg.get("model") or settings.llm_model)
            timeout_raw = cfg.get("timeout", settings.llm_timeout)
            timeout = (
                int(timeout_raw) if isinstance(timeout_raw, (int, str)) else settings.llm_timeout
            )
            client = LlmClient(base_url=base_url, api_key=api_key, model=model, timeout=timeout)
            return client.test_connection()
        except (LlmError, ManagementPrdError, ValueError, TypeError) as exc:
            return _err(exc)

    # ---------- 系统 ----------

    def open_external_url(self, url: str) -> object:
        """用系统默认浏览器打开外部链接（如 GitHub 仓库），避免在 webview 内导航。"""
        try:
            import webbrowser

            if not isinstance(url, str) or not url:
                raise ValueError("url 必填")
            if not url.startswith(("http://", "https://")):
                raise ValueError("仅支持 http/https 链接")
            webbrowser.open(url)
            return True
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # 关于弹窗头像：「打包默认（A）」 + 「访问仓库后缓存的最新版（B）」。
    # 路径：storage_dir/avatar.jpg。storage_dir 可被用户迁移，缓存随迁。
    AUTHOR_GITHUB_USER = "soifow"
    AUTHOR_AVATAR_URL = f"https://github.com/{AUTHOR_GITHUB_USER}.png?size=128"
    _AVATAR_FILENAME = "avatar.jpg"
    _AVATAR_TIMEOUT = 5  # 秒；超时即放弃，避免拖慢 UI

    def _avatar_path(self) -> Path:
        """头像 B 缓存路径。"""
        return self._db.storage_dir / self._AVATAR_FILENAME

    def get_avatar(self) -> object:
        """读取缓存的最新头像（图片 B）。

        Returns:
            ``{"exists": False}``：未访问过仓库或下载失败。
            ``{"exists": True, "data": "data:image/jpeg;base64,..."}``：已缓存。
        """
        try:
            path = self._avatar_path()
            if not path.exists():
                return {"exists": False}
            import base64

            data = path.read_bytes()
            if not data:
                return {"exists": False}
            b64 = base64.b64encode(data).decode("ascii")
            return {"exists": True, "data": f"data:image/jpeg;base64,{b64}"}
        except (ManagementPrdError, ValueError, OSError) as exc:
            return _err(exc)

    def refresh_avatar(self) -> object:
        """从作者 GitHub 拉取最新头像写入 storage_dir/avatar.jpg（图片 B）。

        失败不影响主流程：网络抖动时返回 ``{"updated": False, "reason": "..."}``。
        永远不会删除已存在的 B——只在成功拿到新数据时覆盖。
        """
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(
                self.AUTHOR_AVATAR_URL,
                headers={"User-Agent": "management-prd-vite"},
            )
            with urllib.request.urlopen(req, timeout=self._AVATAR_TIMEOUT) as resp:
                data = resp.read()
            if not data:
                return {"updated": False, "reason": "empty response"}

            path = self._avatar_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            # 临时文件 + 原子替换：避免写入半截文件污染缓存
            import os

            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            logger.info("头像已刷新: %s (%d bytes)", path, len(data))
            return {"updated": True}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # 软失败：返回 updated=False，不抛错、不弹错误
            return {"updated": False, "reason": str(exc)}
        except (ManagementPrdError, ValueError) as exc:
            return _err(exc)

    # ---------- 内部工具 ----------

    @staticmethod
    def _coerce_create_input(d: dict[str, object]) -> CreateRequirementInput:
        """把前端传入的 dict 转换为 CreateRequirementInput。"""
        module_names_raw = d.get("module_names", [])
        if not isinstance(module_names_raw, list):
            raise ValueError("module_names 必须是字符串数组")
        module_names = [str(m).strip() for m in module_names_raw if str(m).strip()]
        feature = d.get("feature", "")
        content = d.get("content", "")
        if not isinstance(content, str):
            raise ValueError("content 必须是字符串")
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
            module_names=module_names,
            feature=feature,
            content=content,
            status=status,
            date=d_val,
            completion_deadline=completion_deadline,
        )

    @staticmethod
    def _coerce_update_input(d: dict[str, object]) -> UpdateRequirementInput:
        """把前端传入的 dict 转换为 UpdateRequirementInput。"""
        module_names_raw = d.get("module_names")
        module_names: list[str] | None = None
        if module_names_raw is not None:
            if not isinstance(module_names_raw, list):
                raise ValueError("module_names 必须是字符串数组")
            module_names = [str(m).strip() for m in module_names_raw if str(m).strip()]
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
            module_names=module_names,
            feature=feature if isinstance(feature, str) else None,
            content=content if isinstance(content, str) else None,
            status=rs,
            date=d_val,
            completion_deadline=cd,
            clear_completion_deadline=clear_deadline,
        )

    @staticmethod
    def _coerce_create_bug_input(d: dict[str, object]) -> CreateBugInput:
        """把前端传入的 dict 转换为 CreateBugInput。"""
        module_names_raw = d.get("module_names", [])
        if not isinstance(module_names_raw, list):
            raise ValueError("module_names 必须是字符串数组")
        module_names = [str(m).strip() for m in module_names_raw if str(m).strip()]
        content = d.get("content", "")
        if not isinstance(content, str):
            raise ValueError("content 必须是字符串")
        level_raw = d.get("level", BugLevel.P3.value)
        if not isinstance(level_raw, str):
            raise ValueError("level 必须是字符串")
        level = BugLevel(level_raw)
        status_raw = d.get("status", BugStatus.OPEN.value)
        if not isinstance(status_raw, str):
            raise ValueError("status 必须是字符串")
        status = BugStatus(status_raw)
        date_raw = d.get("date")
        if not isinstance(date_raw, str) or not date_raw:
            raise ValueError("date 必填")
        d_val = date.fromisoformat(date_raw)
        linked_raw = d.get("linked_iteration_id")
        if linked_raw is not None and not isinstance(linked_raw, str):
            raise ValueError("linked_iteration_id 必须是字符串")
        return CreateBugInput(
            module_names=module_names,
            content=content,
            level=level,
            status=status,
            linked_iteration_id=linked_raw if isinstance(linked_raw, str) and linked_raw else None,
            date=d_val,
        )

    @staticmethod
    def _coerce_update_bug_input(d: dict[str, object]) -> UpdateBugInput:
        """把前端传入的 dict 转换为 UpdateBugInput。"""
        module_names_raw = d.get("module_names")
        module_names: list[str] | None = None
        if module_names_raw is not None:
            if not isinstance(module_names_raw, list):
                raise ValueError("module_names 必须是字符串数组")
            module_names = [str(m).strip() for m in module_names_raw if str(m).strip()]
        level_raw = d.get("level")
        status_raw = d.get("status")
        date_raw = d.get("date")
        linked_raw = d.get("linked_iteration_id")
        content = d.get("content")
        return UpdateBugInput(
            module_names=module_names,
            content=content if isinstance(content, str) else None,
            level=BugLevel(level_raw) if isinstance(level_raw, str) else None,
            status=BugStatus(status_raw) if isinstance(status_raw, str) else None,
            date=date.fromisoformat(date_raw) if isinstance(date_raw, str) and date_raw else None,
            linked_iteration_id=linked_raw if isinstance(linked_raw, str) and linked_raw else None,
            clear_linked=bool(d.get("clear_linked", False)),
        )

    @staticmethod
    def _coerce_create_subitem_input(iteration_id: str, d: dict[str, object]) -> CreateSubitemInput:
        """把前端传入的 dict 转换为 CreateSubitemInput。"""
        content = d.get("content", "")
        if not isinstance(content, str):
            raise ValueError("content 必须是字符串")
        status_raw = d.get("status", RequirementStatus.TODO.value)
        if not isinstance(status_raw, str):
            raise ValueError("status 必须是字符串")
        status = RequirementStatus(status_raw)
        deadline_raw = d.get("completion_deadline")
        completion_deadline: date | None = None
        if isinstance(deadline_raw, str) and deadline_raw:
            completion_deadline = date.fromisoformat(deadline_raw)
        return CreateSubitemInput(
            iteration_id=iteration_id,
            content=content,
            status=status,
            completion_deadline=completion_deadline,
        )

    @staticmethod
    def _coerce_update_subitem_input(d: dict[str, object]) -> UpdateSubitemInput:
        """把前端传入的 dict 转换为 UpdateSubitemInput。"""
        content = d.get("content")
        status = d.get("status")
        rs: RequirementStatus | None = None
        if status is not None:
            if not isinstance(status, str):
                raise ValueError("status 必须是字符串")
            rs = RequirementStatus(status)
        deadline_raw = d.get("completion_deadline")
        cd: date | None = None
        if isinstance(deadline_raw, str) and deadline_raw:
            cd = date.fromisoformat(deadline_raw)
        clear_deadline = bool(d.get("clear_completion_deadline", False))
        return UpdateSubitemInput(
            content=content if isinstance(content, str) else None,
            status=rs,
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

    def _open_md_file(self) -> str | None:
        """调用 webview 打开文件对话框（.md 默认），返回所选路径或 None。"""
        if self._window is None:
            raise ManagementPrdError("WebApi 窗口未注入，无法弹对话框")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=["Markdown 文件 (*.md)", "文本文件 (*.txt)", "所有文件 (*.*)"],
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

    def _save_dialog_md(self, suggested: str) -> str | None:
        """调用 webview 保存文件对话框（.md 默认），返回所选路径或 None。"""
        if self._window is None:
            raise ManagementPrdError("WebApi 窗口未注入，无法弹对话框")
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested,
            file_types=["Markdown 文件 (*.md)", "所有文件 (*.*)"],
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
