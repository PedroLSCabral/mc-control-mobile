# MC Control: proposta de arquitetura

*15/10/2026 · base: suas respostas no projeto e o seu `prompt-claude-code-mc-agent.md`*

## Resumo

| Peça | Recomendação |
|---|---|
| **App mobile** | **Flutter** (Dart), Android agora, iOS a partir do mesmo código |
| **Backend na VM** | **Agente próprio em Python 3.11+ com FastAPI**, um processo só, gerenciado pelo systemd |
| **Rede** | Somente via **Tailscale**; agente nunca exposto na internet |
| **Comunicação** | REST (JSON) para comandos e status; **WebSocket** para console e métricas ao vivo |
| **MVP** | **Ligar e parar servidor como base de tudo**, com o status que isso exige (`offline`/`starting`/`online`/`stopping`). RAM/CPU e jogadores logo em seguida, como no seu prompt. **Console ao vivo vem depois**, e a arquitetura já fica pronta para ele |

Sobre o MVP: você definiu iniciar e parar como a base, e o seu prompt já deixa o console fora da fase 1. Segui isso e coloquei o console como a fase 3 do plano, porque é a função mais útil do Crafty no dia a dia e a que mais exercita o "backend divertido".

---

## 1. App mobile: qual stack

Você pediu uma de duas coisas: código fácil de portar para iOS, ou rodar nativo nos dois sem perda de desempenho relevante. As três opções sérias atendem a (2); a diferença está em produtividade e em quanto do app é compartilhado.

| Critério | **Flutter** | Kotlin/Compose Multiplatform | React Native |
|---|---|---|---|
| Código compartilhado Android/iOS | ~100% (UI + lógica) | Lógica 100%; UI Compose no iOS já estável, mas ecossistema menor | ~95% |
| Desempenho | Compilado AOT para nativo, renderizador próprio (Impeller). Para um app de dashboard, indistinguível de nativo | Nativo no Android; no iOS, muito bom | Bom com a nova arquitetura (JSI/Fabric), mas mais camadas |
| Curva para você (Python forte, pouco Flutter) | Dart é simples e parecido com o que você já sabe | Kotlin + Gradle + Xcode: mais atrito | JS/TS + tooling do Node |
| Ecossistema para o que o app precisa (HTTP, WebSocket, gráficos, armazenamento seguro) | Maduro: `dio`, `web_socket_channel`, `fl_chart`, `flutter_secure_storage` | Ktor, mas menos pacotes de UI prontos | Maduro |
| Hot reload, iteração rápida | Excelente | Bom | Excelente |
| Gerar iOS no futuro | Precisa de um Mac (ou CI com macOS) para compilar, como todas | Idem | Idem |

**Escolha: Flutter.** Ele resolve as duas opções ao mesmo tempo: um código só, nativo compilado nos dois sistemas, e é o que o seu prompt já previa (Riverpod, `dio`, `flutter_secure_storage`). Compose Multiplatform seria a escolha se você quisesse aprender Kotlin ou tivesse um app Android nativo existente; não é o caso.

### Estrutura do app

```
lib/
  core/
    api/          # cliente REST (dio) + cliente WebSocket, modelos gerados
    auth/         # token no flutter_secure_storage
    theme/
  features/
    settings/     # URL do agente, token, "testar conexão"
    servers/      # lista e detalhe (status, RAM/CPU, jogadores, ligar/desligar)
    console/      # fase 2: terminal ao vivo
    backups/      # fase 3
```

- **Estado:** Riverpod. Cada servidor vira um `StreamProvider` alimentado pelo WebSocket quando a tela está aberta, com fallback para polling.
- **Modelos:** gere o cliente a partir do OpenAPI que o FastAPI publica (`openapi-generator` ou `freezed` + `json_serializable` à mão). Assim app e agente não divergem.
- **Portabilidade iOS:** evite plugins só-Android; os listados acima suportam iOS. Notificações push (futuro) via APNs/FCM pedem atenção extra no iOS.

---

## 2. Backend na VM: o agente

### Linguagem: Python + FastAPI

Você domina Python, o FastAPI dá WebSocket, validação (pydantic) e OpenAPI de graça, e o desempenho sobra: o agente só orquestra processos Java, não carrega tráfego de jogo. Se um dia quiser o desafio de um binário único sem venv, **Go** é a alternativa natural (ótimo para processos e WebSockets), mas não há ganho prático que justifique trocar agora.

### Visão geral

```
 Celular (Flutter) ──Tailscale──▶  Agente (FastAPI, systemd, usuário opc)
                                    ├── ServerManager ── processos Java (um por servidor)
                                    ├── Monitor ──────── psutil + mcstatus (amostragem em background)
                                    ├── ConsoleHub ───── stdout dos servidores → WebSockets
                                    ├── BackupService ── tar.zst + rotação (fase 3)
                                    └── Store ────────── servers.yaml (config) + state.json/SQLite (estado)
```

### 2.1 Gerenciamento dos processos

O ponto mais delicado do projeto. A proposta resolve um problema que o seu prompt já antecipou (o servidor sobreviver a um restart do agente) e outro que ele não cobre (recuperar o console depois disso).

**Recomendação: cada servidor Minecraft roda numa unit systemd própria, com stdin por FIFO.**

- Template `mc-server@.service` (instâncias `mc-server@teste`, `mc-server@atm10`…), com `WorkingDirectory`, `ExecStart` montado a partir do `servers.yaml`, `KillSignal=SIGTERM`, `TimeoutStopSec=stop_timeout` e limite de memória (`MemoryMax`).
- **stdin:** um FIFO (`/run/mc/<id>.stdin`) que o agente abre para escrita. Comandos (`stop`, `say`, `whitelist add`) entram por ali, mesmo depois de o agente reiniciar.
- **stdout:** o processo escreve em `logs/<id>/latest.log` (rotacionado), e o agente faz "tail" desse arquivo para o console ao vivo e para detectar `Done (...)`.
- **Vantagens:** reinício automático em crash (`Restart=on-failure`), limites de recursos, logs no journal, e o agente fica sem estado crítico: se ele cair, os servidores continuam rodando e o console volta ao reabrir o FIFO.
- O agente chama `systemctl start/stop` via D-Bus (biblioteca `pystemd` ou `dbus-next`) com uma regra polkit que permite ao usuário `opc` controlar apenas `mc-server@*`.

**Para desenvolvimento no Windows**, a mesma interface `ProcessBackend` tem uma segunda implementação com `subprocess.Popen` (a que o seu prompt descreve, com `state.json` e readoção por PID). O `fake_server.py` roda por ela. Em produção, o backend systemd; nos testes e no Windows, o backend Popen.

```python
class ProcessBackend(Protocol):
    async def start(self, cfg: ServerConfig) -> None: ...
    async def stop(self, cfg: ServerConfig, timeout: int) -> None: ...
    async def send_command(self, server_id: str, line: str) -> None: ...
    async def pid(self, server_id: str) -> int | None: ...
```

Se preferir começar mais simples, a fase 1 pode usar só o backend Popen também na VM (exatamente como no seu prompt) e migrar para systemd quando o console entrar. A interface acima torna essa troca barata.

**Máquina de estados** (por servidor, com `asyncio.Lock`):

```
offline ──start──▶ starting ──"Done"/ping ok──▶ online ──stop──▶ stopping ──saiu──▶ offline
   ▲                  │ timeout/morreu                              │ timeout → kill
   └──────────────────┴─────────────────────────────────────────────┘
                     crashed (saída inesperada; reinício automático opcional)
```

### 2.2 API

REST para ações e consultas, versionada em `/api/v1`:

| Método | Rota | Fase |
|---|---|---|
| GET | `/health` (sem auth) | 1 |
| GET | `/servers`, `/servers/{id}` | 1 |
| POST | `/servers/{id}/start`, `/stop`, `/restart`, `/kill` | 1 (`kill` e `restart` triviais de incluir) |
| POST | `/servers/{id}/command` `{ "line": "say oi" }` | 2 |
| GET | `/servers/{id}/logs?tail=500` | 2 |
| GET/POST | `/servers/{id}/backups`, `/backups/{bid}/restore` | 3 |
| GET/PUT | `/servers/{id}/files?path=` | 4 |
| GET/POST | `/servers/{id}/schedules` | 4 |

**WebSocket** `/api/v1/servers/{id}/ws` com mensagens JSON tipadas:

```json
{"type": "console", "line": "[12:00:01] [Server thread/INFO]: Done (12.3s)!"}
{"type": "status",  "state": "online"}
{"type": "metrics", "cpu": 34.5, "ram_mb": 5120, "players": {"online": 2, "max": 20}}
{"type": "command", "line": "list"}          // cliente → servidor
```

- Ao conectar, o agente envia as últimas N linhas do log (buffer circular em memória) e depois transmite ao vivo.
- Métricas a cada 2 s só enquanto há cliente conectado, para não gastar CPU à toa.
- Um `ConsoleHub` por servidor faz o fan-out para vários clientes (`asyncio.Queue` por assinante, descartando mensagens se o cliente ficar lento).

### 2.3 Autenticação e segurança

- **Camada 1, rede:** bind no IP do Tailscale (`100.x.y.z`) e firewalld fechado para a porta do agente fora da interface `tailscale0`. Na Oracle Cloud, nada na security list para essa porta.
- **Camada 2, token:** fase 1 com token estático em `MC_AGENT_TOKEN` (`secrets.compare_digest`), como no seu prompt. No WebSocket, o token vai no primeiro frame ou em `Sec-WebSocket-Protocol`, não na URL (para não cair em logs).
- **Evolução (multiusuário, se um dia quiser):** login com senha (argon2) emitindo JWT curto + refresh token, e papéis (`admin`, `operador`, `leitura`) por servidor, o que é o modelo do Crafty.
- Comandos de console passam por uma allowlist opcional por papel; sem `shell=True` em lugar nenhum; caminhos de arquivo validados contra o diretório do servidor (evitar `../`).

### 2.4 Métricas

- **Por servidor:** `psutil` somando o processo Java e filhos (CPU %, RSS). Amostragem numa task de background a cada 2–5 s, nunca no handler HTTP.
- **Jogadores e TPS:** `mcstatus` (ping) para contagem, máximo e versão. Para nomes completos e TPS, use **RCON** (`list`, e no NeoForge `neoforge tps`): mais confiável que a `sample` do ping. RCON fica escutando só em `127.0.0.1`.
- **Da VM:** CPU, RAM, disco e rede totais (`psutil`), úteis na tela inicial.
- **Histórico:** grave uma amostra por minuto em **SQLite** (tabela `metrics(server_id, ts, cpu, ram_mb, players)`), com retenção de 7–30 dias. Dá para gráficos no app sem Prometheus. Se um dia quiser Grafana, exponha `/metrics` no formato Prometheus.

### 2.5 Backups (fase 3)

- Antes do backup: `save-off` + `save-all flush` pelo console, espera o "Saved the game", empacota, depois `save-on`. Isso evita mundo corrompido com o servidor ligado.
- Formato `tar.zst` (rápido e compacto; `zstandard` no Python ou o binário `zstd`), em `backups/<id>/<timestamp>.tar.zst`, com exclusões configuráveis (ex.: `logs/`, `crash-reports/`).
- Rotação: manter os últimos N ou por idade. Backups longos rodam como job em background com progresso via WebSocket.
- Opcional: cópia para o Object Storage da Oracle (tem cota gratuita) com `rclone`.
- Restore só com servidor desligado e com backup automático do estado atual antes.

### 2.6 Persistência

- `servers.yaml`: configuração declarativa (o que você já desenhou). O agente lê no boot e em `POST /reload`.
- `SQLite` (via `aiosqlite` ou SQLModel): histórico de métricas, registro de backups, agendamentos, auditoria ("quem ligou o quê e quando").
- `state.json` só no backend Popen; com systemd, o estado vem do próprio systemd.

---

## 3. Mapeamento com o Crafty Controller

| Função do Crafty | No MC Control | Fase |
|---|---|---|
| Ligar, parar, reiniciar, matar | `ServerManager` + systemd | **1** |
| Status, CPU/RAM, jogadores | `Monitor` (psutil, mcstatus, RCON) | **1** |
| Console ao vivo e envio de comandos | WebSocket + FIFO/tail do log | **2** |
| Logs históricos | `GET /logs`, journal | 2 |
| Backups e restauração | `BackupService` | 3 |
| Agendamentos (backup, restart, comando) | APScheduler + SQLite | 4 |
| Gerenciador de arquivos, upload de mods | `/files` com validação de caminho | 4 |
| Gráficos de desempenho | Histórico em SQLite + `fl_chart` | 4 |
| Criar servidor (baixar jar, aceitar EULA) | Templates (vanilla, Paper, NeoForge) | 5 |
| Usuários, papéis e permissões | JWT + papéis | 5 |
| Webhooks (Discord) | Notificações de evento | 5 |

---

## 4. Plano por fases

1. **Agente MVP:** ligar/desligar, status, métricas, jogadores, token, testes com `fake_server.py`. Exatamente a fase 1 do seu prompt, com a interface `ProcessBackend` desde o início.
2. **App MVP:** configuração, lista e detalhe com polling. A fase 2 do seu prompt.
3. **Console ao vivo:** WebSocket, FIFO, buffer de log; no app, tela de terminal com histórico de comandos. Aqui o app troca polling por WebSocket nas telas abertas.
4. **Backups**, depois **agendamentos, arquivos e gráficos**.
5. Só então pensar em **migrar o ATM10** do Crafty para o MC Control. Até lá ele continua intocado.

## 5. Como vamos construir juntos

Você quer que eu seja coautor e, ao mesmo tempo, quer escrever e aprender. Proposta de divisão:

- **Eu faço:** o esqueleto do repositório, configuração (venv, lint, pytest, CI), o `fake_server.py`, os testes de cada etapa *antes* da implementação, e revisão do seu código com explicações.
- **Você escreve:** o núcleo que mais ensina, que é a máquina de estados do `ServerManager` (start/stop com timeout, locks), o cliente da API no Flutter e as telas. Eu deixo o arquivo com assinaturas, docstrings e `TODO`s, e os testes dizem quando está pronto.
- **Ritmo:** uma etapa pequena por vez. Para cada uma, eu explico o conceito (ex.: grupos de processos, `asyncio.Lock`, Riverpod), você implementa, roda os testes, e eu reviso. Quando você travar, peço só a dúvida e dou uma dica antes de dar a resposta.
- **Quando faz sentido eu escrever direto:** código chato e repetitivo (modelos, boilerplate do systemd, firewall), ou quando você pedir.

## 6. Decisões

- **Processos:** Popen na fase 1 (roda no Windows, você aprende o básico de processos), systemd junto com o console. *(decidido em 15/10/2026)*
- **Jogadores:** ping primeiro, RCON depois. *(decidido em 15/10/2026)*
- **Repositório:** monorepo (`agent/` + `app/`). *(decidido em 15/10/2026)*
