"""Modo remoto (celular): quem pode entrar, pareamento por código e a API restrita."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from clipator import remoto
from clipator.models import Clip, Origem
from clipator.workspace import write_json

CASA = ("192.168.0.23", 51000)
H = {"x-clipator": "1"}


@pytest.mark.parametrize("ip, ok", [
    ("192.168.0.23", True), ("10.0.0.5", True), ("172.16.4.1", True), ("127.0.0.1", True),
    ("100.101.102.103", True),  # Tailscale (CGNAT)
    ("fd7a:115c:a1e0::1", True), ("::ffff:192.168.1.2", True), ("fe80::1%eth0", True),
    ("8.8.8.8", False), ("200.147.67.142", False), ("2001:4860:4860::8888", False), ("0.0.0.0", False),
    ("testclient", False), ("", False), (None, False),
])
def test_so_rede_de_casa_e_tailscale(ip, ok):
    assert remoto.endereco_permitido(ip) is ok


def test_codigo_vale_uma_vez_e_vence(tmp_path, monkeypatch):
    r = remoto.Remoto(tmp_path / "remoto.json")
    assert r.parear("qualquer") is None  # sem código gerado
    cod, _ = r.novo_codigo()
    token, ap = r.parear(cod, "Moto G")
    assert ap["nome"] == "Moto G" and r.validar(token)["id"] == ap["id"]
    assert r.parear(cod) is None  # uso único
    assert token not in (tmp_path / "remoto.json").read_text(encoding="utf-8")  # só o hash fica no disco

    cod, _ = r.novo_codigo()
    agora = time.time()
    monkeypatch.setattr(remoto, "_agora", lambda: agora + remoto.VALIDADE_CODIGO + 1)
    assert r.parear(cod) is None  # vencido


def test_codigo_cai_depois_de_muitas_tentativas(tmp_path):
    r = remoto.Remoto(tmp_path / "remoto.json")
    cod, _ = r.novo_codigo()
    for _ in range(remoto.TENTATIVAS_MAX):
        assert r.parear("errado") is None
    assert r.parear(cod) is None  # alguém tentou adivinhar: o código foi invalidado


def test_remover_aparelho_tira_o_acesso(tmp_path):
    r = remoto.Remoto(tmp_path / "remoto.json")
    token, ap = r.parear(r.novo_codigo()[0], "")
    assert ap["nome"] == "Celular"
    assert r.remover(ap["id"]) and r.validar(token) is None and not r.remover(ap["id"])


def test_qr_code_em_svg():
    svg = remoto.qr_svg("http://100.64.0.1:8766/#parear=abc")
    assert svg.startswith("data:image/svg+xml") and "xmlns" in svg


def test_enderecos_poem_o_tailscale_primeiro(monkeypatch):
    monkeypatch.setattr(remoto, "_ip_da_rede", lambda: "192.168.0.10")
    e = remoto.enderecos(8766, {"ip": "100.70.1.2"})
    assert [x["tipo"] for x in e] == ["tailscale", "wifi"] and e[0]["url"] == "http://100.70.1.2:8766"
    assert [x["tipo"] for x in remoto.enderecos(8766, {})] == ["wifi"]


# ---- API remota ---------------------------------------------------------------------------------
@pytest.fixture
def ambiente(tmp_path):
    from clipator.api_remoto import criar_app_remoto
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    rem = remoto.Remoto(tmp_path / "ws" / ".clipator" / "remoto.json")
    app = criar_app_remoto(srv, rem)
    canal = srv.ws.criar_canal("Teste")
    p = canal.criar_projeto("Podcast 12", Origem(tipo="link", valor="https://www.youtube.com/watch?v=abcdefghijk"))
    write_json(p.candidatos_path, [
        {"id": "c01", "inicio": 10, "fim": 50, "duracao": 40, "nota": 72, "modo": "curto", "texto": "Ninguém te conta",
         "titulos": ["O erro de 500 mil"]},
        {"id": "c02", "inicio": 80, "fim": 120, "duracao": 40, "nota": 51, "modo": "curto", "texto": "Outra"},
    ])
    yield srv, rem, app, p
    srv.fila.fechar()


def pareado(rem, app, client=CASA) -> TestClient:
    cl = TestClient(app, client=client)
    cod, _ = rem.novo_codigo()
    r = cl.post("/m/api/parear", json={"codigo": cod, "nome": "iPhone"}, headers=H)
    assert r.status_code == 200, r.text
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    return cl


def test_ip_publico_e_barrado_ate_na_pagina(ambiente):
    _, rem, app, _ = ambiente
    cl = TestClient(app, client=("8.8.8.8", 4000))
    assert cl.get("/").status_code == 403
    assert cl.post("/m/api/parear", json={"codigo": rem.novo_codigo()[0]}, headers=H).status_code == 403


def test_pagina_abre_sem_pareamento_mas_a_api_nao(ambiente):
    _, rem, app, _ = ambiente
    cl = TestClient(app, client=CASA)
    r = cl.get("/")
    assert r.status_code == 200 and "Clipator" in r.text and "script-src 'self'" in r.headers["content-security-policy"]
    assert cl.get("/app.js").status_code == 200 and cl.get("/manifest.webmanifest").status_code == 200
    assert cl.get("/remoto.py").status_code == 404 and cl.get("/..%2Fapi.py").status_code == 404
    assert cl.get("/m/api/estado").status_code == 401
    assert cl.post("/m/api/parear", json={"codigo": "chute"}, headers=H).status_code == 401
    # sem o cabeçalho (um formulário de outro site, por exemplo) o pareamento nem é tentado
    assert cl.post("/m/api/parear", json={"codigo": rem.novo_codigo()[0]}).status_code == 403


def test_celular_ve_projeto_e_aprova_cortes(ambiente):
    srv, rem, app, p = ambiente
    rodou = threading.Event()
    srv.fila.registrar("renderizar", lambda params, ctx: rodou.set())
    cl = pareado(rem, app)

    st = cl.get("/m/api/estado").json()
    assert st["aparelho"]["nome"] == "iPhone" and st["idioma"] == "pt"
    assert cl.get("/m/api/canais").json()[0]["slug"] == "teste"
    assert cl.get("/m/api/canais/teste/projetos").json()[0]["titulo"] == "Podcast 12"
    assert any(e["padrao"] for e in cl.get("/m/api/canais/teste/estilos").json())
    det = cl.get(f"/m/api/canais/teste/projetos/{p.id}").json()
    assert [c["id"] for c in det["candidatos"]] == ["c01", "c02"] and det["candidatos"][0]["titulo"] == "O erro de 500 mil"

    base = f"/m/api/canais/teste/projetos/{p.id}"
    assert cl.post(f"{base}/aprovar", json={"ids": ["c01"]}).status_code == 403  # sem o cabeçalho
    assert cl.post(f"{base}/aprovar", json={"ids": []}, headers=H).status_code == 400
    assert cl.post(f"{base}/aprovar", json={"ids": ["nao-existe"]}, headers=H).status_code == 404
    r = cl.post(f"{base}/aprovar", json={"ids": ["c01"]}, headers=H).json()
    assert len(r["clips"]) == 1 and r["job"]
    assert rodou.wait(5)
    det = cl.get(base).json()
    assert det["candidatos"][0]["clip"] == r["clips"][0] and det["clips"][0]["saida"] is False


def test_celular_assiste_e_baixa_o_clip(ambiente):
    _, rem, app, p = ambiente
    p.salvar_clip(Clip(id="01-erro", inicio=10, fim=50, titulo="O erro"))
    cl = pareado(rem, app)
    base = f"/m/api/canais/teste/projetos/{p.id}/clips/01-erro/video"
    assert cl.get(base).status_code == 404  # ainda não gerado
    (p.clips_dir / "01-erro" / "saida.mp4").write_bytes(b"0123456789")
    r = cl.get(base, headers={"Range": "bytes=2-5"})
    assert r.status_code == 206 and r.content == b"2345"  # o player do celular pede por partes
    r = cl.get(base, params={"baixar": "true"})
    assert r.content == b"0123456789" and "attachment" in r.headers["content-disposition"]


def test_previa_do_corte_vem_do_video_original(ambiente):
    _, rem, app, p = ambiente
    cl = pareado(rem, app)
    base = f"/m/api/canais/teste/projetos/{p.id}"
    assert cl.get(base).json()["tem_video"] is False
    assert cl.get(f"{base}/video-original").status_code == 404
    p.fonte_dir.mkdir(parents=True, exist_ok=True)
    (p.fonte_dir / "video.mp4").write_bytes(bytes(range(100)))
    assert cl.get(base).json()["tem_video"] is True
    r = cl.get(f"{base}/video-original", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and r.content == bytes(range(10, 20)) and r.headers["content-type"] == "video/mp4"
    assert TestClient(app, client=CASA).get(f"{base}/video-original").status_code == 401  # sem pareamento


def test_previa_do_short_traz_legenda_e_cartela_do_estilo(ambiente):
    _, rem, app, p = ambiente
    write_json(p.transcricao_path, {"segmentos": [{"inicio": 9, "fim": 52, "texto": "", "palavras": [
        {"texto": "antes", "inicio": 9.0, "fim": 9.5}, {"texto": "Ninguém", "inicio": 10.2, "fim": 10.6},
        {"texto": "te", "inicio": 10.6, "fim": 10.8}, {"texto": "conta", "inicio": 10.8, "fim": 11.3},
        {"texto": "depois", "inicio": 50.5, "fim": 51.0}]}]})
    cl = pareado(rem, app)
    base = f"/m/api/canais/teste/projetos/{p.id}/candidatos"
    d = cl.get(f"{base}/c01/previa").json()
    assert d["vertical"] is True and d["inicio"] == 10 and d["fim"] == 50 and 0 <= d["rosto_x"] <= 1
    assert [w["t"] for w in d["palavras"]] == ["Ninguém", "te", "conta"]  # só as faladas dentro do corte
    leg = d["legenda"]
    assert leg["modo"] and leg["tamanho"] > 0 and 0 < leg["altura"] < 1 and leg["por_linha"] >= 1
    assert d["titulo"] == "O erro de 500 mil" and "duracao" in d["cartela"]
    for arquivo in d["fontes"].values():  # as fontes do estilo vêm do próprio PC
        assert cl.get(f"/m/fonte/{arquivo}").status_code == 200
    assert cl.get(f"{base}/nao-existe/previa").status_code == 404
    assert TestClient(app, client=CASA).get(f"{base}/c01/previa").status_code == 401


def test_fonte_so_para_celular_pareado_e_so_da_pasta_de_fontes(ambiente):
    from clipator.workspace import fontes_dir

    _, rem, app, _ = ambiente
    fonte = next(iter(sorted(fontes_dir().glob("*.ttf"))), None)
    if fonte is None:
        pytest.skip("sem fontes embutidas")
    assert TestClient(app, client=CASA).get(f"/m/fonte/{fonte.name}").status_code == 401
    cl = pareado(rem, app)
    r = cl.get(f"/m/fonte/{fonte.name}")
    assert r.status_code == 200 and r.content == fonte.read_bytes()
    assert cl.get("/m/fonte/remoto.json").status_code == 404
    assert cl.get("/m/fonte/..%2F..%2Fapi.py").status_code == 404
    assert cl.get("/m/fonte/nao-existe.ttf").status_code == 404


def test_fonte_do_estilo_pelo_nome():
    from clipator.remoto_previa import arquivo_fonte

    f = arquivo_fonte("Montserrat ExtraBold")
    assert f is None or f.name == "Montserrat-ExtraBold.ttf"
    assert arquivo_fonte("") is None and arquivo_fonte("Fonte Que Nao Existe") is None


def test_novo_video_so_por_link(ambiente):
    srv, rem, app, _ = ambiente
    srv.fila.registrar("analisar", lambda params, ctx: None)
    cl = pareado(rem, app)
    url = "/m/api/canais/teste/projetos"
    assert cl.post(url, json={"link": "C:/Users/fulano/segredo.mp4"}, headers=H).status_code == 400
    assert cl.post(url, json={"link": "https://exemplo.com/video"}, headers=H).status_code == 400
    r = cl.post(url, json={"link": "https://www.youtube.com/watch?v=zyxwvutsrqp"}, headers=H).json()
    assert r["id"] and r["job"]


def test_api_remota_nao_tem_as_rotas_do_app(ambiente):
    _, rem, app, _ = ambiente
    cl = pareado(rem, app)
    for metodo, rota in (("get", "/api/config"), ("get", "/api/arquivo?caminho=.clipator/config.yaml"),
                         ("get", "/api/midia?caminho=x"), ("put", "/api/arquivo"), ("delete", "/api/canais/teste"),
                         ("get", "/docs"), ("get", "/openapi.json")):
        assert getattr(cl, metodo)(rota, headers=H).status_code in (404, 405), rota


def test_sair_desconecta_o_celular(ambiente):
    _, rem, app, _ = ambiente
    cl = pareado(rem, app)
    assert cl.post("/m/api/sair", headers=H).json() == {"ok": True}
    assert rem.aparelhos() == [] and cl.get("/m/api/estado").status_code == 401


# ---- pelo app do PC -----------------------------------------------------------------------------
def test_app_do_pc_liga_gera_qr_e_desliga(tmp_path, monkeypatch):
    from clipator.api import criar_app
    from clipator.service import Servico

    monkeypatch.setattr(remoto, "info_tailscale", lambda: {"instalado": True, "ip": "100.80.1.2", "nome": "pc.tail.ts.net"})
    monkeypatch.setattr(remoto, "_ip_da_rede", lambda: "192.168.0.10")
    srv = Servico(tmp_path / "ws")
    app = criar_app(srv, token="t")
    cl = TestClient(app)
    h = {"x-clipator-token": "t"}
    assert cl.get("/api/remoto").status_code == 401  # sem o token do app
    st = cl.get("/api/remoto", headers=h).json()
    assert st["ligado"] is False and st["enderecos"] == []  # desligado por padrão
    assert cl.post("/api/remoto/codigo", headers=h).status_code == 409

    import socket

    with socket.socket() as s:  # uma porta livre para o teste
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    rem = app.state.remoto
    rem.host = "127.0.0.1"  # no teste não abre para a rede
    st = cl.post("/api/remoto/ligar", json={"porta": porta}, headers=h).json()
    try:
        assert st["ligado"] and st["porta"] == porta and [e["tipo"] for e in st["enderecos"]] == ["tailscale", "wifi"]
        cod = cl.post("/api/remoto/codigo", headers=h).json()
        assert cod["links"][0]["link"] == f"http://100.80.1.2:{porta}/#parear={cod['codigo']}"
        assert cod["links"][0]["qr"].startswith("data:image/svg+xml")

        import httpx

        r = httpx.post(f"http://127.0.0.1:{porta}/m/api/parear", json={"codigo": cod["codigo"], "nome": "Pixel"}, headers=H)
        assert r.status_code == 200
        ap = cl.get("/api/remoto", headers=h).json()["aparelhos"]
        assert [a["nome"] for a in ap] == ["Pixel"]
        assert cl.delete(f"/api/remoto/aparelhos/{ap[0]['id']}", headers=h).json()["aparelhos"] == []
    finally:
        st = cl.post("/api/remoto/desligar", headers=h).json()
    assert st["ligado"] is False and rem.quer_ligado is False
    srv.fila.fechar()


def test_capa_do_short_sai_em_pe(ambiente, video_teste):
    import shutil

    from PIL import Image

    _, rem, app, p = ambiente
    write_json(p.candidatos_path, [{"id": "c01", "inicio": 2, "fim": 10, "duracao": 8, "nota": 70, "modo": "curto"}])
    p.fonte_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(video_teste, p.fonte_dir / "video.mp4")
    cl = pareado(rem, app)
    r = cl.get(f"/m/api/canais/teste/projetos/{p.id}/candidatos/c01/quadro", params={"vertical": "true"})
    assert r.status_code == 200
    with Image.open(p.analise_dir / "quadros" / "c01_vertical.jpg") as img:
        w, h = img.size
    assert abs(w / h - 9 / 16) < 0.02  # o mesmo recorte 9:16 do short
