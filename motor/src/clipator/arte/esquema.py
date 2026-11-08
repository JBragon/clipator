"""O esquema da direção de arte (DA) do canal: o arquivo `arte/direcao.yaml`.

A DA é a fonte de verdade visual do canal. Cada estilo, cena e thumbnail lê os tokens daqui em vez de escrever
cor, fonte ou curva à mão; trocar a DA troca o visual de tudo de uma vez.

Convenções do arquivo inteiro:

- **Tamanhos são frações do lado menor do quadro** (0,06 = 65 px em 1080 de lado), para a mesma DA servir ao
  9:16, ao 1:1 e ao 16:9. Onde a fração é da altura ou da largura, o campo diz.
- **Campo de cor aceita o nome de uma cor da paleta ou um hex**: `primaria`, `texto`, `serie-2` ou `#FFB000`.
- Chaves que começam com `x_` ou `_` são anotações livres: o Clipator guarda e ignora (não mudam a identidade).
- `herda` aponta para um predefinido (`clipator arte presets`) ou para outro arquivo; o que este arquivo diz vence,
  e listas substituem a lista herdada inteira.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import cores as _cores

VERSAO_ESQUEMA = 1
NOME_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
POSICOES = ("superior_esquerda", "superior_centro", "superior_direita", "centro",
            "inferior_esquerda", "inferior_centro", "inferior_direita")
Posicao = Literal["superior_esquerda", "superior_centro", "superior_direita", "centro",
                  "inferior_esquerda", "inferior_centro", "inferior_direita"]
ENTRADAS = ("sobe", "desliza", "escala", "mascara", "fade", "digita")
SAIDAS = ("fade", "desce", "mascara", "corte")
TRANSICOES = ("corte", "fade", "empurra", "mascara", "desliza", "zoom")
CORES_OBRIGATORIAS = ("fundo", "superficie", "texto", "texto_suave", "primaria", "secundaria", "destaque",
                      "positivo", "negativo", "alerta")
PAPEIS_OBRIGATORIOS = ("titulo", "subtitulo", "corpo", "dados", "legenda")
DEGRAUS = ("display", "h1", "h2", "h3", "corpo", "nota")


class _No(BaseModel):
    """Seção do arquivo: chave desconhecida é erro (pega erro de digitação), menos as anotações `x_`/`_`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _tirar_anotacoes(cls, dados: Any) -> Any:
        if isinstance(dados, dict):
            return {k: v for k, v in dados.items() if not (isinstance(k, str) and k.startswith(("x_", "_")))}
        return dados


Cor = str  # token da paleta ("primaria", "serie-2", "neutro-1") ou "#RRGGBB"


def _nomes_de_token(mapa: dict[str, Any], onde: str) -> dict[str, Any]:
    for nome in mapa:
        if not NOME_TOKEN.match(nome) or nome.startswith("x_"):
            raise ValueError(f"{onde}: “{nome}” não serve de nome de token (use minúsculas, números e _, "
                             "sem começar por x_)")
    return mapa


# ---- conceito -----------------------------------------------------------------------------------------
class Referencia(_No):
    arquivo: str = Field(description="Imagem em arte/referencias/ (caminho relativo à pasta arte/)")
    nota: str = Field("", description="O que tirar desta referência: a cor, o jeito do texto entrar, o ritmo")


class Conceito(_No):
    frase: str = Field("", description="A DA numa frase, como briefing para um motion designer")
    palavras_chave: list[str] = Field(default_factory=list, description="4 a 8 palavras que resumem o tom")
    referencias: list[Referencia] = Field(default_factory=list)
    faca: list[str] = Field(default_factory=list, description="Regras positivas e concretas que toda peça segue")
    nao_faca: list[str] = Field(default_factory=list, description="O que quebra o estilo e a máquina não pega")


# ---- cor ----------------------------------------------------------------------------------------------
class Gradiente(_No):
    tipo: Literal["linear", "radial"] = "linear"
    angulo: float = Field(180, ge=-360, le=360, description="Graus, convenção do CSS (180 = de cima para baixo)")
    paradas: list[tuple[Cor, float]] = Field(min_length=2, description="[[cor, posição 0–1], …]")

    @field_validator("paradas")
    @classmethod
    def _posicoes(cls, v: list[tuple[str, float]]) -> list[tuple[str, float]]:
        for _, pos in v:
            if not 0 <= pos <= 1:
                raise ValueError("a posição de cada parada vai de 0 a 1")
        return v


class SecaoCor(_No):
    paleta: dict[str, str] = Field(default_factory=dict, description="Cores com nome; as dez de CORES_OBRIGATORIAS "
                                   "são obrigatórias e cores extras viram tokens também")
    neutros: list[str] = Field(default_factory=lambda: ["#000000", "#FFFFFF"],
                               description="Preto e branco de sombra e brilho: tokens neutro-1, neutro-2…")
    serie: list[Cor] = Field(default_factory=list, description="Cores dos gráficos, em ordem (serie-1, serie-2…); "
                             "no mínimo 6. Escreva o nome quando a cor é da paleta")
    gradientes: dict[str, Gradiente] = Field(default_factory=dict)

    @field_validator("paleta")
    @classmethod
    def _paleta(cls, v: dict[str, str]) -> dict[str, str]:
        _nomes_de_token(v, "cor.paleta")
        out = {}
        for nome, hexa in v.items():
            if not _cores.e_hex(hexa):
                raise ValueError(f"cor.paleta.{nome}: “{hexa}” não é hex (#RRGGBB); na paleta só entra hex")
            out[nome] = _cores.normalizar_hex(hexa)
        return out

    @field_validator("neutros")
    @classmethod
    def _neutros(cls, v: list[str]) -> list[str]:
        out = []
        for hexa in v:
            if not _cores.e_hex(hexa):
                raise ValueError(f"cor.neutros: “{hexa}” não é hex")
            out.append(_cores.normalizar_hex(hexa))
        return out

    @field_validator("gradientes")
    @classmethod
    def _grad(cls, v: dict[str, Gradiente]) -> dict[str, Gradiente]:
        return _nomes_de_token(v, "cor.gradientes")


# ---- tipografia ---------------------------------------------------------------------------------------
class Papel(_No):
    familia: str = Field(description="Nome da família, como no arquivo da fonte (Anton, Montserrat ExtraBold…)")
    reserva: str = Field("sans-serif", description="Família usada se a principal faltar (só no navegador)")
    peso: int = Field(400, ge=100, le=1000)
    italico: bool = False
    caixa_alta: bool = False
    espacamento: float = Field(0.0, ge=-0.3, le=1.0, description="letter-spacing em em; caixa alta pequena pede +0,06 a +0,15")
    entrelinha: float = Field(1.15, ge=0.6, le=3.0)
    condensar: float = Field(1.0, ge=0.3, le=2.0, description="Escala horizontal para fontes sem eixo de largura")


class SecaoTipografia(_No):
    papeis: dict[str, Papel] = Field(default_factory=dict, description="titulo, subtitulo, corpo, dados e legenda "
                                     "são obrigatórios; outros nomes podem entrar")
    escala: dict[str, float] = Field(default_factory=dict, description="Degraus de tamanho (fração do lado menor): "
                                     "display, h1, h2, h3, corpo e nota")

    @field_validator("papeis")
    @classmethod
    def _papeis(cls, v: dict[str, Papel]) -> dict[str, Papel]:
        return _nomes_de_token(v, "tipografia.papeis")

    @field_validator("escala")
    @classmethod
    def _escala(cls, v: dict[str, float]) -> dict[str, float]:
        _nomes_de_token(v, "tipografia.escala")
        for nome, f in v.items():
            if not 0 < f <= 0.6:
                raise ValueError(f"tipografia.escala.{nome}: {f} fora da faixa (maior que 0 e até 0,6 do lado menor)")
        return v


# ---- layout -------------------------------------------------------------------------------------------
class Sombra(_No):
    dx: float = Field(0.0, ge=-0.2, le=0.2)
    dy: float = Field(0.01, ge=-0.2, le=0.2)
    desfoque: float = Field(0.03, ge=0, le=0.2)
    cor: Cor = "neutro-1"
    alfa: float = Field(0.45, ge=0, le=1)


class SecaoLayout(_No):
    colunas: int = Field(12, ge=1, le=24)
    margem: float = Field(0.065, ge=0, le=0.25, description="Margem de composição (fração do lado menor)")
    calha: float = Field(0.014, ge=0, le=0.1, description="Espaço entre colunas")
    raio: float = Field(0.012, ge=0, le=0.5, description="Raio de canto padrão; 0 = tudo reto")
    traco: float = Field(0.005, ge=0, le=0.05, description="Espessura de filetes e barras")
    sombra: Sombra | None = None
    densidade: Literal["arejada", "media", "densa"] = "media"


# ---- movimento ----------------------------------------------------------------------------------------
Curva = tuple[float, float, float, float]


class SecaoMovimento(_No):
    curvas: dict[str, Curva] = Field(default_factory=dict, description="cubic-bezier [x1, y1, x2, y2] de entrada, "
                                     "saida, enfase e suave (outros nomes podem entrar)")
    duracoes: dict[str, float] = Field(default_factory=dict, description="micro, curta, media e longa, em segundos")
    escalonamento: float = Field(0.06, ge=0, le=2, description="Atraso entre itens de uma sequência")
    entrada: Literal["sobe", "desliza", "escala", "mascara", "fade", "digita"] = "sobe"
    saida: Literal["fade", "desce", "mascara", "corte"] = "fade"
    transicao_padrao: Literal["corte", "fade", "empurra", "mascara", "desliza", "zoom"] = "corte"
    transicoes: list[Literal["corte", "fade", "empurra", "mascara", "desliza", "zoom"]] = Field(
        default_factory=lambda: ["corte", "fade"])
    principios: list[str] = Field(default_factory=list, description="Regras de animação em frases executáveis")

    @field_validator("curvas")
    @classmethod
    def _curvas(cls, v: dict[str, Curva]) -> dict[str, Curva]:
        _nomes_de_token(v, "movimento.curvas")
        for nome, c in v.items():
            if not (0 <= c[0] <= 1 and 0 <= c[2] <= 1):
                raise ValueError(f"movimento.curvas.{nome}: x1 e x2 vão de 0 a 1 (é tempo)")
            if not (-2 <= c[1] <= 3 and -2 <= c[3] <= 3):
                raise ValueError(f"movimento.curvas.{nome}: y1 e y2 fora de −2 a 3")
        return v

    @field_validator("duracoes")
    @classmethod
    def _duracoes(cls, v: dict[str, float]) -> dict[str, float]:
        _nomes_de_token(v, "movimento.duracoes")
        for nome, d in v.items():
            if not 0 <= d <= 10:
                raise ValueError(f"movimento.duracoes.{nome}: {d} s fora de 0 a 10 s")
        return v


# ---- tratamento do vídeo ------------------------------------------------------------------------------
class SecaoTratamento(_No):
    aplicar_nos_clips: bool = Field(False, description="Aplica este tratamento de cor ao vídeo dos clips do canal")
    contraste: float = Field(1.0, ge=0.5, le=2.0)
    saturacao: float = Field(1.0, ge=0.0, le=3.0, description="0 = preto e branco")
    gama: float = Field(1.0, ge=0.3, le=3.0)
    brilho: float = Field(0.0, ge=-0.3, le=0.3)
    temperatura: float = Field(0.0, ge=-100, le=100, description="−100 fria … 100 quente")
    grao: float = Field(0.0, ge=0, le=40, description="Ruído de película; 3 a 6 une câmera limpa e arquivo")
    vinheta: float = Field(0.0, ge=0, le=0.8, description="Ângulo da vinheta em rad (0,3–0,45 é sutil)")
    nitidez: float = Field(0.0, ge=0, le=2.0)
    lut: str | None = Field(None, description="Arquivo .cube em arte/luts/")
    intensidade_lut: float = Field(1.0, ge=0, le=1)
    encaixe: Literal["desfocado", "recorte", "faixas"] = Field(
        "desfocado", description="Como um vídeo de outra proporção entra no quadro")


# ---- legenda ------------------------------------------------------------------------------------------
class Contorno(_No):
    cor: Cor = "neutro-1"
    espessura: float = Field(0.1, ge=0, le=0.5, description="Fração do tamanho da fonte, para fora da letra")


class SombraTexto(_No):
    dx: float = Field(0.0, ge=-1, le=1)
    dy: float = Field(0.05, ge=-1, le=1)
    desfoque: float = Field(0.08, ge=0, le=1)
    cor: Cor = "neutro-1"
    alfa: float = Field(0.6, ge=0, le=1)


class CaixaTexto(_No):
    cor: Cor = "fundo"
    alfa: float = Field(0.85, ge=0, le=1)
    raio: float = Field(0.2, ge=0, le=1, description="Fração do tamanho da fonte")
    respiro: tuple[float, float] = Field((0.35, 0.18), description="[x, y] em fração do tamanho da fonte")


class SecaoLegenda(_No):
    estilo: Literal["karaoke", "palavra", "bloco"] = "karaoke"
    papel: str = "legenda"
    tamanho: float = Field(0.058, ge=0.01, le=0.3)
    cor: Cor = "texto"
    cor_destaque: Cor = "primaria"
    cor_falada: Cor | None = None
    contorno: Contorno | None = Field(default_factory=Contorno)
    sombra: SombraTexto | None = None
    caixa: CaixaTexto | None = None
    y_vertical: float = Field(0.62, ge=0.05, le=0.95, description="Centro do bloco no 9:16 (fração da altura)")
    y_horizontal: float = Field(0.85, ge=0.05, le=0.95, description="Centro do bloco no 16:9 (fração da altura)")
    largura_max: float = Field(0.8, ge=0.1, le=1.0, description="Largura máxima do bloco (fração da largura)")
    max_linhas: int = Field(2, ge=1, le=4)
    max_palavras: int = Field(4, ge=1, le=12)
    animacao: Literal["pop", "fade", "nenhuma"] = "pop"


# ---- grafismos ----------------------------------------------------------------------------------------
class Tarja(_No):
    """Lower third / gerador de caracteres com o nome de quem fala."""

    estilo: Literal["barra", "caixa", "linha", "etiqueta"] = "barra"
    posicao: Posicao = "inferior_esquerda"
    papel_nome: str = "subtitulo"
    papel_cargo: str = "dados"
    tamanho_nome: float = Field(0.044, ge=0.005, le=0.3)
    tamanho_cargo: float = Field(0.026, ge=0.005, le=0.3)
    cor_nome: Cor = "texto"
    cor_cargo: Cor = "texto_suave"
    cor_fundo: Cor = "fundo"
    cor_acento: Cor = "primaria"
    alfa_fundo: float = Field(0.88, ge=0, le=1)


class Selo(_No):
    """Faixa de destaque: “AO VIVO”, “URGENTE”, sobretítulo."""

    estilo: Literal["chapado", "contorno", "sublinhado"] = "chapado"
    papel: str = "subtitulo"
    tamanho: float = Field(0.032, ge=0.005, le=0.3)
    cor_fundo: Cor = "primaria"
    cor_texto: Cor = "fundo"
    inclinacao: float = Field(0.0, ge=-45, le=45)


class Credito(_No):
    """Crédito de fonte de dado ou de imagem (“Fonte: IBGE, 2025”)."""

    papel: str = "dados"
    tamanho: float = Field(0.024, ge=0.005, le=0.2)
    cor: Cor = "texto_suave"
    prefixo: str = "Fonte: "
    posicao: Posicao = "inferior_direita"


class SecaoGraficos(_No):
    tarja: Tarja = Field(default_factory=Tarja)
    selo: Selo = Field(default_factory=Selo)
    credito: Credito = Field(default_factory=Credito)
    icones: Literal["traco", "cheio"] = "traco"
    eixo: Cor = "texto_suave"
    grade: Cor = "superficie"


# ---- thumbnail ----------------------------------------------------------------------------------------
class TratamentoFoto(_No):
    saturacao: float = Field(1.05, ge=0, le=3)
    contraste: float = Field(1.08, ge=0, le=3)
    recortar_pessoa: bool = True
    contorno_pessoa: Cor | None = "primaria"
    espessura_contorno: float = Field(0.012, ge=0, le=0.1)


class SecaoThumbnail(_No):
    max_palavras: int = Field(4, ge=1, le=12)
    papel: str = "titulo"
    tamanho: float = Field(0.18, ge=0.02, le=0.6, description="Fração da altura da thumb")
    cor: Cor = "texto"
    cor_destaque: Cor = "primaria"
    contorno: Contorno | None = Field(default_factory=lambda: Contorno(espessura=0.06))
    fundo: str = Field("fundo", description="Cor, gradiente:<nome> ou foto")
    borda: Cor | None = None
    canto_reservado: Literal["nenhum", "inferior_direito", "inferior_esquerdo", "superior_direito",
                             "superior_esquerdo"] = Field("inferior_direito", description="Onde a plataforma põe o "
                                                         "selo de duração: o texto não entra ali")
    reserva: tuple[float, float] = Field((0.24, 0.2), description="[largura, altura] do canto reservado, em fração")
    tratamento_foto: TratamentoFoto = Field(default_factory=TratamentoFoto)


# ---- som e marca --------------------------------------------------------------------------------------
class Loudness(_No):
    alvo_lufs: float = Field(-14.0, ge=-40, le=-5)
    pico_dbtp: float = Field(-1.0, ge=-12, le=0)


class Musica(_No):
    clima: str = ""
    bpm: tuple[int, int] = (80, 120)


class SecaoSom(_No):
    identidade: str = Field("", description="A sonoridade do canal numa frase")
    loudness: Loudness = Field(default_factory=Loudness)
    efeitos: dict[str, str] = Field(default_factory=lambda: {"entrada": "whoosh", "enfase": "pop",
                                                             "numero": "click", "alerta": "impacto"})
    volume_efeitos: float = Field(0.45, ge=0, le=1.5)
    musica: Musica = Field(default_factory=Musica)


class SecaoMarca(_No):
    assinatura: str | None = Field(None, description="@canal")
    logo: str | None = Field(None, description="Arquivo em arte/marca/ ou em assets/ do canal")
    posicao_logo: Posicao = "superior_direita"
    marca_dagua: bool = False
    opacidade_logo: float = Field(0.85, ge=0.05, le=1)


# ---- cenas: como a DA guia a IA ao planejar o corte ---------------------------------------------------
TIPOS_DE_CENA = ("titulo", "numero", "citacao", "lista", "comparacao", "linha_do_tempo", "local", "nome",
                 "palavra", "alerta")
TipoCena = Literal["titulo", "numero", "citacao", "lista", "comparacao", "linha_do_tempo", "local", "nome",
                   "palavra", "alerta"]


class SecaoCenas(_No):
    """O que a IA recebe ao planejar as telas do corte, e o que o Clipator confere na resposta dela."""

    tom: str = Field("", description="Como as telas falam, numa frase (ex.: “seco, factual, sem adjetivo”)")
    preferir: list[TipoCena] = Field(default_factory=list, description="Tipos de cena que combinam com a DA")
    evitar: list[TipoCena] = Field(default_factory=list, description="Tipos que a IA não deve usar (são descartados)")
    intervalo: float = Field(3.0, ge=1.0, le=20.0, description="Segundos mínimos entre o começo de duas cenas")
    por_minuto: float = Field(12.0, ge=1.0, le=40.0, description="Teto de cenas por minuto de corte")
    duracao: tuple[float, float] = Field((1.5, 6.0), description="[mínima, máxima] de cada cena, em segundos")
    palavras_titulo: int = Field(6, ge=1, le=15, description="Máximo de palavras num título ou palavra forte")
    palavras_rotulo: int = Field(8, ge=1, le=20, description="Máximo de palavras num rótulo, citação curta ou alerta")
    itens_lista: int = Field(5, ge=2, le=8, description="Máximo de itens numa lista ou linha do tempo")
    palavras_item: int = Field(5, ge=1, le=12, description="Máximo de palavras em cada item")
    abrir_com_titulo: bool = Field(True, description="A primeira cena é um título-gancho nos primeiros segundos")
    regras: list[str] = Field(default_factory=list, description="Regras extras para a IA, em frases curtas")

    @model_validator(mode="after")
    def _coerente(self) -> SecaoCenas:
        comum = set(self.preferir) & set(self.evitar)
        if comum:
            raise ValueError(f"cenas: {', '.join(sorted(comum))} está em preferir e em evitar ao mesmo tempo")
        if self.duracao[0] > self.duracao[1]:
            raise ValueError("cenas.duracao: a mínima passa da máxima")
        return self


# ---- formatos e a DA inteira --------------------------------------------------------------------------
class Quadro(_No):
    largura: int = Field(ge=16, le=8192)
    altura: int = Field(ge=16, le=8192)
    fps: float = Field(30, ge=1, le=120)


def _formatos_padrao() -> dict[str, Quadro]:
    return {"vertical": Quadro(largura=1080, altura=1920), "horizontal": Quadro(largura=1920, altura=1080),
            "quadrado": Quadro(largura=1080, altura=1080), "retrato": Quadro(largura=1080, altura=1350),
            "thumbnail": Quadro(largura=1280, altura=720, fps=1)}


class DA(_No):
    versao: int = VERSAO_ESQUEMA
    herda: str | None = None
    nome: str = ""
    conceito: Conceito = Field(default_factory=Conceito)
    formatos: dict[str, Quadro] = Field(default_factory=_formatos_padrao)
    cor: SecaoCor = Field(default_factory=SecaoCor)
    tipografia: SecaoTipografia = Field(default_factory=SecaoTipografia)
    layout: SecaoLayout = Field(default_factory=SecaoLayout)
    movimento: SecaoMovimento = Field(default_factory=SecaoMovimento)
    tratamento: SecaoTratamento = Field(default_factory=SecaoTratamento)
    legenda: SecaoLegenda = Field(default_factory=SecaoLegenda)
    graficos: SecaoGraficos = Field(default_factory=SecaoGraficos)
    thumbnail: SecaoThumbnail = Field(default_factory=SecaoThumbnail)
    cenas: SecaoCenas = Field(default_factory=SecaoCenas)
    som: SecaoSom = Field(default_factory=SecaoSom)
    marca: SecaoMarca = Field(default_factory=SecaoMarca)

    @field_validator("versao")
    @classmethod
    def _versao(cls, v: int) -> int:
        if v != VERSAO_ESQUEMA:
            raise ValueError(f"versão {v} do esquema não é conhecida (esta versão do Clipator lê a {VERSAO_ESQUEMA})")
        return v


def campos_de_cor() -> list[str]:
    """Caminhos (seção.campo) dos campos que aceitam token de cor; o compilador resolve todos para hex."""
    return [
        "legenda.cor", "legenda.cor_destaque", "legenda.cor_falada", "legenda.contorno.cor", "legenda.sombra.cor",
        "legenda.caixa.cor", "layout.sombra.cor",
        "graficos.tarja.cor_nome", "graficos.tarja.cor_cargo", "graficos.tarja.cor_fundo", "graficos.tarja.cor_acento",
        "graficos.selo.cor_fundo", "graficos.selo.cor_texto", "graficos.credito.cor", "graficos.eixo", "graficos.grade",
        "thumbnail.cor", "thumbnail.cor_destaque", "thumbnail.contorno.cor", "thumbnail.borda",
        "thumbnail.tratamento_foto.contorno_pessoa",
    ]


def campos_de_papel() -> list[str]:
    return ["legenda.papel", "graficos.tarja.papel_nome", "graficos.tarja.papel_cargo", "graficos.selo.papel",
            "graficos.credito.papel", "thumbnail.papel"]
