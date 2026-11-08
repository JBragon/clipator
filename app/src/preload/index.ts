// Ponte segura entre a interface e o processo principal.
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('clipator', {
  infoMotor: () => ipcRenderer.invoke('motor:info'),
  reiniciarMotor: () => ipcRenderer.invoke('motor:reiniciar'),
  escolherVideo: () => ipcRenderer.invoke('dialogo:video'),
  escolherPasta: () => ipcRenderer.invoke('dialogo:pasta'),
  escolherZip: () => ipcRenderer.invoke('dialogo:zip'),
  escolherCookies: () => ipcRenderer.invoke('dialogo:cookies'),
  salvarArquivo: (nome: string) => ipcRenderer.invoke('dialogo:salvar', nome),
  definirWorkspace: (pasta: string) => ipcRenderer.invoke('workspace:definir', pasta),
  definirTema: (tema: string) => ipcRenderer.invoke('tema:definir', tema),
  mostrarNaPasta: (caminho: string) => ipcRenderer.invoke('shell:mostrar', caminho),
  abrir: (caminho: string) => ipcRenderer.invoke('shell:abrir', caminho),
  lixeira: (caminho: string) => ipcRenderer.invoke('shell:lixeira', caminho),
  idiomaSistema: () => ipcRenderer.invoke('app:idioma'),
  chat: {
    abrir: (p: unknown) => ipcRenderer.invoke('chat:abrir', p),
    listar: () => ipcRenderer.invoke('chat:listar'),
    eventos: (id: string) => ipcRenderer.invoke('chat:eventos', id),
    enviar: (id: string, texto: string) => ipcRenderer.invoke('chat:enviar', id, texto),
    responder: (id: string, perm: string, d: string) => ipcRenderer.invoke('chat:responder', id, perm, d),
    interromper: (id: string) => ipcRenderer.invoke('chat:interromper', id),
    fechar: (id: string) => ipcRenderer.invoke('chat:fechar', id),
    aoEvento: (f: (id: string, e: unknown) => void) => {
      const h = (_e: unknown, id: string, ev: unknown): void => f(id, ev)
      ipcRenderer.on('chat:evento', h)
      return () => ipcRenderer.removeListener('chat:evento', h)
    }
  },
  ia: {
    disponivel: () => ipcRenderer.invoke('ia:disponivel'),
    abrir: (p: unknown, cols: number, rows: number) => ipcRenderer.invoke('ia:abrir', p, cols, rows),
    listar: () => ipcRenderer.invoke('ia:listar'),
    saida: (id: string) => ipcRenderer.invoke('ia:saida', id),
    escrever: (id: string, dados: string) => ipcRenderer.send('ia:escrever', id, dados),
    redimensionar: (id: string, cols: number, rows: number) => ipcRenderer.send('ia:redimensionar', id, cols, rows),
    parar: (id: string) => ipcRenderer.invoke('ia:parar', id),
    fechar: (id: string) => ipcRenderer.invoke('ia:fechar', id),
    aoDados: (f: (id: string, d: string, total: number) => void) => {
      const h = (_e: unknown, id: string, d: string, n: number): void => f(id, d, n)
      ipcRenderer.on('ia:dados', h)
      return () => ipcRenderer.removeListener('ia:dados', h)
    },
    aoSair: (f: (id: string, codigo: number) => void) => {
      const h = (_e: unknown, id: string, c: number): void => f(id, c)
      ipcRenderer.on('ia:saiu', h)
      return () => ipcRenderer.removeListener('ia:saiu', h)
    }
  }
})
