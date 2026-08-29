from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.mayan import MayanError, mayan
from services.access import TicketAccessPolicy
from .models import Ticket


def _ticket(request, reference):
    return get_object_or_404(TicketAccessPolicy.visible_queryset(request.user), reference=reference)


@login_required
def ticket_documents(request, reference):
    ticket = _ticket(request, reference)
    documents, error = [], ""
    try:
        payload = mayan.search_documents(query=ticket.reference, page=1, page_size=100)
        documents = payload.get("results", payload if isinstance(payload, list) else [])
    except MayanError as exc:
        error = str(exc)
    return render(request, "tickets/partials/mayan_documents.html", {"ticket": ticket, "mayan_documents": documents, "mayan_error": error})


@login_required
@require_POST
def ticket_document_upload(request, reference):
    ticket = _ticket(request, reference)
    if not TicketAccessPolicy.can_edit(request.user, ticket) and request.user.pk != ticket.requester_id:
        return HttpResponse("Document upload permission is required.", status=403)
    uploads = request.FILES.getlist("documents") or ([request.FILES["file"]] if request.FILES.get("file") else [])
    if not uploads:
        return HttpResponse("Select at least one document.", status=422)
    errors = []
    for upload in uploads:
        try:
            mayan.upload_document(upload, label=f"{ticket.reference} - {upload.name}", metadata={
                "glis_object_type": "ticket",
                "glis_object_id": ticket.pk,
                "glis_reference": ticket.reference,
                "glis_project": ticket.project.code,
                "glis_product": ticket.product.code,
                "glis_category": ticket.category.code,
                "uploaded_by": request.user.email,
            })
        except MayanError as exc:
            errors.append(f"{upload.name}: {exc}")
    if errors:
        messages.error(request, " | ".join(errors))
    else:
        messages.success(request, f"{len(uploads)} document(s) stored in Mayan EDMS.")
    if request.headers.get("HX-Request"):
        return ticket_documents(request, reference)
    return redirect("portal:ticket_detail", reference=ticket.reference)


@login_required
def ticket_document_download(request, reference, document_id):
    _ticket(request, reference)
    try:
        response = mayan.download_document(document_id)
    except MayanError as exc:
        return HttpResponse(f"Document service unavailable: {exc}", status=502)
    return FileResponse(response.raw, as_attachment=True, filename=f"document-{document_id}", content_type=response.headers.get("Content-Type", "application/octet-stream"))
