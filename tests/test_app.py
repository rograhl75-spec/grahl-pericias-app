import io
import unittest
from pathlib import Path
from unittest import mock

from docx import Document
from streamlit.testing.v1 import AppTest

from core import database
from core.config import criar_dados_padrao


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"
MENU_OPTIONS = [
    "➕ Novo Processo / Caso",
    "✏️ Dados, Escritório & SST",
    "🚜 Diligência de Campo & Fotos",
    "🗑️ Excluir Processo",
    "📄 Gerar Documento Word Final",
]


class AppTests(unittest.TestCase):
    def setUp(self):
        self.processos = {}
        self.carregar = mock.patch.object(
            database, "carregar_dados", side_effect=lambda: self.processos.copy()
        )
        self.carregar.start()
        self.addCleanup(self.carregar.stop)

    def test_inicio_sem_integracao_de_importacao_pdf(self):
        app = AppTest.from_file(str(APP_FILE)).run()

        self.assertFalse(app.exception)
        self.assertEqual([button.label for button in app.sidebar.button], MENU_OPTIONS)
        self.assertEqual(
            [button.label for button in app.main.button], ["Criar Caso Completo"]
        )
        uploaders = app.get("file_uploader")
        self.assertEqual(len(uploaders), 1)
        self.assertEqual(
            [extension.lstrip(".") for extension in uploaders[0].proto.type], ["docx"]
        )

    def test_criar_caso_segue_para_edicao(self):
        for previdenciario in (False, True):
            with self.subTest(previdenciario=previdenciario):
                self.processos.clear()
                app = AppTest.from_file(str(APP_FILE)).run()
                if previdenciario:
                    app.radio[0].set_value(app.radio[0].options[1]).run()
                app.text_input(key="novo_num_0").set_value("123")
                app.text_input(key="novo_nome_0").set_value("Autor")
                app.text_input(key="novo_emp_0").set_value("Empresa")

                def salvar(processo_id, dados):
                    self.processos[processo_id] = dados.copy()
                    return True

                with (
                    mock.patch.object(database, "gerar_proximo_id", return_value="Proc_01"),
                    mock.patch.object(database, "salvar_processo", side_effect=salvar) as gravar,
                ):
                    app.main.button[0].click().run()

                self.assertFalse(app.exception)
                gravar.assert_called_once()
                self.assertEqual(app.session_state["processo_ativo"], "Proc_01")
                self.assertEqual(app.session_state["menu_opcao"], MENU_OPTIONS[1])
                self.assertEqual(self.processos["Proc_01"]["processo_num"], "123")
                self.assertEqual(self.processos["Proc_01"]["reclamante_nome"], "Autor")
                self.assertEqual(self.processos["Proc_01"]["reclamada_nome"], "Empresa")
                self.assertEqual(
                    "Previdenciário" in self.processos["Proc_01"]["modulo_atuacao"],
                    previdenciario,
                )

    def test_importacao_judicial_preenche_imediatamente_e_reseta_ao_trocar_modulo(self):
        fields = {
            "processo_num": "123",
            "reclamante_nome": "Autor importado",
            "reclamada_nome": "Empresa importada",
        }
        doc = Document()
        for field, value in fields.items():
            doc.add_paragraph(f"[START_{field.upper()}]{value}[END_{field.upper()}]")
        upload = io.BytesIO()
        doc.save(upload)
        upload.seek(0)
        app = AppTest.from_file(str(APP_FILE)).run()
        for short in ("num", "nome", "emp"):
            app.session_state[f"novo_{short}_0"] = "Valor digitado"

        with mock.patch("streamlit.file_uploader", return_value=upload):
            app.run()
            self.assertFalse(app.exception)
            for field, short in (("processo_num", "num"), ("reclamante_nome", "nome"),
                                 ("reclamada_nome", "emp")):
                self.assertEqual(app.session_state["parsed_data"][field], fields[field])
                self.assertEqual(app.text_input(key=f"novo_{short}_0").value, fields[field])
            self.assertEqual(
                [button.label for button in app.main.button], ["Criar Caso Completo"]
            )

            app.radio[0].set_value(app.radio[0].options[1]).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["parsed_data"], {})
            self.assertIn(
                "Usar campos reconhecidos no novo caso",
                [button.label for button in app.main.button],
            )

    def test_demais_telas_abrem_com_caso_existente(self):
        self.processos["Proc_01"] = criar_dados_padrao()
        app = AppTest.from_file(str(APP_FILE)).run()

        for index, label in enumerate(MENU_OPTIONS[1:], start=1):
            with self.subTest(tela=label):
                app.sidebar.button[index].click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["menu_opcao"], label)


if __name__ == "__main__":
    unittest.main()
