"""Deterministic business rules — plain Python, no LLM involved.

These checks don't require semantic understanding: once the LLM has told us
*what* the action/owner/deadline/deliverable are, whether something is
"missing" or "overdue" is a fact we can check with an if-statement. Doing
this in Python instead of asking the LLM again makes the result
reproducible, fast, free, and testable without hitting an API.
"""
from datetime import date
from typing import Dict, List, Tuple

from .models import Deliverable, Issue, LLMExtraction

HIGH = "high"
MEDIUM = "medium"
LOW = "low"


def check_issues(
    extraction: LLMExtraction,
    deliverables_index: Dict[str, Deliverable],
    today: date | None = None,
) -> Tuple[List[Issue], bool]:
    today = today or date.today()
    issues: List[Issue] = []

    for action in extraction.actions:
        deliverable = (
            deliverables_index.get(action.affected_deliverable)
            if action.affected_deliverable
            else None
        )

        # An owner already on record for the deliverable counts as "assigned"
        # even if the protocol text itself didn't name anyone. Simplification:
        # the deliverable's owner isn't necessarily the owner of this specific
        # action (e.g. someone else on that package could be doing this task) -
        # acceptable for the MVP, but a production version would surface the
        # deliverable owner as a suggested contact rather than silently
        # assigning them the action.
        effective_owner = action.owner or (deliverable.owner if deliverable else None)

        if not effective_owner:
            issues.append(
                Issue(
                    type="missing_owner",
                    severity=HIGH if action.affected_deliverable else MEDIUM,
                    message=f"No owner is assigned for action: '{action.action}'",
                )
            )

        if not action.deadline:
            issues.append(
                Issue(
                    type="missing_deadline",
                    severity=MEDIUM,
                    message=f"No deadline is specified for action: '{action.action}'",
                )
            )
        else:
            try:
                deadline_date = date.fromisoformat(action.deadline)
                if deadline_date < today:
                    issues.append(
                        Issue(
                            type="deadline_passed",
                            severity=HIGH,
                            message=(
                                f"Deadline {action.deadline} for action "
                                f"'{action.action}' has already passed"
                            ),
                        )
                    )
            except ValueError:
                issues.append(
                    Issue(
                        type="invalid_deadline_format",
                        severity=LOW,
                        message=f"Deadline '{action.deadline}' is not a valid ISO date",
                    )
                )

        # Simplification: any extracted dependency is treated as unresolved.
        # The LLM currently has no way to say "this dependency is already
        # satisfied" - a production version would extract a status per
        # dependency (or instruct the LLM to only report unresolved ones).
        if action.dependencies:
            issues.append(
                Issue(
                    type="unresolved_dependency",
                    severity=MEDIUM,
                    message=(
                        f"Action '{action.action}' has unresolved dependencies: "
                        f"{', '.join(action.dependencies)}"
                    ),
                )
            )

        if action.affected_deliverable and deliverable is None:
            issues.append(
                Issue(
                    type="unknown_deliverable",
                    severity=MEDIUM,
                    message=(
                        f"Affected deliverable '{action.affected_deliverable}' was "
                        "not found in the deliverables register"
                    ),
                )
            )

        if deliverable is not None and deliverable.status.lower() == "closed":
            issues.append(
                Issue(
                    type="coordination_issue",
                    severity=MEDIUM,
                    message=(
                        f"Deliverable '{deliverable.deliverable_id}' is marked as "
                        "Closed but is referenced again in this protocol"
                    ),
                )
            )

    requires_attention = any(i.severity in (MEDIUM, HIGH) for i in issues)
    return issues, requires_attention
