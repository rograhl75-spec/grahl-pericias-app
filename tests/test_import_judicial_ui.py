import unittest
from contextlib import ExitStack
from unittest import mock
from pathlib import Path

from ui import import_judicial_ui


class ImportJudicialUiTests(unittest.TestCase):
    def _streamlit_context(self):
        contexto = mock.MagicMock()
        contexto.__enter__.return_value = contexto
        contexto.__exit__.return_value = False
        return contexto

    def _mock_columns(self, spec):
        quantidade = spec if isinstance(spec, int) else len(spec)
        return tuple(self._streamlit_context() for _ in range(quantidade))

    def _mock_tabs(self, labels):
        return tuple(self._streamlit_context() for _ in labels)

    def test_aplicar_dados_importados_mapeia_campos_basicos(self):
        processo_atual, campos = import_judicial_ui.aplicar_dados_importados_ao_processo(
            {"status_contrato": "Ativo"},
            {
                "processo_num": "0001234-56.2024.5.00.0001",
                "reclamante_nome": "Maria da Silva",
                "status_contrato": "[Não localizado nos documentos]",
                "quadro_epis": [{"descricao": "Capacete", "ca": "123"}],
            },
        )

        self.assertEqual(processo_atual["processo_num"], "0001234-56.2024.5.00.0001")
        self.assertEqual(processo_atual["reclamante_nome"], "Maria da Silva")
        self.assertEqual(processo_atual["status_contrato"], "Ativo")
        self.assertEqual(processo_atual["quadro_epis"], [{"descricao": "Capacete", "ca": "123"}])
        self.assertEqual(campos, 2)

    def test_fluxo_sem_arquivos_nao_chama_api(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        streamlit.file_uploader.return_value = []

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "analisar_processo_judicial") as analisar,
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        analisar.assert_not_called()

    def test_bloqueia_quando_custo_projetado_excede_limite(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo = mock.Mock()
        arquivo.name = "processo.pdf"
        arquivo.size = 1024
        streamlit.file_uploader.return_value = [arquivo]
        streamlit.columns.side_effect = self._mock_columns

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value={"max_pdf_files": 5, "max_file_size_mb": 200, "cost_limit_per_day": 250.0, "max_api_calls_per_day": 50}),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=100),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=20.0),  # USD
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=6.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=200.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=0),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(False, 200.0, 250.0)),
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        self.assertTrue(streamlit.error.called)

    def test_falha_na_consolidacao_mostra_mensagem_amigavel_sem_crash(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo_1 = mock.Mock(name="uploaded_1")
        arquivo_1.name = "parte_1.pdf"
        arquivo_1.size = 1024
        arquivo_2 = mock.Mock(name="uploaded_2")
        arquivo_2.name = "parte_2.pdf"
        arquivo_2.size = 2048
        streamlit.file_uploader.return_value = [arquivo_1, arquivo_2]
        streamlit.columns.side_effect = self._mock_columns
        streamlit.button.side_effect = [True, False]
        streamlit.spinner.return_value = self._streamlit_context()
        streamlit.expander.return_value = self._streamlit_context()

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value={"max_pdf_files": 5, "max_file_size_mb": 200, "cost_limit_per_day": 250.0, "max_api_calls_per_day": 50}),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=15),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=1.5),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=10.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=1),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 10.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", side_effect=RuntimeError("falha no merge")),
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        mensagens = [call.args[0] for call in streamlit.error.call_args_list if call.args]
        self.assertTrue(any("Falha na etapa 'consolidar os PDFs'" in mensagem for mensagem in mensagens))
        self.assertTrue(streamlit.caption.called)

    def test_fluxo_com_dois_pdfs_processa_ate_registro(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo_1 = mock.Mock(name="uploaded_1")
        arquivo_1.name = "parte_1.pdf"
        arquivo_1.size = 1024
        arquivo_2 = mock.Mock(name="uploaded_2")
        arquivo_2.name = "parte_2.pdf"
        arquivo_2.size = 2048
        streamlit.file_uploader.return_value = [arquivo_1, arquivo_2]
        streamlit.columns.side_effect = self._mock_columns
        streamlit.tabs.side_effect = self._mock_tabs
        streamlit.button.side_effect = [True, False, True, False]
        streamlit.spinner.return_value = self._streamlit_context()

        registro_mock = {"status": "sucesso", "processo_id": "Proc_01"}

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(
                import_judicial_ui,
                "obter_app_config",
                return_value={
                    "max_pdf_files": 5,
                    "max_file_size_mb": 200,
                    "cost_limit_per_day": 250.0,
                    "max_api_calls_per_day": 50,
                    "cloud_conservative_pdf_count_threshold": 2,
                    "cloud_conservative_chars_threshold": 600_000,
                },
            ),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=24),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=2.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=10.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=1),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 10.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", return_value=("texto consolidado", 24)) as consolidar,
            mock.patch.object(import_judicial_ui, "estimar_chamadas_necessarias", return_value=2) as estimar_chamadas,
            mock.patch.object(import_judicial_ui, "validar_limite_chamadas_claude", return_value=(True, 1, 50)),
            mock.patch.object(
                import_judicial_ui,
                "analisar_processo_judicial",
                return_value=({"processo_num": "0001234-56.2024.5.00.0001", "reclamante_nome": "Maria"}, 100, 50, 0.25, 2),
            ) as analisar,
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia", return_value=registro_mock),
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertTrue(sucesso)
        self.assertEqual(registro, registro_mock)
        self.assertEqual(dados["processo_num"], "0001234-56.2024.5.00.0001")
        consolidar.assert_called_once_with([arquivo_1, arquivo_2])
        estimar_chamadas.assert_called_once_with("texto consolidado", modo_conservador=True)
        analisar.assert_called_once_with(
            "texto consolidado",
            processo_id="Proc_01",
            modo_conservador=True,
            custo_estimado_brl=10.0,
        )
        self.assertTrue(streamlit.warning.called)

    def test_fluxo_com_texto_grande_ativa_modo_conservador(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo = mock.Mock(name="uploaded")
        arquivo.name = "volume_unico.pdf"
        arquivo.size = 1024
        streamlit.file_uploader.return_value = [arquivo]
        streamlit.columns.side_effect = self._mock_columns
        streamlit.tabs.side_effect = self._mock_tabs
        streamlit.button.side_effect = [True, False, True, False]
        streamlit.spinner.return_value = self._streamlit_context()

        with (
            mock.patch.object(
                import_judicial_ui,
                "st",
                streamlit,
            ),
            mock.patch.object(
                import_judicial_ui,
                "obter_app_config",
                return_value={
                    "max_pdf_files": 5,
                    "max_file_size_mb": 200,
                    "cost_limit_per_day": 250.0,
                    "max_api_calls_per_day": 50,
                    "cloud_conservative_pdf_count_threshold": 2,
                    "cloud_conservative_chars_threshold": 600_000,
                },
            ),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=24),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=2.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=10.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=1),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 10.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", return_value=("A" * 700_000, 24)),
            mock.patch.object(import_judicial_ui, "estimar_chamadas_necessarias", return_value=3) as estimar_chamadas,
            mock.patch.object(import_judicial_ui, "validar_limite_chamadas_claude", return_value=(True, 1, 50)),
            mock.patch.object(
                import_judicial_ui,
                "analisar_processo_judicial",
                return_value=({"processo_num": "0001234-56.2024.5.00.0001", "reclamante_nome": "Maria"}, 100, 50, 0.25, 2),
            ) as analisar,
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia", return_value={"status": "ok"}),
        ):
            import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        estimar_chamadas.assert_called_once_with("A" * 700_000, modo_conservador=True)
        analisar.assert_called_once_with(
            "A" * 700_000,
            processo_id="Proc_01",
            modo_conservador=True,
            custo_estimado_brl=10.0,
        )

    def test_revisao_persiste_entre_reruns_sem_repetir_chamada_claude(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo = mock.Mock(name="uploaded")
        arquivo.name = "processo.pdf"
        arquivo.size = 1024
        streamlit.file_uploader.return_value = [arquivo]
        streamlit.columns.side_effect = self._mock_columns
        streamlit.tabs.side_effect = self._mock_tabs
        streamlit.button.side_effect = [True, False, False, False, False, False, True, False]
        streamlit.spinner.return_value = self._streamlit_context()

        config = {
            "max_pdf_files": 5,
            "max_file_size_mb": 200,
            "cost_limit_per_day": 250.0,
            "max_api_calls_per_day": 50,
            "cloud_conservative_pdf_count_threshold": 2,
            "cloud_conservative_chars_threshold": 600_000,
        }
        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value=config),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=10),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=1.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=0.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=0),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 0.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", return_value=("texto", 10)) as consolidar,
            mock.patch.object(import_judicial_ui, "estimar_chamadas_necessarias", return_value=1),
            mock.patch.object(import_judicial_ui, "validar_limite_chamadas_claude", return_value=(True, 0, 50)),
            mock.patch.object(
                import_judicial_ui,
                "analisar_processo_judicial",
                return_value=({"processo_num": "123"}, 20, 10, 0.1, 1),
            ) as analisar,
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia", return_value={"status": "sucesso"}),
        ):
            primeiro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {})
            segundo = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {})

        self.assertFalse(primeiro[0])
        self.assertTrue(segundo[0])
        self.assertEqual(segundo[1]["processo_num"], "123")
        consolidar.assert_called_once()
        analisar.assert_called_once()

    def test_falha_da_claude_retorna_fallback_sem_alterar_processo(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo = mock.Mock(name="uploaded")
        arquivo.name = "processo.pdf"
        arquivo.size = 1024
        streamlit.file_uploader.return_value = [arquivo]
        streamlit.columns.side_effect = self._mock_columns
        streamlit.button.side_effect = [True, False]
        streamlit.spinner.return_value = self._streamlit_context()

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value={"max_pdf_files": 5, "max_file_size_mb": 200, "cost_limit_per_day": 250.0, "max_api_calls_per_day": 50}),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=10),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=1.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=0.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=0),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 0.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", return_value=("texto", 10)),
            mock.patch.object(import_judicial_ui, "estimar_chamadas_necessarias", return_value=1),
            mock.patch.object(import_judicial_ui, "validar_limite_chamadas_claude", return_value=(True, 0, 50)),
            mock.patch.object(import_judicial_ui, "analisar_processo_judicial", return_value=({}, 0, 0, 0.0, 0)),
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia") as criar_registro,
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        criar_registro.assert_not_called()
        mensagens = [call.args[0] for call in streamlit.error.call_args_list if call.args]
        self.assertTrue(any("não retornou dados válidos" in mensagem for mensagem in mensagens))
        self.assertIn("api_key", streamlit.info.call_args.args[0])


    def _config_padrao(self):
        return {
            "max_pdf_files": 5,
            "max_file_size_mb": 200,
            "cost_limit_per_day": 250.0,
            "max_api_calls_per_day": 50,
            "cloud_conservative_pdf_count_threshold": 2,
            "cloud_conservative_chars_threshold": 600_000,
            "max_pdf_chars_total": 1_200_000,
        }

    def _patches_fluxo_feliz(self, texto="texto consolidado", paginas=10):
        return (
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value=self._config_padrao()),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=paginas),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=1.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=0.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=0),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 0.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", return_value=(texto, paginas)),
            mock.patch.object(import_judicial_ui, "estimar_chamadas_necessarias", return_value=1),
            mock.patch.object(import_judicial_ui, "validar_limite_chamadas_claude", return_value=(True, 0, 50)),
        )

    def _streamlit_para_fluxo(self, botoes):
        streamlit = mock.Mock()
        streamlit.session_state = {}
        arquivo = mock.Mock(name="uploaded")
        arquivo.name = "processo.pdf"
        arquivo.size = 1024
        arquivo.getvalue.return_value = b"%PDF-1.7"
        streamlit.file_uploader.return_value = [arquivo]
        streamlit.columns.side_effect = self._mock_columns
        streamlit.tabs.side_effect = self._mock_tabs
        streamlit.button.side_effect = botoes
        streamlit.spinner.return_value = self._streamlit_context()
        return streamlit, arquivo

    def test_assinatura_tolera_falha_de_getvalue(self):
        arquivo = mock.Mock()
        arquivo.name = "processo.pdf"
        arquivo.size = 2048
        arquivo.getvalue.side_effect = OSError("stream fechado")

        assinatura = import_judicial_ui._assinatura_arquivos([arquivo])

        self.assertEqual(len(assinatura), 64)

    def test_erro_inesperado_no_pos_processamento_nao_derruba_app(self):
        streamlit, _ = self._streamlit_para_fluxo([True, False, True, False])

        criar_registro = mock.Mock()
        patches = [
            mock.patch.object(import_judicial_ui, "st", streamlit),
            *self._patches_fluxo_feliz(),
            mock.patch.object(
                import_judicial_ui,
                "analisar_processo_judicial",
                return_value=({"processo_num": "123"}, 20, 10, 0.1, 1),
            ),
            mock.patch.object(
                import_judicial_ui,
                "_renderizar_resultado_analise",
                side_effect=RuntimeError("falha inesperada ao renderizar"),
            ),
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia", criar_registro),
        ]
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        criar_registro.assert_not_called()
        self.assertTrue(streamlit.error.called)

    def test_erro_inesperado_global_retorna_fallback_amigavel(self):
        streamlit = mock.Mock()
        streamlit.session_state = {}

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(
                import_judicial_ui,
                "_executar_tela_importacao_pdf",
                side_effect=MemoryError("memória insuficiente"),
            ),
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        self.assertTrue(streamlit.error.called)

    def test_limite_operacional_de_caracteres_bloqueia_sem_chamar_claude(self):
        streamlit, _ = self._streamlit_para_fluxo([True, False])
        config = self._config_padrao()
        config["max_pdf_chars_total"] = 1_000

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value=config),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=10),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=1.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=0.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=0),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 0.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", return_value=("A" * 2_000, 10)),
            mock.patch.object(import_judicial_ui, "analisar_processo_judicial") as analisar,
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {"foo": "bar"})

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        self.assertEqual(registro, {})
        analisar.assert_not_called()
        mensagens = [call.args[0] for call in streamlit.error.call_args_list if call.args]
        self.assertTrue(any("limite de 1.000 caracteres" in mensagem for mensagem in mensagens))
        self.assertTrue(any("divida o processo em lotes menores" in mensagem for mensagem in mensagens))

    def test_limite_de_caracteres_na_extracao_bloqueia_sem_alterar_processo(self):
        streamlit, _ = self._streamlit_para_fluxo([True, False])
        config = self._config_padrao()
        config["pdf_batch_import_enabled"] = False
        erro_limite = import_judicial_ui.LimiteTextoPDFExcedido(
            import_judicial_ui.mensagem_limite_chars_excedido(1_200_000, "PARTE_2.PDF")
        )
        processo_original = {"foo": "bar", "processo_num": "0001"}

        with (
            mock.patch.object(import_judicial_ui, "st", streamlit),
            mock.patch.object(import_judicial_ui, "obter_app_config", return_value=config),
            mock.patch.object(import_judicial_ui, "validar_pdfs", return_value=(True, "ok")),
            mock.patch.object(import_judicial_ui, "calcular_total_paginas", return_value=10),
            mock.patch.object(import_judicial_ui, "validar_limite_paginas", return_value=(True, "")),
            mock.patch.object(import_judicial_ui, "estimar_custo", return_value=1.0),
            mock.patch.object(import_judicial_ui, "obter_taxa_cambio_usd_brl", return_value=5.0),
            mock.patch.object(import_judicial_ui, "calcular_custo_hoje", return_value=0.0),
            mock.patch.object(import_judicial_ui, "contar_chamadas_claude_hoje", return_value=0),
            mock.patch.object(import_judicial_ui, "validar_limite_diario", return_value=(True, 0.0, 250.0)),
            mock.patch.object(import_judicial_ui, "consolidar_multiplos_pdfs", side_effect=erro_limite),
            mock.patch.object(import_judicial_ui, "analisar_processo_judicial") as analisar,
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia") as criar_registro,
        ):
            sucesso, dados, registro = import_judicial_ui.exibir_tela_importacao_pdf(
                "Proc_01", processo_original
            )

        self.assertFalse(sucesso)
        self.assertIs(dados, processo_original)
        self.assertEqual(dados, {"foo": "bar", "processo_num": "0001"})
        self.assertEqual(registro, {})
        analisar.assert_not_called()
        criar_registro.assert_not_called()
        self.assertFalse(any(isinstance(valor, dict) for valor in streamlit.session_state.values()))
        streamlit.expander.assert_not_called()
        mensagens = [call.args[0] for call in streamlit.error.call_args_list if call.args]
        self.assertEqual(len(mensagens), 1)
        self.assertIn("1.200.000 caracteres", mensagens[0])
        self.assertIn("PARTE_2.PDF", mensagens[0])
        self.assertIn("processo não foi alterado", mensagens[0])
        self.assertIn("divida o processo em lotes menores", mensagens[0])

    def test_sessao_nao_guarda_texto_consolidado_completo(self):
        streamlit, _ = self._streamlit_para_fluxo([True, False, False, False])
        texto = "B" * 5_000

        patches = [
            mock.patch.object(import_judicial_ui, "st", streamlit),
            *self._patches_fluxo_feliz(texto=texto),
            mock.patch.object(
                import_judicial_ui,
                "analisar_processo_judicial",
                return_value=({"processo_num": "123"}, 20, 10, 0.1, 1),
            ),
            mock.patch.object(import_judicial_ui, "criar_registro_importacao_ia", return_value={"status": "ok"}),
        ]
        with ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            import_judicial_ui.exibir_tela_importacao_pdf("Proc_01", {})

        revisao = streamlit.session_state["pdf_import_review::Proc_01"]
        self.assertNotIn("texto_consolidado", revisao)
        self.assertEqual(revisao["tamanho_texto"], len(texto))
        self.assertNotIn(texto, str(revisao))

    # ==================== IMPORTAÇÃO EM LOTES ====================

    def _arquivos_lotes(self):
        arquivos = []
        for nome in ("PARTE_1.PDF", "PARTE_2.PDF"):
            arquivo = mock.Mock(name=nome)
            arquivo.name = nome
            arquivo.size = 1024
            arquivo.getvalue.return_value = f"%PDF-1.7 {nome}".encode()
            arquivos.append(arquivo)
        return arquivos

    def _lotes_planejados(self):
        return [
            {
                "indice": 1,
                "partes": [{
                    "arquivo_idx": 1, "arquivo": "PARTE_1.PDF",
                    "pagina_inicio": 1, "pagina_fim": 400, "total_paginas_arquivo": 700,
                }],
                "chars": 1_150_000,
                "paginas": 400,
                "chunks": 15,
            },
            {
                "indice": 2,
                "partes": [
                    {
                        "arquivo_idx": 1, "arquivo": "PARTE_1.PDF",
                        "pagina_inicio": 401, "pagina_fim": 700, "total_paginas_arquivo": 700,
                    },
                    {
                        "arquivo_idx": 2, "arquivo": "PARTE_2.PDF",
                        "pagina_inicio": 1, "pagina_fim": 120, "total_paginas_arquivo": 120,
                    },
                ],
                "chars": 900_000,
                "paginas": 420,
                "chunks": 15,
            },
        ]

    def _streamlit_lotes(self, botoes, estado_lote=True):
        streamlit = mock.Mock()
        arquivos = self._arquivos_lotes()
        streamlit.session_state = {}
        if estado_lote:
            streamlit.session_state["pdf_import_batch::Proc_01"] = {
                "assinatura": import_judicial_ui._assinatura_arquivos(arquivos),
                "status": "sugerido",
            }
        streamlit.file_uploader.return_value = arquivos
        streamlit.columns.side_effect = self._mock_columns
        streamlit.tabs.side_effect = self._mock_tabs
        streamlit.button.side_effect = botoes
        streamlit.spinner.return_value = self._streamlit_context()
        streamlit.expander.return_value = self._streamlit_context()
        return streamlit, arquivos

    def _patches_lotes(self, **sobrescritas):
        valores = {
            "obter_app_config": mock.Mock(return_value=self._config_padrao()),
            "validar_pdfs": mock.Mock(return_value=(True, "ok")),
            "calcular_total_paginas": mock.Mock(return_value=820),
            "validar_limite_paginas": mock.Mock(return_value=(True, "")),
            "estimar_custo": mock.Mock(return_value=1.0),
            "obter_taxa_cambio_usd_brl": mock.Mock(return_value=5.0),
            "calcular_custo_hoje": mock.Mock(return_value=0.0),
            "contar_chamadas_claude_hoje": mock.Mock(return_value=0),
            "validar_limite_diario": mock.Mock(return_value=(True, 0.0, 250.0)),
            "validar_limite_chamadas_claude": mock.Mock(return_value=(True, 0, 50)),
            "obter_max_lotes": mock.Mock(return_value=4),
            "planejar_lotes_pdf": mock.Mock(return_value=self._lotes_planejados()),
            "extrair_texto_lote": mock.Mock(side_effect=[("X" * 5_000, 400), ("Y" * 5_000, 420)]),
            "obter_parametros_chunk_lote": mock.Mock(return_value=(80_000, 15)),
            "estimar_chamadas_necessarias": mock.Mock(return_value=16),
            "estimar_custo_texto_brl": mock.Mock(return_value=12.0),
            "consolidar_multiplos_pdfs": mock.Mock(),
            "analisar_processo_judicial": mock.Mock(),
            "criar_registro_importacao_ia": mock.Mock(return_value={"status": "sucesso"}),
        }
        valores.update(sobrescritas)
        return valores

    def _executar_lotes(self, streamlit, mocks, processo=None):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(import_judicial_ui, "st", streamlit))
            for nome, valor in mocks.items():
                stack.enter_context(mock.patch.object(import_judicial_ui, nome, valor))
            return import_judicial_ui.exibir_tela_importacao_pdf(
                "Proc_01", processo if processo is not None else {"foo": "bar"}
            )

    def _dados_lote_1(self):
        return {
            "processo_num": "0001234-56.2024.5.09.0001",
            "reclamante_nome": "Maria da Silva",
            "agentes_alegados": "Ruído",
            "fase_processual": "Conhecimento",
            "quadro_epis": [{"descricao": "Protetor auricular", "ca": "123", "data_entrega": "", "obs": ""}],
            "fontes": {
                "processo_num": "PARTE_1.PDF, página 1",
                "agentes_alegados": "PARTE_1.PDF, página 12",
            },
        }

    def _dados_lote_2(self):
        return {
            "processo_num": "0001234-56.2024.5.09.0001",
            "reclamante_nome": "[Não localizado nos documentos]",
            "agentes_alegados": "Calor",
            "fase_processual": "Aguardando perícia",
            "quesitos_juizo": "1) Há insalubridade?",
            "quadro_epis": [{"descricao": "Protetor auricular", "ca": "123", "data_entrega": "", "obs": ""}],
            "fontes": {
                "agentes_alegados": "PARTE_2.PDF, página 30",
                "quesitos_juizo": "PARTE_2.PDF, página 88",
            },
        }

    def test_texto_acima_do_limite_oferece_modo_lotes_sem_processar(self):
        streamlit, _ = self._streamlit_lotes([True, False, False, False], estado_lote=False)
        erro_limite = import_judicial_ui.LimiteTextoPDFExcedido(
            import_judicial_ui.mensagem_limite_chars_excedido(1_200_000, "PARTE_1.PDF")
        )
        mocks = self._patches_lotes(consolidar_multiplos_pdfs=mock.Mock(side_effect=erro_limite))
        processo_original = {"foo": "bar"}

        sucesso, dados, registro = self._executar_lotes(streamlit, mocks, processo_original)

        self.assertFalse(sucesso)
        self.assertIs(dados, processo_original)
        self.assertEqual(registro, {})
        mocks["analisar_processo_judicial"].assert_not_called()
        mocks["planejar_lotes_pdf"].assert_not_called()
        estado = streamlit.session_state["pdf_import_batch::Proc_01"]
        self.assertEqual(estado["status"], "sugerido")
        self.assertNotIn("pdf_import_review::Proc_01", streamlit.session_state)
        rotulos = [call.args[0] for call in streamlit.button.call_args_list]
        self.assertIn("🧩 Processar em lotes", rotulos)
        self.assertIn("🗑️ Descartar importação em lotes", rotulos)
        avisos = " ".join(call.args[0] for call in streamlit.warning.call_args_list if call.args)
        self.assertIn("lote", avisos)
        self.assertIn("processo não foi alterado", avisos)

    def test_lotes_multiplos_mesclados_ate_registro(self):
        streamlit, _ = self._streamlit_lotes([False, False, True, False, True, False])
        analisar = mock.Mock(side_effect=[
            (self._dados_lote_1(), 1000, 200, 0.5, 16),
            (self._dados_lote_2(), 900, 150, 0.4, 16),
        ])
        mocks = self._patches_lotes(analisar_processo_judicial=analisar)

        sucesso, dados, registro = self._executar_lotes(streamlit, mocks, {"foo": "bar"})

        self.assertTrue(sucesso)
        self.assertEqual(analisar.call_count, 2)
        for chamada in analisar.call_args_list:
            self.assertEqual(chamada.kwargs["custo_estimado_brl"], 12.0)
        mocks["consolidar_multiplos_pdfs"].assert_not_called()
        self.assertEqual(dados["processo_num"], "0001234-56.2024.5.09.0001")
        self.assertEqual(dados["reclamante_nome"], "Maria da Silva")
        self.assertEqual(dados["agentes_alegados"], "Ruído\n\nCalor")
        self.assertEqual(dados["fase_processual"], "Aguardando perícia")
        self.assertEqual(dados["quesitos_juizo"], "1) Há insalubridade?")
        self.assertEqual(len(dados["quadro_epis"]), 1)
        self.assertEqual(registro["modo_importacao"], "lotes")
        self.assertEqual(len(registro["lotes"]), 2)
        self.assertIn("PARTE_2.PDF", registro["lotes"][1])
        self.assertEqual(registro["campos_com_conflito_lotes"], ["fase_processual"])
        criar = mocks["criar_registro_importacao_ia"]
        kwargs = criar.call_args.kwargs
        self.assertEqual(kwargs["num_chamadas_claude"], 32)
        self.assertEqual(kwargs["tokens_entrada"], 1900)
        self.assertAlmostEqual(kwargs["custo_real"], 0.9)
        fontes = kwargs["dados_extraidos"]["fontes"]
        self.assertIn("PARTE_1.PDF, página 12", fontes["agentes_alegados"])
        self.assertIn("PARTE_2.PDF, página 30", fontes["agentes_alegados"])
        self.assertIn("PARTE_2.PDF, página 88", fontes["quesitos_juizo"])
        self.assertTrue(streamlit.progress.called)
        self.assertNotIn("pdf_import_batch::Proc_01", streamlit.session_state)

    def test_falha_em_lote_posterior_preserva_processo(self):
        streamlit, _ = self._streamlit_lotes([False, False, True, False])
        analisar = mock.Mock(side_effect=[
            (self._dados_lote_1(), 1000, 200, 0.5, 16),
            ({}, 0, 0, 0.0, 0),
        ])
        mocks = self._patches_lotes(analisar_processo_judicial=analisar)
        processo_original = {"foo": "bar", "processo_num": "0001"}

        sucesso, dados, registro = self._executar_lotes(streamlit, mocks, processo_original)

        self.assertFalse(sucesso)
        self.assertIs(dados, processo_original)
        self.assertEqual(dados, {"foo": "bar", "processo_num": "0001"})
        self.assertEqual(registro, {})
        mocks["criar_registro_importacao_ia"].assert_not_called()
        self.assertNotIn("pdf_import_review::Proc_01", streamlit.session_state)
        estado = streamlit.session_state["pdf_import_batch::Proc_01"]
        self.assertEqual(estado["status"], "falhou")
        self.assertEqual(estado["erro"]["etapa"], "lote 2 de 2")
        self.assertIn("PARTE_2.PDF", estado["erro"]["arquivos"])
        self.assertNotIn("Maria da Silva", str(streamlit.session_state))
        mensagens = " ".join(call.args[0] for call in streamlit.error.call_args_list if call.args)
        self.assertIn("lote 2 de 2", mensagens)
        self.assertIn("PARTE_2.PDF", mensagens)
        self.assertIn("processo não foi alterado", mensagens)

    def test_retentativa_apos_falha_e_descartar_limpa_estado(self):
        streamlit, _ = self._streamlit_lotes([False, False, False, True])
        streamlit.session_state["pdf_import_batch::Proc_01"].update({
            "status": "falhou",
            "erro": {"etapa": "lote 2 de 2", "arquivos": "PARTE_2.PDF (págs. 1–120)", "mensagem": "erro"},
        })
        mocks = self._patches_lotes()

        sucesso, _, _ = self._executar_lotes(streamlit, mocks)

        self.assertFalse(sucesso)
        rotulos = [call.args[0] for call in streamlit.button.call_args_list]
        self.assertIn("🔁 Tentar novamente em lotes", rotulos)
        mensagens = " ".join(call.args[0] for call in streamlit.error.call_args_list if call.args)
        self.assertIn("lote 2 de 2", mensagens)
        self.assertNotIn("pdf_import_batch::Proc_01", streamlit.session_state)
        mocks["planejar_lotes_pdf"].assert_not_called()
        mocks["analisar_processo_judicial"].assert_not_called()

    def test_cota_de_chamadas_insuficiente_para_todos_os_lotes_bloqueia_antes_de_extrair(self):
        streamlit, _ = self._streamlit_lotes([False, False, True, False])
        mocks = self._patches_lotes(
            validar_limite_chamadas_claude=mock.Mock(return_value=(False, 30, 50)),
        )

        sucesso, dados, _ = self._executar_lotes(streamlit, mocks)

        self.assertFalse(sucesso)
        self.assertEqual(dados, {"foo": "bar"})
        mocks["validar_limite_chamadas_claude"].assert_called_once_with(32)
        mocks["extrair_texto_lote"].assert_not_called()
        mocks["analisar_processo_judicial"].assert_not_called()
        estado = streamlit.session_state["pdf_import_batch::Proc_01"]
        self.assertEqual(estado["status"], "falhou")
        self.assertIn("chamadas", estado["erro"]["mensagem"])

    def test_cota_e_custo_validados_por_lote(self):
        # Cota de chamadas esgotada antes do 2º lote.
        streamlit, _ = self._streamlit_lotes([False, False, True, False])
        mocks = self._patches_lotes(
            validar_limite_chamadas_claude=mock.Mock(
                side_effect=[(True, 0, 50), (True, 0, 50), (False, 40, 50)]
            ),
            analisar_processo_judicial=mock.Mock(return_value=(self._dados_lote_1(), 1, 1, 0.1, 16)),
        )

        sucesso, _, _ = self._executar_lotes(streamlit, mocks)

        self.assertFalse(sucesso)
        self.assertEqual(mocks["analisar_processo_judicial"].call_count, 1)
        estado = streamlit.session_state["pdf_import_batch::Proc_01"]
        self.assertEqual(estado["erro"]["etapa"], "lote 2 de 2")
        self.assertIn("necessárias: 16", estado["erro"]["mensagem"])

        # Custo diário esgotado antes do 2º lote (Passo 3, plano, lote 1, lote 2).
        streamlit, _ = self._streamlit_lotes([False, False, True, False])
        mocks = self._patches_lotes(
            validar_limite_diario=mock.Mock(side_effect=[
                (True, 0.0, 250.0), (True, 0.0, 250.0), (True, 0.0, 250.0), (False, 245.0, 250.0),
            ]),
            analisar_processo_judicial=mock.Mock(return_value=(self._dados_lote_1(), 1, 1, 0.1, 16)),
        )

        sucesso, _, registro = self._executar_lotes(streamlit, mocks)

        self.assertFalse(sucesso)
        self.assertEqual(registro, {})
        self.assertEqual(mocks["analisar_processo_judicial"].call_count, 1)
        mocks["validar_limite_diario"].assert_called_with(12.0)
        estado = streamlit.session_state["pdf_import_batch::Proc_01"]
        self.assertIn("custo", estado["erro"]["mensagem"])

    def test_sessao_nao_guarda_texto_dos_lotes(self):
        streamlit, _ = self._streamlit_lotes([False, False, True, False, False, False])
        texto_1, texto_2 = "X" * 5_000, "Y" * 5_000
        mocks = self._patches_lotes(
            extrair_texto_lote=mock.Mock(side_effect=[(texto_1, 400), (texto_2, 420)]),
            analisar_processo_judicial=mock.Mock(side_effect=[
                (self._dados_lote_1(), 1000, 200, 0.5, 16),
                (self._dados_lote_2(), 900, 150, 0.4, 16),
            ]),
        )

        sucesso, _, _ = self._executar_lotes(streamlit, mocks)

        self.assertFalse(sucesso)  # aguardando confirmação do usuário
        revisao = streamlit.session_state["pdf_import_review::Proc_01"]
        self.assertEqual(revisao["modo_importacao"], "lotes")
        self.assertEqual(revisao["tamanho_texto"], 10_000)
        conteudo_sessao = str(streamlit.session_state)
        self.assertNotIn(texto_1, conteudo_sessao)
        self.assertNotIn(texto_2, conteudo_sessao)
        self.assertNotIn("XXXXXXXXXX", conteudo_sessao)
        self.assertNotIn("texto_consolidado", revisao)

    def test_codigo_alterado_nao_usa_use_container_width(self):
        repo_root = Path(__file__).resolve().parents[1]
        for relative_path in ("app.py", "ui/import_judicial_ui.py"):
            source = (repo_root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("use_container_width", source, relative_path)

    def test_fluxo_de_lotes_nao_usa_st_stop(self):
        repo_root = Path(__file__).resolve().parents[1]
        for relative_path in ("ui/import_judicial_ui.py", "core/batch_import.py", "core/pdf_processor.py"):
            source = (repo_root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("st.stop(", source, relative_path)


if __name__ == "__main__":
    unittest.main()
