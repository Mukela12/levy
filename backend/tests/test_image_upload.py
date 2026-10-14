"""A photo attached in chat becomes a one-page PDF and is read as a scan."""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

import pymupdf  # noqa: E402

from app.services import attachments  # noqa: E402


def _png(w=300, h=200) -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pix.set_rect(pix.irect, (255, 255, 255))
    return pix.tobytes("png")


class ImageToPdf(unittest.TestCase):
    def test_a_photo_becomes_one_page(self):
        pdf = attachments.image_to_pdf(_png(), "table.png")
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        self.assertEqual(doc.page_count, 1)
        # No text layer, so the upload reports it for reading as an image.
        self.assertTrue(attachments.looks_scanned(doc[0].get_text(), 1))

    def test_jpeg_spelled_jpg_is_accepted(self):
        jpg = pymupdf.open(stream=_png(), filetype="png")[0].get_pixmap(alpha=False).tobytes("jpeg")
        self.assertEqual(pymupdf.open(stream=attachments.image_to_pdf(jpg, "IMG_1.JPG"), filetype="pdf").page_count, 1)

    def test_a_non_image_is_refused(self):
        with self.assertRaises(ValueError):
            attachments.image_to_pdf(b"not an image", "x.png")


if __name__ == "__main__":
    unittest.main()
