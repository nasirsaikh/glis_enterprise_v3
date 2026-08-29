from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.core.mayan import MayanError, mayan
from .models import Article


def _documents(article):
    payload = mayan.search_documents(query=f"knowledge:{article.slug}", page=1, page_size=100)
    return payload.get("results", payload if isinstance(payload, list) else [])


@login_required
def article_documents(request, slug):
    article = get_object_or_404(Article, slug=slug)
    documents, error = [], ""
    try:
        documents = _documents(article)
    except MayanError as exc:
        error = str(exc)
    return render(request, "knowledge/partials/managed_documents.html", {"article": article, "managed_documents": documents, "mayan_error": error})


@login_required
@require_POST
def article_document_upload(request, slug):
    article = get_object_or_404(Article, slug=slug)
    if not (request.user.is_staff or request.user.is_superuser or article.author_id == request.user.pk):
        return HttpResponse("Controlled document upload permission is required.", status=403)
    upload = request.FILES.get("file")
    if not upload:
        return HttpResponse("Select a document.", status=422)
    try:
        mayan.upload_document(upload, label=f"knowledge:{article.slug} - {upload.name}", metadata={"glis_object_type": "knowledge", "glis_object_id": article.pk, "glis_reference": f"knowledge:{article.slug}", "article": article.title_en, "uploaded_by": request.user.email, "controlled_document": True})
    except MayanError as exc:
        return HttpResponse(f"Document upload failed: {exc}", status=502)
    return article_documents(request, slug)


@login_required
def article_document_download(request, slug, document_id):
    article = get_object_or_404(Article, slug=slug)
    if not article.is_public and not (request.user.is_staff or request.user.is_superuser or article.author_id == request.user.pk):
        return HttpResponse("Controlled document access denied.", status=403)
    try:
        allowed_ids = {int(item["id"]) for item in _documents(article) if item.get("id") is not None}
        if int(document_id) not in allowed_ids:
            return HttpResponse("This document is not linked to the requested article.", status=403)
        response = mayan.download_document(document_id)
    except MayanError as exc:
        return HttpResponse(f"Document service unavailable: {exc}", status=502)
    return FileResponse(response.raw, as_attachment=True, filename=f"document-{document_id}", content_type=response.headers.get("Content-Type", "application/octet-stream"))
