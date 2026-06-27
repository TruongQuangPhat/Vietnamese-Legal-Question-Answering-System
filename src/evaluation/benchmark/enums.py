"""Strict enum values for the legal QA benchmark protocol."""

from __future__ import annotations

from enum import StrEnum


class BenchmarkSplit(StrEnum):
    """Approved benchmark split labels."""

    DEVELOPMENT = "development"
    HELD_OUT_TEST = "held_out_test"


class ExpectedDecision(StrEnum):
    """Final adjudicated answerability labels."""

    ANSWER_ALLOWED = "answer_allowed"
    FALLBACK_REQUIRED = "fallback_required"


class FallbackReason(StrEnum):
    """Approved semantic reasons for fallback-required benchmark cases."""

    NO_RELEVANT_TARGET = "no_relevant_target"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"
    INDIRECT_ONLY_EVIDENCE = "indirect_only_evidence"
    UNSAFE_AMBIGUITY = "unsafe_ambiguity"
    UNRESOLVED_TEMPORAL_SCOPE = "unresolved_temporal_scope"
    OUT_OF_CORPUS = "out_of_corpus"


class LegalDomain(StrEnum):
    """Top-level legal domains used for benchmark stratification."""

    CONSTITUTIONAL_STATE_RIGHTS = "constitutional_state_rights"
    CIVIL_FAMILY_IDENTITY = "civil_family_identity"
    CRIMINAL_PROCEDURE_PENALTY = "criminal_procedure_penalty"
    CIVIL_PROCEDURE_DISPUTE_RESOLUTION = "civil_procedure_dispute_resolution"
    LAND_REAL_ESTATE_CONSTRUCTION_ENVIRONMENT = "land_real_estate_construction_environment"
    BUSINESS_BANKING_TAX = "business_banking_tax"
    TRAFFIC_PUBLIC_ORDER_SANCTIONS = "traffic_public_order_sanctions"
    LABOR_EMPLOYMENT_SOCIAL_SECURITY = "labor_employment_social_security"
    CONSUMER_HEALTH_EDUCATION_DIGITAL_IP = "consumer_health_education_digital_ip"
    ADMINISTRATIVE_GOVERNMENT_INTERACTION = "administrative_government_interaction"
    MARITIME_TRANSPORT = "maritime_transport"


class QuestionType(StrEnum):
    """Approved multi-valued benchmark question types."""

    SINGLE_ARTICLE_LOOKUP = "single_article_lookup"
    CLAUSE_POINT_LOOKUP = "clause_point_lookup"
    COMPLETE_LIST = "complete_list"
    CONDITIONS_AND_EXCEPTIONS = "conditions_and_exceptions"
    MULTI_EVIDENCE = "multi_evidence"
    CROSS_LAW = "cross_law"
    TEMPORAL_VERSION_SENSITIVE = "temporal_version_sensitive"
    PARAPHRASE = "paraphrase"
    LEXICAL_MISMATCH = "lexical_mismatch"
    AMBIGUOUS = "ambiguous"
    FALLBACK = "fallback"
    NEAR_DUPLICATE_PROVISION = "near_duplicate_provision"
    DEFINITION = "definition"
    PROCEDURE = "procedure"
    ELIGIBILITY = "eligibility"
    RIGHTS_AND_OBLIGATIONS = "rights_and_obligations"
    SANCTION_OR_PENALTY = "sanction_or_penalty"


class RelevanceLevel(StrEnum):
    """Evidence relevance levels approved by the protocol."""

    REQUIRED_DIRECT = "required_direct"
    ALTERNATIVE_DIRECT = "alternative_direct"
    SUPPORTING = "supporting"
    NEAR_MISS = "near_miss"
    IRRELEVANT = "irrelevant"

    @property
    def can_satisfy_required_group(self) -> bool:
        """Return whether this relevance level may complete a required group."""
        return self in {self.REQUIRED_DIRECT, self.ALTERNATIVE_DIRECT}


class TargetRole(StrEnum):
    """Legal target roles."""

    REQUIRED = "required"
    ALTERNATIVE = "alternative"
    SUPPORTING = "supporting"
    EXCLUSION = "exclusion"


class MatchLevel(StrEnum):
    """Legal hierarchy depth used for target matching."""

    ARTICLE = "article"
    CLAUSE = "clause"
    POINT = "point"


class ReviewStatus(StrEnum):
    """Approved lifecycle statuses for benchmark annotations."""

    DRAFT = "draft"
    PRIMARY_REVIEWED = "primary_reviewed"
    INDEPENDENT_REVIEWED = "independent_reviewed"
    CONFLICT = "conflict"
    ADJUDICATED = "adjudicated"
    FROZEN = "frozen"


class ReviewStage(StrEnum):
    """Workflow stages recorded in review provenance."""

    PRIMARY_ANNOTATION = "primary_annotation"
    INDEPENDENT_REVIEW = "independent_review"
    ADJUDICATION = "adjudication"
    FREEZE_REVIEW = "freeze_review"


class ReviewerKind(StrEnum):
    """Reviewer category used to separate workflow evidence from assurance claims."""

    AUTOMATED_SYSTEM = "automated_system"
    HUMAN_DOMAIN_REVIEWER = "human_domain_reviewer"
    QUALIFIED_HUMAN_LEGAL_REVIEWER = "qualified_human_legal_reviewer"


class ReviewAssurance(StrEnum):
    """Assurance level represented by a review record."""

    PRIMARY_ANNOTATION = "primary_annotation"
    STRUCTURED_AUTOMATED_REVIEW = "structured_automated_review"
    REPOSITORY_ADJUDICATION = "repository_adjudication"
    HUMAN_DOMAIN_REVIEW = "human_domain_review"
    QUALIFIED_HUMAN_LEGAL_REVIEW = "qualified_human_legal_review"


class AmbiguityCategory(StrEnum):
    """Approved ambiguity categories from the evaluation protocol."""

    HARMLESS_LINGUISTIC_VARIATION = "harmless_linguistic_variation"
    RESOLVABLE_FROM_LEGAL_CONTEXT = "resolvable_from_legal_context"
    REQUIRES_CLARIFICATION = "requires_clarification"
    UNSAFE_FOR_ANSWER_GENERATION = "unsafe_for_answer_generation"


class EvidenceGroupRequirement(StrEnum):
    """Whether an evidence group is required for answer completeness."""

    REQUIRED = "required"
    OPTIONAL = "optional"
