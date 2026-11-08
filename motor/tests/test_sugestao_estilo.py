"""Sugestão de estilo animado pelo tema do corte (conta offline)."""

from clipator import sugestao_estilo as s


def test_tema_do_corte_escolhe_o_estilo_que_conta_melhor_a_historia():
    assert s.sugerir("comprei mais uma placa de vídeo e o chip custa caro", "Essa placa custa 100 mil")[0]["estilo"] == "arte-encaixe-vivo"
    assert s.sugerir("o data center precisa de terreno, energia elétrica e infraestrutura na cidade")[0]["estilo"] == "arte-terreno-vivo"
    assert s.sugerir("o modelo de IA foi treinado e a temperatura muda a aleatoriedade")[0]["estilo"] == "arte-pixel-em-cena"
    assert s.sugerir("o caminho das LLMs é um beco sem saída, precisa de outra estratégia", "Qual o futuro?")[0]["estilo"] == "arte-rota-em-foco"
    r = s.sugerir("tem data center nos Estados Unidos, na Islândia e no Brasil", visiveis=["arte-geo-em-cena", "arte-terreno-vivo"])
    assert [x["estilo"] for x in r] == ["arte-geo-em-cena", "arte-terreno-vivo"] and r[0]["nota"] == 1.0 and r[0]["palavras"]


def test_fala_sem_tema_cai_no_padrao_e_so_mostra_estilos_visiveis():
    assert s.sugerir("pois é, né, então")[0]["estilo"] == s.PADRAO
    assert s.sugerir("jogo", visiveis=[]) == []
    assert s.do_candidato({"texto": "o jogo online", "titulos": ["Games"]})[0]["estilo"] == "arte-pixel-em-cena"
