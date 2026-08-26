from types import MethodType


MODEL_ORDER = {
    "orchestrator": ["DataSource", "AIDomain", "BusinessRule", "TablePolicy", "ColumnPolicy", "ColumnRolePolicy", "RowAccessPolicy", "SuggestedPrompt", "TrainingPrompt", "TrainingCandidate", "AnalysisSession", "QueryAudit", "VannaSettings"],
    "tickets": ["Project", "Product", "Category", "SupportGroup", "ApprovalWorkflow", "ApprovalStep", "SLAPolicy", "SLAEscalationRule", "DynamicForm", "DynamicFormVersion", "DynamicFieldSchema", "FormDataSource", "Ticket", "TicketApproval", "TicketEscalation", "TicketAttachment", "TicketComment", "TicketEvent", "TicketShare", "Notification", "TicketDynamicData", "RelatedTicket", "SavedTicketView"],
    "accounts": ["UserProfile", "AccountPolicy"],
    "ai": ["AISettings", "AIInteraction"],
    "core": ["ModuleRegistry", "ConfigurationVersion", "AuditLog"],
}


def install_numbered_admin_index(admin_site):
    original = admin_site.get_app_list

    def numbered(self, request, app_label=None):
        app_list = original(request, app_label)
        for app in app_list:
            order = MODEL_ORDER.get(app["app_label"], [])
            positions = {name: index for index, name in enumerate(order, 1)}
            app["models"].sort(key=lambda model: (positions.get(model["object_name"], 999), model["name"]))
            for fallback, model in enumerate(app["models"], 1):
                number = positions.get(model["object_name"], fallback)
                clean_name = model["name"].split(". ", 1)[-1]
                model["name"] = f"{number:02d}. {clean_name}"
        return app_list

    admin_site.get_app_list = MethodType(numbered, admin_site)
