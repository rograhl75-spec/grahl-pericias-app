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

    def test_registro_importacao_preserva_fontes_de_evidencia(self):
        fontes = {"processo_num": "volume.pdf, página 2"}
        registro = cost_tracker.criar_registro_importacao_ia(
            processo_id="Proc_01",
            nomes_arquivos=["volume.pdf"],
            tokens_entrada=10,
            tokens_saida=5,
            custo_real=0.1,
            dados_extraidos={"processo_num": "123", "fontes": fontes},
        )

        self.assertEqual(registro["fontes"], fontes)

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

    def test_calcular_custo_hoje_usa_fieldfilter_no_firestore(self):
        query_calls = mock.Mock()
        query_calls.where.return_value = query_calls
        query_calls.stream.return_value = []
        query_imports = mock.Mock()
        query_imports.where.return_value = query_imports
        query_imports.stream.return_value = []
        reserva = mock.Mock()
        reserva.exists = False
        query_daily = mock.Mock()
        query_daily.document.return_value.get.return_value = reserva
        db = mock.Mock()
        db.collection.side_effect = [query_calls, query_imports, query_daily]
        filtro = object()

        with (
            mock.patch.object(cost_tracker, "_obter_db", return_value=db),
            mock.patch.object(cost_tracker, "FieldFilter", return_value=filtro) as field_filter,
        ):
            total = cost_tracker.calcular_custo_hoje()

        self.assertEqual(total, 0.0)
        query_calls.where.assert_called_once_with(filter=filtro)
        query_imports.where.assert_called_once_with(filter=filtro)
        self.assertEqual(field_filter.call_count, 2)

    def test_reservar_limites_claude_bloqueia_excesso_em_transacao(self):
        ref = mock.Mock()
        snapshot = mock.Mock()
        snapshot.exists = True
        snapshot.to_dict.return_value = {
            "chamadas_reservadas": 49,
            "custo_reservado_brl": 240.0,
        }
        ref.get.return_value = snapshot
        transaction = mock.Mock()
        db = mock.Mock()
        db.collection.return_value.document.return_value = ref
        db.transaction.return_value = transaction

        with (
            mock.patch.object(cost_tracker, "_obter_db", return_value=db),
            mock.patch.object(cost_tracker, "contar_chamadas_claude_hoje", return_value=49),
            mock.patch.object(cost_tracker, "calcular_custo_hoje", return_value=240.0),
            mock.patch.object(
                cost_tracker,
                "obter_app_config",
                return_value={"max_api_calls_per_day": 50, "cost_limit_per_day": 250.0},
            ),
            mock.patch.object(cost_tracker.firestore, "transactional", side_effect=lambda fn: fn),
        ):
            with self.assertRaises(cost_tracker.LimiteDiarioExcedido):
                cost_tracker.reservar_limites_claude(2, 20.0)

        transaction.set.assert_not_called()

    def test_calcular_custo_hoje_falha_fechado_quando_firestore_indisponivel(self):
        with mock.patch.object(cost_tracker, "_obter_db", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "verificar o limite diário de custo"):
                cost_tracker.calcular_custo_hoje()

    def test_contar_chamadas_falha_fechado_quando_firestore_indisponivel(self):
        with mock.patch.object(cost_tracker, "_obter_db", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "verificar o limite diário de chamadas"):
                cost_tracker.contar_chamadas_claude_hoje()


if __name__ == "__main__":
    unittest.main()
