"""Store, chain and branch detection from receipt header evidence."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.domain.receipt_extraction import FieldCandidate, ReasonCode, StoreExtraction, StoreResolution

CHAIN_ALIASES_VERSION = "1.0.0"

# Canonical chain id -> list of regex patterns matching chain name
CHAIN_ALIASES: dict[str, list[re.Pattern[str]]] = {
    "rema1000": [re.compile(r"(?i)rema\s*1000"), re.compile(r"(?i)r\s*ema\s*l?0{2,4}")],
    "kiwi": [re.compile(r"(?i)\bkiwi\b")],
    "normal": [re.compile(r"(?i)^normal\b"), re.compile(r"(?i)\bnormal\s+oslo\b")],
    "europris": [re.compile(r"(?i)^ep\b"), re.compile(r"(?i)\beuropris\b")],
    "coop": [re.compile(r"(?i)\bcoop\b"), re.compile(r"(?i)\bextra\b"), re.compile(r"(?i)\bprix\b")],
    "meny": [re.compile(r"(?i)\bmeny\b")],
}

_NON_BRANCH_LINES = re.compile(
    r"(?i)^(?:"
    r"velkommen|velkomst|salgskvittering|kvittering|"
    r"org\.?\s*nr|tlf|telefon|kasse|kvitt|serienr|"
    r"\d{3}\s+\d{3}\s+\d{3}|"  # org number pattern
    r"produktnavn|vare|dato|beskrivelse|beløp|"
    r"\d{2}[./ -]\d{2}[./ -]\d{2,4}"  # date/time lines
    r")\b",
)

_JUNK_FIRST_LINES = re.compile(
    r"(?i)^(?:velkommen|velkomst|welcome|takk\s+for\s+besøket)\.?\s*$",
)

_LEGAL_ENTITY = re.compile(r"(?i)\b(?:as|asa|da|ans)\.?\s*$")


@dataclass
class StoreCandidateInternal:
    candidate_id: str
    chain: str | None
    branch_text: str | None
    observed_text: str
    rule_id: str
    line_index: int
    resolution: StoreResolution
    rank_score: float


@dataclass
class UserStoreContext:
    """Optional user-confirmed store aliases injected by caller (OCR-07)."""
    user_store_id: str
    chain: str | None
    alias_patterns: tuple[str, ...]


def _detect_chain(line: str) -> str | None:
    normalized = line.strip()
    for chain_id, patterns in CHAIN_ALIASES.items():
        if any(p.search(normalized) for p in patterns):
            return chain_id
    return None


def _extract_rema_branch(line: str) -> tuple[str | None, str | None]:
    match = re.match(r"(?i)^rema\s*1000\s+(.+)$", line.strip())
    if match:
        branch = match.group(1).strip()
        return "rema1000", branch if branch else None
    if re.search(r"(?i)rema\s*1000", line):
        return "rema1000", None
    return None, None


def _extract_normal_branch(line: str) -> tuple[str | None, str | None]:
    match = re.match(r"(?i)^normal\s+(.+)$", line.strip())
    if match:
        branch = re.split(r"\s+Tlf", match.group(1), flags=re.I)[0].strip()
        return "normal", branch if branch else None
    return None, None


def _extract_europris_branch(line: str) -> tuple[str | None, str | None]:
    match = re.match(r"(?i)^EP\s+(.+?)(?:\s+Tlf.*)?$", line.strip())
    if match:
        branch = re.split(r"\s+Tlf", match.group(1), flags=re.I)[0].strip()
        return "europris", branch if branch else None
    if re.search(r"(?i)europris", line):
        return "europris", None
    return None, None


def _extract_kiwi_branch(line: str) -> tuple[str | None, str | None]:
    match = re.match(r"(?i)^kiwi\s+(.+)$", line.strip())
    if match:
        branch = match.group(1).strip()
        # "Oslo" alone is not verified branch identity
        if branch.lower() in {"oslo", "bergen", "trondheim", "stavanger"}:
            return "kiwi", branch
        return "kiwi", branch
    if re.search(r"(?i)\bkiwi\b", line):
        return "kiwi", None
    return None, None


_CHAIN_EXTRACTORS = [
    _extract_rema_branch,
    _extract_normal_branch,
    _extract_europris_branch,
    _extract_kiwi_branch,
]


def _is_non_branch_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _NON_BRANCH_LINES.search(stripped):
        return True
    if _LEGAL_ENTITY.search(stripped):
        return True
    return False


def _collect_line_candidates(lines: list[str], max_header_lines: int = 20) -> list[StoreCandidateInternal]:
    candidates: list[StoreCandidateInternal] = []
    header = lines[:max_header_lines]

    for i, line in enumerate(header):
        stripped = line.strip()
        if not stripped or _is_non_branch_line(stripped):
            continue
        if _JUNK_FIRST_LINES.match(stripped):
            continue

        for extractor in _CHAIN_EXTRACTORS:
            chain, branch = extractor(stripped)
            if chain:
                resolution: StoreResolution = "branch" if branch else "chain_only"
                rank = 95.0 - i if branch else 70.0 - i
                candidates.append(
                    StoreCandidateInternal(
                        candidate_id=str(uuid.uuid4()),
                        chain=chain,
                        branch_text=branch,
                        observed_text=stripped,
                        rule_id=f"chain_line_{extractor.__name__}",
                        line_index=i,
                        resolution=resolution,
                        rank_score=rank,
                    ),
                )
                break

        # Multi-line: chain on one line, branch on next (rank above same-line chain_only)
        if i + 1 < len(header):
            next_line = header[i + 1].strip()
            chain_only = _detect_chain(stripped)
            if chain_only and not _is_non_branch_line(next_line) and not _detect_chain(next_line):
                if not _JUNK_FIRST_LINES.match(next_line):
                    candidates.append(
                        StoreCandidateInternal(
                            candidate_id=str(uuid.uuid4()),
                            chain=chain_only,
                            branch_text=next_line,
                            observed_text=f"{stripped} / {next_line}",
                            rule_id="chain_next_line_branch",
                            line_index=i,
                            resolution="branch",
                            rank_score=90.0 - i,
                        ),
                    )
                    continue

    return candidates


def _match_user_context(
    candidate: StoreCandidateInternal,
    contexts: list[UserStoreContext] | None,
) -> str | None:
    if not contexts:
        return None
    for ctx in contexts:
        if ctx.chain and candidate.chain and ctx.chain != candidate.chain:
            continue
        for alias in ctx.alias_patterns:
            if alias.lower() in candidate.observed_text.lower():
                return ctx.user_store_id
    return None


def detect_store(
    text: str,
    *,
    user_store_contexts: list[UserStoreContext] | None = None,
) -> StoreExtraction:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return StoreExtraction(state="missing", reason_codes=(ReasonCode.STORE_UNRESOLVED,))

    candidates = _collect_line_candidates(lines)

    # Detect multiple competing chain headers
    chains_found = {c.chain for c in candidates if c.chain}
    if len(chains_found) > 1:
        field_candidates = tuple(
            FieldCandidate(
                candidate_id=c.candidate_id,
                value_text=c.observed_text,
                rule_id=c.rule_id,
                state="uncertain",
                rank_score=c.rank_score,
            )
            for c in candidates
        )
        return StoreExtraction(
            state="uncertain",
            candidates=field_candidates,
            reason_codes=(ReasonCode.MULTIPLE_DOCUMENTS,),
        )

    if not candidates:
        # Unknown chain — use first non-junk line as observed text only
        for line in lines[:5]:
            if not _JUNK_FIRST_LINES.match(line) and not _is_non_branch_line(line):
                return StoreExtraction(
                    observed_text=line.strip(),
                    resolution="unknown",
                    state="uncertain",
                    reason_codes=(ReasonCode.STORE_UNRESOLVED,),
                )
        return StoreExtraction(state="missing", reason_codes=(ReasonCode.STORE_UNRESOLVED,))

    best = max(candidates, key=lambda c: c.rank_score)
    user_store_id = _match_user_context(best, user_store_contexts)

    reason_codes: tuple[ReasonCode, ...] = ()
    if best.resolution == "chain_only":
        reason_codes = (ReasonCode.BRANCH_UNRESOLVED,)

    field_candidates = tuple(
        FieldCandidate(
            candidate_id=c.candidate_id,
            value_text=c.observed_text,
            rule_id=c.rule_id,
            state="accepted" if c.candidate_id == best.candidate_id else "uncertain",
            rank_score=c.rank_score,
        )
        for c in candidates
    )

    if best.resolution == "branch" and " / " not in best.observed_text:
        store_name = re.split(r"\s+Tlf", best.observed_text, flags=re.I)[0].strip()
    else:
        store_name = _format_store_name(best.chain, best.branch_text, best.observed_text)

    return StoreExtraction(
        chain=best.chain,
        branch_text=best.branch_text,
        observed_text=store_name or best.observed_text,
        resolved_user_store_id=user_store_id,
        resolution=best.resolution,
        state="accepted" if best.resolution == "branch" else "uncertain",
        selected_candidate_id=best.candidate_id,
        candidates=field_candidates,
        reason_codes=reason_codes,
    )


def _format_store_name(chain: str | None, branch: str | None, observed: str) -> str | None:
    if chain == "rema1000":
        if branch:
            return f"REMA 1000 {branch.upper()}"
        return "REMA 1000"
    if chain == "normal" and branch:
        return f"Normal {branch}"
    if chain == "europris" and branch:
        return f"EP {branch}"
    if chain == "kiwi" and branch:
        return f"KIWI {branch.upper()}"
    if chain:
        return observed
    return observed
