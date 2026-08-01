# Stage 01 · 值与行契约

### 目标

实现值与行契约，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `README.md`
    - `pyproject.toml`
    - `src/minipostgres/__init__.py`
    - `src/minipostgres/errors.py`
    - `src/minipostgres/row.py`
    - `src/minipostgres/types.py`
    - `tests/unit/test_rows.py`
    - `tests/unit/test_types.py`
    - `uv.lock`

### 当前遇到的问题

SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。

### 测试契约

#### 先看会坏在哪里

聚焦测试让值与行契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/unit/test_rows.py"
    ```diff
    diff --git a/tests/unit/test_rows.py b/tests/unit/test_rows.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8f7e6b98c6943725d5c6589a1620cabb671af2ab
    --- /dev/null
    +++ b/tests/unit/test_rows.py
    @@ -0,0 +1,38 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.row import TID, ColumnBinding, ExecutionRow
    +
    +
    +def test_execution_row_merges_cells_tids_and_computed_values() -> None:
    +    left = ExecutionRow(
    +        {ColumnBinding(1, 0): 7},
    +        {1: TID(0, 2)},
    +        {"left": "kept"},
    +    )
    +    right = ExecutionRow(
    +        {ColumnBinding(2, 0): "x"},
    +        {2: TID(0, 5)},
    +        {"right": 9},
    +    )
    +
    +    merged = left.merge(right)
    +
    +    assert merged.cells[ColumnBinding(1, 0)] == 7
    +    assert merged.cells[ColumnBinding(2, 0)] == "x"
    +    assert merged.tids == {1: TID(0, 2), 2: TID(0, 5)}
    +    assert merged.computed == {"left": "kept", "right": 9}
    +
    +
    +def test_execution_row_rejects_overlapping_bindings() -> None:
    +    binding = ColumnBinding(1, 0)
    +    with pytest.raises(ValueError, match="overlapping column"):
    +        ExecutionRow({binding: 1}, {}).merge(ExecutionRow({binding: 2}, {}))
    +
    +
    +def test_identifiers_must_be_non_negative() -> None:
    +    with pytest.raises(ValueError):
    +        TID(-1, 0)
    +    with pytest.raises(ValueError):
    +        ColumnBinding(1, -1)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让值与行契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert actual is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/test_types.py"
    ```diff
    diff --git a/tests/unit/test_types.py b/tests/unit/test_types.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..38db53618f52b69ba8a7fec6847f35ad2be1f2b5
    --- /dev/null
    +++ b/tests/unit/test_types.py
    @@ -0,0 +1,45 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.errors import NumericOverflow, TypeMismatch
    +from minipostgres.types import (
    +    DataType,
    +    compare_values,
    +    infer_type,
    +    sql_and,
    +    sql_not,
    +    sql_or,
    +    validate_scalar,
    +    widen_numeric_pair,
    +)
    +
    +
    +def test_sql_boolean_truth_tables_and_null_comparison() -> None:
    +    assert sql_and(True, None) is None
    +    assert sql_and(False, None) is False
    +    assert sql_or(True, None) is True
    +    assert sql_or(False, None) is None
    +    assert sql_not(None) is None
    +    assert compare_values("=", None, 1) is None
    +
    +
    +def test_boolean_operators_reject_non_boolean_values() -> None:
    +    with pytest.raises(TypeMismatch):
    +        sql_and(1, True)  # type: ignore[arg-type]
    +
    +
    +def test_int64_validation_rejects_python_bigints() -> None:
    +    with pytest.raises(NumericOverflow):
    +        validate_scalar(2**63, DataType.INT64, nullable=False)
    +
    +
    +def test_bool_is_not_inferred_as_int64() -> None:
    +    assert infer_type(True) is DataType.BOOLEAN
    +    assert infer_type(1) is DataType.INT64
    +
    +
    +def test_mixed_numeric_pair_widens_int_to_float() -> None:
    +    left, right, data_type = widen_numeric_pair(2, 1.5)
    +    assert (left, right, data_type) == (2.0, 1.5, DataType.FLOAT64)
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让值与行契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert actual is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是值与行契约。SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。

### 为什么需要这个机制

SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

### 机制板块

#### 值与行契约机制

Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

??? note "文件差异：src/minipostgres/errors.py"
    ```diff
    diff --git a/src/minipostgres/errors.py b/src/minipostgres/errors.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c62d4ca2570ef52330276d1ffb92ea27aacaa9b5
    --- /dev/null
    +++ b/src/minipostgres/errors.py
    @@ -0,0 +1,60 @@
    +"""Typed public errors raised by MiniPostgres."""
    +
    +from __future__ import annotations
    +
    +
    +class MiniPostgresError(Exception):
    +    """Base class for errors intended to cross the public API."""
    +
    +
    +class SqlSyntaxError(MiniPostgresError):
    +    """SQL text is outside the accepted grammar."""
    +
    +
    +class BindError(MiniPostgresError):
    +    """A syntactically valid name or expression cannot be bound."""
    +
    +
    +class TypeMismatch(MiniPostgresError):
    +    """A scalar or expression has an incompatible SQL type."""
    +
    +
    +class NumericOverflow(MiniPostgresError):
    +    """An integer result is outside the signed INT64 range."""
    +
    +
    +class ConstraintViolation(MiniPostgresError):
    +    """A row violates an accepted schema constraint."""
    +
    +
    +class SerializationConflict(MiniPostgresError):
    +    """A concurrent write cannot be serialized at the selected isolation."""
    +
    +
    +class DeadlockDetected(MiniPostgresError):
    +    """The current transaction was selected as a deadlock victim."""
    +
    +
    +class TransactionAborted(MiniPostgresError):
    +    """The transaction is failed and must be rolled back."""
    +
    +
    +class RowTooLarge(MiniPostgresError):
    +    """A tuple cannot fit in one heap page."""
    +
    +
    +class CorruptPage(MiniPostgresError):
    +    """A page failed structural or checksum validation."""
    +
    +
    +class CorruptWal(MiniPostgresError):
    +    """A non-tail WAL record failed structural or checksum validation."""
    +
    +
    +class CatalogError(MiniPostgresError):
    +    """Catalog metadata is invalid or conflicts with existing metadata."""
    +
    +
    +class DatabaseClosed(MiniPostgresError):
    +    """An operation was attempted on a closed database."""
    +
    ```

??? note "文件差异：src/minipostgres/row.py"
    ```diff
    diff --git a/src/minipostgres/row.py b/src/minipostgres/row.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b172b15b1e14662ab1c6470601873eb4abadaa9e
    --- /dev/null
    +++ b/src/minipostgres/row.py
    @@ -0,0 +1,60 @@
    +"""Identifiers and rows shared across query and storage layers."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass, field
    +
    +from minipostgres.types import Scalar
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class TID:
    +    """Stable tuple identifier: a page and a slot within that page."""
    +
    +    page_id: int
    +    slot_id: int
    +
    +    def __post_init__(self) -> None:
    +        if self.page_id < 0 or self.slot_id < 0:
    +            raise ValueError("TID components must be non-negative")
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ColumnBinding:
    +    """Stable catalog identity for one table column."""
    +
    +    table_id: int
    +    column_id: int
    +
    +    def __post_init__(self) -> None:
    +        if self.table_id < 0 or self.column_id < 0:
    +            raise ValueError("column binding components must be non-negative")
    +
    +
    +@dataclass(slots=True)
    +class ExecutionRow:
    +    """Internal row carrying values, source TIDs, and computed aggregates."""
    +
    +    cells: dict[ColumnBinding, Scalar]
    +    tids: dict[int, TID]
    +    computed: dict[object, Scalar] = field(
    +        default_factory=lambda: dict[object, Scalar]()
    +    )
    +
    +    def merge(self, other: ExecutionRow) -> ExecutionRow:
    +        """Merge rows from disjoint relational inputs."""
    +
    +        duplicate_cells = self.cells.keys() & other.cells.keys()
    +        if duplicate_cells:
    +            raise ValueError(f"overlapping column bindings: {duplicate_cells}")
    +        duplicate_tids = self.tids.keys() & other.tids.keys()
    +        if duplicate_tids:
    +            raise ValueError(f"overlapping table TIDs: {duplicate_tids}")
    +        duplicate_computed = self.computed.keys() & other.computed.keys()
    +        if duplicate_computed:
    +            raise ValueError(f"overlapping computed values: {duplicate_computed}")
    +        return ExecutionRow(
    +            cells=self.cells | other.cells,
    +            tids=self.tids | other.tids,
    +            computed=self.computed | other.computed,
    +        )
    ```

??? note "文件差异：src/minipostgres/types.py"
    ```diff
    diff --git a/src/minipostgres/types.py b/src/minipostgres/types.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..bc397687183e855ac708a42b63db0886a49b1d95
    --- /dev/null
    +++ b/src/minipostgres/types.py
    @@ -0,0 +1,163 @@
    +"""SQL scalar types and three-valued primitive operations."""
    +
    +from __future__ import annotations
    +
    +from enum import Enum
    +
    +from minipostgres.errors import NumericOverflow, TypeMismatch
    +
    +INT64_MIN = -(2**63)
    +INT64_MAX = 2**63 - 1
    +
    +
    +class DataType(Enum):
    +    """The frozen MiniPostgres scalar type set."""
    +
    +    INT64 = "int64"
    +    FLOAT64 = "float64"
    +    BOOLEAN = "boolean"
    +    TEXT = "text"
    +
    +
    +type Scalar = int | float | bool | str | None
    +type SqlBool = bool | None
    +
    +
    +def infer_type(value: Scalar) -> DataType | None:
    +    """Return a SQL type for a Python scalar; null is untyped."""
    +
    +    if value is None:
    +        return None
    +    if type(value) is bool:
    +        return DataType.BOOLEAN
    +    if type(value) is int:
    +        return DataType.INT64
    +    if type(value) is float:
    +        return DataType.FLOAT64
    +    if type(value) is str:
    +        return DataType.TEXT
    +    raise TypeMismatch(f"unsupported scalar type: {type(value).__name__}")
    +
    +
    +def validate_int64(value: int) -> int:
    +    """Validate a Python integer against the signed INT64 domain."""
    +
    +    if type(value) is not int:
    +        raise TypeMismatch("expected INT64")
    +    if value < INT64_MIN or value > INT64_MAX:
    +        raise NumericOverflow(f"INT64 value out of range: {value}")
    +    return value
    +
    +
    +def validate_scalar(
    +    value: Scalar,
    +    data_type: DataType,
    +    *,
    +    nullable: bool = True,
    +) -> Scalar:
    +    """Validate one scalar without performing implicit casts."""
    +
    +    if value is None:
    +        if not nullable:
    +            raise TypeMismatch("NULL is not allowed")
    +        return None
    +    actual = infer_type(value)
    +    assert actual is not None
    +    if actual is not data_type:
    +        raise TypeMismatch(f"expected {data_type.value}, got {actual.value}")
    +    if data_type is DataType.INT64:
    +        return validate_int64(value)  # type: ignore[arg-type]
    +    return value
    +
    +
    +def widen_numeric_pair(
    +    left: Scalar,
    +    right: Scalar,
    +) -> tuple[int | float, int | float, DataType]:
    +    """Apply the sole implicit widening to a non-null numeric pair."""
    +
    +    left_type = infer_type(left)
    +    right_type = infer_type(right)
    +    assert left_type is not None
    +    assert right_type is not None
    +    numeric = {DataType.INT64, DataType.FLOAT64}
    +    if left_type not in numeric or right_type not in numeric:
    +        raise TypeMismatch("numeric operands required")
    +    if left_type is DataType.FLOAT64 or right_type is DataType.FLOAT64:
    +        return float(left), float(right), DataType.FLOAT64  # type: ignore[arg-type]
    +    return (
    +        validate_int64(left),  # type: ignore[arg-type]
    +        validate_int64(right),  # type: ignore[arg-type]
    +        DataType.INT64,
    +    )
    +
    +
    +def _require_sql_bool(value: SqlBool) -> None:
    +    if value is not None and type(value) is not bool:
    +        raise TypeMismatch("boolean operand required")
    +
    +
    +def sql_not(value: SqlBool) -> SqlBool:
    +    """SQL NOT over true, false, and unknown."""
    +
    +    _require_sql_bool(value)
    +    return None if value is None else not value
    +
    +
    +def sql_and(left: SqlBool, right: SqlBool) -> SqlBool:
    +    """SQL AND over true, false, and unknown."""
    +
    +    _require_sql_bool(left)
    +    _require_sql_bool(right)
    +    if left is False or right is False:
    +        return False
    +    if left is None or right is None:
    +        return None
    +    return True
    +
    +
    +def sql_or(left: SqlBool, right: SqlBool) -> SqlBool:
    +    """SQL OR over true, false, and unknown."""
    +
    +    _require_sql_bool(left)
    +    _require_sql_bool(right)
    +    if left is True or right is True:
    +        return True
    +    if left is None or right is None:
    +        return None
    +    return False
    +
    +
    +def compare_values(operator: str, left: Scalar, right: Scalar) -> SqlBool:
    +    """Compare compatible scalars with SQL null propagation."""
    +
    +    if left is None or right is None:
    +        return None
    +    left_type = infer_type(left)
    +    right_type = infer_type(right)
    +    assert left_type is not None
    +    assert right_type is not None
    +    if left_type in {DataType.INT64, DataType.FLOAT64} and right_type in {
    +        DataType.INT64,
    +        DataType.FLOAT64,
    +    }:
    +        comparable_left, comparable_right, _ = widen_numeric_pair(left, right)
    +    elif left_type is right_type:
    +        comparable_left, comparable_right = left, right
    +    else:
    +        raise TypeMismatch(
    +            f"cannot compare {left_type.value} with {right_type.value}"
    +        )
    +    if operator == "=":
    +        return comparable_left == comparable_right
    +    if operator in {"!=", "<>"}:
    +        return comparable_left != comparable_right
    +    if operator == "<":
    +        return comparable_left < comparable_right  # type: ignore[operator]
    +    if operator == "<=":
    +        return comparable_left <= comparable_right  # type: ignore[operator]
    +    if operator == ">":
    +        return comparable_left > comparable_right  # type: ignore[operator]
    +    if operator == ">=":
    +        return comparable_left >= comparable_right  # type: ignore[operator]
    +    raise TypeMismatch(f"unsupported comparison operator: {operator}")
    ```

**是什么，为什么现在需要**

核心机制是值与行契约。SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。

**在运行时做什么**

Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

**关键语句理解**

真正要守住的边界是：Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（4 个文件）"
    **`README.md`**

    ```diff
    diff --git a/README.md b/README.md
    new file mode 100644
    index 0000000000000000000000000000000000000000..b055eb86db02ece029986756d3d3fafaac155607
    --- /dev/null
    +++ b/README.md
    @@ -0,0 +1,5 @@
    +# MiniPostgres
    +
    +Reference implementation in progress. The accepted design is in
    +`docs/superpowers/specs/2026-07-27-minipostgres-reference-project-design.md`.
    +
    ```

    **`pyproject.toml`**

    ```diff
    diff --git a/pyproject.toml b/pyproject.toml
    new file mode 100644
    index 0000000000000000000000000000000000000000..11a1ffdee6391c56deb95cfd663a577c4d991119
    --- /dev/null
    +++ b/pyproject.toml
    @@ -0,0 +1,39 @@
    +[build-system]
    +requires = ["hatchling"]
    +build-backend = "hatchling.build"
    +
    +[project]
    +name = "mini-postgres"
    +version = "0.1.0"
    +description = "A PostgreSQL-inspired single-process relational database kernel"
    +readme = "README.md"
    +requires-python = ">=3.12"
    +dependencies = []
    +
    +[dependency-groups]
    +dev = [
    +    "hypothesis>=6.136",
    +    "pyright>=1.1.403",
    +    "pytest>=8.4",
    +    "ruff>=0.12",
    +]
    +
    +[tool.hatch.build.targets.wheel]
    +packages = ["src/minipostgres"]
    +
    +[tool.pytest.ini_options]
    +addopts = "-ra"
    +testpaths = ["tests"]
    +
    +[tool.ruff]
    +line-length = 88
    +target-version = "py312"
    +
    +[tool.ruff.lint]
    +select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
    +
    +[tool.pyright]
    +include = ["src", "tests"]
    +pythonVersion = "3.12"
    +typeCheckingMode = "strict"
    +
    ```

    **`src/minipostgres/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/__init__.py b/src/minipostgres/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..20d2556d691b20ac722e5d7c8fd03caa1fe74e58
    --- /dev/null
    +++ b/src/minipostgres/__init__.py
    @@ -0,0 +1,6 @@
    +"""Public package for the MiniPostgres reference database."""
    +
    +from minipostgres.types import DataType, Scalar
    +
    +__all__ = ["DataType", "Scalar"]
    +
    ```

    **`uv.lock`**

    ```diff
    diff --git a/uv.lock b/uv.lock
    new file mode 100644
    index 0000000000000000000000000000000000000000..a8b37b29b18074ed058fe627b0f95dd5466af9ee
    --- /dev/null
    +++ b/uv.lock
    @@ -0,0 +1,205 @@
    +version = 1
    +revision = 3
    +requires-python = ">=3.12"
    +
    +[[package]]
    +name = "colorama"
    +version = "0.4.6"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz", hash = "sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44", size = 27697, upload-time = "2022-10-25T02:36:22.414Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/d1/d6/3965ed04c63042e047cb6a3e6ed1a63a35087b6a609aa3a15ed8ac56c221/colorama-0.4.6-py2.py3-none-any.whl", hash = "sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6", size = 25335, upload-time = "2022-10-25T02:36:20.889Z" },
    +]
    +
    +[[package]]
    +name = "hypothesis"
    +version = "6.161.8"
    +source = { registry = "https://pypi.org/simple" }
    +dependencies = [
    +    { name = "sortedcontainers" },
    +]
    +sdist = { url = "https://files.pythonhosted.org/packages/59/2f/1a67b70064587eb05fddf59964de2a7dedf4135786b4b150ff18dc16a8db/hypothesis-6.161.8.tar.gz", hash = "sha256:d37360094e6203473b15e3cad7ecfb2e08fbd8acaabd8c730dc126cb597fde1c", size = 487771, upload-time = "2026-07-27T20:42:28.898Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/49/1e/bdf7091f82974a26a92850a5539aba20c348e0ffcd4ee48f0f2d020cc3de/hypothesis-6.161.8-cp310-abi3-macosx_10_12_x86_64.whl", hash = "sha256:5b575502ffacd5ac5d3f4a777f0d22b5188693904af876dd46614c12476b4fde", size = 767838, upload-time = "2026-07-27T20:41:00.123Z" },
    +    { url = "https://files.pythonhosted.org/packages/9a/21/4b0718501b1bd05a7be4711277eef8684d1cb7cfb1d4e41554ce47789933/hypothesis-6.161.8-cp310-abi3-macosx_11_0_arm64.whl", hash = "sha256:eb3dd046c8ab7efaeaa5416f4ad1778544ca798f8091284543c814fc73312fad", size = 763377, upload-time = "2026-07-27T20:42:07.77Z" },
    +    { url = "https://files.pythonhosted.org/packages/c8/b6/d7f4848df0d470aa2cdfb3aee7e5261ab494ce18b6e4410f45ef3ff86f58/hypothesis-6.161.8-cp310-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:88d0850723b7c7afe2a0b1372217bf398da2d7ce232907e2debe0075be579fe4", size = 1092627, upload-time = "2026-07-27T20:41:35.883Z" },
    +    { url = "https://files.pythonhosted.org/packages/0c/17/89d48ec82acc56d4894f41ff395258ff0b34539413f205379c7ed4682cb0/hypothesis-6.161.8-cp310-abi3-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:89df776cae9ed73819134c52a3826f351bcb8aadcf7ef69fbe04b1e9306d7a5d", size = 1121255, upload-time = "2026-07-27T20:41:40.298Z" },
    +    { url = "https://files.pythonhosted.org/packages/29/16/6fc009137435bc88d3189ca0ba616727ea46a3efc76afba7e98a4f6a38c1/hypothesis-6.161.8-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:ad8042c20cfaf4d4a679d45725289d639c171bc2d6473238457879d9cfd6a1d6", size = 1142117, upload-time = "2026-07-27T20:42:26.991Z" },
    +    { url = "https://files.pythonhosted.org/packages/26/4d/5e828d3bc3956509cbc5de404e511650cd48473c608a9de0c65952c27994/hypothesis-6.161.8-cp310-abi3-manylinux_2_31_riscv64.whl", hash = "sha256:d4063bbef8f704a68a1c1406ba4496d3373c8d60cdaf261660f2422e3257033a", size = 1097481, upload-time = "2026-07-27T20:40:56.574Z" },
    +    { url = "https://files.pythonhosted.org/packages/b8/d4/beb843943e50e85fc505d618cf914fd646e9864219992d26c1ad4043f1ae/hypothesis-6.161.8-cp310-abi3-manylinux_2_5_i686.manylinux1_i686.whl", hash = "sha256:5a61fd3a9288d5d5543a54c0b363ba2c600815314d89a7eb8a6b3983ac89e255", size = 1134249, upload-time = "2026-07-27T20:41:12.5Z" },
    +    { url = "https://files.pythonhosted.org/packages/a0/ae/b166d504748b7ac014587d14a8aa624a17cb9266219bf48d7859747a0ab9/hypothesis-6.161.8-cp310-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:7a26b54b04579edc8e647dbc0745a0deff96e15a7fa28148ffe7f52f006da57a", size = 1266460, upload-time = "2026-07-27T20:42:04.634Z" },
    +    { url = "https://files.pythonhosted.org/packages/3a/88/1f769673b066df75825c30e9c14d177288cff6ec0af3c74b4880a1590fdc/hypothesis-6.161.8-cp310-abi3-musllinux_1_2_armv7l.whl", hash = "sha256:37dfb915fb24626d8b4f8a99e50d7bdfd7cae044fca170d99e699cdca1dc5421", size = 1394302, upload-time = "2026-07-27T20:40:57.705Z" },
    +    { url = "https://files.pythonhosted.org/packages/5b/4e/712bf26800cbc6a0628c24ecc7ba950a7f0c7b25556bd67a582aa56bed0b/hypothesis-6.161.8-cp310-abi3-musllinux_1_2_riscv64.whl", hash = "sha256:775f65cde6caa1392a1be122dea02cb091650f9dd85d412abe9151931c2c91ba", size = 1266919, upload-time = "2026-07-27T20:41:10.024Z" },
    +    { url = "https://files.pythonhosted.org/packages/77/a8/6b345a74e54b2eb90b729fb98e0fc13356598d27dd64bd896e99a8222868/hypothesis-6.161.8-cp310-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:12847e53cc26f7d58d84c32156c6d0ac52458c26e5ab99f6d423d43124a18680", size = 1309133, upload-time = "2026-07-27T20:41:06.259Z" },
    +    { url = "https://files.pythonhosted.org/packages/b1/c2/c70fd4532c0a6e4bc872054b5c42035c87894b84a60ef959cbdd0e2bcac5/hypothesis-6.161.8-cp310-abi3-win32.whl", hash = "sha256:359e632148a843d326985856e35b4ceb9ab586089de62e46f3f7fb2f22d7d32a", size = 653688, upload-time = "2026-07-27T20:41:42.022Z" },
    +    { url = "https://files.pythonhosted.org/packages/3f/86/7ac7ad3d0fb9ac3f6da84b9e4d366262d05e192a5a1975b1b64d142b056f/hypothesis-6.161.8-cp310-abi3-win_amd64.whl", hash = "sha256:5eadf691d1a7177a962cf379ae413a2527a1f3a1219d9e5fcf35e12707e72a88", size = 659841, upload-time = "2026-07-27T20:41:22.386Z" },
    +    { url = "https://files.pythonhosted.org/packages/ab/1b/2569623d32daecd0b35f5686691e7375bedbbb85bc5aa49f6f742ce7dee0/hypothesis-6.161.8-cp312-cp312-macosx_10_12_x86_64.whl", hash = "sha256:8f3679076ef3e9efd7cfa7ea1c997f9687725e628ebdeef69d385ef3164b6269", size = 769428, upload-time = "2026-07-27T20:42:02.954Z" },
    +    { url = "https://files.pythonhosted.org/packages/bf/0a/d22fa179497e45456a6e97f150dc8b00f0b4ead67a4d09c892b2907a1fc7/hypothesis-6.161.8-cp312-cp312-macosx_11_0_arm64.whl", hash = "sha256:1ea8de981d40a68cb739f67053df2aab6c2e23c337f08da3c3e9ad31f356bfcf", size = 760997, upload-time = "2026-07-27T20:42:23.47Z" },
    +    { url = "https://files.pythonhosted.org/packages/15/23/50e1224bcb1683633beb9ee36c21f59531fa86ccb3c9ef0d65732f5ac035/hypothesis-6.161.8-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:4338436e20c0d5e494c905288364600783edbabeeb19ab5b50746ce631980cd9", size = 1091438, upload-time = "2026-07-27T20:41:50.186Z" },
    +    { url = "https://files.pythonhosted.org/packages/33/63/f6c610567c0eff8c434fdbded63a80f1af60d634b8c13e53670b97887f72/hypothesis-6.161.8-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:7eff53a5d0ef11db420e467c836229b7c07afee183d69adf3aa9c2bca6ba1365", size = 1141504, upload-time = "2026-07-27T20:41:23.755Z" },
    +    { url = "https://files.pythonhosted.org/packages/dd/30/2b0eeea1ff97a97726cd29e93b0a576fece7b7878ef8d3b2ea1f5dbb3acf/hypothesis-6.161.8-cp312-cp312-musllinux_1_2_aarch64.whl", hash = "sha256:3827fd23cd9447bbbd86a307cd1d8e7c545ca6a0f180ffa3f0e3985d8f8e3c8a", size = 1264263, upload-time = "2026-07-27T20:41:56.356Z" },
    +    { url = "https://files.pythonhosted.org/packages/3f/1a/c709ecb4c082e413d464d9d67f8b74612b7518397b7511430cee491c4503/hypothesis-6.161.8-cp312-cp312-musllinux_1_2_x86_64.whl", hash = "sha256:b9b9e69ae32b4a1854f69edfceb0c2f69300108b367ad99bfd6fe1044ca0fa8f", size = 1308470, upload-time = "2026-07-27T20:41:20.814Z" },
    +    { url = "https://files.pythonhosted.org/packages/7d/a9/823db2d2a9b8ec504b2bec5c704cc20fac983d38b396cfef8f29c26898a2/hypothesis-6.161.8-cp312-cp312-win_amd64.whl", hash = "sha256:74c2344e132679a386b91bb2d39ac23a378a084f3bcca31ed477e26f1aaef096", size = 656964, upload-time = "2026-07-27T20:41:59.334Z" },
    +    { url = "https://files.pythonhosted.org/packages/64/1a/79e7459e5a40379bffcd5a3b55c9e8d4925c68bc8d635f14900c44aa22d1/hypothesis-6.161.8-cp313-cp313-macosx_10_12_x86_64.whl", hash = "sha256:f1609a8c76d17016cfeda0c713340134bcfe8795183bca8282a4b59734f5cdd1", size = 769320, upload-time = "2026-07-27T20:41:38.893Z" },
    +    { url = "https://files.pythonhosted.org/packages/17/47/f33bc8ddeb45ac03d92f7157990290ba402a73e7e6e2d3d8184bfc9ce606/hypothesis-6.161.8-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:dd695f63adc27468f13c2bf531a784d62517f498365aa755e3ac0e603dc43719", size = 760961, upload-time = "2026-07-27T20:42:20.067Z" },
    +    { url = "https://files.pythonhosted.org/packages/15/f5/7f1bad0915dbba089c14d69bca8fa69415869c1a18439bf27d404fd3289c/hypothesis-6.161.8-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:6b3e2b1bdd235790f512b2a2bb4be909f8c8d313a924a8b6a321f89b62392bf7", size = 1091354, upload-time = "2026-07-27T20:41:02.809Z" },
    +    { url = "https://files.pythonhosted.org/packages/af/dc/39440c14ab7093294108ff6fd2e05bbf7cdd0a7857b61f049cf7fe5a94f2/hypothesis-6.161.8-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:7e8e38a8e96230815fe048f961dabcb2299293714c08ccf6607110325a24a5a5", size = 1141316, upload-time = "2026-07-27T20:41:03.966Z" },
    +    { url = "https://files.pythonhosted.org/packages/23/0e/d05d9b2f95394c8593bfc2ecc6a8bc1af6ccf3459b86e96b80949b11357d/hypothesis-6.161.8-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:443ed3353b8c64ff3149d93a423e3ea461246b40a84efe5d0cf8e666c62b30b0", size = 1264304, upload-time = "2026-07-27T20:41:16.577Z" },
    +    { url = "https://files.pythonhosted.org/packages/62/ab/c0818b324d930cb608d644117bdbab572b2a018288704fccacd0b39de7d3/hypothesis-6.161.8-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:b5618bc2defc2db09081eaf42f9c0cbcb7a38402a9059c19fa2aafff06ec821e", size = 1308210, upload-time = "2026-07-27T20:42:21.756Z" },
    +    { url = "https://files.pythonhosted.org/packages/f5/4f/d1abdbdf4739adbb63354b9925e011a85ca47f5728a999dd577970f3271c/hypothesis-6.161.8-cp313-cp313-win_amd64.whl", hash = "sha256:3ab3a7311ad78878e3ada8dc85752da4b500102bdeaf25f0977d0b673344d794", size = 656924, upload-time = "2026-07-27T20:41:43.686Z" },
    +    { url = "https://files.pythonhosted.org/packages/80/67/88eae3441dae73b841077229f0160161d8a096ab00e91d393e7ffdd508f1/hypothesis-6.161.8-cp314-cp314-macosx_10_12_x86_64.whl", hash = "sha256:9b7c4758828150bba5df896518e9d2740dd1344ae150f81a63f0babeafa64b95", size = 769534, upload-time = "2026-07-27T20:42:17.801Z" },
    +    { url = "https://files.pythonhosted.org/packages/7f/27/3947531746040650117e600e1e7d40384c4385d6000e82c33d4c0be675d7/hypothesis-6.161.8-cp314-cp314-macosx_11_0_arm64.whl", hash = "sha256:8cbdb9f96961fbabee1acbc0bbc6224176e5bc3eaceb68ec19819a6edd6e866d", size = 761092, upload-time = "2026-07-27T20:41:47.13Z" },
    +    { url = "https://files.pythonhosted.org/packages/7b/3b/5fc2684c7e4a069a02e60c41d12aea1857c5a86235d979a6750b91ff491e/hypothesis-6.161.8-cp314-cp314-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:11d5b887571a8529cd2fb3a91ca3ee8746a2dc0e6be52827ee89b05b6c051b68", size = 1091854, upload-time = "2026-07-27T20:41:19.303Z" },
    +    { url = "https://files.pythonhosted.org/packages/9a/d2/d0d5298ec36b1606d89ea6fe6e39d1fff280e81fc1eecf91b4dd55d8bcbd/hypothesis-6.161.8-cp314-cp314-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:25cfe8cb7890a9f5f72a5b7c9e7bd39685c3f6898bf9003db09a85283f8ed5b0", size = 1141563, upload-time = "2026-07-27T20:41:18.01Z" },
    +    { url = "https://files.pythonhosted.org/packages/94/b4/475d0ad4ea2643ac80a331444664630d0746bc0c7dba9ab8e486123bcc60/hypothesis-6.161.8-cp314-cp314-musllinux_1_2_aarch64.whl", hash = "sha256:b0f07e7818c3ba3b917954240f1f3419c732070a47fdc5e909749d93b37878f9", size = 1264638, upload-time = "2026-07-27T20:42:12.632Z" },
    +    { url = "https://files.pythonhosted.org/packages/b3/fd/93ed917b3fc1120abb96feb5e7e2ba102c1ff5ce9faec9185bdb90cf2a05/hypothesis-6.161.8-cp314-cp314-musllinux_1_2_x86_64.whl", hash = "sha256:321194305d9a7933ca8bd3c4276484021f6a121859b62deb67dad9502993dce5", size = 1308505, upload-time = "2026-07-27T20:41:53.276Z" },
    +    { url = "https://files.pythonhosted.org/packages/0e/59/16a8e14d3917ffb5969d2ee745beef23990d758ca468f740745b00e31d55/hypothesis-6.161.8-cp314-cp314-pyemscripten_2026_0_wasm32.whl", hash = "sha256:233c6e74ca0e6c51bb1082e67deca4bc7ff383ccea8177b79f3b29f50cb3b1d8", size = 601018, upload-time = "2026-07-27T20:42:11.004Z" },
    +    { url = "https://files.pythonhosted.org/packages/fc/cf/1feeb6289d2f1eba404c9aeacd4aef2c21f7fd6ead672101d840fae21e61/hypothesis-6.161.8-cp314-cp314-win_amd64.whl", hash = "sha256:ca46cb623eea27873f89703b92d3ad639b4c6f9c9fbb073714a619f1c2eaa316", size = 656873, upload-time = "2026-07-27T20:40:58.907Z" },
    +    { url = "https://files.pythonhosted.org/packages/28/d2/c928a171e0274284a23c54c09be8c133e4493738c441541dcc2878b1fa0a/hypothesis-6.161.8-cp314-cp314t-macosx_10_12_x86_64.whl", hash = "sha256:108078b1d6ec8f7eec89457ce367a6397e6bcde86fbffa244ae19c524f564926", size = 768113, upload-time = "2026-07-27T20:42:01.276Z" },
    +    { url = "https://files.pythonhosted.org/packages/a7/d4/830f12f769c2ad373c93c2b45eb1dbabe17b3861f26e9a801d2926cb17a3/hypothesis-6.161.8-cp314-cp314t-macosx_11_0_arm64.whl", hash = "sha256:2d670152729fc08cafaa8f73ccd18920234ab4098f9f8881e068a7a4240235d6", size = 759559, upload-time = "2026-07-27T20:41:15.142Z" },
    +    { url = "https://files.pythonhosted.org/packages/58/a2/3dd916c80396eb630dd8a396bdb367395973bebda3490f8ff7605c99b3d9/hypothesis-6.161.8-cp314-cp314t-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:b91af499d1649bd4b26ed0b31d3b5adfcaae2498f28bf14833f494ab3c3d58ee", size = 1090450, upload-time = "2026-07-27T20:41:57.834Z" },
    +    { url = "https://files.pythonhosted.org/packages/b2/d8/02d3f8cd9de6b90d6cad833fdc27bf818d31f12ab05df3072a1c6b384b2b/hypothesis-6.161.8-cp314-cp314t-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:91d91cd991f6f79fe034dd088d55ac8aa713907dcb42b5ddf6583015d837cc32", size = 1140382, upload-time = "2026-07-27T20:42:09.486Z" },
    +    { url = "https://files.pythonhosted.org/packages/f2/3c/291c70bed39d7062b274ec8edc3c1176eea1eb424b2c46767d242335026a/hypothesis-6.161.8-cp314-cp314t-musllinux_1_2_aarch64.whl", hash = "sha256:c2f88729e5fd1400a3fcf28429d7d3fc6853cf0b3094b4050befb9a4b1b7517d", size = 1262874, upload-time = "2026-07-27T20:42:25.109Z" },
    +    { url = "https://files.pythonhosted.org/packages/b8/ef/c25062d285f8fca398b916082efa10574683da3bfbaef1fe81f7857e934a/hypothesis-6.161.8-cp314-cp314t-musllinux_1_2_x86_64.whl", hash = "sha256:f49c1a4e6158168d5b2255e3e5dbd48ecd020127668c1a02fa9ed64b83fc0008", size = 1307228, upload-time = "2026-07-27T20:41:48.594Z" },
    +    { url = "https://files.pythonhosted.org/packages/6a/d2/b006970d5261eef3729e3d5331a4a39d08d532977e230b12820e8587da02/hypothesis-6.161.8-cp314-cp314t-win_amd64.whl", hash = "sha256:efef18d65a9f08009e7036d445a48122f484c05678993e6febaf07cb8e3a8b04", size = 657005, upload-time = "2026-07-27T20:41:25.083Z" },
    +]
    +
    +[[package]]
    +name = "iniconfig"
    +version = "2.3.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/72/34/14ca021ce8e5dfedc35312d08ba8bf51fdd999c576889fc2c24cb97f4f10/iniconfig-2.3.0.tar.gz", hash = "sha256:c76315c77db068650d49c5b56314774a7804df16fee4402c1f19d6d15d8c4730", size = 20503, upload-time = "2025-10-18T21:55:43.219Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl", hash = "sha256:f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12", size = 7484, upload-time = "2025-10-18T21:55:41.639Z" },
    +]
    +
    +[[package]]
    +name = "mini-postgres"
    +version = "0.1.0"
    +source = { editable = "." }
    +
    +[package.dev-dependencies]
    +dev = [
    +    { name = "hypothesis" },
    +    { name = "pyright" },
    +    { name = "pytest" },
    +    { name = "ruff" },
    +]
    +
    +[package.metadata]
    +
    +[package.metadata.requires-dev]
    +dev = [
    +    { name = "hypothesis", specifier = ">=6.136" },
    +    { name = "pyright", specifier = ">=1.1.403" },
    +    { name = "pytest", specifier = ">=8.4" },
    +    { name = "ruff", specifier = ">=0.12" },
    +]
    +
    +[[package]]
    +name = "nodeenv"
    +version = "1.10.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/24/bf/d1bda4f6168e0b2e9e5958945e01910052158313224ada5ce1fb2e1113b8/nodeenv-1.10.0.tar.gz", hash = "sha256:996c191ad80897d076bdfba80a41994c2b47c68e224c542b48feba42ba00f8bb", size = 55611, upload-time = "2025-12-20T14:08:54.006Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/88/b2/d0896bdcdc8d28a7fc5717c305f1a861c26e18c05047949fb371034d98bd/nodeenv-1.10.0-py2.py3-none-any.whl", hash = "sha256:5bb13e3eed2923615535339b3c620e76779af4cb4c6a90deccc9e36b274d3827", size = 23438, upload-time = "2025-12-20T14:08:52.782Z" },
    +]
    +
    +[[package]]
    +name = "packaging"
    +version = "26.2"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/d7/f1/e7a6dd94a8d4a5626c03e4e99c87f241ba9e350cd9e6d75123f992427270/packaging-26.2.tar.gz", hash = "sha256:ff452ff5a3e828ce110190feff1178bb1f2ea2281fa2075aadb987c2fb221661", size = 228134, upload-time = "2026-04-24T20:15:23.917Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/df/b2/87e62e8c3e2f4b32e5fe99e0b86d576da1312593b39f47d8ceef365e95ed/packaging-26.2-py3-none-any.whl", hash = "sha256:5fc45236b9446107ff2415ce77c807cee2862cb6fac22b8a73826d0693b0980e", size = 100195, upload-time = "2026-04-24T20:15:22.081Z" },
    +]
    +
    +[[package]]
    +name = "pluggy"
    +version = "1.6.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz", hash = "sha256:7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3", size = 69412, upload-time = "2025-05-15T12:30:07.975Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl", hash = "sha256:e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746", size = 20538, upload-time = "2025-05-15T12:30:06.134Z" },
    +]
    +
    +[[package]]
    +name = "pygments"
    +version = "2.20.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz", hash = "sha256:6757cd03768053ff99f3039c1a36d6c0aa0b263438fcab17520b30a303a82b5f", size = 4955991, upload-time = "2026-03-29T13:29:33.898Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/f4/7e/a72dd26f3b0f4f2bf1dd8923c85f7ceb43172af56d63c7383eb62b332364/pygments-2.20.0-py3-none-any.whl", hash = "sha256:81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176", size = 1231151, upload-time = "2026-03-29T13:29:30.038Z" },
    +]
    +
    +[[package]]
    +name = "pyright"
    +version = "1.1.411"
    +source = { registry = "https://pypi.org/simple" }
    +dependencies = [
    +    { name = "nodeenv" },
    +    { name = "typing-extensions" },
    +]
    +sdist = { url = "https://files.pythonhosted.org/packages/7e/ab/265f7dc69d28113ebba19092e57b075f41543b2ed048429c5f56e2b88eac/pyright-1.1.411.tar.gz", hash = "sha256:d885a0551f2e763b089a02702174e7f4ba77548cddabc972ab86d1f7f1b0f998", size = 4112861, upload-time = "2026-06-25T02:14:06.37Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/0a/49/385be530a6a5b78d1cbcd5c2e38debc8959a2fc6bdb716f4e581002979fc/pyright-1.1.411-py3-none-any.whl", hash = "sha256:dc7c72a8e2700c55baa127554040e067041ea53ccfd50bf96308cc4291c7d5d9", size = 6181526, upload-time = "2026-06-25T02:14:04.691Z" },
    +]
    +
    +[[package]]
    +name = "pytest"
    +version = "9.1.1"
    +source = { registry = "https://pypi.org/simple" }
    +dependencies = [
    +    { name = "colorama", marker = "sys_platform == 'win32'" },
    +    { name = "iniconfig" },
    +    { name = "packaging" },
    +    { name = "pluggy" },
    +    { name = "pygments" },
    +]
    +sdist = { url = "https://files.pythonhosted.org/packages/e4/47/b9efed96c114afcfa3c9d3fe98a76a1d14c74a9e266d397cf6eb64be5e01/pytest-9.1.1.tar.gz", hash = "sha256:1088fbde8f2b49d95a549a195707afa7a76a3ce9bcadc26b6d71f0ffda5fe313", size = 1636369, upload-time = "2026-06-19T10:58:32.857Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl", hash = "sha256:37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c", size = 386536, upload-time = "2026-06-19T10:58:31.347Z" },
    +]
    +
    +[[package]]
    +name = "ruff"
    +version = "0.16.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/4d/94/1e5e4967626faf12fa56999cd6222dff6992ceb086ad7945756baf70c7a7/ruff-0.16.0.tar.gz", hash = "sha256:e460aafd5495ec89efaa6ced2e4a9a581116451e1c88b9d37ef497e0f8e93982", size = 4790557, upload-time = "2026-07-23T19:11:30.981Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/4b/81/1c8818fee7ce1a04cd7d1b3172e0a8f8e4f1dc4feb7fc390e16daa8af323/ruff-0.16.0-py3-none-linux_armv6l.whl", hash = "sha256:e5115729eb08c585e5121978ba5d5b60caeae394ce21b9fb5e6cd33a1c6c9b1e", size = 10754633, upload-time = "2026-07-23T19:10:46.415Z" },
    +    { url = "https://files.pythonhosted.org/packages/23/df/beaf59c09d68db84304d555f188b276a77132a5d5b0b67a5c762aa143628/ruff-0.16.0-py3-none-macosx_10_12_x86_64.whl", hash = "sha256:3c954b1d580bfa035b41654f7858cc7e71d5fc3ac5b723dd62bd9133830ed522", size = 10969164, upload-time = "2026-07-23T19:10:50.271Z" },
    +    { url = "https://files.pythonhosted.org/packages/42/ce/741cd197496a1abbf51352710fd15ed995d2a2be87189c1da26a450d6e83/ruff-0.16.0-py3-none-macosx_11_0_arm64.whl", hash = "sha256:e01c21d10eb1b29f47b7454e1f4056db9a3f0260c646aa88457c610291db9f81", size = 10488846, upload-time = "2026-07-23T19:10:52.639Z" },
    +    { url = "https://files.pythonhosted.org/packages/52/2a/a2db8e88cade358f5cdcb05674a917751074109315d014eb6352d9a893f7/ruff-0.16.0-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:6e364e5ed22ed8dc05082fd78e35308618260907ac2d3c1d637b2e682415b6c9", size = 10889729, upload-time = "2026-07-23T19:10:54.89Z" },
    +    { url = "https://files.pythonhosted.org/packages/42/65/62a771694ebd63029dc953e27dbad40e1588bd4860ff9fe881018fddaa49/ruff-0.16.0-py3-none-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:d327b8fc113a1d4421a04f3839d3752057c8dd1ee320223a6f3f52d04ada462a", size = 10568275, upload-time = "2026-07-23T19:10:56.993Z" },
    +    { url = "https://files.pythonhosted.org/packages/3f/e2/ced249fe8af5f086c5c58cc21cc3356d50f32f7401c5df87050c999620a7/ruff-0.16.0-py3-none-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:a9b50c55e263103586b3dcf5f73d479eb8cb5fdb6098fec59a62891dab653717", size = 11385112, upload-time = "2026-07-23T19:10:59.615Z" },
    +    { url = "https://files.pythonhosted.org/packages/87/0b/05154977a8fd69eeb6c103271f55403bfd8711f5c0f8ed07489d95a504e7/ruff-0.16.0-py3-none-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:0ff4a79ce3ec0172f3241943835de1c4cb4e2dcd07f0f8c2d02603dbbbee4b17", size = 12207008, upload-time = "2026-07-23T19:11:02.154Z" },
    +    { url = "https://files.pythonhosted.org/packages/fb/29/98225831a3a1eab0e02f4acc6ca6559a98611dcc68b6965ff4b7234627c1/ruff-0.16.0-py3-none-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:e95c448fca1fb2a18372a9440926c5a6ee789639bb975c72e7ae6d0b04218ab4", size = 11650842, upload-time = "2026-07-23T19:11:04.557Z" },
    +    { url = "https://files.pythonhosted.org/packages/91/66/6bd3cf90500653d55dc0ffc8507aa8300bd49d0214b2e8cb4d3fef2943ba/ruff-0.16.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:4f11a8d11010301d0a398a2fdef67691feca7294da6aef55e2150e8fa2cd520b", size = 11400718, upload-time = "2026-07-23T19:11:09.233Z" },
    +    { url = "https://files.pythonhosted.org/packages/8e/a2/a54eb4eae05d66364050a5d3b8a9c5ef88196531b3cbe7109d873f87f819/ruff-0.16.0-py3-none-manylinux_2_31_riscv64.whl", hash = "sha256:48044c678e9cb8698246c99b14aaccfa6601dea7379eb48a6f8f73f7a6d86cd0", size = 11426177, upload-time = "2026-07-23T19:11:11.994Z" },
    +    { url = "https://files.pythonhosted.org/packages/1a/be/16e3eea4b2a478a496919f5e36f17c4559e54620bd3bbac5d6affa068006/ruff-0.16.0-py3-none-musllinux_1_2_aarch64.whl", hash = "sha256:7aa0959bad8eb8bef50340154fc9b58678dae31fa4293afa38b44b6e552c0213", size = 10856126, upload-time = "2026-07-23T19:11:14.221Z" },
    +    { url = "https://files.pythonhosted.org/packages/a2/84/252eb8b868a16eec7257c14f504f77537e734b2d69c762e639e588e304a3/ruff-0.16.0-py3-none-musllinux_1_2_armv7l.whl", hash = "sha256:28ea2b7df8ebf7f9da6b7d47b230ab48f387c0a29be3b474c4d0740e197bb9af", size = 10571208, upload-time = "2026-07-23T19:11:16.378Z" },
    +    { url = "https://files.pythonhosted.org/packages/21/09/817a482f542f7570cbb4554b26e896610c7114f539b1d9e2d2145bf6bef6/ruff-0.16.0-py3-none-musllinux_1_2_i686.whl", hash = "sha256:33a3dfac8c35f81498dea9181bccc2f4c4bc8f1521a1dd9406e77643e0f0fb09", size = 11063329, upload-time = "2026-07-23T19:11:19.173Z" },
    +    { url = "https://files.pythonhosted.org/packages/2e/23/9403c180ca1cb9b1f7335f5c3e5305c09d49ea5b345196682a36028bde4a/ruff-0.16.0-py3-none-musllinux_1_2_x86_64.whl", hash = "sha256:a5237a0bda500d30d81b8e07a6973a5cbc772864cbf746ae2f4e8a2e01c9f4ed", size = 11489751, upload-time = "2026-07-23T19:11:21.74Z" },
    +    { url = "https://files.pythonhosted.org/packages/b2/1d/1b2ef7bcde851c78d7f17f1cca13fd6dc695fc4b3d6197941e72cae5b132/ruff-0.16.0-py3-none-win32.whl", hash = "sha256:7fab76fa065c873f41ff744347c6e77bcc3dfec4bcc754dc26b63d23c0f7f5fb", size = 10785885, upload-time = "2026-07-23T19:11:23.947Z" },
    +    { url = "https://files.pythonhosted.org/packages/b2/a3/d5e4ef7a56be3f928ffb90b94c25ba7d3cb9c7fe0736aeaaedf361770712/ruff-0.16.0-py3-none-win_amd64.whl", hash = "sha256:429c117f022bf481fabd9d551e7a3952b24c65e6ef44337ea09d90bebef14472", size = 11923141, upload-time = "2026-07-23T19:11:26.409Z" },
    +    { url = "https://files.pythonhosted.org/packages/cb/9a/8415f2657cbe200f41a4531ccededf135505a92d4a012229121f885b26f9/ruff-0.16.0-py3-none-win_arm64.whl", hash = "sha256:14296fedcd2705c77ab8235439278bbb38f285cf7da5528b00b3e330c3d4872d", size = 11273407, upload-time = "2026-07-23T19:11:28.705Z" },
    +]
    +
    +[[package]]
    +name = "sortedcontainers"
    +version = "2.4.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/e8/c4/ba2f8066cceb6f23394729afe52f3bf7adec04bf9ed2c820b39e19299111/sortedcontainers-2.4.0.tar.gz", hash = "sha256:25caa5a06cc30b6b83d11423433f65d1f9d76c4c6a0c90e3379eaa43b9bfdb88", size = 30594, upload-time = "2021-05-16T22:03:42.897Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/32/46/9cb0e58b2deb7f82b84065f37f3bffeb12413f947f9388e4cac22c4621ce/sortedcontainers-2.4.0-py2.py3-none-any.whl", hash = "sha256:a163dcaede0f1c021485e957a39245190e74249897e2ae4b2aa38595db237ee0", size = 29575, upload-time = "2021-05-16T22:03:41.177Z" },
    +]
    +
    +[[package]]
    +name = "typing-extensions"
    +version = "4.16.0"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3306cebfbda2c520f545d36b5be2c7255cc528bb45d6/typing_extensions-4.16.0.tar.gz", hash = "sha256:dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5", size = 113555, upload-time = "2026-07-02T08:40:05.92Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl", hash = "sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8", size = 45571, upload-time = "2026-07-02T08:40:04.659Z" },
    +]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/01-value-row-contract/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 1 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/01-getting-started.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/01-value-row-contract/stage.patch)
