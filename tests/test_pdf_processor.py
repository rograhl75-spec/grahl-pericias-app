import unittest
from unittest import mock
from contextlib import nullcontext

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
        with mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_pages_total": 3000}):
            valido, mensagem = pdf_processor.validar_limite_paginas(3001)

        self.assertFalse(valido)
        self.assertIn("3.001 páginas", mensagem)
        self.assertIn("3.000 páginas", mensagem)
        self.assertIn("divida o processo em lotes menores", mensagem)

    def test_validar_limite_paginas_aceita_total_no_limite(self):
        with mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_pages_total": 3000}):
            valido, mensagem = pdf_processor.validar_limite_paginas(3000)

        self.assertTrue(valido)
        self.assertEqual(mensagem, "")

    def test_consolidar_multiplos_pdfs_aceita_texto_ate_limite_configurado(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")
        limite = 1_200_000
        cabecalho = f"\n\n{'='*80}\nARQUIVO 1: {arquivo.name}\n{'='*80}\n\n"
        texto_no_limite = "A" * (limite - len(cabecalho))

        with (
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": limite}),
            mock.patch.object(pdf_processor, "extrair_texto_pdf", return_value=(texto_no_limite, 42)),
        ):
            texto_consolidado, total_paginas = pdf_processor.consolidar_multiplos_pdfs([arquivo])

        self.assertEqual(len(texto_consolidado), limite)
        self.assertEqual(total_paginas, 42)

    def test_consolidar_multiplos_pdfs_informa_limite_de_caracteres(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")
        streamlit = mock.Mock()

        with (
            mock.patch.object(pdf_processor, "st", streamlit),
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 1_200_000}),
            mock.patch.object(
                pdf_processor,
                "extrair_texto_pdf",
                return_value=("A" * 1_200_000, 15),
            ),
        ):
            texto_consolidado, total_paginas = pdf_processor.consolidar_multiplos_pdfs([arquivo])

        self.assertEqual(texto_consolidado, "")
        self.assertEqual(total_paginas, 15)
        streamlit.error.assert_called_once()
        mensagem = streamlit.error.call_args[0][0]
        self.assertIn("1.200.000 caracteres", mensagem)
        self.assertIn("divida o processo em lotes menores", mensagem)

    def test_calcular_total_paginas_continua_quando_um_pdf_falha(self):
        arquivos = [
            DummyUpload("corrompido.pdf", b"%PDF-1.7"),
            DummyUpload("valido.pdf", b"%PDF-1.7"),
        ]
        streamlit = mock.Mock()
        pdf_valido = mock.Mock()
        pdf_valido.pages = [object(), object(), object()]

        with (
            mock.patch.object(pdf_processor, "st", streamlit),
            mock.patch.object(
                pdf_processor.pdfplumber,
                "open",
                side_effect=[ValueError("PDF corrompido"), nullcontext(pdf_valido)],
            ),
        ):
            total_paginas = pdf_processor.calcular_total_paginas(arquivos)

        self.assertEqual(total_paginas, 3)
        streamlit.error.assert_called_once()
        self.assertIn("corrompido.pdf", streamlit.error.call_args[0][0])

    def test_consolidar_multiplos_pdfs_ignora_pdf_sem_leitura_e_mantem_outro_valido(self):
        arquivos = [
            DummyUpload("corrompido.pdf", b"%PDF-1.7"),
            DummyUpload("valido.pdf", b"%PDF-1.7"),
        ]
        streamlit = mock.Mock()

        with (
            mock.patch.object(pdf_processor, "st", streamlit),
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 1_200_000}),
            mock.patch.object(
                pdf_processor,
                "extrair_texto_pdf",
                side_effect=[("", 0), ("Texto útil", 12)],
            ),
        ):
            texto_consolidado, total_paginas = pdf_processor.consolidar_multiplos_pdfs(arquivos)

        self.assertIn("ARQUIVO 2: valido.pdf", texto_consolidado)
        self.assertIn("Texto útil", texto_consolidado)
        self.assertEqual(total_paginas, 12)
        streamlit.error.assert_called_once()
        self.assertIn("corrompido.pdf", streamlit.error.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
