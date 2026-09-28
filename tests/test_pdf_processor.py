import unittest
from unittest import mock

from core import pdf_processor


class DummyUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self.size = len(data)

    def getbuffer(self):
        return memoryview(self._data)


class PdfProcessorTests(unittest.TestCase):
    def test_validar_pdfs_rejeita_assinatura_invalida(self):
        arquivo = DummyUpload("arquivo.pdf", b"NOTPDF")

        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, mensagem = pdf_processor.validar_pdfs([arquivo])

        self.assertFalse(valido)
        self.assertIn("assinatura válida de PDF", mensagem)

    def test_validar_pdfs_rejeita_arquivos_acima_do_limite(self):
        arquivos = [DummyUpload(f"arquivo_{i}.pdf", b"%PDF-1.7") for i in range(6)]

        with mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_files": 5}):
            valido, mensagem = pdf_processor.validar_pdfs(arquivos)

        self.assertFalse(valido)
        self.assertIn("Máximo de 5 PDFs", mensagem)

    def test_validar_limite_paginas_rejeita_total_acima_do_limite(self):
        with mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_pages_total": 10}):
            valido, mensagem = pdf_processor.validar_limite_paginas(11)

        self.assertFalse(valido)
        self.assertIn("11 páginas", mensagem)


if __name__ == "__main__":
    unittest.main()
