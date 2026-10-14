import io
from unittest import mock

import pytest
from docx import Document
from google.api_core.exceptions import PreconditionFailed
from PIL import Image

from core import photo_storage
from core.campo_fotos import adicionar_pendentes, criar_foto, estimar_tamanho_documento, foto_hash
from grahl_app.photos import normalize_photo_entry


def imagem(cor="red", tamanho=(32, 24)):
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def limpar_cache_storage():
    photo_storage._baixar_foto_storage.clear()
    yield
    photo_storage._baixar_foto_storage.clear()


def test_upload_guarda_apenas_metadados_e_reutiliza_objeto():
    foto = criar_foto(imagem(), "1, 2")
    bucket = mock.Mock()
    blob = bucket.blob.return_value
    blob.exists.side_effect = [False, True]
    with mock.patch.object(photo_storage, "_obter_bucket", return_value=bucket):
        referencia = photo_storage.enviar_foto("Proc_01", foto)
        repetida = photo_storage.enviar_foto("Proc_01", foto)
    assert referencia["storage_path"] == repetida["storage_path"]
    assert referencia["hash"] == foto_hash(foto)
    assert referencia["mime_type"] == "image/png"
    assert referencia["gps"] == "1, 2"
    assert "base64" not in referencia
    blob.upload_from_string.assert_called_once_with(
        imagem(), content_type="image/png", if_generation_match=0, timeout=60,
    )
    assert normalize_photo_entry(referencia)["storage_path"] == referencia["storage_path"]


def test_referencias_nao_crescem_com_payload_e_sao_isoladas_por_caso():
    pequena = photo_storage.metadados_storage("Proc_01", criar_foto(imagem()))
    grande = photo_storage.metadados_storage("Proc_01", criar_foto(imagem(tamanho=(2048, 2048))))
    assert abs(estimar_tamanho_documento({"campo_fotos": [pequena]})
               - estimar_tamanho_documento({"campo_fotos": [grande]})) < 10
    outro_caso = photo_storage.metadados_storage("Proc_02", criar_foto(imagem()))
    assert pequena["storage_path"] != outro_caso["storage_path"]
    fila, adicionadas, duplicadas = adicionar_pendentes(
        [pequena], [], [criar_foto(imagem()), criar_foto(imagem("blue"))],
    )
    assert (len(fila), adicionadas, duplicadas) == (1, 1, 1)


def test_criacao_concorrente_do_mesmo_objeto_e_idempotente():
    bucket = mock.Mock()
    bucket.blob.return_value.exists.return_value = False
    bucket.blob.return_value.upload_from_string.side_effect = PreconditionFailed("exists")
    with mock.patch.object(photo_storage, "_obter_bucket", return_value=bucket):
        assert photo_storage.enviar_foto("Proc_01", criar_foto(imagem()))["storage_path"]


def test_resolver_storage_legado_base64_e_path(tmp_path):
    dados = imagem()
    referencia = photo_storage.metadados_storage("Proc_01", criar_foto(dados))
    bucket = mock.Mock()
    bucket.blob.return_value.download_as_bytes.return_value = dados
    with mock.patch.object(photo_storage, "_obter_bucket", return_value=bucket):
        assert photo_storage.resolver_bytes_foto(referencia) == dados
        bucket.blob.assert_called_with(referencia["storage_path"])
    with mock.patch.object(photo_storage, "_obter_bucket") as obter:
        assert photo_storage.resolver_bytes_foto(criar_foto(dados)) == dados
        local = tmp_path / "foto.png"
        local.write_bytes(dados)
        assert photo_storage.resolver_bytes_foto({"path": str(local)}) == dados
        assert foto_hash({"path": str(local)}) == foto_hash(criar_foto(dados))
        obter.assert_not_called()


def test_falhas_e_limite_sao_controlados():
    with mock.patch.object(photo_storage, "_obter_bucket", side_effect=RuntimeError("offline")):
        with pytest.raises(photo_storage.FotoStorageError):
            photo_storage.enviar_foto("Proc_01", criar_foto(imagem()))
        with pytest.raises(photo_storage.FotoStorageError):
            photo_storage.resolver_bytes_foto({"storage_path": "campo_fotos/test.png"})
    with mock.patch.object(photo_storage, "MAX_PHOTO_BYTES", 5):
        with pytest.raises(ValueError, match="10 MiB"):
            photo_storage.metadados_storage("Proc_01", criar_foto(imagem()))
    with pytest.raises(ValueError, match="Imagem ausente"):
        photo_storage.resolver_bytes_foto({"download_url": "http://127.0.0.1/private"})


def test_cache_evitar_download_em_cada_rerun_e_falhas_nao_sao_cacheadas():
    bucket = mock.Mock()
    bucket.blob.return_value.download_as_bytes.side_effect = [RuntimeError("offline"), imagem()]
    with mock.patch.object(photo_storage, "_obter_bucket", return_value=bucket):
        with pytest.raises(photo_storage.FotoStorageError):
            photo_storage.resolver_bytes_foto({"storage_path": "campo_fotos/cache.png"})
        for _ in range(2):
            assert photo_storage.resolver_bytes_foto({"storage_path": "campo_fotos/cache.png"}) == imagem()
    assert bucket.blob.return_value.download_as_bytes.call_count == 2


def test_bucket_usa_configuracao_e_mesma_app_firebase():
    with mock.patch.dict("os.environ", {"FIREBASE_STORAGE_BUCKET": "meu-projeto.firebasestorage.app"}), \
            mock.patch.object(photo_storage, "_obter_app_firebase") as app, \
            mock.patch.object(photo_storage.storage, "bucket") as bucket:
        assert photo_storage._obter_bucket() == bucket.return_value
        bucket.assert_called_once_with("meu-projeto.firebasestorage.app", app=app.return_value)
    with mock.patch.dict("os.environ", {"FIREBASE_STORAGE_BUCKET": ""}), \
            mock.patch.object(photo_storage.st, "secrets", {"firebase": {"storage_bucket": "projeto.appspot.com"}}), \
            mock.patch.object(photo_storage, "_obter_app_firebase"), \
            mock.patch.object(photo_storage.storage, "bucket") as bucket:
        photo_storage._obter_bucket()
        assert bucket.call_args.args == ("projeto.appspot.com",)
    with mock.patch.dict("os.environ", {"FIREBASE_STORAGE_BUCKET": ""}), \
            mock.patch.object(photo_storage.st, "secrets", {}):
        with pytest.raises(photo_storage.FotoStorageError, match="storage_bucket"):
            photo_storage._obter_bucket()


@pytest.mark.parametrize("extrajudicial", [False, True])
def test_word_inclui_storage_e_fotos_legadas(tmp_path, extrajudicial):
    from core.config import criar_dados_padrao
    from core.extrajudicial import new_defaults
    from core.extrajudicial_document import build_extrajudicial_bytes
    from grahl_app.documents import build_document_bytes

    local = tmp_path / "foto.png"
    local.write_bytes(imagem("green"))
    dados = criar_dados_padrao()
    referencia = photo_storage.metadados_storage("Proc_01", criar_foto(imagem()))
    dados["campo_fotos"] = [referencia, criar_foto(imagem("blue")), {"path": str(local)}]
    bucket = mock.Mock()
    bucket.blob.return_value.download_as_bytes.return_value = imagem()
    with mock.patch.object(photo_storage, "_obter_bucket", return_value=bucket):
        if extrajudicial:
            dados.update(new_defaults())
            dados["campo_fotos"] = [referencia, criar_foto(imagem("blue")), {"path": str(local)}]
            buffer, warnings = build_extrajudicial_bytes(dados, preliminary=True)
        else:
            buffer, warnings = build_document_bytes(dados)
    assert not warnings
    doc = Document(buffer)
    assert sum("Figura" in p.text for p in doc.paragraphs) == 3
    assert len(doc.inline_shapes) >= 3
