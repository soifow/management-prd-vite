"""项目服务测试（v3：单 date + feature，SQLite 后端）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from management_prd.models.data import (
    CreateRequirementInput,
    ParsedRequirement,
    UpdateRequirementInput,
)
from management_prd.models.requirement import RequirementStatus
from management_prd.services.db_service import DbService
from management_prd.services.project_service import ProjectService


@pytest.fixture()
def service(tmp_path: Path) -> ProjectService:
    """使用临时目录的 ProjectService（基于临时 SQLite）。"""
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    return ProjectService(db)


# ---------- 项目 ----------


def test_create_and_list_project(service: ProjectService) -> None:
    s = service.create_project("项目A")
    assert s.name == "项目A"
    assert s.requirement_count == 0
    assert s.latest_done_or_ui_date is None

    summaries = service.list_summaries()
    assert len(summaries) == 1
    assert summaries[0].name == "项目A"


def test_rename_project(service: ProjectService) -> None:
    s = service.create_project("旧名")
    s2 = service.rename_project(s.id, "新名")
    assert s2.name == "新名"


def test_create_project_empty_name(service: ProjectService) -> None:
    with pytest.raises(ValueError):
        service.create_project("   ")


def test_delete_project(service: ProjectService) -> None:
    s = service.create_project("项目A")
    assert service.delete_project(s.id) is True
    assert service.list_summaries() == []


# ---------- 需求迭代 ----------


def test_create_requirement(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能X",
            content="第一次描述",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    )
    assert item.module == "模块1"
    assert item.feature == "功能X"
    assert item.content == "第一次描述"
    assert item.date == date(2026, 6, 29)


def test_create_requirement_feature_defaults_to_content(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="",
            content="需求内容",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    )
    assert item.feature == "需求内容"


def test_update_requirement(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="m1",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.update_requirement(
        item.id,
        UpdateRequirementInput(module="m2", content="c2", status=RequirementStatus.DONE),
    )
    assert updated.module == "m2"
    assert updated.content == "c2"
    assert updated.status == RequirementStatus.DONE


def test_set_status(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.set_status(item.id, RequirementStatus.DONE)
    assert updated.status == RequirementStatus.DONE


def test_delete_requirement(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.delete_requirement(item.id) is True
    assert service.get(p.id).items == []


# ---------- list_modules / list_features / list_iterations ----------


def test_list_modules(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块B",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块A",
            feature="f2",
            content="c2",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="c3",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.list_modules(p.id) == ["模块A", "模块B"]


def test_list_features(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能B",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能A",
            content="c2",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.list_features(p.id, "模块1") == ["功能A", "功能B"]


def test_list_iterations(service: ProjectService) -> None:
    p = service.create_project("项目A")
    # 两次迭代同一个功能
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能X",
            content="v1描述",
            status=RequirementStatus.DONE,
            date=date(2026, 3, 27),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能X",
            content="v2描述",
            status=RequirementStatus.TODO,
            date=date(2026, 5, 20),
        ),
    )
    iters = service.list_iterations(p.id, "模块1", "功能X")
    assert len(iters) == 2
    assert iters[0].date == date(2026, 3, 27)
    assert iters[0].content == "v1描述"
    assert iters[1].date == date(2026, 5, 20)
    assert iters[1].content == "v2描述"


# ---------- 汇总 latest_done_or_ui_date ----------


def test_summary_latest_done_or_ui_date(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="done1",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f2",
            content="ui1",
            status=RequirementStatus.UI_DONE_WAITING_BACKEND,
            date=date(2026, 7, 15),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="todo1",
            status=RequirementStatus.TODO,
            date=date(2026, 8, 1),
        ),
    )
    summaries = service.list_summaries()
    assert summaries[0].latest_done_or_ui_date == date(2026, 7, 15)
    assert summaries[0].requirement_count == 3


def test_summary_no_done_items(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="todo1",
            status=RequirementStatus.TODO,
            date=date(2026, 8, 1),
        ),
    )
    summaries = service.list_summaries()
    assert summaries[0].latest_done_or_ui_date is None


# ---------- apply_import 去重 ----------


def test_apply_import_new_items(service: ProjectService) -> None:
    p = service.create_project("项目A")
    parsed = [
        ParsedRequirement(
            module="模块A",
            feature="功能X",
            content="需求X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
        ParsedRequirement(
            module="模块A",
            feature="需求Y",
            content="需求Y",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    ]
    project = service.apply_import(p.id, parsed)
    assert len(project.items) == 2


def test_apply_import_dedup_same_date_module_content(service: ProjectService) -> None:
    p = service.create_project("项目A")
    parsed1 = [
        ParsedRequirement(
            module="模块A",
            feature="需求X",
            content="需求X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        )
    ]
    service.apply_import(p.id, parsed1)
    # 重复导入同一条（同 date+module+content）-> 不复制
    service.apply_import(p.id, parsed1)
    project = service.get(p.id)
    assert len(project.items) == 1


def test_apply_import_different_date_same_feature(service: ProjectService) -> None:
    """同 feature 不同 date -> 两条记录（迭代链）。"""
    p = service.create_project("项目A")
    service.apply_import(
        p.id,
        [
            ParsedRequirement(
                module="模块A",
                feature="功能X",
                content="功能X",
                status=RequirementStatus.DONE,
                date=date(2026, 6, 29),
            )
        ],
    )
    service.apply_import(
        p.id,
        [
            ParsedRequirement(
                module="模块A",
                feature="功能X",
                content="功能X",
                status=RequirementStatus.TODO,
                date=date(2026, 7, 15),
            )
        ],
    )
    project = service.get(p.id)
    assert len(project.items) == 2
    # 不改已有状态
    assert project.items[0].status == RequirementStatus.DONE


def test_apply_import_skips_unselected(service: ProjectService) -> None:
    p = service.create_project("项目A")
    parsed = [
        ParsedRequirement(
            module="模块A",
            feature="需求X",
            content="需求X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
            selected=False,
        )
    ]
    project = service.apply_import(p.id, parsed)
    assert project.items == []


# ---------- persistence ----------


def test_persistence_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "requment.db"
    DbService(db_path=db_path).init_db()
    s1 = ProjectService(DbService(db_path=db_path))
    p = s1.create_project("项目A")
    s1.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )

    s2 = ProjectService(DbService(db_path=db_path))
    summaries = s2.list_summaries()
    assert len(summaries) == 1
    assert summaries[0].requirement_count == 1
