from datetime import datetime

from ..registry import register_job


@register_job("system.test_job")
def test_job(message="Hello from GLIS Job Center"):
    return {
        "success": True,
        "message": message,
        "executed_at": datetime.now().isoformat(),
    }


# Example integration:
#
# from apps.orchestrator.services.reports import generate_claim_dashboard
#
# @register_job("reports.claim_dashboard")
# def claim_dashboard(**kwargs):
#     return generate_claim_dashboard(**kwargs)
