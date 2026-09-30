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

    def test_consolidar_multiplos_pdfs_excede_limite_de_caracteres(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")

        with (
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 1_200_000}),
            mock.patch.object(
                pdf_processor,
                "extrair_texto_pdf",
                return_value=("A" * 1_200_000, 15),
            ),
        ):
            with self.assertRaises(ValueError) as exc:
                pdf_processor.consolidar_multiplos_pdfs([arquivo])

        mensagem = str(exc.exception)
        self.assertIn("1.200.000 caracteres", mensagem)
        self.assertIn("divida o processo em lotes menores", mensagem)

    def test_calcular_total_paginas_bloqueia_quando_um_pdf_falha(self):
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
            with self.assertRaisesRegex(ValueError, "corrompido.pdf"):
                pdf_processor.calcular_total_paginas(arquivos)


    def test_consolidar_multiplos_pdfs_bloqueia_pdf_sem_leitura(self):
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
            with self.assertRaisesRegex(ValueError, "corrompido.pdf"):
                pdf_processor.consolidar_multiplos_pdfs(arquivos)


    def test_validar_pdfs_trata_falha_de_leitura_do_upload(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")
        arquivo.getbuffer = mock.Mock(side_effect=OSError("stream fechado"))

        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, mensagem = pdf_processor.validar_pdfs([arquivo])

        self.assertFalse(valido)
        self.assertIn("Não foi possível ler o conteúdo", mensagem)

    def test_validar_pdfs_usa_getvalue_quando_getbuffer_falha(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")
        arquivo.getbuffer = mock.Mock(side_effect=OSError("stream fechado"))
        arquivo.getvalue = mock.Mock(return_value=b"%PDF-1.7")

        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, _ = pdf_processor.validar_pdfs([arquivo])

        self.assertTrue(valido)

    def test_validar_pdfs_tolera_tamanho_invalido(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")
        arquivo.size = None

        with mock.patch.object(pdf_processor, "obter_app_config", return_value={}):
            valido, _ = pdf_processor.validar_pdfs([arquivo])

        self.assertTrue(valido)

    def test_consolidar_multiplos_pdfs_falha_amigavel_quando_upload_nao_pode_ser_lido(self):
        arquivo = DummyUpload("corrompido.pdf", b"%PDF-1.7")
        arquivo.getbuffer = mock.Mock(side_effect=OSError("stream fechado"))
        streamlit = mock.Mock()

        with (
            mock.patch.object(pdf_processor, "st", streamlit),
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 1_000}),
        ):
            with self.assertRaisesRegex(ValueError, "corrompido.pdf"):
                pdf_processor.consolidar_multiplos_pdfs([arquivo])


    def test_limites_padrao_documentados_cabem_na_capacidade_da_claude(self):
        from core.config import APP_CONFIG_DEFAULTS

        self.assertEqual(APP_CONFIG_DEFAULTS["max_pdf_chars_total"], 1_200_000)
        self.assertEqual(APP_CONFIG_DEFAULTS["max_pdf_pages_total"], 3000)
        self.assertLessEqual(
            APP_CONFIG_DEFAULTS["max_pdf_chars_total"],
            APP_CONFIG_DEFAULTS["claude_chunk_chars"] * APP_CONFIG_DEFAULTS["claude_max_chunks"],
        )
        self.assertLessEqual(
            APP_CONFIG_DEFAULTS["max_pdf_chars_total"],
            APP_CONFIG_DEFAULTS["claude_chunk_chars_conservative"]
            * APP_CONFIG_DEFAULTS["claude_max_chunks_conservative"],
        )

    def test_secrets_example_usa_os_mesmos_limites_padrao(self):
        import tomllib
        from pathlib import Path
        from core.config import APP_CONFIG_DEFAULTS

        exemplo = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml.example"
        app = tomllib.loads(exemplo.read_text(encoding="utf-8"))["app"]
        for chave in ("max_pdf_pages_total", "max_pdf_chars_total", "claude_chunk_chars", "claude_max_chunks"):
            self.assertEqual(app[chave], APP_CONFIG_DEFAULTS[chave], chave)

    def test_limite_de_caracteres_continua_configuravel_por_secrets(self):
        from core import config

        secrets = {"app": {"max_pdf_chars_total": 500_000, "max_pdf_pages_total": 800}}
        with mock.patch.object(config.st, "secrets", secrets):
            configuracao = config.obter_app_config()

        self.assertEqual(configuracao["max_pdf_chars_total"], 500_000)
        self.assertEqual(configuracao["max_pdf_pages_total"], 800)

    def _pdf_falso(self, textos):
        paginas = []
        for texto in textos:
            pagina = mock.Mock()
            pagina.extract_text.return_value = texto
            paginas.append(pagina)
        pdf = mock.MagicMock()
        pdf.pages = paginas
        pdf.__enter__.return_value = pdf
        pdf.__exit__.return_value = False
        return pdf

    def test_extrair_texto_pdf_informa_limite_configurado_e_libera_paginas(self):
        pdf = self._pdf_falso(["A" * 400, "B" * 400, "C" * 400])

        with mock.patch.object(pdf_processor.pdfplumber, "open", return_value=pdf):
            with self.assertRaises(pdf_processor.LimiteTextoPDFExcedido) as exc:
                pdf_processor.extrair_texto_pdf("/tmp/qualquer.pdf", max_chars=1_000)

        self.assertIsInstance(exc.exception, ValueError)
        mensagem = str(exc.exception)
        self.assertIn("1.000 caracteres", mensagem)
        self.assertIn("divida o processo em lotes menores", mensagem)
        self.assertIn("Nenhum dado foi importado", mensagem)
        for pagina in pdf.pages:
            pagina.close.assert_called_once()

    def test_consolidar_limite_na_extracao_por_arquivo_informa_limite_total_e_arquivo(self):
        arquivos = [
            DummyUpload("PARTE_1.PDF", b"%PDF-1.7"),
            DummyUpload("PARTE_2.PDF", b"%PDF-1.7"),
        ]
        pdfs = [self._pdf_falso(["A" * 600]), self._pdf_falso(["B" * 600])]

        with (
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 1_000}),
            mock.patch.object(pdf_processor.pdfplumber, "open", side_effect=pdfs),
        ):
            with self.assertRaises(pdf_processor.LimiteTextoPDFExcedido) as exc:
                pdf_processor.consolidar_multiplos_pdfs(arquivos)

        mensagem = str(exc.exception)
        self.assertIn("1.000 caracteres", mensagem)
        self.assertIn("PARTE_2.PDF", mensagem)
        self.assertIn("divida o processo em lotes menores", mensagem)

    def test_consolidar_limite_por_arquivo_desconta_cabecalho(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")
        cabecalho = f"\n\n{'='*80}\nARQUIVO 1: {arquivo.name}\n{'='*80}\n\n"

        with (
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 5_000}),
            mock.patch.object(pdf_processor, "extrair_texto_pdf", return_value=("A", 1)) as extrair,
        ):
            pdf_processor.consolidar_multiplos_pdfs([arquivo])

        self.assertEqual(extrair.call_args.kwargs["max_chars"], 5_000 - len(cabecalho))

    def test_consolidar_usa_limite_padrao_quando_config_invalida(self):
        arquivo = DummyUpload("processo.pdf", b"%PDF-1.7")

        with (
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": "abc"}),
            mock.patch.object(pdf_processor, "extrair_texto_pdf", return_value=("A" * 1_300_000, 15)),
        ):
            with self.assertRaisesRegex(pdf_processor.LimiteTextoPDFExcedido, "1.200.000 caracteres"):
                pdf_processor.consolidar_multiplos_pdfs([arquivo])

    def test_consolidar_falha_fechada_em_erro_inesperado_de_um_arquivo(self):
        arquivos = [
            DummyUpload("PARTE_1.PDF", b"%PDF-1.7"),
            DummyUpload("PARTE_2.PDF", b"%PDF-1.7"),
        ]

        with (
            mock.patch.object(pdf_processor, "obter_app_config", return_value={"max_pdf_chars_total": 1_200_000}),
            mock.patch.object(
                pdf_processor,
                "extrair_texto_pdf",
                side_effect=[("Texto útil", 10), RuntimeError("falha inesperada")],
            ),
        ):
            with self.assertRaisesRegex(ValueError, "PARTE_2.PDF"):
                pdf_processor.consolidar_multiplos_pdfs(arquivos)


if __name__ == "__main__":
    unittest.main()
