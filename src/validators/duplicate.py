"""Duplicate detection via Levenshtein distance and token-overlap similarity."""

from __future__ import annotations

import structlog

from src.validators.models import ValidationResult

logger = structlog.get_logger(__name__)

# Thresholds
LEVENSHTEIN_THRESHOLD = 3  # names within this edit distance are flagged
JACCARD_THRESHOLD = 0.6    # description overlap above this is flagged


# ------------------------------------------------------------------
# Levenshtein distance (manual implementation)
# ------------------------------------------------------------------

def levenshtein_distance(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Uses the classic dynamic-programming approach with O(min(m,n)) space.
    """
    if len(a) < len(b):
        return levenshtein_distance(b, a)

    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            current_row.append(
                min(
                    current_row[j] + 1,        # insertion
                    previous_row[j + 1] + 1,    # deletion
                    previous_row[j] + cost,     # substitution
                )
            )
        previous_row = current_row

    return previous_row[-1]


# ------------------------------------------------------------------
# Token overlap (Jaccard similarity)
# ------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Lowercase and split on whitespace/punctuation into a token set."""
    import re
    return set(re.findall(r"[\w]+", text.lower()))


def jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two strings based on word tokens."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# ------------------------------------------------------------------
# Validator
# ------------------------------------------------------------------

class DuplicateValidator:
    """Detects potential duplicate content using string similarity metrics."""

    def __init__(
        self,
        *,
        name_threshold: int = LEVENSHTEIN_THRESHOLD,
        description_threshold: float = JACCARD_THRESHOLD,
    ) -> None:
        self.name_threshold = name_threshold
        self.description_threshold = description_threshold
        self.log = logger.bind(validator="DuplicateValidator")

    def check_name_similarity(
        self,
        name: str,
        existing_names: list[str],
    ) -> ValidationResult:
        """Check whether *name* is too close to any existing name
        (Levenshtein distance <= threshold)."""
        self.log.info("check_name_similarity", name=name, existing_count=len(existing_names))

        similar: list[dict[str, object]] = []
        name_lower = name.lower()

        for existing in existing_names:
            dist = levenshtein_distance(name_lower, existing.lower())
            if dist <= self.name_threshold and dist > 0:
                similar.append({"existing_name": existing, "distance": dist})
            elif dist == 0:
                similar.append({"existing_name": existing, "distance": 0})

        if not similar:
            return ValidationResult(
                passed=True,
                check_name="name_similarity",
                severity="info",
                message=f"Name '{name}' has no close matches.",
            )

        exact = [s for s in similar if s["distance"] == 0]
        if exact:
            return ValidationResult(
                passed=False,
                check_name="name_similarity",
                severity="error",
                message=f"Name '{name}' is an exact duplicate.",
                details={"matches": similar},
            )

        return ValidationResult(
            passed=False,
            check_name="name_similarity",
            severity="warning",
            message=(
                f"Name '{name}' is very similar to {len(similar)} existing name(s)."
            ),
            details={"matches": similar},
        )

    def check_description_similarity(
        self,
        description: str,
        existing_descriptions: list[str],
    ) -> ValidationResult:
        """Check whether *description* overlaps too much with any existing
        description (Jaccard similarity >= threshold)."""
        self.log.info(
            "check_description_similarity",
            desc_length=len(description),
            existing_count=len(existing_descriptions),
        )

        high_overlap: list[dict[str, object]] = []

        for idx, existing in enumerate(existing_descriptions):
            sim = jaccard_similarity(description, existing)
            if sim >= self.description_threshold:
                high_overlap.append({
                    "index": idx,
                    "similarity": round(sim, 4),
                    "existing_snippet": existing[:100],
                })

        if not high_overlap:
            return ValidationResult(
                passed=True,
                check_name="description_similarity",
                severity="info",
                message="Description has no significant overlap with existing content.",
            )

        max_sim = max(m["similarity"] for m in high_overlap)  # type: ignore[type-var]
        severity = "error" if max_sim >= 0.9 else "warning"

        return ValidationResult(
            passed=False,
            check_name="description_similarity",
            severity=severity,  # type: ignore[arg-type]
            message=(
                f"Description overlaps with {len(high_overlap)} existing "
                f"description(s) (max similarity={max_sim:.2%})."
            ),
            details={"matches": high_overlap},
        )
