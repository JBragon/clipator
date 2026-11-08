"""Thumbnails por código e skills do usuário."""

from __future__ import annotations

import zipfile

import pytest

from clipator import pipeline, skills, thumbs
from clipator.models import Clip, Origem, Thumb
from clipator.workspace import write_json

from .conftest import precisa_ffmpeg, transcricao_falsa


# ---- thumbnails ---------------------------------------------------------------
def test_frase_local_quebra_e_destaca():
    linhas, dest = thumbs.frase_local("Ele PERDEU 500 mil em um ano investindo errado", "", 4)
    assert 2 <= len(linhas) <= 4
    assert all(len(ln.split()) <= 4 for ln in linhas)
    assert "PERDEU" in dest and "500" in dest


def test_fontes_embutidas_por_nome():
    assert thumbs.caminho_fonte("Anton").name == "Anton-Regular.ttf"
    assert thumbs.caminho_fonte("Montserrat ExtraBold").name == "Montserrat-ExtraBold.ttf"
    assert thumbs.caminho_fonte("Fonte Que Nao Existe") is None


@pytest.mark.parametrize("tamanho", [(1280, 720), (1080, 1920), (1080, 1350)])
@pytest.mark.parametrize("layout", ["rosto-frase", "frase-gancho", "moldura", "rosto-grande"])
def test_layouts_no_tamanho_do_formato_com_destaque(layout, tamanho):
    from PIL import Image

    quadro = Image.new("RGB", (640, 360), (40, 90, 160))
    cfg = Thumb(cor_destaque="#00FF00", cor_borda="#FF0000")
    img = thumbs.desenhar(layout, quadro, (0.5, 0.4, 0.05), ["O ERRO", "QUE CUSTOU", "TUDO"], ["TUDO"], cfg,
                          thumbs.caminho_fonte("Anton"), tamanho)
    assert img.size == tamanho
    cores = {c for _, c in img.getcolors(1 << 20)}
    assert (0, 255, 0) in cores  # palavra destacada
    assert img.getpixel((2, 2)) == (255, 0, 0)  # borda do canal
    if tamanho[1] > tamanho[0]:  # no Shorts, nada de texto destacado na faixa de baixo que o app cobre
        faixa = img.crop((20, int(tamanho[1] * 0.86), tamanho[0] - 20, tamanho[1] - 20))
        assert (0, 255, 0) not in {c for _, c in faixa.getcolors(1 << 20)}


def test_tamanho_da_thumb_segue_o_formato():
    assert thumbs.tamanho_thumb("9:16") == (1080, 1920)
    assert thumbs.tamanho_thumb("16:9") == (1280, 720)
    assert thumbs.tamanho_thumb("4:5") == (1080, 1350)
    assert thumbs.tamanho_thumb(None) == (1280, 720)


TRECHO = ("Eu perdi 500 mil reais em um ano investindo errado. Ninguém me avisou do risco da corretora. "
          "Depois disso o Marcos me ensinou a diversificar a carteira inteira.")
FORA = "O campeonato de futebol acabou empatado em 3 a 3 na final."


def test_frases_locais_so_usam_o_que_foi_dito_no_corte():
    frases = thumbs.frases_locais(TRECHO, "O ERRO que custou caro", 4)
    tipos = [f.tipo for f in frases]
    assert tipos.count("insight") >= 2 and tipos.count("sensacionalista") >= 2
    palavras_fora = {"campeonato", "futebol", "empatado", "final"}
    for f in frases:
        assert thumbs.apoiada(f, TRECHO), f
        texto = " ".join(f.linhas).lower()
        assert not any(p in texto for p in palavras_fora)
    assert any("500" in " ".join(f.linhas) for f in frases)  # o número dito vira gancho


def test_frases_da_ia_sem_prova_no_corte_sao_descartadas():
    resposta = {"frases": [
        {"tipo": "insight", "linhas": ["PERDEU 500 MIL", "EM UM ANO"], "destaques": ["500"],
         "prova": "perdi 500 mil reais em um ano"},
        {"tipo": "sensacionalista", "linhas": ["ELE PERDEU", "1 MILHÃO!"], "destaques": ["1"],
         "prova": "perdi 500 mil reais em um ano"},  # número inventado
        {"tipo": "sensacionalista", "linhas": ["PRESO PELA", "POLÍCIA"], "destaques": [],
         "prova": "foi preso pela polícia"},  # prova que não está no corte
        {"tipo": "sensacionalista", "linhas": ["A FINAL", "EMPATOU"], "destaques": [],
         "prova": FORA},  # fala de fora do corte
        {"tipo": "sensacionalista", "linhas": ["NINGUÉM AVISOU", "DO RISCO!"], "destaques": ["RISCO"],
         "prova": "Ninguém me avisou do risco da corretora."},
    ]}
    ok = thumbs.frases_da_ia(resposta, TRECHO, 4)
    assert [" / ".join(f.linhas) for f in ok] == ["PERDEU 500 MIL / EM UM ANO", "NINGUÉM AVISOU / DO RISCO!"]
    completas = thumbs.completar(ok, thumbs.frases_locais(TRECHO, "", 4))
    assert [f.tipo for f in completas].count("sensacionalista") >= 2


@precisa_ffmpeg
def test_gerar_thumbs_sem_ia(ws, video_teste, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("CLIPATOR_CLAUDE", "/nao/existe/claude")
    c = ws.criar_canal("Teste")
    assert (c.arquivo("thumb.md")).exists()
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    from clipator import ingest

    ingest.importar_arquivo(video_teste, p)
    write_json(p.transcricao_path, transcricao_falsa(duracao=13))
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=9, titulo="O ERRO que custou quinhentos mil", formato="9:16"))
    info = thumbs.gerar(p, "01-x", usar_ia=True)
    assert info["fonte_frase"] == "local" and info["linhas"] and info["tamanho"] == [1080, 1920]
    tipos = {d["tipo"] for d in info["detalhes"].values()}
    assert tipos == {"insight", "sensacionalista"}
    n = len(info["frases"]) * 4
    assert len(info["quadros"]) == 3 and len(info["variacoes"]) == n
    pasta = p.clips_dir / "01-x"
    with Image.open(pasta / "thumb.png") as im:
        assert im.size == (1080, 1920)  # short: thumb vertical
    outra = next(v for v in info["variacoes"] if v.startswith("sensacionalista-1-moldura"))
    thumbs.escolher(p, "01-x", outra)
    assert (pasta / "thumb.png").read_bytes() == (pasta / "thumbs" / outra).read_bytes()
    with pytest.raises(FileNotFoundError):
        thumbs.escolher(p, "01-x", "../clip.yaml")
    lista = thumbs.listar(p, "01-x")
    assert lista["escolhida"] and len(lista["variacoes"]) == n

    clip, _ = p.clip("01-x")
    clip.formato = "16:9"
    p.salvar_clip(clip)
    info = thumbs.gerar(p, "01-x", usar_ia=True)
    with Image.open(pasta / "thumb.png") as im:
        assert im.size == (1280, 720)  # mudou o formato: a escolhida acompanha
    assert len(thumbs.listar(p, "01-x")["variacoes"]) == len(info["variacoes"])


# ---- skills -------------------------------------------------------------------
def _skill(raiz, nome="titulos-curtos", tipos=("titulos", "estilo"), manifesto=True):
    d = raiz / nome
    (d / "estilos").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: Títulos curtos\n---\nSempre use no máximo 4 palavras no título.\n", encoding="utf-8")
    (d / "estilos" / "neon.md").write_text("---\nnome: Neon\nformato: \"9:16\"\nlegenda:\n  cor: \"#00FFFF\"\n---\n",
                                           encoding="utf-8")
    if manifesto:
        (d / "clipator-skill.yaml").write_text(
            f"nome: Títulos curtos\nautor: Ana\nversao: 1.2.0\nlicenca: MIT\npreco: gratis\ntipos: [{', '.join(tipos)}]\n",
            encoding="utf-8")
    return d


def test_skill_instalar_ativar_por_canal(ws, tmp_path):
    a, b = ws.criar_canal("Canal A"), ws.criar_canal("Canal B")
    s = skills.instalar_pasta(_skill(tmp_path / "src"))
    assert s.id == "titulos-curtos" and s.estilos == ["neon"]
    assert any("estilo" in r for r in s.resumo())
    assert [x.id for x in skills.listar(ws)[0] if x.origem != "embutida"] == ["titulos-curtos"]
    assert "neon" not in ws.estilos(a)  # instalada, mas ainda não ativa
    skills.ativar(ws, "titulos-curtos", "canal", "canal-a")
    assert "neon" in ws.estilos(a) and "neon" not in ws.estilos(b)
    assert ws.carregar_estilo("neon", a)[0].legenda.cor == "#00FFFF"
    assert "4 palavras" in skills.texto_para_ia(ws, "titulos", "canal-a")
    assert "4 palavras" not in skills.texto_para_ia(ws, "titulos", "canal-b")  # só as embutidas valem lá
    assert "4 palavras" not in skills.texto_para_ia(ws, "ranking", "canal-a")  # a do usuário é só de títulos
    # o contexto da IA do projeto leva a skill
    p = a.criar_projeto("v")
    _, _, tmd = pipeline._contexto_com_skills(p)
    assert "4 palavras" in tmd
    skills.desativar(ws, "titulos-curtos")
    assert ws.config().skills == []
    with pytest.raises(skills.SkillError):
        skills.instalar_pasta(_skill(tmp_path / "src2"))  # já instalada
    skills.remover(ws, "titulos-curtos")
    assert [x for x in skills.listar(ws)[0] if x.origem != "embutida"] == []


def test_skill_zip_ida_e_volta_e_zip_inseguro(ws, tmp_path):
    skills.instalar_pasta(_skill(tmp_path / "src"))
    z = skills.exportar_zip(ws, "titulos-curtos", tmp_path)
    assert z.name == "titulos-curtos-1.2.0.zip"
    novas = skills.instalar_zip(z, substituir=True)
    assert [s.id for s in novas] == ["titulos-curtos"]
    ruim = tmp_path / "ruim.zip"
    with zipfile.ZipFile(ruim, "w") as zf:
        zf.writestr("../fora.txt", "x")
        zf.writestr("SKILL.md", "oi")
    with pytest.raises(skills.SkillError, match="inseguro"):
        skills.instalar_zip(ruim)
    assert not (tmp_path / "fora.txt").exists()
    vazio = tmp_path / "vazio.zip"
    with zipfile.ZipFile(vazio, "w") as zf:
        zf.writestr("leia.txt", "x")
    with pytest.raises(skills.SkillError, match="SKILL.md"):
        skills.instalar_zip(vazio)


def test_skill_sem_manifesto_e_manifesto_invalido(ws, tmp_path):
    s = skills.ler_skill(_skill(tmp_path / "a", manifesto=False))
    assert set(s.manifesto.tipos) == {"fluxo", "estilo"} and s.avisos
    d = _skill(tmp_path / "b", tipos=("magica",))
    with pytest.raises(skills.SkillError, match="tipos"):
        skills.ler_skill(d)


def test_pasta_extra_de_skills(ws, tmp_path):
    raiz = tmp_path / "SKILLS"
    _skill(raiz, "uma")
    _skill(raiz, "outra", tipos=("ranking",))
    cfg = ws.config()
    cfg.pastas_skills = [str(raiz)]
    ws.salvar_config(cfg)
    lista, erros = skills.listar(ws)
    assert {s.origem for s in lista} == {"pasta-extra", "embutida"} and not erros
    with pytest.raises(skills.SkillError):
        skills.remover(ws, lista[0].id)


def test_skill_editada_aparece_sem_reiniciar(ws, tmp_path, monkeypatch):
    """A lista guarda as skills lidas, mas a edição, o erro e o conserto têm que valer na hora."""
    d = _skill(tmp_path / "extras")
    cfg = ws.config()
    cfg.pastas_skills = [str(tmp_path / "extras")]
    ws.salvar_config(cfg)
    assert any(s.id == "titulos-curtos" for s in skills.listar(ws)[0])

    leituras = []
    original = skills.ler_skill
    monkeypatch.setattr(skills, "ler_skill", lambda *a, **k: leituras.append(a[0]) or original(*a, **k))
    skills.listar(ws)
    assert d not in leituras  # nada mudou: não relê

    (d / "SKILL.md").write_text("---\nname: Títulos curtos\n---\nAgora no máximo 3 palavras no título.\n", encoding="utf-8")
    assert "3 palavras" in next(s for s in skills.listar(ws)[0] if s.id == "titulos-curtos").instrucoes

    (d / "estilos" / "novo.md").write_text("---\nnome: Novo\n---\n", encoding="utf-8")
    assert "novo" in next(s for s in skills.listar(ws)[0] if s.id == "titulos-curtos").estilos

    (d / "SKILL.md").unlink()
    lista, erros = skills.listar(ws)
    assert not any(s.id == "titulos-curtos" for s in lista)


def test_link_github():
    assert skills.ler_link_github("https://github.com/ana/skills") == ("ana", "skills", None, "")
    assert skills.ler_link_github("https://github.com/ana/skills/tree/main/titulos/curtos") == ("ana", "skills", "main", "titulos/curtos")
    with pytest.raises(skills.SkillError):
        skills.ler_link_github("https://gitlab.com/ana/skills")


def test_api_skills_e_thumbs(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    cli = TestClient(criar_app(srv, "t"))
    h = {"x-clipator-token": "t"}
    origem = _skill(tmp_path / "src")
    r = cli.post("/api/skills/importar", json={"origem": str(origem)}, headers=h)
    assert r.status_code == 200 and r.json()["skills"][0]["id"] == "titulos-curtos"
    assert cli.post("/api/skills/importar", json={"origem": str(origem)}, headers=h).status_code == 400
    assert cli.post("/api/skills/titulos-curtos/ativar", json={"escopo": "global"}, headers=h).json()["ok"]
    lst = cli.get("/api/skills", headers=h).json()
    assert next(x for x in lst["skills"] if x["id"] == "titulos-curtos")["ativacoes"] == [{"skill": "titulos-curtos", "escopo": "global"}]
    estilos = {e["id"]: e for e in cli.get("/api/estilos", headers=h).json()}
    assert estilos["neon"]["skill"] and not estilos["neon"]["embutido"] and estilos["impacto"]["embutido"]
    assert cli.delete("/api/skills/titulos-curtos", headers=h).status_code == 409
    assert cli.delete("/api/skills/titulos-curtos", params={"confirmar": True}, headers=h).json()["ok"]
    srv.fila.fechar()
