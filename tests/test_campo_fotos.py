import unittest
from unittest import mock

from core import database
from core.campo_fotos import (
    DOC_SIZE_BUDGET_BYTES,
    adicionar_pendentes,
    criar_foto,
    estimar_tamanho_documento,
    ids_fotos,
    resumo_armazenamento,
    separar_por_limite,
)


class CampoFotosTests(unittest.TestCase):
    def test_ids_estaveis_por_conteudo_e_unicos_com_duplicatas_legadas(self):
        a, b = criar_foto(b"a"), criar_foto(b"b")
        ids = ids_fotos([a, b, dict(a)])
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(ids_fotos([b])[0], ids[1])

    def test_adicionar_pendentes_ignora_salvas_e_pendentes(self):
        salvas = [criar_foto(b"a")]
        fila, adicionadas, duplicadas = adicionar_pendentes(
            salvas, [criar_foto(b"b")], [criar_foto(b"a"), criar_foto(b"b"), criar_foto(b"c")],
        )
        self.assertEqual((adicionadas, duplicadas), (1, 2))
        self.assertEqual(len(fila), 2)

    def test_separar_por_limite_mantem_ordem_e_excedentes(self):
        base = {"campo_fotos": [], "texto": "x" * (DOC_SIZE_BUDGET_BYTES - 2000)}
        fotos = [criar_foto(bytes([i]) * 1000) for i in range(3)]
        cabem, excedentes = separar_por_limite(base, fotos)
        self.assertEqual(cabem, fotos[:1])
        self.assertEqual(excedentes, fotos[1:])
        self.assertLessEqual(
            estimar_tamanho_documento({**base, "campo_fotos": cabem}), DOC_SIZE_BUDGET_BYTES)


    def test_resumo_armazenamento_distingue_salvas_e_pendentes(self):
        dados = {"campo_fotos": [criar_foto(b"a"), criar_foto(b"b")]}
        resumo = resumo_armazenamento(dados, [criar_foto(b"c")])
        self.assertEqual((resumo["salvas"], resumo["pendentes"]), (2, 1))
        self.assertEqual(resumo["bytes_usados"], estimar_tamanho_documento(dados))
        self.assertEqual(resumo["bytes_limite"], DOC_SIZE_BUDGET_BYTES)
        self.assertGreater(resumo["fracao_usada"], 0)
        cheio = resumo_armazenamento({"campo_fotos": [], "x": "y" * DOC_SIZE_BUDGET_BYTES})
        self.assertEqual(cheio["fracao_usada"], 1.0)
        self.assertEqual(resumo_armazenamento(None)["salvas"], 0)

class DatabaseIntegridadeTests(unittest.TestCase):
    def test_excluir_processo_informa_resultado(self):
        estado = {"_process_revision_snapshot": {"Proc_01": 3}}
        with mock.patch.object(database, "_obter_db"), \
                mock.patch.object(database.st, "session_state", estado):
            self.assertTrue(database.excluir_processo("Proc_01"))
        self.assertNotIn("Proc_01", estado["_process_revision_snapshot"])
        with mock.patch.object(database, "_obter_db", side_effect=RuntimeError("offline")), \
                mock.patch.object(database.st, "error"):
            self.assertFalse(database.excluir_processo("Proc_01"))

    def test_documento_acima_do_limite_tem_mensagem_clara(self):
        erro = RuntimeError("400 Document exceeds the maximum allowed size of 1,048,576 bytes.")
        with mock.patch.object(database, "_obter_db", side_effect=erro), \
                mock.patch.object(database.st, "error") as st_error:
            self.assertFalse(database.salvar_processo("Proc_01", {}))
        self.assertIn("limite de armazenamento", st_error.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
