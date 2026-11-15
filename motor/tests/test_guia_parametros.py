"""Guia dos parâmetros nos arquivos de regras-e-textos/: cobre cada chave e nunca vai para a IA."""

from __future__ import annotations

import pytest

from clipator import markdown as md
from clipator.models import Canal, Pesos, Regras, Thumb
from clipator.workspace import PASTA_TEXTOS, modelo_canal_dir

GUIAS = {
    "regras.md": [*Regras.model_fields, *Pesos.model_fields],
    "thumb.md": list(Thumb.model_fields),
    "canal.md": list(Canal.model_fields),
    "titulos.md": ["temperatura", "formulas", "formulas_por_temperatura", "palavras_gatilho", "nunca_usar",
                   "max_caracteres", "caixa_alta_total", "palavras_caixa_alta", "emojis"],
}


@pytest.mark.parametrize("arquivo", [*GUIAS, "referencias.md"])
def test_modelo_do_canal_tem_o_guia(arquivo):
    corpo = md.read(modelo_canal_dir() / arquivo).body
    assert "<!-- GUIA" in corpo and corpo.rstrip().endswith("-->")


@pytest.mark.parametrize("arquivo", list(GUIAS))
def test_guia_explica_todas_as_chaves(arquivo):
    corpo = md.read(modelo_canal_dir() / arquivo).body
    guia = corpo[corpo.index("<!-- GUIA"):]
    faltando = [k for k in GUIAS[arquivo] if k not in guia]
    assert not faltando, f"{arquivo}: o guia não explica {faltando}"


def test_sem_comentarios():
    assert md.sem_comentarios("Regra A.\n\n<!-- guia\nlinha -->\n") == "Regra A.\n"
    assert md.sem_comentarios("a <!-- x --> b <!-- y -->").strip() == "a  b"
    assert md.sem_comentarios("sem comentário") == "sem comentário"


def test_guia_fica_no_arquivo_mas_nao_vai_para_a_ia(ws):
    c = ws.criar_canal("Canal Guia")
    textos = c.path / PASTA_TEXTOS
    for arq in (c.path / "canal.md", *(textos / n for n in ("regras.md", "titulos.md", "thumb.md", "referencias.md"))):
        assert "GUIA DOS PAR" in arq.read_text(encoding="utf-8") or "GUIA DO " in arq.read_text(encoding="utf-8"), arq
    corpos = [c.info()[1], c.regras()[1], c.titulos()[1], c.thumb()[1], c.referencias()]
    for corpo in corpos:
        assert "GUIA" not in corpo and "<!--" not in corpo
    assert "Regras livres para a IA" in c.regras()[1]
    assert "temperatura: auto" in c.titulos()[1]
    regras, _ = c.regras()
    assert regras.duracao_min == 40 and regras.duracao_ideal == 90
