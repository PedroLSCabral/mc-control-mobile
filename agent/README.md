# Agente

API HTTP que roda na VM e controla o ciclo de vida dos servidores de Minecraft.

## Rodar localmente (Windows ou Linux)

Precisa de Python 3.11 ou mais novo.

```powershell
cd agent
python -m venv .venv
.venv\Scripts\activate          # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy servers.example.yaml servers.yaml   # Linux: cp
copy .env.example .env                    # depois troque o token
```

Testes e linter:

```powershell
pytest                 # todos
pytest tests/test_manager.py -x   # para no primeiro que falhar
ruff check . ; ruff format .
```

Subir a API. O `--env-file` carrega o `.env` (token, caminho do servers.yaml e dos logs):

```powershell
uvicorn app.main:create_app --factory --env-file .env --port 8765
```

Testar com curl, trocando `abc` pelo token do seu `.env` (no PowerShell use `curl.exe`):

```bash
curl localhost:8765/health
curl -H "Authorization: Bearer abc" localhost:8765/servers
curl -X POST -H "Authorization: Bearer abc" localhost:8765/servers/fake/start
curl -H "Authorization: Bearer abc" localhost:8765/servers/fake
curl -X POST -H "Authorization: Bearer abc" localhost:8765/servers/fake/stop
```

O servidor `fake` roda `tests/fake_server.py`, que imita um servidor de Minecraft: imprime
`Done (...)!` quando "fica pronto" e encerra ao receber `stop`. Assim dá para testar tudo
sem Java. A documentação interativa da API fica em `http://localhost:8765/docs`.

## API

| Método | Rota | Auth |
|---|---|---|
| GET | `/health` | não |
| GET | `/servers` | sim |
| GET | `/servers/{id}` | sim |
| POST | `/servers/{id}/start` | sim (409 se não estiver desligado) |
| POST | `/servers/{id}/stop` | sim (409 se não estiver ligado) |

Start e stop respondem na hora com `starting`/`stopping`; o estado final aparece em
`GET /servers/{id}`.

## Estrutura

```
app/
  main.py      rotas e tratamento de erros
  manager.py   ciclo de vida dos servidores (start/stop/estado)
  models.py    schemas pydantic
  config.py    variáveis de ambiente e servers.yaml
  auth.py      verificação do token
tests/
  fake_server.py   servidor de Minecraft falso
  test_api.py      testes da API (com um manager de mentira)
  test_manager.py  testes do ciclo de vida, usando o fake server
```

Instalação na VM (Python 3.11 no Oracle Linux 9, systemd, firewall e Tailscale) entra
depois que o start/stop estiver pronto.
