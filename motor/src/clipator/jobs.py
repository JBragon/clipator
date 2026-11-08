"""Fila de jobs local em SQLite, com progresso, logs e cancelamento.

Um processo só, sem servidor externo. Jobs pesados (download, transcrição,
render) rodam um de cada vez por padrão para não disputar CPU/GPU.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .media import Cancelado


@dataclass
class ContextoJob:
    id: str
    cancelar: threading.Event
    _fila: "FilaJobs"
    _etapa: str | None = None

    def progresso(self, frac: float, msg: str = "", etapa: str | None = None, fracao_etapa: float | None = None) -> None:
        """Progresso geral do job (0 a 1) e, se der, a etapa atual e quanto dela já foi.

        Ao trocar de etapa, guarda quando ela começou e o progresso geral daquele momento,
        para a interface estimar o tempo restante pela velocidade da etapa atual.
        """
        if self.cancelar.is_set():
            raise Cancelado()
        frac = max(0.0, min(1.0, frac))
        campos: dict[str, Any] = {"progresso": frac, "mensagem": msg}
        if etapa is not None:
            if etapa != self._etapa:
                self._etapa = etapa
                campos.update(etapa=etapa, etapa_iniciado=time.time(), etapa_progresso_inicial=frac)
            campos["progresso_etapa"] = max(0.0, min(1.0, fracao_etapa if fracao_etapa is not None else 0.0))
        self._fila._atualizar(self.id, **campos)

    def log(self, linha: str) -> None:
        self._fila._log(self.id, linha)

    def esperar_login(self, agente: str, logado: Callable[[], bool]) -> bool:
        """Pausa o job até `logado()` dar True (o usuário entrou na CLI).

        Devolve False se o usuário pediu a outra IA ou se o tempo acabou; cancelar continua valendo.
        """
        fila = self._fila
        outra = fila._usar_outra.setdefault(self.id, threading.Event())
        outra.clear()
        nome = {"claude": "Claude", "codex": "Codex"}.get(agente, agente)
        self.log(f"{nome} sem login: aguardando você entrar (ou escolher a outra IA)")
        fila._atualizar(self.id, aguardando=f"login_{agente}", mensagem=f"aguardando login do {nome}")
        limite = time.monotonic() + fila.tempo_login
        try:
            while True:
                if self.cancelar.is_set():
                    raise Cancelado()
                if outra.is_set():
                    self.log(f"usando a outra IA no lugar do {nome}, como você pediu")
                    return False
                if logado():
                    self.log(f"login do {nome} feito; continuando por ele")
                    return True
                if time.monotonic() > limite:
                    self.log(f"{nome} continuou sem login por {fila.tempo_login / 60:.0f} min; usando a outra IA")
                    return False
                outra.wait(fila.intervalo_login)
        finally:
            fila._atualizar(self.id, aguardando=None, mensagem="")


Handler = Callable[[dict, ContextoJob], Any]
Ouvinte = Callable[[dict], None]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  tipo TEXT NOT NULL,
  params TEXT NOT NULL,
  status TEXT NOT NULL,
  progresso REAL NOT NULL DEFAULT 0,
  mensagem TEXT NOT NULL DEFAULT '',
  resultado TEXT,
  erro TEXT,
  log TEXT NOT NULL DEFAULT '',
  aguardando TEXT,
  etapa TEXT,
  progresso_etapa REAL,
  etapa_iniciado REAL,
  etapa_progresso_inicial REAL,
  criado REAL NOT NULL,
  iniciado REAL,
  terminado REAL
);
"""


# tipos que correm numa faixa própria (cada faixa tem o seu trabalhador): uma prévia de estilo ou uma
# conversa com a IA não fica esperando o render terminar, nem o render espera por elas
FAIXAS: dict[str, str] = {
    "amostras_estilo": "previas", "amostra_video": "previas",
    "melhorar_edicao": "ia", "revisao": "ia", "efeitos_ia": "ia",
}


class FilaJobs:
    def __init__(self, db_path: str | Path, workers: int = 1, limpar: bool = False):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.executescript(_SCHEMA)
        colunas = {r[1] for r in self._con.execute("PRAGMA table_info(jobs)")}
        # filas criadas por versões anteriores ganham as colunas novas
        for coluna, tipo in (("aguardando", "TEXT"), ("etapa", "TEXT"), ("progresso_etapa", "REAL"),
                             ("etapa_iniciado", "REAL"), ("etapa_progresso_inicial", "REAL")):
            if coluna not in colunas:
                self._con.execute(f"ALTER TABLE jobs ADD COLUMN {coluna} {tipo}")
        self._con.execute("UPDATE jobs SET aguardando=NULL")
        # quanto um job espera o login da IA e de quanto em quanto tempo confere
        self.tempo_login = 600.0
        self.intervalo_login = 5.0
        self._usar_outra: dict[str, threading.Event] = {}
        if limpar:
            # o app sobe com a fila limpa: some o que falhou ou ficou pela metade, e os logs antigos
            self._con.execute("DELETE FROM jobs WHERE status != 'ok'")
            self._con.execute("UPDATE jobs SET log = ''")
        else:
            # jobs que estavam rodando quando o processo fechou viram "interrompido"
            self._con.execute("UPDATE jobs SET status='interrompido' WHERE status IN ('rodando','na_fila')")
        self.handlers: dict[str, Handler] = {}
        self.ouvintes: list[Ouvinte] = []
        self._cancelar: dict[str, threading.Event] = {}
        self._filas: dict[str, list[str]] = {"principal": [], **{f: [] for f in set(FAIXAS.values())}}
        self._fila = self._filas["principal"]
        self._cond = threading.Condition(self._lock)
        self._parar = False
        self._threads = [threading.Thread(target=self._loop, args=("principal",), daemon=True, name=f"clipator-job-{i}")
                         for i in range(workers)]
        self._threads += [threading.Thread(target=self._loop, args=(f,), daemon=True, name=f"clipator-job-{f}")
                          for f in self._filas if f != "principal"]
        for t in self._threads:
            t.start()

    # ---- API ----------------------------------------------------------------
    def registrar(self, tipo: str, handler: Handler) -> None:
        self.handlers[tipo] = handler

    def enviar(self, tipo: str, params: dict | None = None) -> str:
        if tipo not in self.handlers:
            raise KeyError(f"Tipo de job desconhecido: {tipo}")
        jid = uuid.uuid4().hex[:12]
        with self._lock:
            self._con.execute(
                "INSERT INTO jobs (id, tipo, params, status, criado) VALUES (?,?,?,?,?)",
                (jid, tipo, json.dumps(params or {}, ensure_ascii=False), "na_fila", time.time()),
            )
            self._cancelar[jid] = threading.Event()
            self._filas[FAIXAS.get(tipo, "principal")].append(jid)
            self._cond.notify_all()
        self._emitir(jid)
        return jid

    def cancelar(self, jid: str) -> bool:
        with self._lock:
            ev = self._cancelar.get(jid)
            if ev is None:
                return False
            ev.set()
            outra = self._usar_outra.get(jid)
            if outra is not None:
                outra.set()  # acorda a espera de login para ver o cancelamento
            fila = next((f for f in self._filas.values() if jid in f), None)
            if fila is not None:
                fila.remove(jid)
                self._con.execute("UPDATE jobs SET status='cancelado', terminado=? WHERE id=?", (time.time(), jid))
        self._emitir(jid)
        return True

    def usar_outra_ia(self, jid: str) -> bool:
        """Para um job que espera login: segue pela outra IA."""
        with self._lock:
            ev = self._usar_outra.get(jid)
        if ev is None:
            return False
        ev.set()
        return True

    def obter(self, jid: str) -> dict | None:
        with self._lock:
            row = self._con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return self._row(row) if row else None

    def listar(self, limite: int = 50) -> list[dict]:
        with self._lock:
            rows = self._con.execute("SELECT * FROM jobs ORDER BY criado DESC LIMIT ?", (limite,)).fetchall()
        return [self._row(r, com_log=False) for r in rows]

    def esperar(self, jid: str, timeout: float | None = None) -> dict:
        fim = time.time() + timeout if timeout else None
        while True:
            j = self.obter(jid)
            if j and j["status"] in ("ok", "erro", "cancelado", "interrompido"):
                return j
            if fim and time.time() > fim:
                raise TimeoutError(jid)
            time.sleep(0.1)

    def fechar(self) -> None:
        with self._lock:
            self._parar = True
            for ev in self._cancelar.values():
                ev.set()
            self._cond.notify_all()

    # ---- internos -------------------------------------------------------------
    def _row(self, row: sqlite3.Row, com_log: bool = True) -> dict:
        d = dict(row)
        d["params"] = json.loads(d["params"])
        d["resultado"] = json.loads(d["resultado"]) if d.get("resultado") else None
        if not com_log:
            d.pop("log", None)
        return d

    def _atualizar(self, jid: str, **campos: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in campos)
        with self._lock:
            self._con.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*campos.values(), jid))  # noqa: S608 - chaves internas
        self._emitir(jid)

    def _log(self, jid: str, linha: str) -> None:
        with self._lock:
            self._con.execute("UPDATE jobs SET log = substr(log || ? , -60000) WHERE id=?",
                              (time.strftime("%H:%M:%S ") + linha.rstrip() + "\n", jid))
        self._emitir(jid, log=linha)

    def _emitir(self, jid: str, log: str | None = None) -> None:
        j = self.obter(jid)
        if not j:
            return
        j.pop("log", None)
        if log:
            j["linha_log"] = log
        for o in list(self.ouvintes):
            try:
                o(j)
            except Exception:
                pass

    def _loop(self, faixa: str = "principal") -> None:
        fila = self._filas[faixa]
        while True:
            with self._cond:
                while not fila and not self._parar:
                    self._cond.wait()
                if self._parar:
                    return
                jid = fila.pop(0)
            j = self.obter(jid)
            if not j:
                continue
            ev = self._cancelar[jid]
            ctx = ContextoJob(jid, ev, self)
            self._atualizar(jid, status="rodando", iniciado=time.time())
            try:
                res = self.handlers[j["tipo"]](j["params"], ctx)
                self._atualizar(jid, status="ok", progresso=1.0, terminado=time.time(),
                                resultado=json.dumps(res, ensure_ascii=False, default=str))
            except Cancelado:
                self._atualizar(jid, status="cancelado", terminado=time.time(), mensagem="cancelado")
            except Exception as exc:  # noqa: BLE001 - o erro vai para a interface
                ctx.log(traceback.format_exc())
                self._atualizar(jid, status="erro", erro=str(exc)[:2000], terminado=time.time())
            finally:
                with self._lock:
                    self._cancelar.pop(jid, None)
                    self._usar_outra.pop(jid, None)
