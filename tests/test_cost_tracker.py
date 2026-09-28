import unittest
from unittest import mock

from core import cost_tracker


class CostTrackerTests(unittest.TestCase):
    def test_criar_registro_importacao_normaliza_campos(self):
        registro = cost_tracker.criar_registro_importacao_ia(
            processo_id="Proc_01",
            nomes_arquivos=[" principal.pdf ", "", None],
            tokens_entrada=-5,
            tokens_saida="7",
            custo_real="-1.2",
            dados_extraidos={"processo_num": "123"},
            num_chamadas_claude="3",
        )

        self.assertEqual(registro["arquivos"], ["principal.pdf"])
        self.assertEqual(registro["num_arquivos"], 1)
        self.assertEqual(registro["tokens_entrada"], 0)
        self.assertEqual(registro["tokens_saida"], 7)
        self.assertEqual(registro["tokens_total"], 7)
        self.assertEqual(registro["custo_usd"], 0.0)
        self.assertEqual(registro["custo_brl"], 0.0)
        self.assertEqual(registro["num_chamadas_claude"], 3)

    def test_validar_limite_chamadas_considera_chamadas_previstas(self):
        with (
            mock.patch.object(cost_tracker, "contar_chamadas_claude_hoje", return_value=48),
            mock.patch.object(cost_tracker, "obter_app_config", return_value={"max_api_calls_per_day": 50}),
        ):
            permitido, chamadas_hoje, limite = cost_tracker.validar_limite_chamadas_claude(3)

        self.assertFalse(permitido)
        self.assertEqual(chamadas_hoje, 48)
        self.assertEqual(limite, 50)

    def test_validar_limite_diario_considera_custo_adicional(self):
        with (
            mock.patch.object(cost_tracker, "calcular_custo_hoje", return_value=200.0),
            mock.patch.object(cost_tracker, "obter_app_config", return_value={"cost_limit_per_day": 250.0}),
        ):
            permitido, custo_atual, limite = cost_tracker.validar_limite_diario(custo_adicional_brl=60.0)

        self.assertFalse(permitido)
        self.assertEqual(custo_atual, 200.0)
        self.assertEqual(limite, 250.0)

    def test_criar_registro_importacao_usa_taxa_configuravel(self):
        with mock.patch.object(cost_tracker, "obter_taxa_cambio_usd_brl", return_value=6.0):
            registro = cost_tracker.criar_registro_importacao_ia(
                processo_id="Proc_02",
                nomes_arquivos=["a.pdf"],
                tokens_entrada=100,
                tokens_saida=50,
                custo_real=2.5,
                dados_extraidos={"processo_num": "123"},
            )

        self.assertEqual(registro["custo_usd"], 2.5)
        self.assertEqual(registro["custo_brl"], 15.0)


if __name__ == "__main__":
    unittest.main()
