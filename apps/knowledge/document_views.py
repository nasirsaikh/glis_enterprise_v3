from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.core.mayan import MayanError, mayan
from .models import Article


@login_required
def article_documents(request, slug):
    article = get_object_or_404(Article, slug=slug)
    documents, error = [], ""
    try:
        payload = mayan.search_documents(query=f"knowledge:{article.slug}", page=1, page_size=100)
        documents = payload.get("results", payload if isinstance(payload, list) else [])
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
