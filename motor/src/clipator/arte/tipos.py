"""Onde está o arquivo de cada fonte que a DA pede (para a prancha, a thumbnail e a camada HyperFrames)."""

from __future__ import annotations

from pathlib import Path

from .carregar import Resolvida


def pastas_de_fonte(r: Resolvida | None = None, extras: list[Path] | None = None) -> list[Path]:
    """Ordem de busca: fontes da DA (arte/fontes), as do canal (extras), as baixadas pelo Clipator, as embutidas."""
    from .. import fontes as _fontes

    out: list[Path] = []
    if r is not None and r.pasta is not None:
        out.append(r.pasta / "fontes")
    for a in r.ancestrais if r is not None else []:
        out.append(Path(a).parent / "fontes")  # predefinido pessoal com as fontes junto
    out += list(extras or [])
    out.append(_fontes.pasta())
    return out


def arquivo_da_fonte(familia: str, r: Resolvida | None = None, extras: list[Path] | None = None,
                     italico: bool = False) -> Path | None:
    from ..thumbs import caminho_fonte

    pastas = pastas_de_fonte(r, extras)
    if italico:
        p = caminho_fonte(f"{familia} Italic", pastas) or caminho_fonte(f"{familia}Italic", pastas)
        if p is not None:
            return p
    return caminho_fonte(familia, pastas)


def familias(r: Resolvida) -> list[str]:
    """As famílias distintas que a DA usa, na ordem dos papéis."""
    return list(dict.fromkeys(p.familia for p in r.da.tipografia.papeis.values()))


def fonte_pil(r: Resolvida, papel: str, tamanho_px: int, extras: list[Path] | None = None):
    """ImageFont do papel, no tamanho em px (cai na fonte padrão do Pillow se o arquivo não existir)."""
    from PIL import ImageFont

    p = r.papel(papel)
    arq = arquivo_da_fonte(p.familia, r, extras, p.italico) if p else None
    if arq is None:
        return ImageFont.load_default(max(8, tamanho_px))
    return ImageFont.truetype(str(arq), max(8, tamanho_px))
