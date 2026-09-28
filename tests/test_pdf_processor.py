import unittest
from unittest import mock
from contextlib import contextmanager

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

    def test_validar_limite_paginas_aceita_ate_limite_padrao_3000(self):
        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, mensagem = pdf_processor.validar_limite_paginas(3000)

        self.assertTrue(valido)
        self.assertEqual(mensagem, "")

    def test_validar_limite_paginas_rejeita_acima_de_3000_no_default(self):
        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, mensagem = pdf_processor.validar_limite_paginas(3001)

        self.assertFalse(valido)
        self.assertIn("3001 páginas", mensagem)
        self.assertIn("3000 páginas", mensagem)
        self.assertNotIn("1200", mensagem)

    def test_consolidar_multiplos_pdfs_rejeita_quando_texto_excede_limite_padrao(self):
        arquivo = DummyUpload("arquivo.pdf", b"%PDF-1.7")
        st_mock = mock.Mock()

        @contextmanager
        def _arquivo_temporario_fake(*_args, **_kwargs):
            yield "/tmp/fake.pdf"

        with (
            mock.patch.object(pdf_processor, "st", st_mock),
            mock.patch.object(pdf_processor, "obter_app_config", return_value={}),
            mock.patch.object(pdf_processor, "_arquivo_pdf_temporario", side_effect=_arquivo_temporario_fake),
            mock.patch.object(
                pdf_processor,
                "extrair_texto_pdf",
                return_value=("A" * 1_200_001, 1),
            ),
        ):
            texto_consolidado, total_paginas = pdf_processor.consolidar_multiplos_pdfs([arquivo])

        self.assertEqual(texto_consolidado, "")
        self.assertEqual(total_paginas, 1)
        st_mock.error.assert_called_once()
        mensagem = st_mock.error.call_args[0][0]
        self.assertIn("texto consolidado projetado", mensagem.lower())
        self.assertIn("1,200,000", mensagem)
        self.assertIn("lotes menores", mensagem.lower())


if __name__ == "__main__":
    unittest.main()
