# Atalhos do Clipator. Funciona no PowerShell, no cmd e no Git Bash: as receitas só usam
# o que os três entendem, e no Windows o make as roda pelo cmd, sem o bloqueio do npm.ps1.

DEPENDENCIAS := app/node_modules/.package-lock.json

.DEFAULT_GOAL := run
.PHONY: run

# Abre o app de desktop, que sobe sozinho o motor da pasta motor/ via uv e fecha junto com ele.
run: $(DEPENDENCIAS)
	cd app && npm run dev

# Só reinstala quando o package.json ou o package-lock.json mudam. O npm nem sempre regrava
# o arquivo de referência, então a data dele é atualizada aqui para não repetir a instalação.
$(DEPENDENCIAS): app/package.json app/package-lock.json
	cd app && npm install && node -e "const f='node_modules/.package-lock.json',t=new Date();require('fs').utimesSync(f,t,t)"
