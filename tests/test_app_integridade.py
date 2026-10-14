"""Regressões de integridade: seleção de casos, rascunhos e fotos incrementais.

Testes com AppTest e banco simulado (mocks); não substituem validação em
dispositivo real nem no Firestore.
"""

import copy
import io
import unittest
from pathlib import Path
from unittest import mock

import streamlit as st
from PIL import Image
from streamlit.testing.v1 import AppTest

from core import database
from core.config import criar_dados_padrao
from core.extrajudicial import evidence_hash, new_defaults


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"
MENU_DADOS = "✏️ Dados, Escritório & SST"
SELETOR = "seletor_caso_id"


class _Arquivo:
    def __init__(self, cor, nome=None):
        buffer = io.BytesIO()
        Image.new("RGB", (32, 24), cor).save(buffer, "PNG")
        self._dados = buffer.getvalue()
        self.name = nome or f"{cor}.png"

    def getvalue(self):
        return self._dados


def _caso(nome="Fulano", numero="0001", **extra):
    dados = criar_dados_padrao()
    dados.update({
        "reclamante_nome": nome, "processo_num": numero, "reclamada_nome": "",
        "campo_data": "01/02/2024", "campo_horario": "10:00", "local_diligencia": "Fábrica",
    })
    dados.update(extra)
    return dados


class IntegridadeAppTests(unittest.TestCase):
    def setUp(self):
        # Rótulos repetidos de propósito: mesmo nome e número nos dois casos.
        self.processos = {"Proc_01": _caso(), "Proc_02": _caso()}
        self.gravacoes = []
        self.falhar_gravacao = False
        self.uploads = {}
        self.cameras = {}

        def salvar(processo_id, dados):
            if self.falhar_gravacao:
                return False
            self.gravacoes.append(processo_id)
            self.processos[processo_id] = copy.deepcopy(dados)
            return True

        def file_uploader(*_args, key=None, **_kwargs):
            return self.uploads.get(key)

        def camera_input(*_args, key=None, **_kwargs):
            return self.cameras.get(key)

        for patcher in (
            mock.patch.object(database, "carregar_dados",
                              side_effect=lambda: copy.deepcopy(self.processos)),
            mock.patch.object(database, "salvar_processo", side_effect=salvar),
            mock.patch.object(st, "file_uploader", side_effect=file_uploader),
            mock.patch.object(st, "camera_input", side_effect=camera_input),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _app(self):
        app = AppTest.from_file(str(APP_FILE), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def _selecionar(self, app, caso):
        app.sidebar.selectbox(key=SELETOR).set_value(caso).run()
        self.assertFalse(app.exception)

    def _ir_campo(self, app):
        app.sidebar.button[2].click().run()
        self.assertFalse(app.exception)

    def _cabecalho(self, app):
        return [info.value for info in app.main.info if info.value.startswith("Caso Ativo:")]

    def _versao(self, app, caso):
        return app.session_state[f"fotos_widget_versao_{caso}"] if (
            f"fotos_widget_versao_{caso}" in app.session_state) else 0

    def _enviar(self, app, caso, *arquivos):
        self.uploads[f"fotos_upload_{caso}_{self._versao(app, caso)}"] = list(arquivos)
        app.run()
        self.assertFalse(app.exception)

    # 1) Seleção A -> B --------------------------------------------------------

    def test_selecao_apos_criar_caso_reflete_caso_ativo_e_permite_voltar(self):
        app = self._app()
        app.text_input(key="novo_nome_0").set_value("Novo")
        with mock.patch.object(database, "gerar_proximo_id", return_value="Proc_03"):
            app.main.button[0].click().run()
        self.assertEqual(app.session_state["processo_ativo"], "Proc_03")
        # Antes da correção a caixa continuava mostrando Proc_01 com o caso Proc_03 ativo.
        self.assertEqual(app.sidebar.selectbox(key=SELETOR).value, "Proc_03")

        self._selecionar(app, "Proc_01")
        self.assertEqual(app.session_state["processo_ativo"], "Proc_01")
        self.assertTrue(self._cabecalho(app)[0].startswith("Caso Ativo: Proc_01"))
        self.assertEqual(app.query_params["caso"], "Proc_01")

    def test_troca_a_b_com_rotulos_iguais_muda_dados_e_destino_do_save(self):
        app = self._app()
        self._selecionar(app, "Proc_02")
        self.assertEqual(app.session_state["menu_opcao"], MENU_DADOS)
        self.assertTrue(self._cabecalho(app)[0].startswith("Caso Ativo: Proc_02"))
        self._ir_campo(app)
        self.assertTrue(self._cabecalho(app)[0].startswith("Caso Ativo: Proc_02"))
        self.assertTrue(app.text_input(key="ld_Proc_02").placeholder.endswith("caso Proc_02"))

        app.text_input(key="ld_Proc_02").set_value("Galpão B").run()
        app.button(key="campo_salvar_Proc_02").click().run()
        self.assertEqual(self.gravacoes, ["Proc_02"])
        self.assertEqual(self.processos["Proc_02"]["local_diligencia"], "Galpão B")
        self.assertEqual(self.processos["Proc_01"]["local_diligencia"], "Fábrica")

        self._selecionar(app, "Proc_01")
        self._ir_campo(app)
        self.assertTrue(self._cabecalho(app)[0].startswith("Caso Ativo: Proc_01"))
        self.assertEqual(app.text_input(key="ld_Proc_01").value, "Fábrica")
        self.assertEqual(len(app.text_input(key="ld_Proc_01").placeholder) > 0, True)

    def test_pesquisa_nao_troca_caso_ativo_silenciosamente(self):
        self.processos["Proc_02"]["reclamante_nome"] = "Beltrano"
        app = self._app()
        self._ir_campo(app)
        app.sidebar.text_input[0].set_value("beltrano").run()
        self.assertEqual(app.session_state["processo_ativo"], "Proc_01")
        self.assertEqual(app.sidebar.selectbox(key=SELETOR).options[0], "[Proc_01] Fulano (0001)")
        self.assertTrue(self._cabecalho(app)[0].startswith("Caso Ativo: Proc_01"))
        self._selecionar(app, "Proc_02")
        self.assertEqual(app.session_state["processo_ativo"], "Proc_02")

    def test_recarga_restaura_caso_da_url(self):
        app = AppTest.from_file(str(APP_FILE), default_timeout=30)
        app.query_params["caso"] = "Proc_02"
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["processo_ativo"], "Proc_02")
        self.assertEqual(app.sidebar.selectbox(key=SELETOR).value, "Proc_02")

    def test_exclusao_limpa_estado_e_resseleciona_caso_existente(self):
        app = self._app()
        self._selecionar(app, "Proc_02")
        app.sidebar.button[3].click().run()

        def excluir(caso):
            self.processos.pop(caso)
            return True

        with mock.patch.object(database, "excluir_processo", side_effect=excluir):
            app.main.button[0].click().run()
            app.text_input(key="confirmar_exclusao_input_1").set_value("Proc_02").run()
            app.main.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertNotIn("Proc_02", self.processos)
        self.assertEqual(app.session_state["processo_ativo"], "Proc_01")
        self.assertEqual(app.sidebar.selectbox(key=SELETOR).value, "Proc_01")

    # 2) Rascunhos/estado não vazam entre casos -------------------------------

    def test_rascunho_de_texto_fica_no_caso_de_origem(self):
        app = self._app()
        self._ir_campo(app)
        app.text_area(key="pp_Proc_01").set_value("Pessoas do caso A").run()
        self.assertIn("textos da vistoria", app.sidebar.warning[0].value)

        self._selecionar(app, "Proc_02")
        self._ir_campo(app)
        self.assertEqual(app.text_area(key="pp_Proc_02").value, "")
        app.button(key="campo_salvar_Proc_02").click().run()
        self.assertEqual(self.processos["Proc_02"]["presentes_pericia"], "")
        self.assertEqual(self.processos["Proc_01"]["presentes_pericia"], "")

        self._selecionar(app, "Proc_01")
        self._ir_campo(app)
        self.assertEqual(app.text_area(key="pp_Proc_01").value, "Pessoas do caso A")
        app.button(key="campo_descartar_Proc_01").click().run()
        self.assertEqual(app.text_area(key="pp_Proc_01").value, "")
        self.assertEqual(self.gravacoes, ["Proc_02"])

    def test_importacao_extrajudicial_nao_vaza_para_outro_caso(self):
        for caso in self.processos:
            self.processos[caso].update(new_defaults())
            self.processos[caso]["modulo_atuacao"] = "Laudo Extrajudicial Previdenciário (LTCAT+PPP)"
        csv = io.BytesIO(b"periodo_id,inicio,fim,empresa,cnpj,condicao,cargo,setor,atividade\n"
                         b"P1,2020-01-01,,Empresa,,CLT,Cargo,Setor,Atividade\n")
        csv.name = "cnis.csv"
        self.uploads["extra_Proc_01_import"] = csv
        app = self._app()
        app.sidebar.button[1].click().run()
        self.assertTrue(any("Aplicar importação" in b.label for b in app.main.button))
        self._selecionar(app, "Proc_02")
        self.assertFalse(any("Aplicar importação" in b.label for b in app.main.button))
        self.assertEqual(self.gravacoes, [])

    # 3) Fotos incrementais ------------------------------------------------------

    def test_fotos_em_ciclos_sem_duplicar_e_preservando_legendas(self):
        app = self._app()
        self._ir_campo(app)
        vermelho, azul, verde, amarelo = (_Arquivo(c) for c in ("red", "blue", "green", "yellow"))

        self._enviar(app, "Proc_01", vermelho, azul)
        self.assertEqual(len(self.processos["Proc_01"]["campo_fotos"]), 2)
        legenda = [t for t in app.text_input if t.label == "Legenda 1"][0]
        legenda.set_value("Fachada").run()
        [b for b in app.button if b.label == "💾 Atualizar 1"][0].click().run()
        self.assertEqual(self.processos["Proc_01"]["campo_fotos"][0]["legenda"], "Fachada")

        # Segundo ciclo: o uploader foi reiniciado; reenvio de foto já salva não duplica.
        self._enviar(app, "Proc_01", verde, vermelho, amarelo)
        fotos = self.processos["Proc_01"]["campo_fotos"]
        self.assertEqual(len(fotos), 4)
        self.assertEqual(len({f["base64"] for f in fotos}), 4)
        self.assertEqual(fotos[0]["legenda"], "Fachada")
        self.assertEqual(self._versao(app, "Proc_01"), 2)
        self.assertEqual([t.value for t in app.text_input if t.label == "Legenda 1"], ["Fachada"])

        # Terceiro ciclo e reruns adicionais não regravam/duplicam.
        self._enviar(app, "Proc_01", _Arquivo("white"))
        app.run()
        self.assertEqual(len(self.processos["Proc_01"]["campo_fotos"]), 5)
        self.assertEqual(self.gravacoes.count("Proc_01"), 4)
        self.assertEqual(self.processos["Proc_02"]["campo_fotos"], [])

    def test_camera_libera_nova_captura_apos_salvar(self):
        app = self._app()
        self._ir_campo(app)
        self.cameras["camera_Proc_01_0"] = _Arquivo("red")
        app.run()
        self.cameras["camera_Proc_01_1"] = _Arquivo("blue")
        app.run()
        self.assertEqual(len(self.processos["Proc_01"]["campo_fotos"]), 2)

    def test_excluir_foto_persiste_e_legendas_seguem_a_foto(self):
        app = self._app()
        self._ir_campo(app)
        self._enviar(app, "Proc_01", _Arquivo("red"), _Arquivo("blue"))
        [t for t in app.text_input if t.label == "Legenda 2"][0].set_value("Máquina").run()
        [b for b in app.button if b.label == "💾 Atualizar 2"][0].click().run()
        [b for b in app.button if b.label == "🗑️ Excluir 1"][0].click().run()
        app.run()
        fotos = self.processos["Proc_01"]["campo_fotos"]
        self.assertEqual(len(fotos), 1)
        self.assertEqual(fotos[0]["legenda"], "Máquina")
        self.assertEqual([t.value for t in app.text_input if t.label == "Legenda 1"], ["Máquina"])

    def test_falha_conserva_pendentes_e_reenvio_grava(self):
        app = self._app()
        self._ir_campo(app)
        self.falhar_gravacao = True
        self._enviar(app, "Proc_01", _Arquivo("red"), _Arquivo("blue"))
        self.assertEqual(self.processos["Proc_01"]["campo_fotos"], [])
        self.assertEqual(len(app.session_state["fotos_pendentes"]["Proc_01"]), 2)
        app.run()
        self.assertEqual(len(app.session_state["fotos_pendentes"]["Proc_01"]), 2)
        self.assertTrue(any("foto(s)" in w.value for w in app.sidebar.warning))

        # Trocar de caso não leva as pendentes de A para B.
        self.falhar_gravacao = False
        self._selecionar(app, "Proc_02")
        self._ir_campo(app)
        self._enviar(app, "Proc_02", _Arquivo("green"))
        self.assertEqual(len(self.processos["Proc_02"]["campo_fotos"]), 1)
        self.assertEqual(self.gravacoes, ["Proc_02"])

        self._selecionar(app, "Proc_01")
        self._ir_campo(app)
        app.button(key="fotos_reenviar_Proc_01").click().run()
        self.assertEqual(len(self.processos["Proc_01"]["campo_fotos"]), 2)
        self.assertNotIn("Proc_01", app.session_state["fotos_pendentes"])
        self.assertEqual(len(self.processos["Proc_02"]["campo_fotos"]), 1)

    def test_limite_do_documento_e_comunicado_e_pendentes_mantidas(self):
        self.processos["Proc_01"]["campo_medicoes"] = "x" * 999_900
        app = self._app()
        self._ir_campo(app)
        self._enviar(app, "Proc_01", _Arquivo("red"))
        self.assertEqual(self.gravacoes, [])
        self.assertTrue(any("Limite de armazenamento" in e.value for e in app.main.error))
        self.assertEqual(len(app.session_state["fotos_pendentes"]["Proc_01"]), 1)

    def test_recarregar_versao_da_nuvem_mantem_pendentes(self):
        app = self._app()
        self._ir_campo(app)
        self.falhar_gravacao = True
        self._enviar(app, "Proc_01", _Arquivo("red"))
        app.session_state["_process_revision_snapshot"] = {"Proc_01": 1, "Proc_02": 0}
        app.button(key="fotos_recarregar_Proc_01").click().run()
        self.assertNotIn("Proc_01", app.session_state["_process_revision_snapshot"])
        self.assertEqual(len(app.session_state["fotos_pendentes"]["Proc_01"]), 1)

    # 4) Revisão extrajudicial invalidada por fotos -------------------------------

    def test_foto_nova_invalida_revisao_extrajudicial(self):
        dados = self.processos["Proc_01"]
        dados.update(new_defaults())
        dados["modulo_atuacao"] = "Laudo Extrajudicial Previdenciário (LTCAT+PPP)"
        dados["revisado_profissional"] = True
        dados["revisao_evidencias"] = evidence_hash(dados)
        app = self._app()
        self._ir_campo(app)
        self._enviar(app, "Proc_01", _Arquivo("red"))
        salvo = self.processos["Proc_01"]
        self.assertEqual(len(salvo["campo_fotos"]), 1)
        self.assertFalse(salvo["revisado_profissional"])
        self.assertEqual(salvo["revisao_evidencias"], "")


if __name__ == "__main__":
    unittest.main()
