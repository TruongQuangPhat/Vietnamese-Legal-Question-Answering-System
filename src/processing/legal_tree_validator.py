"""Read-only validation for canonical Phase 5 legal hierarchy documents."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.processing.legal_hierarchy_models import (
    LegalHierarchyDocument,
    LegalNode,
    LegalNodeLevel,
    ParsingIssueCode,
    StructuredParsingIssue,
    ValidationSummary,
)

_ARTICLE_NUMBER_PREFIX_RE = re.compile(r"^(\d+)")

_ALLOWED_CHILD_LEVELS: dict[LegalNodeLevel, set[LegalNodeLevel]] = {
    LegalNodeLevel.LAW: {
        LegalNodeLevel.PART,
        LegalNodeLevel.CHAPTER,
        LegalNodeLevel.SECTION,
        LegalNodeLevel.ARTICLE,
    },
    LegalNodeLevel.PART: {
        LegalNodeLevel.CHAPTER,
        LegalNodeLevel.SECTION,
        LegalNodeLevel.ARTICLE,
    },
    LegalNodeLevel.CHAPTER: {LegalNodeLevel.SECTION, LegalNodeLevel.ARTICLE},
    LegalNodeLevel.SECTION: {LegalNodeLevel.ARTICLE},
    LegalNodeLevel.ARTICLE: {LegalNodeLevel.CLAUSE},
    LegalNodeLevel.CLAUSE: {LegalNodeLevel.POINT},
    LegalNodeLevel.POINT: set(),
}


class LegalTreeValidationResult(BaseModel):
    """Result of read-only legal hierarchy validation.

    Attributes:
        is_valid: Whether the document has no hard validation errors.
        validation_summary: Aggregated validation counters for reports.
        warnings: Existing document warnings plus new validation warnings.
        errors: Hard validation errors.
    """

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(...)
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    warnings: list[StructuredParsingIssue] = Field(default_factory=list)
    errors: list[StructuredParsingIssue] = Field(default_factory=list)


@dataclass
class _ValidationState:
    """Mutable local accumulator for one validation run."""

    document: LegalHierarchyDocument
    normalized_text: str
    warnings: list[StructuredParsingIssue] = field(default_factory=list)
    errors: list[StructuredParsingIssue] = field(default_factory=list)
    warning_keys: set[tuple[Any, ...]] = field(default_factory=set)
    error_keys: set[tuple[Any, ...]] = field(default_factory=set)
    summary: ValidationSummary = field(default_factory=ValidationSummary)
    invalid_sibling_issue_count: int = 0


class LegalTreeValidator:
    """Validate a completed legal hierarchy document without mutation.

    The validator inspects structural relationships, IDs, offsets, text slices,
    reachability, legal parent-child levels, and Phase 4 Article metrics. It
    returns structured issues and never repairs or rewrites the input document.
    """

    def validate(
        self,
        *,
        document: LegalHierarchyDocument,
        normalized_text: str,
    ) -> LegalTreeValidationResult:
        """Validate a canonical hierarchy document against its source text.

        Args:
            document: Completed hierarchy document to inspect.
            normalized_text: Exact authoritative source string used for parsing.

        Returns:
            Validation result containing errors, warnings, and summary counts.

        Legal assumptions:
            The method is read-only. It must not mutate node IDs, parent links,
            children lists, offsets, node text, document warnings, or source
            content.
        """
        state = _ValidationState(document=document, normalized_text=normalized_text)
        for warning in document.warnings:
            self._append_warning(state, warning)

        nodes = list(document.nodes)
        nodes_by_id, duplicate_ids = self._index_nodes(state, nodes)
        root = self._validate_root(state, nodes, nodes_by_id)

        self._validate_references(state, nodes, nodes_by_id, root)
        self._validate_cycles(state, nodes, nodes_by_id, root)
        self._validate_reachability(state, nodes, nodes_by_id, root)
        self._validate_allowed_levels(state, nodes, nodes_by_id)
        self._validate_offsets_and_text(state, nodes)
        self._validate_parent_containment(state, nodes, nodes_by_id, root)
        self._validate_siblings(state, nodes, nodes_by_id)
        self._validate_article_metrics(state, nodes)

        state.summary.duplicate_node_ids = len(duplicate_ids)
        state.summary.orphan_nodes = self._count_issue_code(
            state.errors,
            ParsingIssueCode.ORPHAN_NODE,
        )
        state.summary.invalid_offsets = self._count_issue_codes(
            state.errors,
            {ParsingIssueCode.INVALID_OFFSET, ParsingIssueCode.TEXT_OFFSET_MISMATCH},
        )
        state.summary.invalid_parent_chain = self._count_issue_code(
            state.errors,
            ParsingIssueCode.INVALID_TREE,
        )
        state.summary.invalid_sibling_overlap = state.invalid_sibling_issue_count

        return LegalTreeValidationResult(
            is_valid=len(state.errors) == 0,
            validation_summary=state.summary,
            warnings=state.warnings,
            errors=state.errors,
        )

    def _index_nodes(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
    ) -> tuple[dict[str, LegalNode], set[str]]:
        """Index nodes by first-seen ID and report duplicate IDs."""
        nodes_by_id: dict[str, LegalNode] = {}
        id_counts = Counter(node.node_id for node in nodes)
        duplicate_ids = {node_id for node_id, count in id_counts.items() if count > 1}

        for node in nodes:
            nodes_by_id.setdefault(node.node_id, node)

        for node_id in sorted(duplicate_ids):
            first = nodes_by_id[node_id]
            self._append_error(
                state,
                code=ParsingIssueCode.UNRESOLVED_DUPLICATE_NODE_ID,
                message="Duplicate node_id found in hierarchy document.",
                node=first,
                context={"node_id": node_id, "count": id_counts[node_id]},
            )
        return nodes_by_id, duplicate_ids

    def _validate_root(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
    ) -> LegalNode | None:
        """Validate root Law invariants and return the best root candidate."""
        law_nodes = [node for node in nodes if node.level == LegalNodeLevel.LAW]
        if len(law_nodes) != 1:
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_TREE,
                message="Hierarchy must contain exactly one Law root node.",
                context={"law_node_count": len(law_nodes)},
            )

        referenced_root = nodes_by_id.get(state.document.root_node_id)
        if referenced_root is None:
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_TREE,
                message="root_node_id does not reference an existing node.",
                context={"root_node_id": state.document.root_node_id},
            )
        elif referenced_root.level != LegalNodeLevel.LAW:
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_TREE,
                message="root_node_id must reference the Law root node.",
                node=referenced_root,
                context={
                    "root_node_id": state.document.root_node_id,
                    "referenced_level": referenced_root.level.value,
                },
            )

        root = (
            referenced_root
            if referenced_root is not None
            else (law_nodes[0] if law_nodes else None)
        )
        if root is None:
            return None

        if root.node_id != state.document.root_node_id:
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_TREE,
                message="Root node ID must equal document.root_node_id.",
                node=root,
                context={"root_node_id": state.document.root_node_id},
            )
        if root.parent_id is not None:
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_TREE,
                message="Root parent_id must be null.",
                node=root,
                context={"parent_id": root.parent_id},
            )
        if root.number is not None:
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_TREE,
                message="Root number must be null.",
                node=root,
                context={"number": root.number},
            )
        if root.start_offset != 0 or root.end_offset != len(state.normalized_text):
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_OFFSET,
                message="Root offsets must span the entire normalized text.",
                node=root,
                context={
                    "expected_start": 0,
                    "expected_end": len(state.normalized_text),
                    "actual_start": root.start_offset,
                    "actual_end": root.end_offset,
                },
            )
        if root.text != state.normalized_text:
            self._append_error(
                state,
                code=ParsingIssueCode.TEXT_OFFSET_MISMATCH,
                message="Root text must exactly equal normalized_text.",
                node=root,
                context={
                    "expected_length": len(state.normalized_text),
                    "actual_length": len(root.text),
                },
            )
        return root

    def _validate_references(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
        root: LegalNode | None,
    ) -> None:
        """Validate parent existence and bidirectional parent-child references."""
        listed_by: dict[str, list[str]] = defaultdict(list)

        for parent in nodes:
            child_counts = Counter(parent.children)
            for child_id, count in child_counts.items():
                if count > 1:
                    self._append_error(
                        state,
                        code=ParsingIssueCode.INVALID_TREE,
                        message="Parent lists the same child ID more than once.",
                        node=parent,
                        context={"child_id": child_id, "count": count},
                    )

            for child_id in parent.children:
                child = nodes_by_id.get(child_id)
                listed_by[child_id].append(parent.node_id)
                if child is None:
                    self._append_error(
                        state,
                        code=ParsingIssueCode.INVALID_TREE,
                        message="Parent children list references a missing node.",
                        node=parent,
                        context={"child_id": child_id},
                    )
                    continue
                if child.parent_id != parent.node_id:
                    self._append_error(
                        state,
                        code=ParsingIssueCode.INVALID_TREE,
                        message="Child parent_id disagrees with parent.children.",
                        node=child,
                        context={"listed_parent_id": parent.node_id, "parent_id": child.parent_id},
                    )

        for child_id, parent_ids in sorted(listed_by.items()):
            unique_parent_ids = sorted(set(parent_ids))
            if len(unique_parent_ids) > 1:
                self._append_error(
                    state,
                    code=ParsingIssueCode.INVALID_TREE,
                    message="Child is listed by multiple parents.",
                    node=nodes_by_id.get(child_id),
                    context={"child_id": child_id, "parent_ids": unique_parent_ids},
                )

        for node in nodes:
            if root is not None and node.node_id == root.node_id:
                if node.parent_id == node.node_id:
                    self._append_error(
                        state,
                        code=ParsingIssueCode.PARENT_CYCLE,
                        message="Root node cannot be its own parent.",
                        node=node,
                        context={"parent_id": node.parent_id},
                    )
                continue

            if node.parent_id is None:
                self._append_error(
                    state,
                    code=ParsingIssueCode.ORPHAN_NODE,
                    message="Non-root node is missing parent_id.",
                    node=node,
                )
                continue
            if node.parent_id == node.node_id:
                self._append_error(
                    state,
                    code=ParsingIssueCode.PARENT_CYCLE,
                    message="Node parent_id references itself.",
                    node=node,
                    context={"parent_id": node.parent_id},
                )
            parent = nodes_by_id.get(node.parent_id)
            if parent is None:
                self._append_error(
                    state,
                    code=ParsingIssueCode.ORPHAN_NODE,
                    message="Node parent_id references a missing node.",
                    node=node,
                    context={"parent_id": node.parent_id},
                )
                continue
            if parent.children.count(node.node_id) == 0:
                self._append_error(
                    state,
                    code=ParsingIssueCode.INVALID_TREE,
                    message="Non-root node is not listed in its parent.children.",
                    node=node,
                    context={"parent_id": parent.node_id},
                )

    def _validate_cycles(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
        root: LegalNode | None,
    ) -> None:
        """Detect cycles through parent chains and child traversal."""
        for node in nodes:
            seen: set[str] = set()
            current = node
            while current.parent_id is not None:
                if current.node_id in seen:
                    self._append_error(
                        state,
                        code=ParsingIssueCode.PARENT_CYCLE,
                        message="Cycle detected in parent chain.",
                        node=node,
                        context={"cycle_node_id": current.node_id},
                    )
                    break
                seen.add(current.node_id)
                parent = nodes_by_id.get(current.parent_id)
                if parent is None:
                    break
                current = parent

        if root is None:
            return

        stack: list[tuple[str, tuple[str, ...]]] = [(root.node_id, (root.node_id,))]
        while stack:
            node_id, path = stack.pop()
            node = nodes_by_id.get(node_id)
            if node is None:
                continue
            for child_id in reversed(node.children):
                if child_id in path:
                    self._append_error(
                        state,
                        code=ParsingIssueCode.PARENT_CYCLE,
                        message="Cycle detected in child traversal.",
                        node=node,
                        context={"child_id": child_id, "path": list(path)},
                    )
                    continue
                stack.append((child_id, (*path, child_id)))

    def _validate_reachability(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
        root: LegalNode | None,
    ) -> None:
        """Ensure every node is reachable from root by following children."""
        if root is None:
            return

        reachable: set[str] = set()
        stack = [root.node_id]
        while stack:
            node_id = stack.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            node = nodes_by_id.get(node_id)
            if node is None:
                continue
            for child_id in reversed(node.children):
                if child_id in nodes_by_id:
                    stack.append(child_id)

        for node in nodes:
            if node.node_id not in reachable:
                self._append_error(
                    state,
                    code=ParsingIssueCode.ORPHAN_NODE,
                    message="Node is not reachable from the root via children.",
                    node=node,
                    context={"root_node_id": root.node_id},
                )

    def _validate_allowed_levels(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
    ) -> None:
        """Validate legal parent-child level relationships."""
        checked_pairs: set[tuple[str, str]] = set()
        for parent in nodes:
            for child_id in parent.children:
                child = nodes_by_id.get(child_id)
                if child is None:
                    continue
                self._validate_level_pair(state, parent, child, checked_pairs)

        for child in nodes:
            if child.parent_id is None:
                continue
            parent = nodes_by_id.get(child.parent_id)
            if parent is None:
                continue
            self._validate_level_pair(state, parent, child, checked_pairs)

    def _validate_offsets_and_text(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
    ) -> None:
        """Validate offset bounds and exact source slice agreement."""
        document_length = len(state.normalized_text)
        for node in nodes:
            if not self._has_valid_bounds(node, document_length):
                self._append_error(
                    state,
                    code=ParsingIssueCode.INVALID_OFFSET,
                    message="Node offsets are outside normalized text bounds.",
                    node=node,
                    context={
                        "document_length": document_length,
                        "start_offset": node.start_offset,
                        "end_offset": node.end_offset,
                    },
                )
                continue

            expected_text = state.normalized_text[node.start_offset : node.end_offset]
            if node.text != expected_text:
                self._append_error(
                    state,
                    code=ParsingIssueCode.TEXT_OFFSET_MISMATCH,
                    message="Node text does not match normalized_text slice.",
                    node=node,
                    context={
                        "expected_length": len(expected_text),
                        "actual_length": len(node.text),
                    },
                )

    def _validate_parent_containment(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
        root: LegalNode | None,
    ) -> None:
        """Validate that each child span is contained in its parent span."""
        document_length = len(state.normalized_text)
        for child in nodes:
            if root is not None and child.node_id == root.node_id:
                continue
            if child.parent_id is None:
                continue
            parent = nodes_by_id.get(child.parent_id)
            if parent is None:
                continue
            if not self._has_valid_bounds(parent, document_length):
                continue
            if not self._has_valid_bounds(child, document_length):
                continue
            if parent.start_offset <= child.start_offset and child.end_offset <= parent.end_offset:
                continue
            self._append_error(
                state,
                code=ParsingIssueCode.INVALID_OFFSET,
                message="Child span is not contained inside parent span.",
                node=child,
                context={
                    "parent_id": parent.node_id,
                    "parent_start_offset": parent.start_offset,
                    "parent_end_offset": parent.end_offset,
                },
            )

    def _validate_siblings(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
        nodes_by_id: dict[str, LegalNode],
    ) -> None:
        """Validate sibling source ordering and non-overlap."""
        document_length = len(state.normalized_text)
        for parent in nodes:
            resolved_children = [
                nodes_by_id[child_id]
                for child_id in parent.children
                if child_id in nodes_by_id
                and self._has_valid_bounds(nodes_by_id[child_id], document_length)
            ]
            for previous, current in zip(resolved_children, resolved_children[1:], strict=False):
                if previous.start_offset > current.start_offset:
                    state.invalid_sibling_issue_count += 1
                    self._append_error(
                        state,
                        code=ParsingIssueCode.INVALID_TREE,
                        message="Sibling children are not ordered by source start_offset.",
                        node=parent,
                        context={
                            "check": "sibling_order",
                            "previous_child_id": previous.node_id,
                            "current_child_id": current.node_id,
                        },
                    )
                    continue
                if previous.end_offset > current.start_offset:
                    state.invalid_sibling_issue_count += 1
                    self._append_error(
                        state,
                        code=ParsingIssueCode.INVALID_TREE,
                        message="Sibling spans overlap.",
                        node=parent,
                        context={
                            "check": "sibling_overlap",
                            "previous_child_id": previous.node_id,
                            "current_child_id": current.node_id,
                        },
                    )

    def _validate_article_metrics(
        self,
        state: _ValidationState,
        nodes: list[LegalNode],
    ) -> None:
        """Validate Article presence and Phase 4 metric compatibility."""
        articles = [node for node in nodes if node.level == LegalNodeLevel.ARTICLE]
        if not articles:
            self._append_error(
                state,
                code=ParsingIssueCode.NO_ARTICLES_FOUND,
                message="Hierarchy document contains no Article nodes.",
                context={"article_count": 0},
            )
            return

        has_article_1 = any(node.number == "1" for node in articles)
        if state.document.metadata.has_heading_article_1 and not has_article_1:
            state.summary.missing_article_1 = 1
            self._append_warning(
                state,
                StructuredParsingIssue(
                    code=ParsingIssueCode.MISSING_ARTICLE_1,
                    message="Phase 4 expected Article 1 but parsed hierarchy does not contain it.",
                    law_id=state.document.law_id,
                    context={"expected": True, "actual": False},
                ),
            )

        expected_count = state.document.metadata.article_heading_count
        actual_count = len(articles)
        if actual_count != expected_count:
            state.summary.article_heading_mismatch = 1
            self._append_warning(
                state,
                StructuredParsingIssue(
                    code=ParsingIssueCode.ARTICLE_COUNT_MISMATCH,
                    message="Parsed article count differs from Phase 4 heading count.",
                    law_id=state.document.law_id,
                    context={"expected": expected_count, "actual": actual_count},
                ),
            )

        expected_max = state.document.metadata.max_heading_article_number
        actual_max = max(
            (
                number
                for number in (_article_number_prefix(article.number) for article in articles)
                if number
            ),
            default=0,
        )
        if actual_max != expected_max:
            self._append_warning(
                state,
                StructuredParsingIssue(
                    code=ParsingIssueCode.MAX_ARTICLE_NUMBER_MISMATCH,
                    message="Parsed maximum Article number differs from Phase 4 metric.",
                    law_id=state.document.law_id,
                    context={"expected": expected_max, "actual": actual_max},
                ),
            )

        for article in articles:
            if self._is_empty_article(article):
                state.summary.empty_article_nodes += 1
                self._append_warning(
                    state,
                    StructuredParsingIssue(
                        code=ParsingIssueCode.EMPTY_ARTICLE_NODE,
                        message="Article node contains no body text after its heading.",
                        law_id=state.document.law_id,
                        node_id=article.node_id,
                        start_offset=article.start_offset,
                        end_offset=article.end_offset,
                        context={"number": article.number, "title": article.title},
                    ),
                )

    def _validate_level_pair(
        self,
        state: _ValidationState,
        parent: LegalNode,
        child: LegalNode,
        checked_pairs: set[tuple[str, str]],
    ) -> None:
        """Validate one parent-child level pair once."""
        pair = (parent.node_id, child.node_id)
        if pair in checked_pairs:
            return
        checked_pairs.add(pair)
        if child.level in _ALLOWED_CHILD_LEVELS[parent.level]:
            return

        self._append_error(
            state,
            code=ParsingIssueCode.INVALID_TREE,
            message="Invalid legal parent-child level relationship.",
            node=child,
            context={"parent_id": parent.node_id, "parent_level": parent.level.value},
        )

    @staticmethod
    def _has_valid_bounds(node: LegalNode, document_length: int) -> bool:
        """Return whether node offsets can safely slice normalized_text."""
        return (
            isinstance(node.start_offset, int)
            and isinstance(node.end_offset, int)
            and 0 <= node.start_offset < node.end_offset <= document_length
        )

    @staticmethod
    def _is_empty_article(article: LegalNode) -> bool:
        """Conservatively detect Articles with no body after heading text."""
        heading_end = article.metadata.get("heading_end_offset")
        if (
            isinstance(heading_end, int)
            and article.start_offset <= heading_end <= article.end_offset
        ):
            relative_heading_end = heading_end - article.start_offset
            return article.text[relative_heading_end:].strip() == ""

        lines = article.text.splitlines()
        return "\n".join(lines[1:]).strip() == "" if lines else True

    def _append_error(
        self,
        state: _ValidationState,
        *,
        code: ParsingIssueCode,
        message: str,
        node: LegalNode | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Append a deduplicated hard validation issue."""
        issue = self._build_issue(state, code=code, message=message, node=node, context=context)
        key = _issue_key(issue)
        if key in state.error_keys:
            return
        state.error_keys.add(key)
        state.errors.append(issue)

    def _append_warning(
        self,
        state: _ValidationState,
        issue: StructuredParsingIssue,
    ) -> None:
        """Append a deduplicated warning while preserving first-seen order."""
        key = _issue_key(issue)
        if key in state.warning_keys:
            return
        state.warning_keys.add(key)
        state.warnings.append(issue)

    def _build_issue(
        self,
        state: _ValidationState,
        *,
        code: ParsingIssueCode,
        message: str,
        node: LegalNode | None,
        context: dict[str, Any] | None,
    ) -> StructuredParsingIssue:
        """Build a structured issue with safe nullable offsets."""
        start_offset, end_offset = _safe_issue_offsets(node)
        return StructuredParsingIssue(
            code=code,
            message=message,
            law_id=state.document.law_id,
            node_id=node.node_id if node is not None else None,
            start_offset=start_offset,
            end_offset=end_offset,
            context=context or {},
        )

    @staticmethod
    def _count_issue_code(
        issues: list[StructuredParsingIssue],
        code: ParsingIssueCode,
    ) -> int:
        """Count issues with one code."""
        return sum(1 for issue in issues if issue.code == code)

    @staticmethod
    def _count_issue_codes(
        issues: list[StructuredParsingIssue],
        codes: set[ParsingIssueCode],
    ) -> int:
        """Count issues whose code is in a set."""
        return sum(1 for issue in issues if issue.code in codes)


def _safe_issue_offsets(node: LegalNode | None) -> tuple[int | None, int | None]:
    """Return issue offsets without violating `StructuredParsingIssue` constraints."""
    if node is None:
        return None, None
    start = (
        node.start_offset if isinstance(node.start_offset, int) and node.start_offset >= 0 else None
    )
    end = node.end_offset if isinstance(node.end_offset, int) and node.end_offset >= 0 else None
    if start is not None and end is not None and end < start:
        end = None
    return start, end


def _issue_key(issue: StructuredParsingIssue) -> tuple[Any, ...]:
    """Build a deterministic deduplication key for structured issues."""
    context = json.dumps(issue.context, ensure_ascii=False, sort_keys=True, default=str)
    return (
        issue.code.value,
        issue.node_id,
        issue.start_offset,
        issue.end_offset,
        context,
    )


def _article_number_prefix(number: str | None) -> int | None:
    """Return comparable numeric Article prefix, e.g. `217a` -> `217`."""
    if number is None:
        return None
    match = _ARTICLE_NUMBER_PREFIX_RE.match(number)
    if match is None:
        return None
    return int(match.group(1))
