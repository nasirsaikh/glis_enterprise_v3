from abc import ABC, abstractmethod
from hashlib import sha256


class AIProvider(ABC):
    @abstractmethod
    def analyze_ticket(self, ticket_payload: dict) -> dict:
        raise NotImplementedError


class MockAIProvider(AIProvider):
    def analyze_ticket(self, ticket_payload: dict) -> dict:
        text = f"{ticket_payload.get('subject', '')} {ticket_payload.get('description', '')}".lower()
        priority = "high" if any(word in text for word in ("urgent", "hospital", "blocked", "payment")) else "medium"
        group = "Claims" if "claim" in text else "Customer Service"
        digest = sha256(text.encode()).hexdigest()[:6]
        return {
            "summary": f"Request captured for review: {ticket_payload.get('description', '')[:260]}",
            "suggested_priority": priority, "suggested_group": group,
            "suggested_category": ticket_payload.get("category", "General service"),
            "suggested_solution": "Verify the request details and supporting documents, then route to the responsible service team.",
            "similar_tickets": [f"DEMO-{digest}"], "knowledge_articles": ["Preparing documents for a service request"],
            "confidence": 0.82, "label": "AI-generated recommendation",
        }


class OpenAICompatibleProvider(AIProvider):
    def analyze_ticket(self, ticket_payload: dict) -> dict:
        raise RuntimeError("Real provider calls are intentionally disabled until an approved endpoint, data policy and secret are configured.")


def get_provider(name="mock"):
    return MockAIProvider() if name == "mock" else OpenAICompatibleProvider()
