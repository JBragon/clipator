"""Câmera do seguir-rosto: acompanha o locutor com movimento suave, parada quando ele está parado, corte seco em
troca de cena ou de pessoa, e a tela dividida com cada metade acompanhando a própria pessoa."""

from __future__ import annotations

import numpy as np

from clipator import reframe, render
from clipator.models import Estilo

R = reframe.Rosto
W, H = 1920, 1080
CW, CH = reframe.tamanho_crop(W, H, 1080, 1920)
POR_S = 8


def _amostras(rostos_em, fim=12.0, por_s=POR_S):
    return [(i / por_s, list(rostos_em(i / por_s))) for i in range(int(fim * por_s))]


def _xs(cmd: str) -> list[tuple[float, int]]:
    out = []
    for linha in cmd.strip().splitlines():
        t, _, _, x = linha.rstrip(";").split()
        out.append((float(t), int(x)))
    return out


def _x_no_tempo(xs: list[tuple[float, int]], t: float) -> int:
    return [x for tt, x in xs if tt <= t + 1e-6][-1]


def _quadros(traj, fps=30):
    """x do crop (px da saída 1080x1920) em cada quadro, como o FFmpeg aplica: o último comando antes do quadro."""
    cantos = reframe.cantos_camera(traj, W, CW)
    m = reframe.movel(cantos, [0], CW, CH, W, H, 1080, 1920)
    cmds = [(float(l.split()[0]), int(l.split()[3].rstrip(";,"))) for l in
            m.comandos([(t, (x, 0), p) for (t, _, p), x in zip(traj, cantos)], "cam", fps).strip().splitlines()]
    n = int(traj[-1][0] * fps) + 1
    return [[x for t, x in cmds if t <= f / fps][-1] for f in range(n)]


def test_panoramica_lenta_anda_em_todo_quadro_sem_engasgar():
    # rosto andando devagar (3% da largura por segundo): a câmera tem que andar em todo quadro, de 1 a 2 px
    am = _amostras(lambda t: [R(0.3 + 0.03 * t, 0.4, 0.02)], fim=8)
    xs = _quadros(reframe.trajetoria(am, largura_crop=CW / W))
    v = np.diff(xs[60:180])  # do segundo 2 ao 6, já em velocidade de cruzeiro
    assert (v >= 1).all() and v.max() <= 4


def test_troca_de_pessoa_sem_atraso():
    # o locutor sai do quadro aos 4 s e a outra pessoa fica: o corte é no instante em que ele sumiu, não 0,8 s depois
    am = _amostras(lambda t: [R(0.2, 0.4, 0.02), R(0.8, 0.4, 0.012)] if t < 4 else [R(0.8, 0.4, 0.012)])
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    pulos = [p for _, _, p in traj if p is not None]
    assert len(pulos) == 1 and abs(pulos[0] - 4.0) < 0.2


def test_acompanha_quem_anda_sem_degraus_nem_vai_e_vem():
    # o locutor anda de 30% a 70% da largura em 8 s e para
    am = _amostras(lambda t: [R(0.3 + 0.4 * min(t, 8) / 8, 0.4, 0.02)])
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    assert abs(traj[-1][1] - 0.7) < reframe.FOLGA * CW / W + 0.005  # chegou junto
    xs = _xs(reframe.comandos_sendcmd(traj, W, CW, fps=30))
    passos = np.diff([x for _, x in xs])
    assert len(xs) > 100  # muda quadro a quadro, não a cada amostra
    assert (passos >= 0).all()  # só vai para a direita: sem vai e vem
    assert np.abs(passos).max() <= 16  # nenhum salto: no máximo ~16 px num quadro de 1920
    assert abs(_x_no_tempo(xs, 11.5) + CW / 2 - 0.7 * W) < 0.07 * CW  # o rosto termina centrado


def test_parado_nao_treme_e_ignora_falso_positivo():
    rng = np.random.default_rng(1)
    ruido = {i: 0.5 + rng.normal(0, 0.004) for i in range(12 * POR_S)}
    am = [(t, [R(ruido[i], 0.4, 0.02)] if i != 30 else [R(0.1, 0.4, 0.03)]) for i, (t, _) in enumerate(_amostras(lambda t: []))]
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    xs = _xs(reframe.comandos_sendcmd(traj, W, CW, fps=30))
    assert max(x for _, x in xs) - min(x for _, x in xs) <= 4  # a câmera fica parada


def test_corte_de_cena_e_seco():
    am = _amostras(lambda t: [R(0.3 if t < 5 else 0.7, 0.4, 0.02)])
    traj = reframe.trajetoria(am, cortes_cena=[5.0], largura_crop=CW / W)
    assert [p for _, _, p in traj if p is not None] == [5.0]
    xs = _xs(reframe.comandos_sendcmd(traj, W, CW, fps=30))
    antes, depois = _x_no_tempo(xs, 4.97), _x_no_tempo(xs, 5.0)
    assert abs(antes + CW / 2 - 0.3 * W) < 4 and abs(depois + CW / 2 - 0.7 * W) < 4  # sem deslizar pelo corte


def test_duas_pessoas_do_mesmo_tamanho_nao_fazem_a_camera_ir_e_voltar():
    # o detector alterna qual rosto parece maior a cada amostra
    am = _amostras(lambda t: [R(0.3, 0.4, 0.020 + 0.002 * (int(t * POR_S) % 2)), R(0.7, 0.4, 0.021)])
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    cxs = [cx for _, cx, _ in traj]
    assert max(cxs) - min(cxs) < 0.01


def test_troca_de_pessoa_quando_o_locutor_some_ou_outro_domina():
    # some aos 4 s e só a outra pessoa fica: troca com corte seco depois de ~0,8 s
    am = _amostras(lambda t: [R(0.25, 0.4, 0.02)] + ([R(0.75, 0.4, 0.015)] if t >= 2 else []) if t < 4 else [R(0.75, 0.4, 0.015)])
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    pulos = [p for _, _, p in traj if p is not None]
    assert len(pulos) == 1 and 4.0 <= pulos[0] <= 4.3  # no instante em que ele sumiu
    assert traj[-1][1] > 0.7
    # outra pessoa bem maior (close) por mais de 1,5 s: troca
    am = _amostras(lambda t: [R(0.25, 0.4, 0.01)] + ([R(0.75, 0.4, 0.05)] if t >= 3 else []))
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    assert traj[int(2 * POR_S)][1] < 0.3 and traj[-1][1] > 0.7


def test_sem_rosto_segura_a_posicao():
    am = _amostras(lambda t: [R(0.7, 0.4, 0.02)] if t < 3 or t > 9 else [])
    traj = reframe.trajetoria(am, largura_crop=CW / W)
    assert all(abs(cx - 0.7) < 0.01 for _, cx, _ in traj)
    assert reframe.trajetoria([]) == [(0.0, 0.5, None)]


def test_rosto_no_quadro_usa_quem_a_camera_segue():
    am = _amostras(lambda t: [R(0.2, 0.4, 0.01), R(0.8, 0.4, 0.03)])
    traj = [(t, 0.2, None) for t, _ in am]  # a câmera seguiu a pessoa da esquerda
    cx, _, _ = reframe.rosto_no_quadro(am, traj, W, H, CW, CH, 0)
    assert abs(cx - 0.5) < 0.05


def test_tela_dividida_cada_metade_acompanha_a_sua_pessoa():
    # a pessoa da esquerda se inclina para a direita; a da direita fica parada
    am = _amostras(lambda t: [R(0.25 + 0.06 * min(t, 6) / 6, 0.40, 0.012), R(0.72, 0.42, 0.010)])
    d = reframe.enquadramento_dividido(am, W, H, 1080, 960, 12.0)
    assert d is not None and len(d.trilhas) == 2
    cima, baixo = d.trilhas
    c0, c1 = d.caixas
    assert cima[-1][1] - cima[0][1] > 0.04 * W  # o recorte de cima andou junto
    assert max(x for _, x, _, _ in baixo) - min(x for _, x, _, _ in baixo) < 2  # o de baixo ficou parado
    for trilha, c in ((cima, c0), (baixo, c1)):
        for _, x, y, _ in trilha:
            assert 0 <= x <= W - c.w and 0 <= y <= H - c.h
            assert abs(x - c.x) <= 0.35 * c.w + 1  # não invade o lado da outra pessoa
    m = reframe.movel([x for _, x, _, _ in cima], [y for _, _, y, _ in cima], c0.w, c0.h, W, H, 1080, 960)
    cmd = m.comandos([(t, (x, y), p) for t, x, y, p in cima], "cima", fps=30)
    assert cmd.splitlines()[0].startswith("0.0000 crop@cima x ")
    assert m.ex <= min(x for _, x, _, _ in cima) and max(x for _, x, _, _ in cima) + c0.w <= m.ex + m.ew


def test_cadeia_da_tela_dividida_com_movimento(tmp_path):
    am = _amostras(lambda t: [R(0.28, 0.40, 0.012), R(0.72, 0.42, 0.010)])
    d = reframe.enquadramento_dividido(am, W, H, 1080, 960, 12.0)
    cmd = tmp_path / "camera.cmd"
    moveis = tuple(reframe.movel([x for _, x, _, _ in tr], [y for _, _, y, _ in tr], c.w, c.h, W, H, 1080, 960)
                   for tr, c in zip(d.trilhas, d.caixas))
    g = render._cadeia_layout(Estilo(), "dividido", W, H, 1080, 1920, cmd, 0, d, None, moveis)
    assert g.startswith("[vin]sendcmd=") and "split=2" in g  # um sendcmd só, antes de dividir, move os dois recortes
    assert "crop@cima=" in g and "crop@baixo=" in g and ":exact=1" in g
    # sem arquivo de comandos, os recortes ficam parados nas caixas
    g = render._cadeia_layout(Estilo(), "dividido", W, H, 1080, 1920, None, 0, d)
    c = d.caixas[0]
    assert "sendcmd" not in g and f"crop@cima=w={c.w}:h={c.h}:x={c.x}:y={c.y}" in g


def test_tela_dividida_nao_corta_a_cabeca_de_quem_aparece_mais_alto():
    from clipator import render

    hb = 960
    sem = render.enquadrar_rosto((0.5, 0.5, 0.15), 1080, 1920, 1080, hb, *render.ROSTO_CORTE)
    com = render.enquadrar_rosto((0.5, 0.5, 0.15, 0.25), 1080, 1920, 1080, hb, *render.ROSTO_CORTE)
    assert com[3] < sem[3] and com[3] <= 0.25 * com[1]  # a caixa desce até o alto da cabeça mais alta caber
    # com zoom, cabeças em alturas muito diferentes tiram zoom em vez de deixar o rosto do meio lá embaixo
    z = render.enquadrar_rosto((0.5, 0.55, 0.06, 0.1), 1080, 1920, 1080, hb, *render.ROSTO_CORTE)
    assert z[1] == 1920 and z[3] <= 0.1 * z[1]  # sem caber com zoom: zoom 1 e as duas cabeças inteiras


def test_topo_dos_rostos_pega_a_cabeca_mais_alta_sem_ruido():
    import pytest

    am = [(k * 0.5, [reframe.Rosto(0.5, 0.5 if k % 2 else 0.35, 0.01)]) for k in range(20)]
    topo = reframe.topo_dos_rostos(am, None, 1920, 1080, 608, 1080, 656)
    assert topo == pytest.approx(0.35 - 0.8 * (0.01 * 1920 * 1080) ** 0.5 / 1080, abs=1e-3)
    assert reframe.topo_dos_rostos(am[:2], None, 1920, 1080, 608, 1080, 656) is None


def _react(fala_esq, fala_dir, fim=24.0):
    """React: o vídeo reagido à esquerda (rosto maior) e o locutor à direita, os dois sempre na imagem.
    `fala_*(t)` diz se a boca daquele lado está mexendo naquele instante."""
    def rostos(t):
        k = int(round(t * POR_S))
        mexe = lambda falando: (0.45 + 0.1 * (k % 3)) if falando else (0.05 + 0.02 * (k % 2))  # noqa: E731
        return [R(0.3, 0.4, 0.03, fala=mexe(fala_esq(t))), R(0.8, 0.4, 0.015, fala=mexe(fala_dir(t)))]
    return _amostras(rostos, fim=fim)


def _lado_em(traj, t):
    x = [cx for tt, cx, _ in traj if tt <= t + 1e-6][-1]
    return "esq" if x < 0.55 else "dir"


def test_react_a_camera_vai_para_quem_esta_falando():
    # o locutor (direita, rosto menor) fala de 0 a 4 s e de 12 a 16 s; no resto fala o vídeo reagido
    loc = lambda t: t < 4 or 12 <= t < 16  # noqa: E731
    traj = reframe.trajetoria(_react(lambda t: not loc(t), loc), largura_crop=CW / W)
    assert [_lado_em(traj, t) for t in (1, 3, 6, 10, 13, 15, 18, 22)] == ["dir", "dir", "esq", "esq", "dir", "dir", "esq", "esq"]
    # a troca chega quando a fala começa (no máximo meio segundo depois), em corte seco
    cortes = [p for _, _, p in traj if p is not None]
    assert len(cortes) == 3 and all(min(abs(c - x) for x in (4, 12, 16)) <= 0.6 for c in cortes)


def test_react_fala_curta_ou_empate_nao_faz_a_camera_ir_e_voltar():
    # o locutor solta meio segundo de "hum" no meio da fala do vídeo reagido: a câmera fica onde está
    traj = reframe.trajetoria(_react(lambda t: True if not 8 <= t < 8.5 else False, lambda t: 8 <= t < 8.5),
                              largura_crop=CW / W)
    assert {_lado_em(traj, t) for t in np.arange(1, 23, 0.5)} == {"esq"}
    # os dois mexendo a boca igual (ninguém sabe quem fala): segue a regra de sempre, sem trocar
    traj = reframe.trajetoria(_react(lambda t: True, lambda t: True), largura_crop=CW / W)
    assert all(p is None for _, _, p in traj)


def test_sem_medida_da_boca_a_escolha_e_a_de_antes():
    # MediaPipe/Haar não dão a boca: fala None e a câmera segue a regra de tamanho e presença, como sempre
    am = _amostras(lambda t: [R(0.3, 0.4, 0.03), R(0.8, 0.4, 0.015)])
    assert reframe.quem_fala(am) == [None] * len(am)
    assert {_lado_em(reframe.trajetoria(am, largura_crop=CW / W), t) for t in (1, 6, 11)} == {"esq"}


def test_boca_alinhada_pelos_marcos_do_rosto():
    cinza = np.zeros((360, 640), np.float32)
    cinza[200:215, 300:340] = 255  # a boca aberta
    marcos = [300, 160, 340, 160, 320, 185, 305, 205, 335, 205]  # olho d, olho e, nariz, boca d, boca e
    p = reframe.recorte_boca(cinza, marcos)
    assert p is not None and p.shape == (24, 32) and abs(float(p.mean())) < 1e-3
    assert reframe.recorte_boca(cinza, [0, 0, 2, 0, 1, 1, 0, 2, 2, 2]) is None  # rosto pequeno demais
    fechada = np.zeros_like(cinza)
    fechada[205:208, 300:340] = 255
    a, b = R(0.5, 0.5, 0.02, boca=p), R(0.5, 0.5, 0.02, boca=reframe.recorte_boca(fechada, marcos))
    reframe._medir_fala([b], [a])
    assert b.fala is not None and b.fala > 0.3
