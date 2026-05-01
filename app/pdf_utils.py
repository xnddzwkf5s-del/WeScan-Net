"""Server-side PDF rendering and signature overlay using PyMuPDF."""
import fitz
import io
import base64


def pdf_page_as_png(pdf_bytes: bytes, page_num: int = 0) -> str:
    """Convert a specific page of a PDF to base64 PNG. page_num is 0-indexed."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count < 1:
            doc.close()
            return ""
        page_num = max(0, min(page_num, doc.page_count - 1))
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for quality
        img_bytes = pix.tobytes("png")
        doc.close()
        return base64.b64encode(img_bytes).decode()
    except Exception:
        return ""


def pdf_first_page_as_png(pdf_bytes: bytes) -> str:
    """Convert first page of PDF to base64 PNG (convenience wrapper)."""
    return pdf_page_as_png(pdf_bytes, 0)


def pdf_page_count(pdf_bytes: bytes) -> int:
    """Return number of pages in PDF."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return 0


def overlay_signature_on_pdf(pdf_bytes: bytes, signature_png_base64: str,
                              x_rel: float, y_rel: float, page_num: int = 0) -> bytes:
    """Overlay a signature image on a PDF page at relative position.
    x_rel, y_rel are 0-1 coordinates (0,0 = top-left, 1,1 = bottom-right)."""
    x_rel = max(0.0, min(1.0, x_rel))
    y_rel = max(0.0, min(1.0, y_rel))

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_num >= doc.page_count:
        page_num = doc.page_count - 1

    page = doc[page_num]
    rect = page.rect

    # Decode the signature image to get dimensions
    try:
        sig_bytes = base64.b64decode(signature_png_base64)
    except Exception:
        doc.close()
        raise ValueError("Invalid base64 signature data")

    # Signature: 150px wide, ~50px tall at the given position
    sig_w = min(150, rect.width * 0.4)  # cap at 40% of page width
    sig_h = sig_w * 0.35  # approximate aspect ratio

    sig_rect = fitz.Rect(
        rect.width * x_rel - sig_w / 2,
        rect.height * y_rel - sig_h / 2,
        rect.width * x_rel + sig_w / 2,
        rect.height * y_rel + sig_h / 2
    )
    page.insert_image(sig_rect, stream=sig_bytes)

    output = io.BytesIO()
    doc.save(output, garbage=4, deflate=True)
    doc.close()
    output.seek(0)
    return output.read()
