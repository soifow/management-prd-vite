"""智能导入测试（Step 5，已按 smart-import-progress 设计拆分为 pick/run 两段）。

覆盖设计 §7 智能导入：
1. ``from_llm_intermediate``：中间格式 -> ParsedProject 转换（模块/迭代/子需求/bug 映射、
   内部 id 自洽、bug linked 用 (feature,date) 查找、未命中置空）。
2. ``parse_llm_intermediate``：结构非法（缺必填 / 枚举越界）抛 ImportParseError。
3. 端到端：LLM 返回中间格式 -> ParsedProject -> ``apply_full_import(reuse_id=False)``
   -> 断言需求 / 子需求 / bug 入库、bug 按 (feature,date) 关联、未配置 LLM 提示。
4. ``WebApi.pick_smart_import_file`` / ``run_smart_import``：mock LlmClient + 注入 LLM 配置
   的 SettingsService -> 拆段后各测；未启用 / 缺配置 / 大文件超长 / 取消返回 None 各降级路径。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from management_prd.llm.client import LlmClient
from management_prd.llm.prompt import build_messages
from management_prd.models.data import (
    LlmParsedBug,
    LlmParsedIteration,
    LlmParsedProject,
    LlmParsedSubitem,
)
from management_prd.models.requirement import RequirementStatus
from management_prd.services.bootstrap_service import BootstrapService
from management_prd.services.db_service import DbService
from management_prd.services.importer import (
    from_llm_intermediate,
    parse_llm_intermediate,
)
from management_prd.services.project_service import ProjectService, ProjectTarget

# ── 1. from_llm_intermediate 转换 ──


def _sample_llm_project() -> LlmParsedProject:
    """构造一个含多模块 + 迭代 + 子需求 + bug(含 linked) 的中间格式。"""
    return LlmParsedProject(
        project_name="会员系统",
        modules=["主界面", "账户"],
        iterations=[
            LlmParsedIteration(
                modules=["主界面", "账户"],
                feature="登录",
                content="实现微信与手机号登录……",
                status=RequirementStatus.DONE,
                date=date(2026, 1, 5),
                completion_deadline=date(2026, 1, 10),
                subitems=[
                    LlmParsedSubitem(
                        content="微信登录",
                        status=RequirementStatus.DONE,
                        completion_deadline=date(2026, 1, 8),
                    ),
                    LlmParsedSubitem(content="手机验证码", status=RequirementStatus.TODO),
                ],
            ),
            LlmParsedIteration(
                modules=["主界面"],
                feature="支付",
                content="实现支付",
                status=RequirementStatus.TODO,
                date=date(2026, 1, 16),
            ),
        ],
        bugs=[
            LlmParsedBug(
                content="登录回调偶发崩溃",
                level="P1",
                status="open",
                modules=["主界面"],
                date=date(2026, 1, 6),
                linked_feature="登录",
                linked_date=date(2026, 1, 5),
            ),
            LlmParsedBug(
                content="无关联的 bug",
                level="P3",
                status="open",
                modules=["账户"],
                date=date(2026, 1, 7),
            ),
        ],
    )


def test_from_llm_intermediate_basic_shape() -> None:
    parsed = from_llm_intermediate(_sample_llm_project())
    assert parsed.name == "会员系统"
    assert len(parsed.modules) == 2
    assert [m.name for m in parsed.modules] == ["主界面", "账户"]
    # 模块 id 内部唯一
    assert len({m.id for m in parsed.modules}) == 2
    assert len(parsed.iterations) == 2
    assert len(parsed.bugs) == 2
    assert parsed.includes_bug is True


def test_from_llm_intermediate_module_refs_resolved() -> None:
    parsed = from_llm_intermediate(_sample_llm_project())
    mod_id_by_name = {m.name: m.id for m in parsed.modules}
    login = next(it for it in parsed.iterations if it.feature == "登录")
    # 登录迭代引用了两个模块 id
    assert set(login.modules) == {mod_id_by_name["主界面"], mod_id_by_name["账户"]}
    # 子需求 seq 从 1 顺序赋值
    assert [s.seq for s in login.subitems] == [1, 2]
    assert login.subitems[0].content == "微信登录"
    assert login.subitems[0].completion_deadline == date(2026, 1, 8)


def test_from_llm_intermediate_bug_linked_resolved_by_feature_date() -> None:
    """bug linked 用 (feature, date) 命中目标迭代 id；未命中置 None。"""
    parsed = from_llm_intermediate(_sample_llm_project())
    login = next(it for it in parsed.iterations if it.feature == "登录")
    linked_bug = next(b for b in parsed.bugs if b.content == "登录回调偶发崩溃")
    unlinked_bug = next(b for b in parsed.bugs if b.content == "无关联的 bug")

    assert linked_bug.linked == login.id  # 命中
    assert unlinked_bug.linked is None  # 未设置 linked_feature/date


def test_from_llm_intermediate_bug_linked_miss_when_no_match() -> None:
    """linked_feature/date 指向不存在的迭代 -> linked=None（不报错）。"""
    llm = _sample_llm_project()
    llm.bugs[0].linked_feature = "不存在功能"
    llm.bugs[0].linked_date = date(2026, 1, 5)
    parsed = from_llm_intermediate(llm)
    assert parsed.bugs[0].linked is None


def test_from_llm_intermediate_unreferenced_module_still_kept() -> None:
    """modules 列表里的模块即使没被迭代/bug 引用也保留（供前端分组展示）。"""
    llm = LlmParsedProject(
        project_name="P",
        modules=["M1", "M2"],
        iterations=[
            LlmParsedIteration(
                modules=["M1"],
                feature="F",
                content="C",
                date=date(2026, 1, 1),
            )
        ],
        bugs=[],
    )
    parsed = from_llm_intermediate(llm)
    assert {m.name for m in parsed.modules} == {"M1", "M2"}


def test_from_llm_intermediate_no_bugs_sets_includes_bug_false() -> None:
    llm = LlmParsedProject(
        project_name="P",
        modules=[],
        iterations=[LlmParsedIteration(feature="F", content="C", date=date(2026, 1, 1))],
        bugs=[],
    )
    parsed = from_llm_intermediate(llm)
    assert parsed.bugs == []
    assert parsed.includes_bug is False


# ── 2. parse_llm_intermediate 结构校验 ──


def test_parse_llm_intermediate_minimal_valid() -> None:
    data = {
        "project_name": "X",
        "iterations": [{"feature": "F", "content": "C", "date": "2026-01-01"}],
    }
    parsed = parse_llm_intermediate(data)
    assert parsed.name == "X"
    assert parsed.iterations[0].status == RequirementStatus.TODO  # 默认


def test_parse_llm_intermediate_missing_required_raises() -> None:
    from management_prd.errors import ImportParseError

    # iterations 缺 date
    bad = {"project_name": "X", "iterations": [{"feature": "F", "content": "C"}]}
    with pytest.raises(ImportParseError):
        parse_llm_intermediate(bad)


def test_parse_llm_intermediate_invalid_enum_raises() -> None:
    from management_prd.errors import ImportParseError

    bad = {
        "project_name": "X",
        "iterations": [
            {"feature": "F", "content": "C", "date": "2026-01-01", "status": "not_a_status"}
        ],
    }
    with pytest.raises(ImportParseError):
        parse_llm_intermediate(bad)


# ── 3. 端到端：LLM 中间格式 -> apply_full_import(reuse_id=False) ──


@pytest.fixture()
def service(bootstrap: BootstrapService) -> ProjectService:
    """使用 conftest 提供的隔离 bootstrap，settings.json 落 tmp_path，不触达真实用户目录。"""
    db = DbService(bootstrap=bootstrap)
    db.init_db()
    return ProjectService(db)


def test_smart_import_end_to_end_applies_to_new_project(service: ProjectService) -> None:
    """LLM 返回中间格式 -> 全新建（reuse_id=False）-> 入库正确、bug 按 (feature,date) 关联。"""
    parsed = from_llm_intermediate(_sample_llm_project())
    project = service.apply_full_import(ProjectTarget(name="智能会员系统"), parsed, reuse_id=False)

    assert project.name == "智能会员系统"
    assert len(project.items) == 2
    login = next(it for it in project.items if it.feature == "登录")
    assert set(login.modules) == {"主界面", "账户"}
    assert login.completion_deadline == date(2026, 1, 10)
    subs = service.list_subitems(login.id)
    assert [s.content for s in subs] == ["微信登录", "手机验证码"]

    # bug 入库且 linked 正确指向登录迭代
    from management_prd.services.bug_service import BugService

    bugs = BugService(service._db).list_bugs(project.id)
    assert len(bugs) == 2
    linked_bug = next(b for b in bugs if b.content == "登录回调偶发崩溃")
    assert linked_bug.linked_iteration_id == login.id
    unlinked_bug = next(b for b in bugs if b.content == "无关联的 bug")
    assert unlinked_bug.linked_iteration_id is None


def test_smart_import_generates_fresh_ids_each_call(service: ProjectService) -> None:
    """reuse_id=False 时每次导入生成的 DB id 都是全新的（不复用内部 llm- 前缀 id）。"""
    parsed = from_llm_intermediate(_sample_llm_project())
    project = service.apply_full_import(ProjectTarget(name="P1"), parsed, reuse_id=False)
    # 落库 id 不应包含 llm- 前缀（说明 _build_entity_id_map 生成了新 id）
    for it in project.items:
        assert not it.id.startswith("llm-")


# ── 4. WebApi.pick_smart_import_file / run_smart_import 集成（mock LLM transport + 注入 LLM 配置）──


def _mock_transport(return_args: dict[str, Any]) -> httpx.MockTransport:
    """构造返回 import_project tool_call(arguments=return_args) 的 MockTransport。"""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "import_project",
                                        "arguments": json.dumps(return_args),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    return httpx.MockTransport(handler)


def _make_api(service: ProjectService) -> tuple[Any, Any]:
    """构造一个 WebApi + 已启用 LLM 的 SettingsService。

    SettingsService 复用 ``service._bootstrap``（conftest 隔离到 tmp_path），
    settings.json 落在 tmp_path 下，不触达真实用户目录。
    """
    from management_prd.api import WebApi
    from management_prd.models.settings import AppSettings
    from management_prd.services.settings_service import SettingsService

    # SettingsService 落盘一份启用 LLM 的配置（缺省值需要 api 能读到）
    settings_svc = SettingsService(service._bootstrap)
    settings_svc.update_settings(
        AppSettings(
            llm_enabled=True,
            llm_base_url="https://api.example.com/v1",
            llm_api_key="sk-test",
            llm_model="test-model",
        ).model_dump(mode="json")
    )

    api = WebApi(
        project_service=service,
        settings_service=settings_svc,
    )
    return api, settings_svc


# ── pick + run 成功链路 ──


def test_pick_smart_import_file_success(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """pick 返回 {filename, text, char_count}；LLM 配置有效且文件不超长。"""
    api, _ = _make_api(service)

    doc = tmp_path / "doc.txt"
    doc.write_text("登录：实现微信登录\n支付：实现支付", encoding="utf-8")
    monkeypatch.setattr(api, "_open_text_file", lambda *a, **kw: str(doc))

    result = api.pick_smart_import_file()
    assert isinstance(result, dict)
    assert result["filename"] == "doc"
    assert "登录" in str(result["text"])
    assert result["char_count"] == len("登录：实现微信登录\n支付：实现支付")


def test_run_smart_import_success(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run 返回 {parsed, filename}；mock LLM 返回合法中间格式。"""
    api, _ = _make_api(service)

    return_args = {
        "project_name": "智能项目",
        "modules": ["主界面"],
        "iterations": [
            {
                "feature": "登录",
                "content": "实现微信登录",
                "date": "2026-01-05",
                "modules": ["主界面"],
            }
        ],
        "bugs": [],
    }
    orig_init = LlmClient.__init__

    def patched_init(self: LlmClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = _mock_transport(return_args)
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(LlmClient, "__init__", patched_init)

    result = api.run_smart_import("登录：实现微信登录", "doc")
    assert isinstance(result, dict)
    assert "parsed" in result
    assert result["filename"] == "doc"
    assert result["parsed"]["name"] == "智能项目"
    assert len(result["parsed"]["iterations"]) == 1


# ── pick：配置/文件校验 ──


def test_pick_smart_import_file_disabled_returns_error(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """未启用智能导入（llm_enabled=False）-> 错误信封，不弹文件框。"""
    api, settings_svc = _make_api(service)
    settings_svc.update_settings({"llm_enabled": False})

    called = {"open": False}

    def fake_open(*a: Any, **kw: Any) -> str | None:
        called["open"] = True
        return None

    monkeypatch.setattr(api, "_open_text_file", fake_open)

    result = api.pick_smart_import_file()
    assert isinstance(result, dict)
    assert result.get("success") is False
    assert "未启用" in result.get("error", "")
    assert called["open"] is False


def test_pick_smart_import_file_incomplete_config_returns_error(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """启用但缺 model -> 错误信封。"""
    api, settings_svc = _make_api(service)
    settings_svc.update_settings({"llm_enabled": True, "llm_model": ""})

    result = api.pick_smart_import_file()
    assert isinstance(result, dict)
    assert result.get("success") is False
    assert "配置不完整" in result.get("error", "")


def test_pick_smart_import_file_too_long(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """文件超过字符上限 -> 错误信封。"""
    api, _ = _make_api(service)
    doc = tmp_path / "big.txt"
    doc.write_text("x" * (api._LLM_MAX_INPUT_CHARS + 1), encoding="utf-8")
    monkeypatch.setattr(api, "_open_text_file", lambda *a, **kw: str(doc))

    result = api.pick_smart_import_file()
    assert isinstance(result, dict)
    assert result.get("success") is False
    assert "文件过长" in result.get("error", "")


def test_pick_smart_import_file_cancel_returns_none(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """用户取消选文件 -> None。"""
    api, _ = _make_api(service)
    monkeypatch.setattr(api, "_open_text_file", lambda *a, **kw: None)

    result = api.pick_smart_import_file()
    assert result is None


# ── run：LLM 错误 ──


def test_run_smart_import_llm_error(
    service: ProjectService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 调用失败（HTTP 401）-> LlmError 被捕获为错误信封。"""
    api, _ = _make_api(service)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    orig_init = LlmClient.__init__

    def patched_init(self: LlmClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(LlmClient, "__init__", patched_init)

    result = api.run_smart_import("内容", "doc")
    assert isinstance(result, dict)
    assert result.get("success") is False
    assert "认证失败" in result.get("error", "")


# ── prompt 一致性（与 build_messages 联动）──


def test_build_messages_feeds_into_client_payload() -> None:
    """smart_import 用 build_messages 构造 messages 喂 chat_structured（结构契约）。"""
    msgs = build_messages("任意文档内容", "会员.md")
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "会员.md" in msgs[1]["content"]
    assert "任意文档内容" in msgs[1]["content"]
