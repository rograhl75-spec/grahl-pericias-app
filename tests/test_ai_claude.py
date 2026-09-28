import unittest
from unittest import mock

from core import ai_claude


class AiClaudeTests(unittest.TestCase):
    def test_estimar_chamadas_considera_chunks_e_consolidacao(self):
        texto = "A" * 25

        with mock.patch.object(
            ai_claude,
            "obter_app_config",
            return_value={"claude_chunk_chars": 10, "claude_max_chunks": 10},
        ):
            chamadas = ai_claude.estimar_chamadas_necessarias(texto)

        self.assertEqual(chamadas, 4)

    def test_estimar_chamadas_usa_modo_conservador_quando_ativado(self):
        texto = "A" * 25
        config = {
            "claude_chunk_chars": 20,
            "claude_max_chunks": 10,
            "claude_chunk_chars_conservative": 10,
            "claude_max_chunks_conservative": 20,
            "cloud_conservative_chars_threshold": 600_000,
        }

        with mock.patch.object(ai_claude, "obter_app_config", return_value=config):
            chamadas = ai_claude.estimar_chamadas_necessarias(texto, modo_conservador=True)

        self.assertEqual(chamadas, 4)

    def test_limite_consolidado_de_1200000_chars_cabe_em_10_chunks(self):
        texto = "A" * 1_200_000
        config = {"claude_chunk_chars": 120_000, "claude_max_chunks": 10}

        with mock.patch.object(
            ai_claude,
            "obter_app_config",
            return_value=config,
        ):
            chunks = ai_claude._dividir_texto_em_chunks(
                texto,
                config["claude_chunk_chars"],
                config["claude_max_chunks"],
            )

        self.assertEqual(len(chunks), 10)

    def test_parsear_json_resposta_aceita_json_embutido(self):
        resposta = "resultado:\n{\"processo_num\": \"123\"}\nobrigado"

        dados = ai_claude._parsear_json_resposta(resposta)

        self.assertEqual(dados["processo_num"], "123")

    def test_parsear_json_resposta_rejeita_texto_sem_json(self):
        with self.assertRaises(ValueError):
            ai_claude._parsear_json_resposta("sem json válido aqui")

    def test_executar_chamada_claude_rejeita_resposta_sem_texto(self):
        cliente = mock.Mock()
        resposta = mock.Mock()
        resposta.content = []
        resposta.usage.input_tokens = 10
        resposta.usage.output_tokens = 20
        cliente.messages.create.return_value = resposta

        with self.assertRaises(ValueError):
            ai_claude._executar_chamada_claude(
                cliente=cliente,
                model="claude",
                conteudo="prompt",
                processo_id="Proc_01",
                etapa="teste",
            )


if __name__ == "__main__":
    unittest.main()
