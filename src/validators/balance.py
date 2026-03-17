"""Statistical balance validation for game items."""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from src.generators.item_generator import GeneratedItem
from src.validators.models import ValidationResult

logger = structlog.get_logger(__name__)

# Rarity ordering used for hierarchy checks
RARITY_ORDER: dict[str, int] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
}

STAT_KEYS = ("atk", "def", "hp", "mp")


def _total_stats(item: dict[str, Any]) -> int:
    """Return the sum of all stat values for an item dict."""
    stats = item.get("stats", {})
    return sum(stats.get(k, 0) for k in STAT_KEYS)


def _item_to_dict(item: GeneratedItem | dict[str, Any]) -> dict[str, Any]:
    """Normalize to a plain dict."""
    if isinstance(item, GeneratedItem):
        return item.model_dump(by_alias=True)
    return item


class BalanceValidator:
    """Validates item stats against statistical ranges derived from existing items."""

    def __init__(self) -> None:
        self.log = logger.bind(validator="BalanceValidator")

    # ------------------------------------------------------------------
    # Public checks
    # ------------------------------------------------------------------

    def check_stat_range(
        self,
        item: GeneratedItem | dict[str, Any],
        existing_items: list[dict[str, Any]],
    ) -> ValidationResult:
        """Check that each stat is within mean +/- 2 standard deviations of
        existing items at a similar level and rarity."""
        item_d = _item_to_dict(item)
        self.log.info("check_stat_range", item_name=item_d.get("name"))

        pool = self._same_bucket(item_d, existing_items)
        if len(pool) < 3:
            return ValidationResult(
                passed=True,
                check_name="stat_range",
                severity="info",
                message="Not enough reference data to perform stat range check.",
                details={"pool_size": len(pool)},
            )

        out_of_range: list[dict[str, Any]] = []
        item_stats = item_d.get("stats", {})

        for key in STAT_KEYS:
            values = np.array([p.get("stats", {}).get(key, 0) for p in pool], dtype=float)
            mean = float(np.mean(values))
            std = float(np.std(values))
            val = item_stats.get(key, 0)
            lo = mean - 2 * std
            hi = mean + 2 * std
            if val < lo or val > hi:
                out_of_range.append({
                    "stat": key,
                    "value": val,
                    "mean": round(mean, 2),
                    "std": round(std, 2),
                    "range": [round(lo, 2), round(hi, 2)],
                })

        if out_of_range:
            return ValidationResult(
                passed=False,
                check_name="stat_range",
                severity="warning",
                message=f"{len(out_of_range)} stat(s) outside expected range.",
                details={"violations": out_of_range},
            )

        return ValidationResult(
            passed=True,
            check_name="stat_range",
            severity="info",
            message="All stats within expected range.",
        )

    def check_rarity_hierarchy(
        self,
        item: GeneratedItem | dict[str, Any],
        existing_items: list[dict[str, Any]],
    ) -> ValidationResult:
        """Verify that higher-rarity items have strictly higher total stats
        than the median of the next-lower rarity at the same level band."""
        item_d = _item_to_dict(item)
        rarity = item_d.get("rarity", "common")
        rarity_rank = RARITY_ORDER.get(rarity, 0)
        self.log.info("check_rarity_hierarchy", item_name=item_d.get("name"), rarity=rarity)

        if rarity_rank == 0:
            return ValidationResult(
                passed=True,
                check_name="rarity_hierarchy",
                severity="info",
                message="Common rarity; no lower tier to compare against.",
            )

        lower_rarity = next(r for r, v in RARITY_ORDER.items() if v == rarity_rank - 1)
        level = item_d.get("level_requirement", 1)
        level_band = (max(1, level - 5), level + 5)

        lower_items = [
            i for i in existing_items
            if i.get("rarity") == lower_rarity
            and level_band[0] <= i.get("level_requirement", 0) <= level_band[1]
        ]

        if not lower_items:
            return ValidationResult(
                passed=True,
                check_name="rarity_hierarchy",
                severity="info",
                message=f"No {lower_rarity} items in level band to compare.",
            )

        lower_totals = np.array([_total_stats(i) for i in lower_items], dtype=float)
        lower_median = float(np.median(lower_totals))
        item_total = _total_stats(item_d)

        if item_total <= lower_median:
            return ValidationResult(
                passed=False,
                check_name="rarity_hierarchy",
                severity="error",
                message=(
                    f"{rarity} item total stats ({item_total}) should exceed "
                    f"{lower_rarity} median ({lower_median:.0f})."
                ),
                details={
                    "item_total": item_total,
                    "lower_rarity": lower_rarity,
                    "lower_median": round(lower_median, 2),
                },
            )

        return ValidationResult(
            passed=True,
            check_name="rarity_hierarchy",
            severity="info",
            message="Item properly exceeds lower-rarity stat median.",
        )

    def check_level_curve(
        self,
        item: GeneratedItem | dict[str, Any],
        existing_items: list[dict[str, Any]],
    ) -> ValidationResult:
        """Verify that the item's total stats follow a reasonable
        increasing trend relative to level."""
        item_d = _item_to_dict(item)
        rarity = item_d.get("rarity", "common")
        self.log.info("check_level_curve", item_name=item_d.get("name"))

        same_rarity = [i for i in existing_items if i.get("rarity") == rarity]
        if len(same_rarity) < 5:
            return ValidationResult(
                passed=True,
                check_name="level_curve",
                severity="info",
                message="Not enough data to check level curve.",
                details={"pool_size": len(same_rarity)},
            )

        levels = np.array([i.get("level_requirement", 1) for i in same_rarity], dtype=float)
        totals = np.array([_total_stats(i) for i in same_rarity], dtype=float)

        # Simple linear regression: total_stats = a * level + b
        coeffs = np.polyfit(levels, totals, 1)
        slope, intercept = float(coeffs[0]), float(coeffs[1])

        item_level = item_d.get("level_requirement", 1)
        item_total = _total_stats(item_d)
        expected = slope * item_level + intercept
        residuals = totals - (slope * levels + intercept)
        residual_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

        deviation = abs(item_total - expected)
        threshold = max(2 * residual_std, 10)  # at least 10 to avoid false positives

        if deviation > threshold:
            return ValidationResult(
                passed=False,
                check_name="level_curve",
                severity="warning",
                message=(
                    f"Item total stats ({item_total}) deviate from level curve "
                    f"(expected ~{expected:.0f} +/- {threshold:.0f})."
                ),
                details={
                    "item_total": item_total,
                    "expected": round(expected, 2),
                    "threshold": round(threshold, 2),
                    "slope": round(slope, 4),
                    "intercept": round(intercept, 2),
                },
            )

        return ValidationResult(
            passed=True,
            check_name="level_curve",
            severity="info",
            message="Item stats follow the expected level curve.",
        )

    # ------------------------------------------------------------------
    # Auto-fix
    # ------------------------------------------------------------------

    def auto_fix_stats(
        self,
        item: GeneratedItem | dict[str, Any],
        existing_items: list[dict[str, Any]],
    ) -> GeneratedItem:
        """Clamp item stats to the valid range (mean +/- 2 sigma) and return
        a corrected GeneratedItem."""
        item_d = _item_to_dict(item)
        self.log.info("auto_fix_stats", item_name=item_d.get("name"))

        pool = self._same_bucket(item_d, existing_items)
        fixed_stats = dict(item_d.get("stats", {}))

        if len(pool) >= 3:
            for key in STAT_KEYS:
                values = np.array([p.get("stats", {}).get(key, 0) for p in pool], dtype=float)
                mean = float(np.mean(values))
                std = float(np.std(values))
                lo = max(0, mean - 2 * std)
                hi = mean + 2 * std
                current = fixed_stats.get(key, 0)
                fixed_stats[key] = int(np.clip(current, lo, hi))

        item_d["stats"] = fixed_stats
        return GeneratedItem.model_validate(item_d)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _same_bucket(
        item: dict[str, Any],
        existing: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return existing items with the same rarity and within +/-5 levels."""
        rarity = item.get("rarity")
        level = item.get("level_requirement", 1)
        return [
            e for e in existing
            if e.get("rarity") == rarity
            and abs(e.get("level_requirement", 1) - level) <= 5
        ]
