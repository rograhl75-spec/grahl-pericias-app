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
            "max_pdf_chars_total": 800_000,
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
        self.assertTrue(any("limite operacional" in mensagem for mensagem in mensagens))

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

    def test_codigo_alterado_nao_usa_use_container_width(self):
        repo_root = Path(__file__).resolve().parents[1]
        for relative_path in ("app.py", "ui/import_judicial_ui.py"):
            source = (repo_root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("use_container_width", source, relative_path)


if __name__ == "__main__":
    unittest.main()
