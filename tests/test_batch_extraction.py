import json
from pathlib import Path
from unittest import mock

import pytest

import extract_batch
from batch_extraction import extractor as extractor_module
from batch_extraction.config import BatchConfig, load_config
from batch_extraction.extractor import extract_pdf
from batch_extraction.fields import extract_fields
from batch_extraction.ocr import OcrStatus
from batch_extraction.processor import discover_pdfs, output_name, run_batch

OCR_OFF = OcrStatus(False, reason="indisponível no teste")
OCR_ON = OcrStatus(True, lang="por")


def make_text_pdf(pages):
    """Gera um PDF mínimo com texto nativo (uma lista de linhas por página)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    n = len(pages)
    font_id = 3 + 2 * n
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, lines in enumerate(pages):
        escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
        content = ("BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({line}) '" for line in escaped) + " ET").encode("latin-1")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for idx, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % idx + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def make_blank_image_pdf(path: Path, pages: int = 1):
    from PIL import Image

    imagens = [Image.new("RGB", (200, 280), "white") for _ in range(pages)]
    imagens[0].save(path, save_all=True, append_images=imagens[1:])


PAGINA_PROCESSO = [
    "PROCESSO n. 0001234-56.2023.5.09.0663",
    "RECLAMANTE: JOAO DA SILVA CPF: 123.456.789-09",
    "RECLAMADO: EMPRESA XYZ LTDA",
    "CNPJ: 12.345.678/0001-90",
    "Valor da causa: R$ 50.000,00",
]
PAGINA_VARA = ["2a Vara do Trabalho de Londrina - PR", "Autuado em 10/01/2023"]


def make_config(tmp_path: Path, **kwargs) -> BatchConfig:
    base = tmp_path / "data"
    config = BatchConfig(
        input_dir=base / "input",
        output_dir=base / "output",
        logs_dir=base / "logs",
        failed_dir=base / "failed",
        use_subprocess=False,
    )
    for chave, valor in kwargs.items():
        setattr(config, chave, valor)
    return config


def test_extract_fields_rules_based():
    campos = extract_fields([(1, "\n".join(PAGINA_PROCESSO)), (2, "\n".join(PAGINA_VARA))])

    assert campos["processo_num"] == {"valor": "0001234-56.2023.5.09.0663", "pagina": 1}
    assert campos["reclamante_nome"]["valor"] == "JOAO DA SILVA"
    assert campos["reclamada_nome"]["valor"] == "EMPRESA XYZ LTDA"
    assert campos["reclamante_cpf"]["valor"] == "123.456.789-09"
    assert campos["reclamada_cnpj"]["valor"] == "12.345.678/0001-90"
    assert campos["valor_causa"]["valor"] == "R$ 50.000,00"
    assert campos["orgao_julgador"] == {"valor": "2a Vara do Trabalho de Londrina", "pagina": 2}
    assert campos["data_autuacao"]["valor"] == "10/01/2023"
    assert campos["cpfs_encontrados"] == {"valor": ["123.456.789-09"], "paginas": [1]}
    assert campos["rito_processual"] == {"valor": None, "pagina": None}


def test_extract_fields_normaliza_numeros_sem_mascara():
    campos = extract_fields([(3, "Processo nº 00012345620235090663\nCPF: 12345678909\nCNPJ: 12345678000190")])

    assert campos["processo_num"] == {"valor": "0001234-56.2023.5.09.0663", "pagina": 3}
    assert campos["reclamante_cpf"]["valor"] == "123.456.789-09"
    assert campos["reclamada_cnpj"]["valor"] == "12.345.678/0001-90"


def test_load_config_from_env(tmp_path):
    config = load_config(
        {
            "BATCH_DATA_DIR": str(tmp_path / "base"),
            "BATCH_OCR_ENABLED": "nao",
            "BATCH_FILE_TIMEOUT": "60",
            "BATCH_OUTPUT_DIR": str(tmp_path / "saida"),
        }
    )

    assert config.input_dir == tmp_path / "base" / "input"
    assert config.output_dir == tmp_path / "saida"
    assert config.ocr_enabled is False
    assert config.file_timeout_seconds == 60


def test_load_config_rejects_invalid_values():
    with pytest.raises(ValueError, match="BATCH_FILE_TIMEOUT"):
        load_config({"BATCH_FILE_TIMEOUT": "abc"})
    with pytest.raises(ValueError, match="BATCH_OCR_ENABLED"):
        load_config({"BATCH_OCR_ENABLED": "talvez"})


def test_extract_pdf_text_based(tmp_path):
    pdf = tmp_path / "processo.pdf"
    pdf.write_bytes(make_text_pdf([PAGINA_PROCESSO, PAGINA_VARA]))

    resultado = extract_pdf(pdf, make_config(tmp_path), OCR_OFF)

    assert resultado["status"] == "sucesso"
    assert resultado["tipo_pdf"] == "texto"
    assert resultado["metodo_extracao"] == "texto"
    assert resultado["paginas_total"] == 2
    assert resultado["paginas_processadas"] == 2
    assert resultado["erros"] == []
    assert resultado["campos_extraidos"]["processo_num"]["valor"] == "0001234-56.2023.5.09.0663"
    assert "JOAO DA SILVA" in resultado["paginas"][0]["texto"]
    assert resultado["sha256"] and resultado["inicio_processamento"] and resultado["fim_processamento"]


def test_extract_pdf_scanned_without_ocr_fails_with_clear_message(tmp_path):
    pdf = tmp_path / "escaneado.pdf"
    make_blank_image_pdf(pdf, pages=2)

    resultado = extract_pdf(pdf, make_config(tmp_path), OCR_OFF)

    assert resultado["status"] == "falha"
    assert resultado["tipo_pdf"] == "imagem"
    assert any("OCR indisponível" in aviso for aviso in resultado["avisos"])
    assert any("Nenhum texto extraído" in erro for erro in resultado["erros"])


def test_extract_pdf_uses_ocr_fallback_for_low_text_pages(tmp_path):
    pdf = tmp_path / "escaneado.pdf"
    make_blank_image_pdf(pdf, pages=2)

    with mock.patch.object(extractor_module, "ocr_page", return_value="RECLAMANTE: MARIA DE SOUZA\nTexto via OCR") as ocr:
        resultado = extract_pdf(pdf, make_config(tmp_path), OCR_ON)

    assert ocr.call_count == 2
    assert resultado["status"] == "sucesso"
    assert resultado["metodo_extracao"] == "ocr"
    assert resultado["ocr"]["paginas_ocr"] == 2
    assert resultado["campos_extraidos"]["reclamante_nome"]["valor"] == "MARIA DE SOUZA"


def test_extract_pdf_respects_max_ocr_pages(tmp_path):
    pdf = tmp_path / "escaneado.pdf"
    make_blank_image_pdf(pdf, pages=3)

    with mock.patch.object(extractor_module, "ocr_page", return_value="Texto reconhecido pelo OCR com tamanho suficiente"):
        resultado = extract_pdf(pdf, make_config(tmp_path, max_ocr_pages=1), OCR_ON)

    assert resultado["status"] == "parcial"
    assert resultado["ocr"]["paginas_ocr"] == 1
    assert any("BATCH_MAX_OCR_PAGES" in aviso for aviso in resultado["avisos"])


def test_extract_pdf_rejects_invalid_signature_and_size(tmp_path):
    invalido = tmp_path / "invalido.pdf"
    invalido.write_bytes(b"nao sou pdf")
    grande = tmp_path / "grande.pdf"
    grande.write_bytes(b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10))

    r1 = extract_pdf(invalido, make_config(tmp_path), OCR_OFF)
    r2 = extract_pdf(grande, make_config(tmp_path, max_file_size_mb=1), OCR_OFF)

    assert r1["status"] == "falha" and "assinatura" in r1["erros"][0]
    assert r2["status"] == "falha" and "excede o limite" in r2["erros"][0]


def test_extract_pdf_truncates_text_but_keeps_fields(tmp_path):
    pdf = tmp_path / "processo.pdf"
    pdf.write_bytes(make_text_pdf([PAGINA_PROCESSO, PAGINA_VARA]))

    resultado = extract_pdf(pdf, make_config(tmp_path, max_text_chars=50), OCR_OFF)

    assert "texto" not in resultado["paginas"][0]
    assert resultado["campos_extraidos"]["orgao_julgador"]["valor"] == "2a Vara do Trabalho de Londrina"
    assert any("não foi incluído" in aviso for aviso in resultado["avisos"])


def test_discover_and_output_name(tmp_path):
    entrada = tmp_path / "input"
    (entrada / "sub").mkdir(parents=True)
    (entrada / "a.PDF").write_bytes(b"%PDF-")
    (entrada / "b.txt").write_text("x")
    (entrada / "sub" / "c.pdf").write_bytes(b"%PDF-")

    assert [p.name for p in discover_pdfs(entrada)] == ["a.PDF"]
    recursivos = discover_pdfs(entrada, recursive=True)
    assert [p.name for p in recursivos] == ["a.PDF", "c.pdf"]
    assert output_name(recursivos[1], entrada) == "sub__c.json"


def test_run_batch_creates_dirs_and_isolates_failures(tmp_path):
    config = make_config(tmp_path)
    config.ensure_dirs()
    (config.input_dir / "bom.pdf").write_bytes(make_text_pdf([PAGINA_PROCESSO]))
    (config.input_dir / "ruim.pdf").write_bytes(b"corrompido")

    relatorio = run_batch(config, ocr_status=OCR_OFF)

    for pasta in ("input", "output", "logs", "failed"):
        assert (tmp_path / "data" / pasta).is_dir()
    assert relatorio["total_arquivos"] == 2
    assert relatorio["sucesso"] == 1
    assert relatorio["falha"] == 1
    assert json.loads((config.output_dir / "bom.json").read_text(encoding="utf-8"))["status"] == "sucesso"
    assert json.loads((config.output_dir / "ruim.json").read_text(encoding="utf-8"))["status"] == "falha"
    assert (config.failed_dir / "ruim.pdf").exists()
    assert not (config.failed_dir / "bom.pdf").exists()
    assert Path(relatorio["relatorio_path"]).exists()

    config.skip_existing = True
    segundo = run_batch(config, ocr_status=OCR_OFF)
    assert segundo["pulado"] == 1
    assert segundo["falha"] == 1


def test_run_batch_in_subprocess(tmp_path):
    config = make_config(tmp_path, use_subprocess=True, file_timeout_seconds=120)
    config.ensure_dirs()
    (config.input_dir / "bom.pdf").write_bytes(make_text_pdf([PAGINA_PROCESSO]))

    relatorio = run_batch(config, ocr_status=OCR_OFF)

    assert relatorio["sucesso"] == 1
    dados = json.loads((config.output_dir / "bom.json").read_text(encoding="utf-8"))
    assert dados["campos_extraidos"]["reclamante_nome"]["valor"] == "JOAO DA SILVA"


def test_cli_creates_structure_and_returns_exit_code(tmp_path, monkeypatch):
    base = tmp_path / "dados"
    monkeypatch.setenv("BATCH_DATA_DIR", str(base))

    assert extract_batch.main(["--no-ocr", "--no-subprocess"]) == 0
    for pasta in ("input", "output", "logs", "failed"):
        assert (base / pasta).is_dir()
    assert list((base / "logs").glob("extracao_*.log"))

    (base / "input" / "ruim.pdf").write_bytes(b"corrompido")
    assert extract_batch.main(["--no-ocr", "--no-subprocess"]) == 1
