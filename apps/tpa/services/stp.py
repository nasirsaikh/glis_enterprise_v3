def evaluate_stp(tx):
    blockers = []
    actions = list(tx.member_actions.all())

    if not tx.policy.stp_enabled:
        blockers.append("POLICY_STP_DISABLED")
    if tx.validation_bypassed:
        blockers.append("VALIDATION_BYPASSED")
    if tx.transaction_type != tx.Type.POLICY_CANCEL and not actions:
        blockers.append("NO_MEMBER_ROWS")

    for action in actions:
        if action.validation_status == action.Result.ERROR:
            blockers.append("BLOCKING_VALIDATION")
        if (
            action.extraction_confidence is not None
            and action.extraction_confidence < 80
        ):
            blockers.append("LOW_AI_CONFIDENCE")

    if tx.ticket_id and tx.ticket.approval_state == "pending":
        blockers.append("APPROVAL_REQUIRED")

    tx.stp_blockers = sorted(set(blockers))
    tx.stp_eligible = not tx.stp_blockers
    tx.save(update_fields=["stp_blockers", "stp_eligible", "updated_at"])
    return tx.stp_eligible, tx.stp_blockers
