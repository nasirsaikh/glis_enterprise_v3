"""Local full-page OCR recovery; no document is sent to a hosted service."""
import io
import tempfile
from pathlib import Path

from django.conf import settings


def docling_text(name, content):
    if not getattr(settings, "TPA_DOCLING_FALLBACK_ENABLED", True):
        raise RuntimeError("Docling recovery is disabled in backend settings.")
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError("Document recovery requires docling and easyocr from requirements.txt.") from exc

    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    options.enable_remote_services = False
    options.document_timeout = float(getattr(settings, "TPA_DOCLING_TIMEOUT", 180))
    ocr = EasyOcrOptions(lang=["en", "ar"], use_gpu=getattr(settings, "TPA_DOCLING_USE_GPU", False))
    if hasattr(ocr, "force_full_page_ocr"):
        ocr.force_full_page_ocr = True
    else:
        from docling.datamodel.pipeline_options import OcrMode
        ocr.mode = OcrMode.FULL_PAGE
    options.ocr_options = ocr
    with tempfile.TemporaryDirectory(prefix="glis-ocr-") as directory:
        path = Path(directory) / "evidence.pdf"
        if Path(name).suffix.lower() == ".pdf":
            path.write_bytes(content)
        else:
            from PIL import Image, ImageOps
            with Image.open(io.BytesIO(content)) as image:
                ImageOps.exif_transpose(image).convert("RGB").save(path, format="PDF")
        converter = DocumentConverter(format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        })
        result = converter.convert(
            path, max_num_pages=getattr(settings, "TPA_DOCLING_MAX_PAGES", 50),
            max_file_size=10 * 1024 * 1024,
        )
        text = result.document.export_to_markdown().strip()
        if not text:
            raise RuntimeError("Docling could not recover readable text.")
        return text
