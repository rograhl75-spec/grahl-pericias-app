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

    def test_parsear_json_resposta_aceita_json_embutido(self):
        resposta = "resultado:\n{\"processo_num\": \"123\"}\nobrigado"

        dados = ai_claude._parsear_json_resposta(resposta)

        self.assertEqual(dados["processo_num"], "123")


if __name__ == "__main__":
    unittest.main()
