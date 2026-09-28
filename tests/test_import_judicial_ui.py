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


if __name__ == "__main__":
    unittest.main()
