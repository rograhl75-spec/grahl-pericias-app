import unittest
from unittest import mock

from core import database


class _FakeSnapshot:
    def __init__(self, exists=True, value=0):
        self.exists = exists
        self._value = value

    def to_dict(self):
        return {"ultimo_numero": self._value}


class _FakeRef:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.set_calls = []

    def get(self, transaction=None):
        return self._snapshot

    def set(self, payload, merge=False):
        self.set_calls.append((payload, merge))


class _FakeCollection:
    def __init__(self, ref):
        self._ref = ref

    def document(self, _doc_id):
        return self._ref


class _FakeDb:
    def __init__(self, ref):
        self._ref = ref

    def collection(self, _name):
        return _FakeCollection(self._ref)

    def transaction(self):
        return mock.Mock()


class DatabaseTests(unittest.TestCase):
    def test_gerar_proximo_id_fallback_local(self):
        with mock.patch.object(database, "_obter_db", side_effect=RuntimeError("sem db")):
            proc_id = database.gerar_proximo_id({"Proc_01": {}, "Proc_02": {}})

        self.assertEqual(proc_id, "Proc_03")

    def test_gerar_proximo_id_atomico_respeita_maior_id_local_quando_contador_ausente(self):
        fake_ref = _FakeRef(_FakeSnapshot(exists=False, value=0))
        fake_db = _FakeDb(fake_ref)

        with (
            mock.patch.object(database, "_obter_db", return_value=fake_db),
            mock.patch.object(database.firestore, "transactional", side_effect=lambda fn: fn),
        ):
            proc_id = database.gerar_proximo_id({"Proc_01": {}, "Proc_02": {}})

        self.assertEqual(proc_id, "Proc_03")

    def test_gerar_proximo_id_atomico_no_firestore(self):
        fake_ref = _FakeRef(_FakeSnapshot(exists=True, value=5))
        fake_db = _FakeDb(fake_ref)

        with (
            mock.patch.object(database, "_obter_db", return_value=fake_db),
            mock.patch.object(database.firestore, "transactional", side_effect=lambda fn: fn),
        ):
            proc_id = database.gerar_proximo_id({})

        self.assertEqual(proc_id, "Proc_06")

    def test_gerar_proximo_id_atomico_corrige_contador_defasado(self):
        fake_ref = _FakeRef(_FakeSnapshot(exists=True, value=1))
        fake_db = _FakeDb(fake_ref)

        with (
            mock.patch.object(database, "_obter_db", return_value=fake_db),
            mock.patch.object(database.firestore, "transactional", side_effect=lambda fn: fn),
        ):
            proc_id = database.gerar_proximo_id({"Proc_01": {}, "Proc_02": {}, "Proc_03": {}})

        self.assertEqual(proc_id, "Proc_04")

    def _limpar_cache_db(self):
        database._obter_db.clear()
        self.addCleanup(database._obter_db.clear)

    def test_obter_db_config_ausente_levanta_erro_controlado_sem_st_stop(self):
        self._limpar_cache_db()
        with (
            mock.patch.object(database.firebase_admin, "get_app", side_effect=ValueError),
            mock.patch.object(
                database,
                "obter_credenciais_firebase",
                side_effect=database.ConfigurationError("faltando private_key"),
            ),
            mock.patch.object(database.st, "stop") as st_stop,
        ):
            with self.assertRaises(database.FirebaseIndisponivelError):
                database._obter_db()

        st_stop.assert_not_called()

    def test_obter_db_firestore_indisponivel_levanta_erro_controlado(self):
        self._limpar_cache_db()
        with (
            mock.patch.object(database.firebase_admin, "get_app", return_value=object()),
            mock.patch.object(database.firestore, "client", side_effect=RuntimeError("offline")),
            mock.patch.object(database.st, "stop") as st_stop,
        ):
            with self.assertRaises(database.FirebaseIndisponivelError):
                database._obter_db()

        st_stop.assert_not_called()

    def test_carregar_dados_com_firebase_indisponivel_retorna_vazio_e_exibe_erro(self):
        with (
            mock.patch.object(
                database,
                "_obter_db",
                side_effect=database.FirebaseIndisponivelError("sem secrets"),
            ),
            mock.patch.object(database.st, "error") as st_error,
            mock.patch.object(database.st, "stop") as st_stop,
        ):
            dados = database.carregar_dados()

        self.assertEqual(dados, {})
        st_error.assert_called_once()
        st_stop.assert_not_called()

    def test_salvar_processo_com_firebase_indisponivel_retorna_false(self):
        with (
            mock.patch.object(
                database,
                "_obter_db",
                side_effect=database.FirebaseIndisponivelError("sem secrets"),
            ),
            mock.patch.object(database.st, "error") as st_error,
        ):
            self.assertFalse(database.salvar_processo("Proc_01", {}))

        st_error.assert_called_once()

    def test_salvar_processo_rejeita_snapshot_desatualizado(self):
        snapshot = mock.Mock(exists=True)
        snapshot.to_dict.return_value = {"_revision": 2}
        ref = mock.Mock()
        ref.get.return_value = snapshot
        transaction = mock.Mock()
        fake_db = mock.Mock()
        fake_db.collection.return_value.document.return_value = ref
        fake_db.transaction.return_value = transaction

        with (
            mock.patch.object(database, "_obter_db", return_value=fake_db),
            mock.patch.object(database.firestore, "transactional", side_effect=lambda fn: fn),
            mock.patch.object(database.st, "session_state", {}),
            mock.patch.object(database.st, "error") as st_error,
        ):
            resultado = database.salvar_processo("Proc_01", {"_revision": 1})

        self.assertFalse(resultado)
        transaction.set.assert_not_called()
        self.assertIn("alterado por outro usuário", st_error.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
