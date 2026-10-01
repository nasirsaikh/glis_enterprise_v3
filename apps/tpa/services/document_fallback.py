"""Local full-page OCR recovery; no document is sent to a hosted service."""
import io
import tempfile
import shutil
import subprocess
from pathlib import Path
from functools import lru_cache

from django.conf import settings


def _docling_text(name, content):
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


def _tesseract_text(name, content):
    command = getattr(settings, "TPA_TESSERACT_CMD", "") or shutil.which("tesseract")
    if not command:
        raise RuntimeError("Tesseract is not installed; install it or configure TPA_TESSERACT_CMD for an optional OCR fallback.")
    from PIL import Image, ImageOps
    with tempfile.TemporaryDirectory(prefix="glis-tesseract-") as directory:
        paths = []
        if Path(name).suffix.lower() == ".pdf":
            import fitz
            with fitz.open(stream=content, filetype="pdf") as pdf:
                if len(pdf) > getattr(settings, "TPA_DOCLING_MAX_PAGES", 50):
                    raise ValueError("The PDF exceeds the configured OCR page limit.")
                for number, page in enumerate(pdf):
                    path = Path(directory) / f"page-{number}.png"
                    page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(str(path))
                    paths.append(path)
        else:
            path = Path(directory) / "image.png"
            with Image.open(io.BytesIO(content)) as image:
                ImageOps.exif_transpose(image).convert("RGB").save(path)
            paths.append(path)
        languages = subprocess.run([command, "--list-langs"], capture_output=True, text=True, timeout=15, check=True).stdout
        lang = "eng+ara" if "ara" in languages.splitlines() else "eng"
        text = []
        for path in paths:
            result = subprocess.run(
                [command, str(path), "stdout", "-l", lang, "--psm", "12"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=float(getattr(settings, "TPA_DOCLING_TIMEOUT", 180)), check=True,
            )
            if result.stdout.strip():
                text.append(result.stdout.strip())
        if not text:
            raise RuntimeError("Tesseract could not recover readable text.")
        return "\n\n".join(text)


@lru_cache(maxsize=2)
def _easyocr_reader(use_gpu):
    import easyocr
    return easyocr.Reader(["en", "ar"], gpu=use_gpu, verbose=False)


def _easyocr_text(name, content):
    """OCR without Docling's layout/table models, including rotated ID pages."""
    import numpy as np
    from PIL import Image, ImageOps
    reader = _easyocr_reader(bool(getattr(settings, "TPA_DOCLING_USE_GPU", False)))
    images = []
    if Path(name).suffix.lower() == ".pdf":
        import fitz
        with fitz.open(stream=content, filetype="pdf") as pdf:
            if len(pdf) > getattr(settings, "TPA_DOCLING_MAX_PAGES", 50):
                raise ValueError("The PDF exceeds the configured OCR page limit.")
            for page in pdf:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                images.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3))
    else:
        with Image.open(io.BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            # Small ID photos need larger characters for detection/recognition.
            if image.width < 1400:
                image = image.resize((1400, round(image.height * 1400 / image.width)))
            images.append(np.array(image))
    pages = []
    for number, image in enumerate(images, 1):
        lines = reader.readtext(image, detail=0, paragraph=False, rotation_info=[90, 180, 270])
        if lines:
            pages.append(f"--- PAGE {number} ---\n" + "\n".join(str(line) for line in lines))
    if not pages:
        raise RuntimeError("EasyOCR could not recover readable text.")
    return "\n\n".join(pages)


def docling_text(name, content):
    if not getattr(settings, "TPA_DOCLING_FALLBACK_ENABLED", True):
        raise RuntimeError("Local OCR recovery is disabled in backend settings.")
    try:
        return _docling_text(name, content)
    except Exception as docling_error:
        try:
            return _easyocr_text(name, content)
        except Exception as easyocr_error:
            try:
                return _tesseract_text(name, content)
            except Exception as tesseract_error:
                raise RuntimeError(
                    f"Local OCR recovery failed. Docling: {docling_error}; "
                    f"EasyOCR: {easyocr_error}; Tesseract: {tesseract_error}"
                ) from docling_error
