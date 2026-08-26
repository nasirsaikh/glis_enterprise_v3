from typing import Any, Literal, TypedDict


class UserContract(TypedDict):
    id: int
    email: str
    role: str


class TicketContract(TypedDict):
    reference: str
    subject: str
    description: str
    status: str
    priority: str
    project_id: int
    product_id: int
    category_id: int
    requester: UserContract
    dynamic_data: dict[str, Any]


class FieldSchemaContract(TypedDict, total=False):
    name: str
    label_en: str
    label_ar: str
    control: str
    required: bool
    validation: dict[str, Any]
    data_source: dict[str, Any]


class DynamicFormContract(TypedDict):
    key: str
    version: int
    state: Literal["draft", "published", "archived"]
    fields: list[FieldSchemaContract]


class AIAnalysisContract(TypedDict, total=False):
    summary: str
    suggested_category: str
    suggested_priority: str
    suggested_group: str
    suggested_assignee: str
    suggested_solution: str
    similar_tickets: list[str]
    knowledge_articles: list[str]
    confidence: float
