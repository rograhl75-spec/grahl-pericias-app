import unittest
from unittest import mock

import httpx

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

    def test_parametros_de_chunk_e_custo_para_lotes(self):
        config = {
            "claude_chunk_chars": 120_000,
            "claude_max_chunks": 10,
            "claude_chunk_chars_conservative": 80_000,
            "claude_max_chunks_conservative": 15,
            "claude_model": "modelo-x",
            "claude_model_pricing": {
                "modelo-x": {"input_usd_per_million_tokens": 3.0, "output_usd_per_million_tokens": 15.0}
            },
            "usd_brl_exchange_rate": 5.0,
        }

        with mock.patch.object(ai_claude, "obter_app_config", return_value=config):
            self.assertEqual(ai_claude.obter_parametros_chunk_lote(), (80_000, 15))
            custo = ai_claude.estimar_custo_texto_brl(300_000, 2)

        self.assertEqual(ai_claude.chamadas_para_chunks(1), 1)
        self.assertEqual(ai_claude.chamadas_para_chunks(15), 16)
        esperado = ((100_000 * 3.0 + 8192 * 15.0) / 1_000_000) * 5.0 * 1.2
        self.assertAlmostEqual(custo, esperado)

        with mock.patch.object(ai_claude, "obter_app_config", return_value={}):
            with self.assertRaises(ai_claude.ConfigurationError):
                ai_claude.estimar_custo_texto_brl(1_000, 1)

    def test_parsear_json_resposta_aceita_json_embutido(self):
        resposta = "resultado:\n{\"processo_num\": \"123\"}\nobrigado"

        dados = ai_claude._parsear_json_resposta(resposta)

        self.assertEqual(dados["processo_num"], "123")

    def test_parsear_json_resposta_rejeita_texto_sem_json(self):
        with self.assertRaises(ValueError):
            ai_claude._parsear_json_resposta("sem json válido aqui")

    def test_validar_dados_extraidos_normaliza_tipos_e_epis(self):
        dados = ai_claude._validar_dados_extraidos({
            "processo_num": 123,
            "reclamante_nome": None,
            "quadro_epis": [{"descricao": "Luva", "ca": 456}],
            "fontes": {"processo_num": ["volume.pdf, página 2"], "campo_inexistente": "página 1"},
            "campo_nao_mapeado": "ignorado",
        })

        self.assertEqual(dados["processo_num"], "123")
        self.assertEqual(dados["quadro_epis"], [{
            "descricao": "Luva",
            "ca": "456",
            "data_entrega": "",
            "obs": "",
        }])
        self.assertEqual(dados["fontes"], {"processo_num": "volume.pdf, página 2"})
        self.assertNotIn("campo_nao_mapeado", dados)

    def test_validar_dados_extraidos_rejeita_quadro_epis_malformado(self):
        with self.assertRaises(ValueError):
            ai_claude._validar_dados_extraidos({"quadro_epis": ["luva"]})

    def test_calcular_custo_usa_precos_especificos_do_modelo(self):
        config = {
            "claude_model_pricing": {
                "sonnet-test": {
                    "input_usd_per_million_tokens": 2.0,
                    "output_usd_per_million_tokens": 7.0,
                }
            }
        }
        with mock.patch.object(ai_claude, "obter_app_config", return_value=config):
            custo = ai_claude._calcular_custo_tokens("sonnet-test", 1_000_000, 1_000_000)

        self.assertEqual(custo, 9.0)

    def test_calcular_custo_rejeita_modelo_sem_precos(self):
        with (
            mock.patch.object(ai_claude, "obter_app_config", return_value={"claude_model_pricing": {}}),
            self.assertRaises(ai_claude.ConfigurationError),
        ):
            ai_claude._calcular_custo_tokens("sonnet-test", 100, 100)

    def test_calcular_custo_aceita_precos_em_mapping_do_streamlit_secrets(self):
        from streamlit.runtime.secrets import AttrDict

        config = {
            "claude_model_pricing": AttrDict({
                "claude-sonnet-4-6": AttrDict({
                    "input_usd_per_million_tokens": 3.0,
                    "output_usd_per_million_tokens": 15.0,
                })
            })
        }
        with mock.patch.object(ai_claude, "obter_app_config", return_value=config):
            custo = ai_claude._calcular_custo_tokens("claude-sonnet-4-6", 1_000_000, 1_000_000)

        self.assertEqual(custo, 18.0)

    def test_estimar_custo_com_precos_lidos_de_st_secrets(self):
        from streamlit.runtime.secrets import AttrDict

        from core import config as core_config

        secrets = AttrDict({
            "app": {
                "claude_model": "claude-sonnet-4-6",
                "usd_brl_exchange_rate": 5.0,
                "claude_model_pricing": {
                    "claude-sonnet-4-6": {
                        "input_usd_per_million_tokens": 3.0,
                        "output_usd_per_million_tokens": 15.0,
                    }
                },
            }
        })
        streamlit = mock.Mock(secrets=secrets)
        with mock.patch.object(core_config, "st", streamlit):
            precos = core_config.obter_app_config()["claude_model_pricing"]["claude-sonnet-4-6"]
            self.assertNotIsInstance(precos, dict)
            custo = ai_claude._calcular_custo_tokens("claude-sonnet-4-6", 1_000_000, 1_000_000)

        self.assertEqual(custo, 18.0)

    def test_executar_chamada_claude_rejeita_resposta_sem_texto(self):
        cliente = mock.Mock()
        resposta = mock.Mock()
        resposta.content = []
        resposta.usage.input_tokens = 10
        resposta.usage.output_tokens = 20
        cliente.messages.create.return_value = resposta

        with self.assertRaises(ValueError):
            with mock.patch.object(ai_claude, "_calcular_custo_tokens", return_value=0.1):
                ai_claude._executar_chamada_claude(
                    cliente=cliente,
                    model="claude",
                    conteudo="prompt",
                    processo_id="Proc_01",
                    etapa="teste",
                )

    def test_obter_cliente_sem_api_key_lanca_erro_controlado_sem_st_stop(self):
        streamlit = mock.Mock()
        with (
            mock.patch.object(ai_claude, "st", streamlit),
            mock.patch.object(
                ai_claude,
                "obter_api_key_anthropic",
                side_effect=ai_claude.ConfigurationError("sem chave"),
            ),
        ):
            with self.assertRaises(ai_claude.ConfigurationError):
                ai_claude.obter_cliente_anthropic()

        streamlit.stop.assert_not_called()

    def test_obter_cliente_falha_criacao_lanca_runtime_error(self):
        with (
            mock.patch.object(ai_claude, "obter_api_key_anthropic", return_value="sk-teste"),
            mock.patch.object(ai_claude.anthropic, "Anthropic", side_effect=TypeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                ai_claude.obter_cliente_anthropic()

    def _analisar_com_cliente(self, cliente=None, cliente_erro=None):
        streamlit = mock.MagicMock()
        patch_cliente = (
            mock.patch.object(ai_claude, "obter_cliente_anthropic", side_effect=cliente_erro)
            if cliente_erro
            else mock.patch.object(ai_claude, "obter_cliente_anthropic", return_value=cliente)
        )
        with (
            mock.patch.object(ai_claude, "st", streamlit),
            patch_cliente,
            mock.patch.object(
                ai_claude,
                "obter_app_config",
                return_value={
                    "claude_chunk_chars": 1000,
                    "claude_max_chunks": 10,
                    "claude_model": "claude-3-5-sonnet-20241022",
                    "claude_model_pricing": {
                        "claude-3-5-sonnet-20241022": {
                            "input_usd_per_million_tokens": 3.0,
                            "output_usd_per_million_tokens": 15.0,
                        }
                    },
                    "usd_brl_exchange_rate": 5.0,
                },
            ),
            mock.patch.object(ai_claude, "ajustar_reserva_claude", return_value=True),
            mock.patch.object(ai_claude, "validar_limite_chamadas_claude", return_value=(True, 0, 50)),
            mock.patch.object(ai_claude, "reservar_limites_claude", return_value="reserva"),
            mock.patch.object(ai_claude, "registrar_chamada_claude") as registrar,
        ):
            resultado = ai_claude.analisar_processo_judicial("texto", processo_id="Proc_01")
        return resultado, streamlit, registrar

    def test_analisar_com_configuracao_invalida_retorna_vazio_sem_crash(self):
        resultado, streamlit, registrar = self._analisar_com_cliente(
            cliente_erro=ai_claude.ConfigurationError("sem chave")
        )

        self.assertEqual(resultado, ({}, 0, 0, 0.0, 0))
        streamlit.error.assert_called_once()
        self.assertIn("api_key", streamlit.error.call_args.args[0])
        streamlit.stop.assert_not_called()
        registrar.assert_not_called()

    def test_analisar_com_falha_de_cliente_retorna_vazio_sem_crash(self):
        resultado, streamlit, _ = self._analisar_com_cliente(cliente_erro=RuntimeError("falhou"))

        self.assertEqual(resultado, ({}, 0, 0, 0.0, 0))
        streamlit.error.assert_called_once()

    def test_analisar_com_erro_de_api_retorna_vazio(self):
        cliente = mock.Mock()
        requisicao = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        cliente.messages.create.side_effect = ai_claude.anthropic.APIConnectionError(request=requisicao)

        resultado, streamlit, registrar = self._analisar_com_cliente(cliente=cliente)

        self.assertEqual(resultado, ({}, 0, 0, 0.0, 0))
        streamlit.error.assert_called_once()
        self.assertEqual(registrar.call_args.args[1], "erro_conexao")

    def test_analisar_com_api_key_recusada_mostra_mensagem_amigavel(self):
        cliente = mock.Mock()
        requisicao = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        resposta = httpx.Response(401, request=requisicao)
        cliente.messages.create.side_effect = ai_claude.anthropic.AuthenticationError(
            "invalid x-api-key", response=resposta, body=None
        )

        resultado, streamlit, registrar = self._analisar_com_cliente(cliente=cliente)

        self.assertEqual(resultado, ({}, 0, 0, 0.0, 0))
        self.assertIn("API key", streamlit.error.call_args.args[0])
        self.assertEqual(registrar.call_args.args[1], "erro_autenticacao")

    def test_analisar_com_resposta_sem_json_retorna_vazio(self):
        cliente = mock.Mock()
        bloco = mock.Mock()
        bloco.text = "desculpe, não consegui"
        cliente.messages.create.return_value = mock.Mock(content=[bloco])

        resultado, streamlit, _ = self._analisar_com_cliente(cliente=cliente)

        self.assertEqual(resultado, ({}, 0, 0, 0.0, 0))
        streamlit.error.assert_called_once()

    def test_analisar_fluxo_feliz_retorna_dados(self):
        cliente = mock.Mock()
        bloco = mock.Mock()
        bloco.text = '{"processo_num": "123"}'
        resposta = mock.Mock(content=[bloco])
        resposta.usage.input_tokens = 10
        resposta.usage.output_tokens = 5
        cliente.messages.create.return_value = resposta

        (dados, entrada, saida, _, chamadas), streamlit, _ = self._analisar_com_cliente(cliente=cliente)

        self.assertEqual(dados, {"processo_num": "123", "quadro_epis": []})
        self.assertEqual((entrada, saida, chamadas), (10, 5, 1))
        streamlit.error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
