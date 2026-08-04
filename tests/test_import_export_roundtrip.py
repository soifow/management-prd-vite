"""导入/导出往返测试（.md 双轨格式）。

覆盖设计文档 §15 验证标准：
1. 往返无损（核心）：含多模块迭代 + 子需求 + 截止 + bug(含 linked) 的项目 -> 导出
   .md -> 干净实例导入 -> 逐字段断言全等（含 ID/关联/子需求 seq/deadline）。
2. deferred 不变量：deferred 项 deadline 导入后 NULL。
3. ID 冲突映射：目标库占用某 ID -> 导入 -> 该 ID 被映射、所有引用一致重写。
4. Bug 可选导出：不含 bug 导出 -> 提示丢失项；导入该文件 -> 无 bug 段、需求侧完整。
5. 导入到已有项目 upsert：同 (feature,date) 迭代被更新、子需求整体替换、新迭代新建。
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from management_prd.errors import ImportFormatError
from management_prd.models.bug import BugStatus, CreateBugInput
from management_prd.models.data import CreateRequirementInput
from management_prd.models.requirement import RequirementStatus
from management_prd.models.subitem import CreateSubitemInput
from management_prd.services.db_service import DbService
from management_prd.services.exporter import Exporter
from management_prd.services.importer import parse_import_md
from management_prd.services.project_service import ProjectService, ProjectTarget


@pytest.fixture()
def service(tmp_path: Path) -> ProjectService:
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    return ProjectService(db)


def _now() -> datetime:
    return datetime(2026, 1, 5, 9, 0, 0)


def _build_project(service: ProjectService, name: str = "会员系统") -> str:
    """构造一个含多模块迭代 + 子需求 + 截止 + bug(含 linked) 的项目，返回 project_id。"""
    p = service.create_project(name)
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["主界面", "账户"],
            feature="登录",
            content="实现微信与手机号登录……",
            status=RequirementStatus.DONE,
            date=date(2026, 1, 5),
            completion_deadline=date(2026, 1, 10),
        ),
    )
    service.create_subitem(
        CreateSubitemInput(
            iteration_id=item.id,
            content="微信登录",
            status=RequirementStatus.DONE,
            completion_deadline=date(2026, 1, 8),
        )
    )
    service.create_subitem(
        CreateSubitemInput(
            iteration_id=item.id,
            content="手机验证码",
            status=RequirementStatus.TODO,
        )
    )
    # 第二模块迭代
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["主界面"],
            feature="支付",
            content="实现支付",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 16),
        ),
    )
    # bug 关联到登录迭代
    from management_prd.services.bug_service import BugService

    BugService(service._db).create_bug(
        p.id,
        CreateBugInput(
            module_names=["主界面"],
            content="登录回调偶发崩溃",
            level="P1",
            linked_iteration_id=item.id,
            date=date(2026, 1, 6),
        ),
    )
    return p.id


def _export_md(service: ProjectService, project_id: str, include_bug: bool = True) -> str:
    snap = service.get_full_snapshot(project_id)
    return Exporter().export(snap, include_bug=include_bug)


# ── 1. 往返无损（核心） ──


def test_roundtrip_lossless(service: ProjectService) -> None:
    """含多模块迭代 + 子需求 + 截止 + bug(含 linked) 的项目往返无损。"""
    pid = _build_project(service)
    text = _export_md(service, pid)

    # 导入到干净实例（新建项目）
    parsed = parse_import_md(text)
    new_project = service.apply_full_import(
        ProjectTarget(name="导入会员系统"), parsed, reuse_id=True
    )

    # 逐字段断言
    assert new_project.name == "导入会员系统"
    # 两个迭代（登录、支付）
    assert len(new_project.items) == 2
    login = next(it for it in new_project.items if it.feature == "登录")
    pay = next(it for it in new_project.items if it.feature == "支付")

    # 登录：多模块、截止、子需求
    assert login.modules == ["主界面", "账户"]
    assert login.content == "实现微信与手机号登录……"
    assert login.status == RequirementStatus.DONE
    assert login.completion_deadline == date(2026, 1, 10)
    subs = service.list_subitems(login.id)
    assert len(subs) == 2
    assert subs[0].content == "微信登录"
    assert subs[0].status == RequirementStatus.DONE
    assert subs[0].completion_deadline == date(2026, 1, 8)
    assert subs[1].content == "手机验证码"
    assert subs[1].status == RequirementStatus.TODO
    assert subs[1].completion_deadline is None

    # 支付
    assert pay.modules == ["主界面"]
    assert pay.status == RequirementStatus.TODO

    # 模块
    modules = service.list_modules(new_project.id)
    assert {m.name for m in modules} == {"主界面", "账户"}

    # bug + linked
    from management_prd.services.bug_service import BugService

    bugs = BugService(service._db).list_bugs(new_project.id)
    assert len(bugs) == 1
    b = bugs[0]
    assert b.content == "登录回调偶发崩溃"
    assert b.level == "P1"
    assert b.status == BugStatus.OPEN
    assert b.modules == ["主界面"]
    # linked 指向新项目的登录迭代（id 映射一致）
    assert b.linked_iteration_id == login.id


def test_roundtrip_preserves_ids_on_clean_instance(service: ProjectService, tmp_path: Path) -> None:
    """干净实例（独立空库）导入复用原始 ID（1:1 还原关联）。

    真正的「干净实例」= 全新空数据库，与源数据无 ID 交集，id_map 恒等。
    同一库内导入到新项目时，源 ID 已被占用，会走冲突映射（见 test_id_conflict_mapping）。
    """
    pid = _build_project(service)
    snap = service.get_full_snapshot(pid)
    text = Exporter().export(snap)

    # 独立空库（干净实例）
    clean_db = DbService(db_path=tmp_path / "clean.db")
    clean_db.init_db()
    clean_service = ProjectService(clean_db)

    parsed = parse_import_md(text)
    new_project = clean_service.apply_full_import(ProjectTarget(name="导入"), parsed, reuse_id=True)

    # 模块 ID 复用（与源快照一致）
    new_mods = {m.name: m.id for m in clean_service.list_modules(new_project.id)}
    for sm in snap.modules:
        assert new_mods[sm.name] == sm.id
    # 迭代 ID 复用
    assert {it.id for it in new_project.items} == {s.id for s in snap.iterations}


# ── 2. deferred 不变量 ──


def test_deferred_deadline_null_on_import(service: ProjectService) -> None:
    pid = _build_project(service)
    # 把登录迭代改成 deferred 并清空截止后导出
    snap = service.get_full_snapshot(pid)
    login = next(it for it in snap.iterations if it.feature == "登录")
    login.status = RequirementStatus.DEFERRED
    login.completion_deadline = None
    text = Exporter().export(snap)

    parsed = parse_import_md(text)
    new_project = service.apply_full_import(ProjectTarget(name="导入"), parsed, reuse_id=True)
    new_login = next(it for it in new_project.items if it.feature == "登录")
    assert new_login.status == RequirementStatus.DEFERRED
    assert new_login.completion_deadline is None  # 强制 NULL


# ── 3. ID 冲突映射 ──


def test_id_conflict_mapping(service: ProjectService, tmp_path: Path) -> None:
    """目标库占用某 ID -> 导入 -> 该 ID 被映射、所有引用一致重写。"""
    # 用两个独立数据库模拟：源库导出，目标库有一个与源迭代同 id 的需求
    src_pid = _build_project(service, "源项目")
    snap = service.get_full_snapshot(src_pid)
    text = Exporter().export(snap)

    # 独立目标库：先建项目与模块，再用原生 SQL 插入一条与源迭代同 id 的需求
    target_db = DbService(db_path=tmp_path / "target.db")
    target_db.init_db()
    target_service = ProjectService(target_db)

    target = target_service.create_project("目标项目")
    target_service.create_module(target.id, "占位模块")
    conflict_id = snap.iterations[0].id  # 源「登录」迭代的 id

    # 关闭 FK 插入占位需求（直接用冲突 id），避免关联表引用
    with target_db.transaction() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO requirements"
            "(id, project_id, feature, content, status, date, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conflict_id,
                target.id,
                "占位",
                "占位内容",
                "done",
                "2020-01-01",
                "2020-01-01T00:00:00",
                "2020-01-01T00:00:00",
            ),
        )
        conn.execute("PRAGMA foreign_keys = ON")

    parsed = parse_import_md(text)
    new_project = target_service.apply_full_import(
        ProjectTarget(project_id=target.id), parsed, reuse_id=True
    )

    # 冲突 ID 被映射为新 id，目标占位需求仍保留
    all_ids = {it.id for it in new_project.items}
    assert conflict_id in all_ids  # 占位需求仍占用原 id
    imported_login = next(it for it in new_project.items if it.feature == "登录")
    assert imported_login.id != conflict_id  # 被映射
    assert imported_login.feature == "登录"
    assert imported_login.content == "实现微信与手机号登录……"


# ── 4. Bug 可选导出 ──


def test_export_without_bug_imports_requirements_only(service: ProjectService) -> None:
    pid = _build_project(service)
    text = _export_md(service, pid, include_bug=False)

    parsed = parse_import_md(text)
    assert parsed.includes_bug is False
    assert parsed.bugs == []

    new_project = service.apply_full_import(ProjectTarget(name="无bug"), parsed, reuse_id=True)
    assert len(new_project.items) == 2  # 需求侧完整
    from management_prd.services.bug_service import BugService

    assert BugService(service._db).list_bugs(new_project.id) == []


# ── 5. 导入到已有项目 upsert ──


def test_upsert_into_existing_project(service: ProjectService) -> None:
    """同 (feature,date) 迭代被更新、子需求整体替换、新迭代新建。"""
    pid = _build_project(service)
    text = _export_md(service, pid)

    # 已存在一个「登录」迭代（同 feature,date 但内容不同）
    target = service.create_project("目标")
    service.create_requirement(
        target.id,
        CreateRequirementInput(
            module_names=["旧模块"],
            feature="登录",
            content="旧内容",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 5),
        ),
    )

    parsed = parse_import_md(text)
    new_project = service.apply_full_import(
        ProjectTarget(project_id=target.id), parsed, reuse_id=True
    )

    # 迭代数：登录(已存在,更新) + 支付(新建) = 2
    assert len(new_project.items) == 2
    login = next(it for it in new_project.items if it.feature == "登录")
    # 内容被更新
    assert login.content == "实现微信与手机号登录……"
    assert login.status == RequirementStatus.DONE
    # 子需求整体替换为文件内容
    subs = service.list_subitems(login.id)
    assert len(subs) == 2
    assert subs[0].content == "微信登录"
    # 支付新建
    pay = next(it for it in new_project.items if it.feature == "支付")
    assert pay.content == "实现支付"


# ── format_version 校验 ──


def test_unsupported_format_version_rejected(service: ProjectService) -> None:
    text = _export_md(service, _build_project(service))
    # 把 format_version 改成不支持的版本
    text = text.replace("format_version: 1", "format_version: 99")
    with pytest.raises(ImportFormatError):
        parse_import_md(text)


def test_missing_frontmatter_rejected() -> None:
    with pytest.raises(ImportFormatError):
        parse_import_md("没有 frontmatter 的纯文本")
