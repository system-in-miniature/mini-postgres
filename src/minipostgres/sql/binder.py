"""Catalog-aware name and type binding for MiniPostgres SQL."""

from __future__ import annotations

from dataclasses import dataclass

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column, TableMetadata
from minipostgres.errors import BindError, CatalogError, NumericOverflow, TypeMismatch
from minipostgres.row import ColumnBinding
from minipostgres.sql.ast import (
    AnalyzeStmt,
    BeginStmt,
    BinaryExpr,
    ColumnRef,
    CommitStmt,
    CreateIndexStmt,
    CreateTableStmt,
    DeleteStmt,
    ExplainStmt,
    Expr,
    FunctionCall,
    InsertStmt,
    IsNullExpr,
    Literal,
    RollbackStmt,
    SelectStmt,
    Star,
    Statement,
    TableRef,
    UnaryExpr,
    UpdateStmt,
    VacuumStmt,
)
from minipostgres.sql.bound import (
    BoundAnalyze,
    BoundAssignment,
    BoundBegin,
    BoundBinary,
    BoundCast,
    BoundColumn,
    BoundCommit,
    BoundCreateIndex,
    BoundCreateTable,
    BoundDelete,
    BoundExplain,
    BoundExpr,
    BoundFunction,
    BoundInsert,
    BoundIsNull,
    BoundJoin,
    BoundLiteral,
    BoundOrderItem,
    BoundRollback,
    BoundSelect,
    BoundSelectItem,
    BoundStatement,
    BoundTable,
    BoundUnary,
    BoundUpdate,
    BoundVacuum,
)
from minipostgres.types import DataType, infer_type, validate_int64

_NUMERIC = {DataType.INT64, DataType.FLOAT64}
_AGGREGATES = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


@dataclass(frozen=True, slots=True)
class _ScopeEntry:
    table: BoundTable
    visible_names: frozenset[str]


class Binder:
    """Resolve syntax nodes against one catalog snapshot."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._scope: tuple[_ScopeEntry, ...] = ()
        self._aggregate_depth = 0
        self._aggregate_context = "SELECT"

    def bind(self, statement: Statement) -> BoundStatement:
        """Bind one syntax-level statement."""

        self._scope = ()
        if isinstance(statement, SelectStmt):
            return self._bind_select(statement)
        if isinstance(statement, InsertStmt):
            return self._bind_insert(statement)
        if isinstance(statement, UpdateStmt):
            return self._bind_update(statement)
        if isinstance(statement, DeleteStmt):
            return self._bind_delete(statement)
        if isinstance(statement, CreateTableStmt):
            return BoundCreateTable(statement.name, statement.columns)
        if isinstance(statement, CreateIndexStmt):
            table = self._table(statement.table)
            columns = tuple(self._column(table, name) for name in statement.columns)
            return BoundCreateIndex(
                statement.name,
                table,
                columns,
                statement.unique,
            )
        if isinstance(statement, ExplainStmt):
            return BoundExplain(self.bind(statement.statement), statement.analyze)
        if isinstance(statement, AnalyzeStmt):
            return BoundAnalyze(
                None if statement.table is None else self._table(statement.table)
            )
        if isinstance(statement, VacuumStmt):
            return BoundVacuum(
                None if statement.table is None else self._table(statement.table)
            )
        if isinstance(statement, BeginStmt):
            return BoundBegin()
        if isinstance(statement, CommitStmt):
            return BoundCommit()
        if isinstance(statement, RollbackStmt):
            return BoundRollback()
        raise BindError(f"unsupported statement: {type(statement).__name__}")

    def _table(self, name: str) -> TableMetadata:
        try:
            return self._catalog.table(name)
        except CatalogError as error:
            raise BindError(str(error)) from error

    @staticmethod
    def _column(table: TableMetadata, name: str) -> Column:
        try:
            return table.schema.column(name)
        except CatalogError as error:
            raise BindError(str(error)) from error

    def _bind_table_ref(self, reference: TableRef) -> BoundTable:
        metadata = self._table(reference.name)
        alias = reference.alias or reference.name
        normalized_names = {alias.casefold()}
        for entry in self._scope:
            if entry.visible_names & normalized_names:
                raise BindError(f"duplicate table or alias: {alias}")
        table = BoundTable(metadata, alias)
        self._scope += (_ScopeEntry(table, frozenset(normalized_names)),)
        return table

    def _bind_select(self, statement: SelectStmt) -> BoundSelect:
        self._scope = ()
        from_table = (
            None
            if statement.from_table is None
            else self._bind_table_ref(statement.from_table)
        )
        bound_join_tables: list[BoundTable] = []
        for join in statement.joins:
            bound_join_tables.append(self._bind_table_ref(join.table))

        joins: list[BoundJoin] = []
        for join, table in zip(
            statement.joins,
            bound_join_tables,
            strict=True,
        ):
            condition = self._bind_predicate(
                join.condition,
                context="JOIN",
                allow_aggregate=False,
            )
            joins.append(BoundJoin(table, condition))

        where = (
            None
            if statement.where is None
            else self._bind_predicate(
                statement.where,
                context="WHERE",
                allow_aggregate=False,
            )
        )
        group_by = tuple(
            self._bind_expression(
                expression,
                allow_aggregate=False,
                context="GROUP BY",
            )
            for expression in statement.group_by
        )

        items: list[BoundSelectItem] = []
        for item in statement.items:
            if isinstance(item.expression, Star):
                for column in self._expand_star(item.expression):
                    items.append(BoundSelectItem(column, column.name))
                continue
            expression = self._bind_expression(
                item.expression,
                allow_aggregate=True,
                context="SELECT",
            )
            name = item.alias or self._default_output_name(item.expression)
            items.append(BoundSelectItem(expression, name))

        aliases: dict[str, BoundExpr] = {}
        for item in items:
            aliases.setdefault(item.name.casefold(), item.expression)

        order_by: list[BoundOrderItem] = []
        for item in statement.order_by:
            expression: BoundExpr
            if (
                isinstance(item.expression, ColumnRef)
                and item.expression.table is None
                and item.expression.name.casefold() in aliases
            ):
                expression = aliases[item.expression.name.casefold()]
            else:
                expression = self._bind_expression(
                    item.expression,
                    allow_aggregate=True,
                    context="ORDER BY",
                )
            order_by.append(BoundOrderItem(expression, item.direction, item.nulls))

        has_aggregate = any(
            self._contains_aggregate(item.expression) for item in items
        ) or any(self._contains_aggregate(item.expression) for item in order_by)
        if has_aggregate or group_by:
            for item in items:
                self._require_grouped(item.expression, group_by)
            for item in order_by:
                self._require_grouped(item.expression, group_by)

        return BoundSelect(
            tuple(items),
            from_table,
            tuple(joins),
            where,
            group_by,
            tuple(order_by),
            statement.limit,
        )

    def _expand_star(self, star: Star) -> tuple[BoundColumn, ...]:
        entries = self._scope
        if star.table is not None:
            normalized = star.table.casefold()
            entries = tuple(
                entry for entry in entries if normalized in entry.visible_names
            )
            if not entries:
                raise BindError(f"unknown table or alias: {star.table}")
        if not entries:
            raise BindError("star requires a FROM table")
        return tuple(
            BoundColumn(
                ColumnBinding(entry.table.metadata.table_id, column.column_id),
                column.name,
                column.data_type,
                column.nullable,
            )
            for entry in entries
            for column in entry.table.metadata.schema.columns
        )

    @staticmethod
    def _default_output_name(expression: Expr) -> str:
        if isinstance(expression, ColumnRef):
            return expression.name
        if isinstance(expression, FunctionCall):
            return expression.name.casefold()
        return "?column?"

    def _bind_insert(self, statement: InsertStmt) -> BoundInsert:
        table = self._table(statement.table)
        target_columns = (
            table.schema.columns
            if statement.columns is None
            else self._insert_columns(table, statement.columns)
        )
        rows: list[tuple[BoundExpr, ...]] = []
        for row in statement.rows:
            if len(row) != len(target_columns):
                raise BindError(
                    f"INSERT has {len(row)} values for "
                    f"{len(target_columns)} target columns"
                )
            bound_values: list[BoundExpr] = []
            for syntax, column in zip(row, target_columns, strict=True):
                expression = self._bind_expression(
                    syntax,
                    allow_aggregate=False,
                    context="INSERT",
                )
                try:
                    bound_values.append(self._coerce(expression, column.data_type))
                except TypeMismatch as error:
                    raise TypeMismatch(f"column {column.name}: {error}") from error
            rows.append(tuple(bound_values))
        return BoundInsert(table, target_columns, tuple(rows))

    def _insert_columns(
        self,
        table: TableMetadata,
        names: tuple[str, ...],
    ) -> tuple[Column, ...]:
        seen: set[str] = set()
        columns: list[Column] = []
        for name in names:
            normalized = name.casefold()
            if normalized in seen:
                raise BindError(f"duplicate insert column: {name}")
            seen.add(normalized)
            columns.append(self._column(table, name))
        return tuple(columns)

    def _bind_update(self, statement: UpdateStmt) -> BoundUpdate:
        table = self._table(statement.table)
        self._scope = ()
        self._bind_table_ref(TableRef(table.name))
        seen: set[str] = set()
        assignments: list[BoundAssignment] = []
        for assignment in statement.assignments:
            column = self._column(table, assignment.column)
            if column.normalized_name in seen:
                raise BindError(f"duplicate assignment: {column.name}")
            seen.add(column.normalized_name)
            expression = self._bind_expression(
                assignment.expression,
                allow_aggregate=False,
                context="UPDATE",
            )
            assignments.append(
                BoundAssignment(
                    column,
                    self._coerce(expression, column.data_type),
                )
            )
        where = (
            None
            if statement.where is None
            else self._bind_predicate(
                statement.where,
                context="WHERE",
                allow_aggregate=False,
            )
        )
        return BoundUpdate(table, tuple(assignments), where)

    def _bind_delete(self, statement: DeleteStmt) -> BoundDelete:
        table = self._table(statement.table)
        self._scope = ()
        self._bind_table_ref(TableRef(table.name))
        where = (
            None
            if statement.where is None
            else self._bind_predicate(
                statement.where,
                context="WHERE",
                allow_aggregate=False,
            )
        )
        return BoundDelete(table, where)

    def _bind_predicate(
        self,
        expression: Expr,
        *,
        context: str,
        allow_aggregate: bool,
    ) -> BoundExpr:
        bound = self._bind_expression(
            expression,
            allow_aggregate=allow_aggregate,
            context=context,
        )
        if isinstance(bound, BoundLiteral) and bound.value is None:
            return BoundLiteral(None, DataType.BOOLEAN, nullable=True)
        if bound.data_type is not DataType.BOOLEAN:
            raise TypeMismatch(f"{context} expression must be BOOLEAN")
        return bound

    def _bind_expression(
        self,
        expression: Expr,
        *,
        allow_aggregate: bool,
        context: str,
    ) -> BoundExpr:
        previous_context = self._aggregate_context
        self._aggregate_context = context
        try:
            return self._bind_expression_inner(expression, allow_aggregate)
        finally:
            self._aggregate_context = previous_context

    def _bind_expression_inner(
        self,
        expression: Expr,
        allow_aggregate: bool,
    ) -> BoundExpr:
        if isinstance(expression, Literal):
            data_type = infer_type(expression.value)
            if data_type is DataType.INT64:
                try:
                    validate_int64(expression.value)  # type: ignore[arg-type]
                except NumericOverflow:
                    raise
            return BoundLiteral(
                expression.value,
                data_type,
                expression.value is None,
            )
        if isinstance(expression, ColumnRef):
            return self._resolve_column(expression)
        if isinstance(expression, Star):
            raise BindError("star is only valid in SELECT lists or COUNT(*)")
        if isinstance(expression, UnaryExpr):
            operand = self._bind_expression_inner(expression.operand, allow_aggregate)
            if expression.operator == "NOT":
                if operand.data_type is not DataType.BOOLEAN:
                    raise TypeMismatch("NOT operand must be BOOLEAN")
                return BoundUnary(
                    "NOT",
                    operand,
                    DataType.BOOLEAN,
                    operand.nullable,
                )
            self._require_numeric(operand)
            assert operand.data_type is not None
            return BoundUnary(
                expression.operator,
                operand,
                operand.data_type,
                operand.nullable,
            )
        if isinstance(expression, BinaryExpr):
            return self._bind_binary(expression, allow_aggregate)
        if isinstance(expression, IsNullExpr):
            return BoundIsNull(
                self._bind_expression_inner(expression.operand, allow_aggregate),
                expression.negated,
            )
        if isinstance(expression, FunctionCall):
            return self._bind_function(expression, allow_aggregate)
        raise BindError(f"unsupported expression: {type(expression).__name__}")

    def _resolve_column(self, reference: ColumnRef) -> BoundColumn:
        entries = self._scope
        if reference.table is not None:
            normalized = reference.table.casefold()
            entries = tuple(
                entry for entry in entries if normalized in entry.visible_names
            )
            if not entries:
                raise BindError(f"unknown table or alias: {reference.table}")
        matches: list[tuple[TableMetadata, Column]] = []
        for entry in entries:
            try:
                column = entry.table.metadata.schema.column(reference.name)
            except CatalogError:
                continue
            matches.append((entry.table.metadata, column))
        if not matches:
            raise BindError(f"unknown column: {reference.name}")
        if len(matches) > 1:
            raise BindError(f"ambiguous column: {reference.name}")
        table, column = matches[0]
        return BoundColumn(
            ColumnBinding(table.table_id, column.column_id),
            column.name,
            column.data_type,
            column.nullable,
        )

    def _bind_binary(
        self,
        expression: BinaryExpr,
        allow_aggregate: bool,
    ) -> BoundExpr:
        left = self._bind_expression_inner(expression.left, allow_aggregate)
        right = self._bind_expression_inner(expression.right, allow_aggregate)
        if expression.operator in {"AND", "OR"}:
            if (
                left.data_type is not DataType.BOOLEAN
                or right.data_type is not DataType.BOOLEAN
            ):
                raise TypeMismatch(f"{expression.operator} operands must be BOOLEAN")
            return BoundBinary(
                left,
                expression.operator,
                right,
                DataType.BOOLEAN,
                left.nullable or right.nullable,
            )
        if expression.operator in {"+", "-", "*", "/"}:
            left, right, result_type = self._numeric_pair(left, right)
            return BoundBinary(
                left,
                expression.operator,
                right,
                result_type,
                left.nullable or right.nullable,
            )
        left, right = self._comparable_pair(left, right)
        return BoundBinary(
            left,
            expression.operator,
            right,
            DataType.BOOLEAN,
            left.nullable or right.nullable,
        )

    def _bind_function(
        self,
        function: FunctionCall,
        allow_aggregate: bool,
    ) -> BoundFunction:
        name = function.name.upper()
        if name not in _AGGREGATES:
            raise BindError(f"unknown function: {function.name}")
        if not allow_aggregate:
            raise BindError(
                f"aggregate function is not allowed in {self._aggregate_context}"
            )
        if self._aggregate_depth:
            raise BindError("nested aggregate functions are not supported")
        self._aggregate_depth += 1
        try:
            if len(function.arguments) != 1:
                raise BindError(f"{name} requires exactly one argument")
            syntax_argument = function.arguments[0]
            if isinstance(syntax_argument, Star):
                if name != "COUNT":
                    raise BindError(f"{name}(*) is not supported")
                return BoundFunction(
                    name,
                    (),
                    DataType.INT64,
                    nullable=False,
                    star=True,
                )
            argument = self._bind_expression_inner(syntax_argument, True)
        finally:
            self._aggregate_depth -= 1

        if name == "COUNT":
            return BoundFunction(
                name,
                (argument,),
                DataType.INT64,
                nullable=False,
            )
        if name in {"SUM", "AVG"}:
            self._require_numeric(argument)
        if argument.data_type is None:
            raise TypeMismatch(f"{name} requires a typed argument")
        result_type = DataType.FLOAT64 if name == "AVG" else argument.data_type
        return BoundFunction(
            name,
            (argument,),
            result_type,
            nullable=True,
        )

    @staticmethod
    def _require_numeric(expression: BoundExpr) -> None:
        if expression.data_type not in _NUMERIC:
            raise TypeMismatch("numeric operand required")

    def _numeric_pair(
        self,
        left: BoundExpr,
        right: BoundExpr,
    ) -> tuple[BoundExpr, BoundExpr, DataType]:
        self._require_numeric(left)
        self._require_numeric(right)
        if left.data_type is DataType.FLOAT64 or right.data_type is DataType.FLOAT64:
            return (
                self._coerce(left, DataType.FLOAT64),
                self._coerce(right, DataType.FLOAT64),
                DataType.FLOAT64,
            )
        return left, right, DataType.INT64

    def _comparable_pair(
        self,
        left: BoundExpr,
        right: BoundExpr,
    ) -> tuple[BoundExpr, BoundExpr]:
        if left.data_type is None and right.data_type is None:
            return left, right
        if left.data_type is None:
            assert right.data_type is not None
            return self._coerce(left, right.data_type), right
        if right.data_type is None:
            return left, self._coerce(right, left.data_type)
        if left.data_type is right.data_type:
            return left, right
        if left.data_type in _NUMERIC and right.data_type in _NUMERIC:
            coerced_left, coerced_right, _ = self._numeric_pair(left, right)
            return coerced_left, coerced_right
        raise TypeMismatch(
            f"cannot compare {left.data_type.value} with {right.data_type.value}"
        )

    @staticmethod
    def _coerce(expression: BoundExpr, target: DataType) -> BoundExpr:
        if expression.data_type is None:
            if not isinstance(expression, BoundLiteral) or expression.value is not None:
                raise TypeMismatch(f"cannot infer value as {target.value}")
            return BoundLiteral(None, target, nullable=True)
        if expression.data_type is target:
            return expression
        if expression.data_type is DataType.INT64 and target is DataType.FLOAT64:
            return BoundCast(expression, target, expression.nullable)
        raise TypeMismatch(f"expected {target.value}, got {expression.data_type.value}")

    @classmethod
    def _contains_aggregate(cls, expression: BoundExpr) -> bool:
        if isinstance(expression, BoundFunction):
            return True
        if isinstance(expression, BoundUnary):
            return cls._contains_aggregate(expression.operand)
        if isinstance(expression, BoundBinary):
            return cls._contains_aggregate(expression.left) or cls._contains_aggregate(
                expression.right
            )
        if isinstance(expression, BoundCast):
            return cls._contains_aggregate(expression.operand)
        if isinstance(expression, BoundIsNull):
            return cls._contains_aggregate(expression.operand)
        return False

    @classmethod
    def _ungrouped_columns(
        cls,
        expression: BoundExpr,
        group_by: tuple[BoundExpr, ...],
        *,
        inside_aggregate: bool = False,
    ) -> tuple[BoundColumn, ...]:
        if expression in group_by and not inside_aggregate:
            return ()
        if isinstance(expression, BoundFunction):
            return ()
        if isinstance(expression, BoundColumn):
            return () if inside_aggregate else (expression,)
        if isinstance(expression, BoundUnary):
            return cls._ungrouped_columns(
                expression.operand,
                group_by,
                inside_aggregate=inside_aggregate,
            )
        if isinstance(expression, BoundBinary):
            return cls._ungrouped_columns(
                expression.left,
                group_by,
                inside_aggregate=inside_aggregate,
            ) + cls._ungrouped_columns(
                expression.right,
                group_by,
                inside_aggregate=inside_aggregate,
            )
        if isinstance(expression, BoundCast):
            return cls._ungrouped_columns(
                expression.operand,
                group_by,
                inside_aggregate=inside_aggregate,
            )
        if isinstance(expression, BoundIsNull):
            return cls._ungrouped_columns(
                expression.operand,
                group_by,
                inside_aggregate=inside_aggregate,
            )
        return ()

    @classmethod
    def _require_grouped(
        cls,
        expression: BoundExpr,
        group_by: tuple[BoundExpr, ...],
    ) -> None:
        ungrouped = cls._ungrouped_columns(expression, group_by)
        if ungrouped:
            raise BindError(f"column {ungrouped[0].name} must appear in GROUP BY")
