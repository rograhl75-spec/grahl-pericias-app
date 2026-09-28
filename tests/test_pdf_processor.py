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
    def test_obter_limite_chars_total_alinha_default_com_capacidade_de_processamento(self):
        limite = pdf_processor._obter_limite_chars_total({})

        self.assertEqual(limite, 720_000)

    def test_obter_limite_chars_total_respeita_capacidade_de_chunks(self):
        limite = pdf_processor._obter_limite_chars_total(
            {"max_pdf_chars_total": 500, "claude_chunk_chars": 100, "claude_max_chunks": 2}
        )

        self.assertEqual(limite, 200)

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

    def test_validar_limite_paginas_aceita_total_no_novo_limite_padrao(self):
        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, mensagem = pdf_processor.validar_limite_paginas(3000)

        self.assertTrue(valido)
        self.assertEqual("", mensagem)

    def test_consolidar_multiplos_pdfs_orienta_dividir_lote_ao_exceder_limite(self):
        arquivo = DummyUpload("grande.pdf", b"%PDF-1.7")

        with mock.patch.object(
            pdf_processor,
            "obter_app_config",
            return_value={"max_pdf_chars_total": 180, "claude_chunk_chars": 90, "claude_max_chunks": 2},
        ), mock.patch.object(
            pdf_processor,
            "extrair_texto_pdf",
            return_value=("A" * 200, 1),
        ), mock.patch.object(pdf_processor.st, "error") as error_mock:
            texto, total_paginas = pdf_processor.consolidar_multiplos_pdfs([arquivo])

        self.assertEqual("", texto)
        self.assertEqual(1, total_paginas)
        error_mock.assert_called_once()
        mensagem = error_mock.call_args[0][0]
        self.assertIn("atingiria cerca de", mensagem)
        self.assertIn("180", mensagem)
        self.assertIn("Divida os PDFs em lotes menores", mensagem)


if __name__ == "__main__":
    unittest.main()
