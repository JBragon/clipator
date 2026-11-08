"""Schemas dos arquivos do workspace.

Os cabeçalhos YAML dos .md e os .yaml do workspace são validados aqui. Os nomes
das chaves ficam em português porque são os que o usuário edita.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Formato = Literal["9:16", "1:1", "4:5", "16:9"]
Reenquadramento = Literal["seguir-rosto", "centro", "fundo-desfocado", "dividido", "original"]
ModoIA = Literal["sem-ia", "economico", "completo"]
NivelIA = Literal["fixo", "assistido", "autoral"]
Agente = Literal["claude", "codex", "nenhum"]

RESOLUCOES: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


class _Base(BaseModel):
    # Chaves desconhecidas são mantidas: o usuário e a IA podem anotar o .md
    # com campos que versões futuras vão usar.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Pesos(_Base):
    """Pesos da nota local (camada 1). Ficam no regras.md do canal."""

    gancho: float = 20
    energia: float = 15
    reacoes: float = 10
    ritmo: float = 15
    historia: float = 20
    palavras_chave: float = 10
    plataforma: float = 10
    fechamento: float = 25  # o corte fecha o assunto (conclusão, sem pergunta no ar, antes de mudar de tema)


class Regras(_Base):
    """regras.md: como escolher os cortes."""

    duracao_min: float = Field(20, ge=5, le=600)
    duracao_max: float = Field(60, ge=10, le=1200, description="Duração máxima dos Shorts (padrão 60 s)")
    duracao_max_fechamento: float = Field(
        90, ge=10, le=1500,
        description="Até quanto um Short pode passar da duração máxima, só quando é para fechar o assunto")
    corte_longo_min: float = Field(480, ge=120)
    corte_longo_max: float = Field(1200, le=3600)
    quantidade: int = Field(8, ge=1, le=50)
    modo_ia: ModoIA = "economico"
    nivel_ia: NivelIA = "assistido"
    candidatos_para_ia: int = Field(20, ge=1, le=60)
    pesos: Pesos = Field(default_factory=Pesos)
    palavras_chave: list[str] = Field(default_factory=list)
    temas_proibidos: list[str] = Field(default_factory=list)
    trava_titulo: bool = True
    censor_leetspeak: bool = False
    palavras_censuradas: list[str] = Field(default_factory=list)
    revisao_cruzada: bool = False

    @field_validator("duracao_max")
    @classmethod
    def _max_maior_que_min(cls, v: float, info: Any) -> float:
        lo = info.data.get("duracao_min", 5)
        if v < lo + 5:
            raise ValueError("duracao_max precisa ser pelo menos 5 s maior que duracao_min")
        return v


class Canal(_Base):
    """canal.md: identidade do canal."""

    nome: str
    idioma: Literal["pt", "en", "auto"] = "pt"
    publico: str = ""
    tom: str = ""
    assuntos: list[str] = Field(default_factory=list)
    palavras_chave: list[str] = Field(default_factory=list)
    evitar: list[str] = Field(default_factory=list)
    estilo_padrao: str = "podcast-limpo"
    formato_padrao: Formato = "9:16"
    glossario: list[str] = Field(default_factory=list, description="Nomes próprios e termos que o Whisper costuma errar")
    direcao_de_arte: dict[str, Any] = Field(default_factory=dict, description="Ficha do canal (cores, fontes) por cima da do estilo")
    chamada_automatica: Literal["nenhuma", "inicio", "fim", "inicio-e-fim"] = Field(
        "nenhuma", description="Sugerir o sticker animado de Inscreva-se no começo e/ou no fim dos clips")


class Legenda(_Base):
    modo: Literal["palavra-a-palavra", "uma-palavra", "frase", "nenhuma"] = "palavra-a-palavra"
    fonte: str = "Montserrat ExtraBold"
    tamanho: int = Field(72, ge=10, le=300)
    cor: str = "#FFFFFF"
    destaque: str = "#FFE600"
    contorno: str = "#000000"
    espessura_contorno: float = Field(5, ge=0, le=20)
    sombra: float = Field(0, ge=0, le=10)
    fundo: str | None = None
    opacidade_fundo: float = Field(0.0, ge=0, le=1)
    posicao: Literal["topo", "centro", "centro-baixo", "terco-inferior", "baixo"] = "centro-baixo"
    altura_relativa: float | None = Field(None, ge=0.05, le=0.95, description="Altura do centro da legenda (0 = topo, 1 = base)")
    animacao: Literal["nenhuma", "pop", "caixa", "brilho", "marca-texto", "revelar"] = "pop"
    max_palavras_por_linha: int = Field(3, ge=1, le=12)
    linhas: int = Field(1, ge=1, le=3)
    caixa_alta: bool = False
    italico: bool = False
    opacidade_base: float = Field(1.0, ge=0.05, le=1.0)
    palavras_destaque: list[str] = Field(default_factory=list, description="Palavras ou regex pintadas com a cor de destaque")
    destacar_numeros: bool = False
    destacar_chave: bool = Field(False, description="Destaca sem IA as palavras que se repetem e marcam o assunto do corte")
    escala_destaque: float = Field(1.0, ge=1.0, le=1.8, description="Palavra destacada sai maior (1 = mesmo tamanho)")
    cores_falantes: list[str] = Field(default_factory=list)


class Cartela(_Base):
    """Cartela de título nos primeiros segundos. O estilo só sugere; o usuário decide por clip."""

    sugerida: bool = True
    duracao: float = Field(3.0, ge=0.5, le=10)
    fonte: str = "Montserrat ExtraBold"
    tamanho: int = Field(64, ge=10, le=300)
    cor: str = "#000000"
    fundo: str = "#FFFFFF"
    destaque: str = "#FFE600"
    posicao: Literal["topo", "centro", "baixo"] = "topo"
    caixa_alta: bool = True


class Zoom(_Base):
    enfase: bool = False
    intensidade: float = Field(1.12, ge=1.0, le=1.6)
    intervalo: tuple[float, float] | None = None


class Dividido(_Base):
    """Tela dividida (reenquadramento "dividido"): duas pessoas empilhadas, uma em cada metade."""

    em_cima: Literal["esquerda", "direita"] = Field("esquerda", description="Quem fica na metade de cima: a pessoa da "
                                                    "esquerda ou a da direita do vídeo original")
    tamanho_rosto: float = Field(0.35, ge=0.15, le=0.8, description="Altura do rosto em fração da metade (maior = mais perto)")


class Abertura(_Base):
    """Abertura com ganchos: os momentos mais fortes do próprio corte, em preto e branco, antes do corte inteiro."""

    ativa: bool = False
    duracao: float = Field(6.0, ge=2.0, le=15.0, description="Duração total desejada dos ganchos (s)")
    max_trechos: int = Field(2, ge=1, le=4, description="Quantos momentos entram na abertura")
    max_trecho: float = Field(4.5, ge=1.0, le=8.0, description="Duração máxima de cada momento (s)")
    inicio_minimo: float = Field(0.15, ge=0.0, le=0.8, description="Não pega ganchos desta fração inicial do corte, "
                                 "que o público vai ver logo em seguida")
    preto_e_branco: bool = True
    contraste: float = Field(1.12, ge=0.8, le=1.6)
    transicao: Literal["flash", "corte"] = Field("flash", description="flash: clarão branco que some ao entrar o corte")
    duracao_flash: float = Field(0.3, ge=0.05, le=1.0)
    som: str | None = Field(None, description="Efeito na virada para o corte (whoosh, impacto, riser…) ou arquivo do canal")
    trechos: list[tuple[float, float]] = Field(default_factory=list, description="Escolha manual, em segundos do "
                                               "vídeo original (vazio = o motor escolhe pela energia e pela fala)")


class Musica(_Base):
    arquivo: str | None = None
    volume: str = "-22dB"
    trecho: Literal["inteiro", "inicio", "fim"] = "inteiro"


CantoJanela = Literal["inferior-direito", "inferior-esquerdo", "superior-direito", "superior-esquerdo"]


class LayoutArte(_Base):
    """A composição que o usuário escolheu para um clip: mora no edicao.json e entra nas versões da edição."""

    layout: Literal["em-cima", "janela"]
    proporcao: float | None = Field(None, ge=0.25, le=0.7)
    janela_canto: CantoJanela | None = None
    janela_escala: float | None = Field(None, ge=0.2, le=0.7)
    janela_encaixe: Literal["enquadrar", "barras"] | None = None


class DirecaoArte(_Base):
    """Cenas animadas que acompanham a fala, misturadas com o vídeo (direcao.py e render.py)."""

    layout: Literal["nenhum", "em-cima", "fundo", "sobreposto", "janela"] = Field(
        "nenhum", description="em-cima: animação em cima e vídeo embaixo; fundo: animação atrás da pessoa recortada; "
        "sobreposto: cartões por cima do vídeo; janela: vídeo numa janela sobre a animação")
    ficha: str = Field("neon", description="Predefinição da ficha: neon, dossie, editorial, laboratorio, ou canal (a direção de arte do canal em arte/direcao.yaml) (desenho: quadro, noite, caderno)")
    cores: dict[str, str] = Field(default_factory=dict, description="Sobrescreve fundo, superficie, texto, texto_suave, primaria, destaque")
    fontes: dict[str, str] = Field(default_factory=dict, description="fonte_titulo e fonte_corpo")
    proporcao: float = Field(0.45, ge=0.25, le=0.7, description="em-cima: altura da animação (fração do quadro)")
    pessoa_escala: float = Field(0.92, ge=0.4, le=1.2, description="fundo: altura da pessoa (fração do quadro)")
    pessoa_x: float = Field(0.5, ge=0.0, le=1.0, description="fundo: posição da pessoa (0 esquerda, 1 direita)")
    janela_escala: float = Field(0.42, ge=0.2, le=0.7, description="janela: largura do vídeo (fração do quadro)")
    janela_canto: CantoJanela | None = Field(None, description="janela: o canto do vídeo; sem valor, a posição antiga (clips de antes dos cantos)")
    janela_encaixe: Literal["enquadrar", "barras"] = Field("enquadrar", description="janela: recorta pelo rosto ou mostra o quadro inteiro com barras; nunca deforma")
    recorte: Literal["auto", "segmentar", "chroma", "oval"] = "auto"
    densidade: float = Field(3.0, ge=1.5, le=10, description="Segundos mínimos entre uma cena e outra")
    sons: bool = True
    modo: Literal["cenas", "desenho", "arte"] = Field(
        "cenas", description="cenas: cartões de texto e dados; desenho: desenho animado em traço que a IA roteiriza (desenho.py); "
        "arte: uma das direções com renderizador próprio (artes/)")
    arte: str | None = Field(None, description="modo arte: o id da direção (dados/artes/<id>.json)")
    parametros: dict[str, Any] = Field(default_factory=dict, description="modo arte: ajustes da direção, nos limites dela")

    @property
    def ativa(self) -> bool:
        return self.layout != "nenhum"


class Estilo(_Base):
    """Cabeçalho de estilos/*.md e de estilos/<nome>/estilo.md."""

    nome: str = ""
    descricao: str = ""
    objetivo: list[str] = Field(default_factory=list)
    formato: Formato = "9:16"
    resolucao: str | None = None
    reenquadramento: Reenquadramento = "seguir-rosto"
    dividido: Dividido = Field(default_factory=Dividido, description="Ajustes da tela dividida (duas pessoas)")
    motor: Literal["ffmpeg", "hyperframes"] = "ffmpeg"
    template: str | None = Field(None, description="Motor hyperframes: template embutido (ex.: marca-texto) ou "
                                 "arquivo .css/.html ao lado do estilo; sem ele, usa o de mesmo nome do estilo")
    nivel_ia: NivelIA = "fixo"
    legenda: Legenda = Field(default_factory=Legenda)
    cartela: Cartela = Field(default_factory=Cartela)
    zoom: Zoom = Field(default_factory=Zoom)
    jump_cuts: bool = False
    sons: dict[str, str] = Field(default_factory=dict, description="Efeito por momento: inicio, cartela, corte, "
                                 "destaque, fim -> nome sintetizado (whoosh, impacto, riser, pop, click, ding, "
                                 "swoosh-reverso, glitch) ou arquivo do canal")
    volume_sons: float = Field(0.5, ge=0, le=1.5)
    musica: Musica = Field(default_factory=Musica)
    abertura: Abertura = Field(default_factory=Abertura, description="Ganchos do próprio corte antes dele (preto e branco)")
    logo: str | None = None
    posicao_logo: Literal["topo-esquerda", "topo-direita", "baixo-esquerda", "baixo-direita"] = "topo-direita"
    normalizar_audio: bool = True
    corte_longo: bool = False
    direcao: DirecaoArte = Field(default_factory=DirecaoArte, description="Direção de arte: cenas animadas e layout")
    requer_ia: bool = Field(False, description="Só funciona com a IA integrada (Claude Code ou Codex): sem ela, o render recusa")

    def tamanho_saida(self) -> tuple[int, int]:
        if self.resolucao:
            try:
                w, h = (int(x) for x in self.resolucao.lower().split("x"))
                return w - w % 2, h - h % 2
            except ValueError:
                pass
        return RESOLUCOES[self.formato]


LayoutThumb = Literal["rosto-frase", "frase-gancho", "moldura", "rosto-grande"]


class Thumb(_Base):
    """thumb.md do canal: identidade visual das thumbnails."""

    layouts: list[LayoutThumb] = Field(default_factory=lambda: ["rosto-frase", "frase-gancho", "moldura", "rosto-grande"])
    fonte: str = "Anton"
    cor_texto: str = "#FFFFFF"
    cor_destaque: str = "#FFE600"
    cor_fundo: str = "#111111"
    cor_borda: str = "#FFE600"
    espessura_borda: int = Field(14, ge=0, le=60)
    lado_rosto: Literal["direita", "esquerda"] = "direita"
    maiusculas: bool = True
    linhas_max: int = Field(4, ge=1, le=6)
    citacao: bool = Field(
        False, description="Frase dita no clip vai entre aspas e, se foi cortada no meio, termina em reticências "
                           "(\"EU NÃO QUERIA FAZER ISSO...\"), o padrão dos canais de cortes de podcast")


class AtivacaoSkill(_Base):
    skill: str
    escopo: Literal["global", "canal", "projeto"] = "global"
    canal: str | None = None
    projeto: str | None = None


class ConfigWhisper(_Base):
    modelo: str = "auto"
    dispositivo: Literal["auto", "cpu", "cuda"] = "auto"
    idioma: Literal["auto", "pt", "en"] = "auto"


class ConfigIA(_Base):
    ranking: Agente = "claude"
    estilos: Agente = "claude"
    imagens: Agente = "codex"
    timeout_s: int = 600


class ConfigYoutube(_Base):
    cookies_navegador: Literal["", "firefox", "edge", "chrome", "brave", "opera", "vivaldi", "chromium"] = Field(
        "", description="Navegador cujos cookies o yt-dlp usa quando o YouTube pede login (vazio = nenhum)")
    cookies_arquivo: str = Field("", description="Arquivo cookies.txt (formato Netscape); tem prioridade sobre o navegador")


class ConfigApp(_Base):
    """.clipator/config.yaml do workspace."""

    idioma_interface: Literal["pt", "en"] = "pt"
    tema: Literal["sistema", "claro", "escuro"] = "sistema"
    whisper: ConfigWhisper = Field(default_factory=ConfigWhisper)
    youtube: ConfigYoutube = Field(default_factory=ConfigYoutube)
    ia: ConfigIA = Field(default_factory=ConfigIA)
    aviso_direitos_aceito: bool = False
    skills: list[AtivacaoSkill] = Field(default_factory=list, description="Skills ativas e onde valem")
    pastas_skills: list[str] = Field(default_factory=list, description="Pastas extras com skills, só leitura")
    skills_desligadas: list[str] = Field(default_factory=list, description="Skills embutidas que o usuário desligou")


EtapaStatus = Literal["pendente", "rodando", "ok", "erro", "cancelado"]


class Etapa(_Base):
    status: EtapaStatus = "pendente"
    atualizado_em: str | None = None
    erro: str | None = None


class Origem(_Base):
    tipo: Literal["link", "arquivo"]
    valor: str
    titulo: str | None = None
    canal_origem: str | None = None


class Projeto(_Base):
    """projeto.yaml."""

    id: str
    titulo: str
    criado_em: str
    origem: Origem | None = None
    estilo: str | None = None
    formato: Formato | None = None
    etapas: dict[str, Etapa] = Field(default_factory=dict)


class PedidoIA(_Base):
    """Pedido de edição feito no passo 2: vai para o Claude Code ou o Codex quando o render terminar."""

    agente: Literal["claude", "codex"] = "claude"
    texto: str = ""
    abrir_ao_terminar: bool = True
    enviado: str | None = Field(None, description="Lote (data-hora) da conversa aberta; vazio = ainda não enviado")
    erro: str | None = Field(None, description="Por que a conversa não abriu, se não abriu")


class Clip(_Base):
    """clips/<id>/clip.yaml."""

    id: str
    candidato: str | None = None
    inicio: float
    fim: float
    titulo: str = ""
    titulos_sugeridos: list[str] = Field(default_factory=list)
    gancho: str = ""
    thumb_frase: list[str] = Field(default_factory=list, description="Frase-gancho da thumbnail, uma linha por item")
    formato: Formato = "9:16"
    plataforma: Literal["youtube-shorts", "instagram-reels", "tiktok", "youtube"] | None = Field(
        None, description="Onde o clip vai ser publicado: define a zona segura (vazio = pelo formato)")
    estilo: str = "podcast-limpo"
    cartela: bool = False
    cortes_internos: list[tuple[float, float]] = Field(default_factory=list, description="Trechos removidos, em segundos do vídeo original")
    ajustes_estilo: dict[str, Any] = Field(default_factory=dict, description="Sobrescreve o estilo só neste clip")
    status: Literal["selecionado", "renderizado", "erro"] = "selecionado"
    versao: str | None = Field(None, description="Vídeo editado escolhido (edicoes/<data>/...); vazio = saida.mp4")
    pedido_ia: PedidoIA | None = Field(None, description="Pedido para a IA feito antes do render (passo 2)")

    @field_validator("fim")
    @classmethod
    def _fim_depois_do_inicio(cls, v: float, info: Any) -> float:
        if v <= info.data.get("inicio", 0):
            raise ValueError("fim precisa ser maior que inicio")
        return v
