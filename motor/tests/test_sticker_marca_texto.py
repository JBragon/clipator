"""Sticker da marca enviado pelo usuário (PNG validado) e sticker de texto digitável."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from clipator import cta, edicao, stickers
from clipator.models import Origem


def _png(tam=(200, 120), modo="RGBA") -> bytes:
    buf = io.BytesIO()
    Image.new(modo, tam, (200, 30, 30, 255) if modo == "RGBA" else (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_texto_fica_na_tela_e_mantem_maiusculas(tmp_path):
    m = cta.MODELOS["texto"]
    assert m.fixo and m.som is None and not m.caixa_alta
    with Image.open(cta.gerar("texto", {"texto": "É por isso"}, tmp_path, None)) as img:
        img.seek(img.n_frames - 1)
        q = img.convert("RGBA")
        assert q.getchannel("A").getextrema()[1] == 255  # não some no fim
        assert q.getpixel((q.width // 2, 2))[3] < 40  # sem caixa de fundo: a borda de cima fica transparente
    assert cta.opcoes("texto", {"texto": "  É por   isso  "})["texto"] == "É por isso"
    assert cta.opcoes("texto", {}) == {"texto": "@seucanal", "texto2": "", "cor": "#141416", "cor_texto": "#FFFFFF"}
    assert cta.opcoes("inscreva-se", {"texto": "se inscreve"})["texto"] == "SE INSCREVE"  # as chamadas seguem em caps
    [it] = edicao.validar([{"tipo": "sticker", "inicio": 0, "fim": 20, "params": {"ref": "cta:texto", "texto": "Oi",
                                                                                  "repetir": False}}], 30)
    ent, partes, _ = edicao.filtros_video(edicao.Edicao(itens=[it]), "vlay", 540, 960, 30, tmp_path, 1, None)
    assert ent[:1] == ["-i"] and "eof_action=repeat" in ";".join(partes)  # o render segura o último quadro
    assert edicao.sons_da_edicao(edicao.Edicao(itens=[it]), []) == ([], {})


def test_png_enviado_vai_para_os_stickers_do_canal(tmp_path):
    r = stickers.salvar_enviado(tmp_path, "Minha Marca!.png", _png())
    assert r["ref"] == "canal:minha-marca.png" and (r["largura"], r["altura"]) == (200, 120)
    r2 = stickers.salvar_enviado(tmp_path, "Minha Marca!.png", _png())
    assert r2["arquivo"] == "minha-marca-2.png"  # não apaga o anterior
    assert stickers.resolver(r["ref"], tmp_path) == tmp_path / "stickers" / "minha-marca.png"
    lib = stickers.listar(tmp_path, {"pacotes": {}, "stickers": []})
    assert {"canal:minha-marca.png", "canal:minha-marca-2.png"} <= {s["ref"] for s in lib["stickers"]}


@pytest.mark.parametrize("dados, erro", [
    (b"", "vazio"),
    (b"\x89PNG\r\n\x1a\n" + b"x" * (stickers.LIMITE_ENVIO + 1), "limite"),
    (b"GIF89a" + b"x" * 50, "PNG"),
    (b"<svg></svg>", "PNG"),
    (b"\x89PNG\r\n\x1a\n" + b"lixo" * 20, "corrompida"),
])
def test_envio_recusa_arquivo_ruim(tmp_path, dados, erro):
    with pytest.raises(stickers.ErroSticker, match=erro):
        stickers.salvar_enviado(tmp_path, "x.png", dados)
    assert not (tmp_path / "stickers").exists() or not list((tmp_path / "stickers").iterdir())


def test_envio_recusa_png_cortado_e_tamanho_fora_do_limite(tmp_path):
    bom = _png((300, 300))
    with pytest.raises(stickers.ErroSticker, match="corrompida"):
        stickers.salvar_enviado(tmp_path, "x.png", bom[: len(bom) // 2])
    with pytest.raises(stickers.ErroSticker, match="px"):
        stickers.salvar_enviado(tmp_path, "x.png", _png((10, 10)))
    with pytest.raises(stickers.ErroSticker, match="px"):
        stickers.salvar_enviado(tmp_path, "x.png", _png((5000, 40), "RGB"))


def test_api_de_envio(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws", nome_fila="jobs-envio")
    c = srv.ws.criar_canal("Iron Studios")
    c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    dados = "data:image/png;base64," + base64.b64encode(_png()).decode()
    r = cl.post("/api/stickers/canal/enviar", json={"canal": c.slug, "nome": "logo.png", "png": dados}, headers=h)
    assert r.status_code == 200 and r.json()["ref"] == "canal:logo.png"
    assert (c.path / "stickers" / "logo.png").read_bytes() == _png()
    ruim = base64.b64encode(b"nada").decode()
    assert cl.post("/api/stickers/canal/enviar", json={"canal": c.slug, "png": ruim}, headers=h).status_code == 400
    assert cl.post("/api/stickers/canal/enviar", json={"canal": c.slug, "png": "%%%"}, headers=h).status_code == 400
    assert cl.post("/api/stickers/canal/enviar", json={"png": dados}, headers=h).status_code == 400
    r = cl.get("/api/stickers/arquivo", params={"ref": "canal:logo.png", "canal": c.slug}, headers=h)
    assert r.status_code == 200 and r.content == _png()


def test_texto_com_fontes_e_formatos(tmp_path):
    fmt = cta.formato({"fonte": "anton", "negrito": "1", "italico": True, "contorno": "false"})
    assert fmt == {"fonte": "anton", "negrito": True, "italico": True, "sublinhado": False, "riscado": False,
                   "contorno": False, "sombra": True, "maiusculas": False}
    assert cta.formato({"fonte": "../../etc/x.ttf"})["fonte"] == "montserrat"
    assert cta.formato({"fonte": "canal:../x.ttf"})["fonte"] == "montserrat"
    vistos = set()
    for f in cta.FONTES:
        for extra in ({}, {"negrito": "1", "italico": "1", "sublinhado": "1", "riscado": "1", "maiusculas": "1",
                           "contorno": "0", "sombra": "0"}):
            arq = cta.gerar("texto", {"texto": "@canal", "fonte": f, **extra}, tmp_path, None)
            with Image.open(arq) as img:
                assert img.width >= 100
            vistos.add(arq)
    assert len(vistos) == 2 * len(cta.FONTES)  # cada fonte e formato é um arquivo diferente
    [it] = edicao.validar([{"tipo": "sticker", "inicio": 0, "fim": 3, "params": {
        "ref": "cta:texto", "fonte": "bangers", "sublinhado": True, "hack": 1}}], 10)
    assert it.params["fonte"] == "bangers" and it.params["sublinhado"] is True and it.params["contorno"] is True
    assert "hack" not in it.params


def test_fonte_do_canal(tmp_path):
    from clipator.workspace import fontes_dir

    dados = (fontes_dir() / "Anton-Regular.ttf").read_bytes()
    pasta = tmp_path / "assets" / "fontes"
    f = cta.salvar_fonte(pasta, "Minha Fonte.ttf", dados)
    assert f["id"] == "canal:Minha-Fonte.ttf" and (pasta / "Minha-Fonte.ttf").read_bytes() == dados
    assert f["id"] in [x["id"] for x in cta.listar_fontes(pasta)]
    with pytest.raises(ValueError):
        cta.salvar_fonte(pasta, "x.ttf", b"nada de fonte")
    with pytest.raises(ValueError):
        cta.salvar_fonte(pasta, "x.ttf", b"\x00\x01\x00\x00" + b"lixo" * 10)
    p = stickers.resolver("cta:texto", tmp_path, params={"texto": "@c", "fonte": f["id"]})
    assert p is not None and p != stickers.resolver("cta:texto", tmp_path, params={"texto": "@c"})


def test_api_de_fontes(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico
    from clipator.workspace import fontes_dir

    srv = Servico(tmp_path / "ws", nome_fila="jobs-fontes")
    c = srv.ws.criar_canal("Canal")
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    lista = cl.get("/api/fontes", params={"canal": c.slug}, headers=h).json()
    assert set(cta.FONTES) < {f["id"] for f in lista} and any(f["origem"] == "google" and not f["instalada"] for f in lista)
    assert cl.get("/api/fontes/amostra", params={"id": "anton"}, headers=h).content[1:4] == b"PNG"
    assert cl.get("/api/fontes/amostra", params={"id": "poppins"}, headers=h).status_code == 404  # ainda não baixada
    assert cl.post("/api/fontes/baixar", json={"id": "nao-existe"}, headers=h).status_code == 400
    dados = base64.b64encode((fontes_dir() / "Bangers-Regular.ttf").read_bytes()).decode()
    r = cl.post("/api/fontes/enviar", json={"canal": c.slug, "nome": "b.ttf", "arquivo": dados}, headers=h)
    assert r.status_code == 200 and r.json()["id"] == "canal:b.ttf"
    assert cl.post("/api/fontes/enviar", json={"canal": c.slug, "arquivo": "bm9wZQ=="}, headers=h).status_code == 400
    r = cl.get("/api/stickers/arquivo", params={"ref": "cta:texto", "canal": c.slug, "texto": "@x", "fonte": "canal:b.ttf",
                                                "italico": "true"}, headers=h)
    assert r.status_code == 200 and r.content[1:4] == b"PNG"


def _baixador_falso(m):
    """Serve os arquivos do pacote a partir das fontes do Clipator, com o sha256 do manifesto ajustado."""
    from clipator.workspace import fontes_dir

    dados = (fontes_dir() / "Anton-Regular.ttf").read_bytes()
    import hashlib

    for f in m["fontes"]:
        for k in ("normal", "italico"):
            if f.get(k):
                f[k]["sha256"] = hashlib.sha256(dados).hexdigest()
    pedidos = []

    def baixar(url):
        pedidos.append(url)
        return dados

    return baixar, pedidos


def test_pacote_de_fontes_valido_e_baixado_sob_demanda(tmp_path, monkeypatch):
    import copy

    from clipator import fontes

    m = fontes.manifesto()
    assert len(m["fontes"]) >= 60 and {f["licenca"] for f in m["fontes"]} <= {"OFL", "Apache 2.0"}
    assert not set(cta.FONTES) & {f["id"] for f in m["fontes"]}  # sem repetir as que já vêm junto
    m2 = copy.deepcopy(m)
    baixar, pedidos = _baixador_falso(m2)
    monkeypatch.setattr(fontes, "manifesto", lambda caminho=None: m2)
    assert fontes.caminho("poppins", False) is None and not next(f for f in fontes.listar() if f["id"] == "poppins")["instalada"]
    antes = cta.gerar("texto", {"texto": "@c", "fonte": "poppins"}, tmp_path, None)  # não baixada: Montserrat
    fontes.baixar("poppins", baixar_url=baixar)
    assert len(pedidos) == 2  # normal e itálico
    arq, ja_italica, _ = fontes.caminho("poppins", True)
    assert ja_italica and arq.is_file()
    fontes.baixar("poppins", baixar_url=baixar)
    assert len(pedidos) == 2  # já estava: não baixa de novo
    assert cta.gerar("texto", {"texto": "@c", "fonte": "poppins"}, tmp_path, None) != antes
    with pytest.raises(fontes.ErroFonte):
        fontes.baixar("poppins-falsa", baixar_url=baixar)
    m2["fontes"][0]["normal"]["sha256"] = "0" * 64
    with pytest.raises(fontes.ErroFonte, match="sha256"):
        fontes.baixar(m2["fontes"][0]["id"], baixar_url=baixar)
    r = fontes.instalar(baixar_url=baixar)
    assert r["instaladas"] == len(m2["fontes"]) - 1 and len(r["erros"]) == 1
    # fonte variável no peso do manifesto, com e sem negrito
    var = next(f for f in m2["fontes"] if f.get("peso"))
    assert cta.gerar("texto", {"texto": "@c", "fonte": var["id"], "negrito": "1"}, tmp_path, None).is_file()
    assert cta.amostra_fonte("poppins", None, tmp_path / "amostras").is_file()
    assert cta.amostra_fonte("nao-existe", None, tmp_path / "amostras") is None


def test_manifesto_de_fontes_recusa_url_sem_commit():
    import copy

    from clipator import fontes

    m = copy.deepcopy(fontes.manifesto())
    m["fontes"][0]["normal"]["url"] = "https://exemplo.com/x.ttf"
    with pytest.raises(fontes.ErroFonte):
        fontes.validar_manifesto(m)
