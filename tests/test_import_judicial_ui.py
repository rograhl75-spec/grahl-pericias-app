import unittest
from unittest import mock

from ui import import_judicial_ui


class ImportJudicialUiTests(unittest.TestCase):
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
        coluna = mock.MagicMock()
        coluna.__enter__.return_value = coluna
        coluna.__exit__.return_value = False

        def _mock_columns(spec):
            quantidade = spec if isinstance(spec, int) else len(spec)
            return tuple(coluna for _ in range(quantidade))

        arquivo = mock.Mock()
        arquivo.name = "processo.pdf"
        arquivo.size = 1024
        streamlit.file_uploader.return_value = [arquivo]
        streamlit.columns.side_effect = _mock_columns

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


if __name__ == "__main__":
    unittest.main()
