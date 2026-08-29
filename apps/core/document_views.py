from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .mayan import MayanError, mayan


@login_required
def document_center(request):
    query = request.GET.get("q", "").strip()
    page = max(int(request.GET.get("page", 1) or 1), 1)
    payload = {"results": [], "count": 0}
    error = ""
    if mayan.enabled:
        try:
            payload = mayan.search_documents(query=query, page=page, page_size=25)
        except MayanError as exc:
            error = str(exc)
    else:
        error = "Mayan EDMS is not enabled on this GLIS environment."
    context = {
        "query": query,
        "documents": payload.get("results", payload if isinstance(payload, list) else []),
        "total": payload.get("count", 0) if isinstance(payload, dict) else len(payload),
        "mayan_enabled": mayan.enabled,
        "mayan_error": error,
        "can_open_mayan": request.user.is_superuser or request.user.is_staff,
        "mayan_admin_url": mayan.admin_url,
    }
    template = "documents/partials/results.html" if request.headers.get("HX-Request") else "documents/center.html"
    return render(request, template, context)


@login_required
def mayan_document_download(request, document_id):
    try:
        response = mayan.download_document(document_id)
    except MayanError as exc:
        return HttpResponse(f"Document service unavailable: {exc}", status=502)
    filename = f"document-{document_id}"
    disposition = response.headers.get("Content-Disposition", "")
    if "filename=" in disposition:
        filename = disposition.split("filename=", 1)[1].strip().strip('"')
    return FileResponse(response.raw, as_attachment=True, filename=filename, content_type=response.headers.get("Content-Type", "application/octet-stream"))


@login_required
def mayan_document_open(request, document_id):
    return redirect(mayan.document_url(document_id))


@login_required
@permission_required("core.open_mayan_edms", raise_exception=True)
def mayan_admin(request):
    return redirect(mayan.admin_url)


@login_required
@require_POST
def document_upload(request):
    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Select a document to upload.")
        return redirect("documents:center")
    try:
        mayan.upload_document(upload, label=request.POST.get("title", upload.name), metadata={"glis_category": request.POST.get("category", "general"), "uploaded_by": request.user.email})
        messages.success(request, f"{upload.name} was sent to Mayan EDMS.")
    except MayanError as exc:
        messages.error(request, f"Document upload failed: {exc}")
    return redirect("documents:center")
