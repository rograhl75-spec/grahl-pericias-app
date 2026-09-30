import unittest

from core.batch_import import NAO_LOCALIZADO, consolidar_resultados_lotes


def _lote(indice, arquivo, inicio, fim):
    return {
        "indice": indice,
        "partes": [{
            "arquivo_idx": 1,
            "arquivo": arquivo,
            "pagina_inicio": inicio,
            "pagina_fim": fim,
            "total_paginas_arquivo": 999,
        }],
        "chars": 1000,
    }


class ConsolidarResultadosLotesTests(unittest.TestCase):
    def setUp(self):
        self.lotes = [
            _lote(1, "PARTE_1.PDF", 1, 400),
            _lote(2, "PARTE_1.PDF", 401, 700),
            _lote(3, "PARTE_2.PDF", 1, 120),
        ]
        self.resultados = [
            {
                "processo_num": "0001234-56.2024.5.09.0001",
                "reclamante_nome": "Maria da Silva",
                "fase_processual": "Conhecimento",
                "agentes_alegados": "Ruído",
                "quadro_epis": [{"descricao": "Protetor auricular", "ca": "123", "data_entrega": "", "obs": ""}],
                "fontes": {
                    "processo_num": "PARTE_1.PDF, página 1",
                    "reclamante_nome": "PARTE_1.PDF, página 2",
                    "agentes_alegados": "PARTE_1.PDF, página 12",
                    "quadro_epis": "PARTE_1.PDF, página 300",
                },
            },
            {
                "processo_num": "0009999-00.2024.5.09.0001",
                "reclamante_nome": "  maria   da SILVA ",
                "agentes_alegados": "ruído",
                "fontes": {"processo_num": "PARTE_1.PDF, página 450"},
            },
            {
                "processo_num": NAO_LOCALIZADO,
                "fase_processual": "Aguardando perícia",
                "agentes_alegados": "Calor",
                "quesitos_juizo": "1) Há insalubridade?",
                "quadro_epis": [
                    {"descricao": "protetor auricular", "ca": "123", "data_entrega": "", "obs": "repetido"},
                    {"descricao": "Luva", "ca": "456", "data_entrega": "01/01/2024", "obs": ""},
                ],
                "fontes": {"fase_processual": "PARTE_2.PDF, página 110"},
            },
        ]

    def test_primeiro_valor_prevalece_e_conflito_e_registrado(self):
        dados, conflitos = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(dados["processo_num"], "0001234-56.2024.5.09.0001")
        self.assertEqual(
            conflitos["processo_num"],
            ["Lote 1: 0001234-56.2024.5.09.0001", "Lote 2: 0009999-00.2024.5.09.0001"],
        )
        self.assertEqual(dados["fontes"]["processo_num"], "PARTE_1.PDF, página 1 [lote 1]")

    def test_valores_equivalentes_sao_unificados_sem_conflito(self):
        dados, conflitos = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(dados["reclamante_nome"], "Maria da Silva")
        self.assertNotIn("reclamante_nome", conflitos)
        # Fonte do lote 2 sem referência explícita usa o intervalo de páginas do lote.
        self.assertEqual(
            dados["fontes"]["reclamante_nome"],
            "PARTE_1.PDF, página 2 [lote 1]; PARTE_1.PDF (págs. 401–700) [lote 2]",
        )

    def test_ultimo_valor_prevalece_para_fase_processual(self):
        dados, conflitos = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(dados["fase_processual"], "Aguardando perícia")
        self.assertIn("fase_processual", conflitos)
        self.assertEqual(dados["fontes"]["fase_processual"], "PARTE_2.PDF, página 110 [lote 3]")

    def test_campos_narrativos_concatenam_valores_distintos_com_todas_as_fontes(self):
        dados, conflitos = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(dados["agentes_alegados"], "Ruído\n\nCalor")
        self.assertNotIn("agentes_alegados", conflitos)
        fontes = dados["fontes"]["agentes_alegados"]
        self.assertIn("PARTE_1.PDF, página 12 [lote 1]", fontes)
        self.assertIn("PARTE_1.PDF (págs. 401–700) [lote 2]", fontes)
        self.assertIn("PARTE_2.PDF (págs. 1–120) [lote 3]", fontes)

    def test_campo_ausente_em_todos_os_lotes_fica_nao_localizado(self):
        dados, _ = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(dados["reclamada_cnpj"], NAO_LOCALIZADO)
        self.assertNotIn("reclamada_cnpj", dados["fontes"])
        self.assertEqual(dados["quesitos_juizo"], "1) Há insalubridade?")

    def test_quadro_epis_sem_duplicidade_e_com_fontes(self):
        dados, _ = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(
            [(item["descricao"], item["ca"]) for item in dados["quadro_epis"]],
            [("Protetor auricular", "123"), ("Luva", "456")],
        )
        self.assertEqual(
            dados["fontes"]["quadro_epis"],
            "PARTE_1.PDF, página 300 [lote 1]; PARTE_2.PDF (págs. 1–120) [lote 3]",
        )

    def test_mesclagem_e_deterministica(self):
        primeiro = consolidar_resultados_lotes(self.resultados, self.lotes)
        segundo = consolidar_resultados_lotes(self.resultados, self.lotes)

        self.assertEqual(primeiro, segundo)

    def test_resultados_incompletos_falham_fechado(self):
        with self.assertRaises(ValueError):
            consolidar_resultados_lotes(self.resultados[:2], self.lotes)
        with self.assertRaises(ValueError):
            consolidar_resultados_lotes([], [])


if __name__ == "__main__":
    unittest.main()
