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


if __name__ == "__main__":
    unittest.main()
