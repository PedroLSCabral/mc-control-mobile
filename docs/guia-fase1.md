# Guia da fase 1: ligar e parar servidores

Este guia acompanha os `TODO(Pedro)` em `agent/app/manager.py`. A ideia é você escrever o
núcleo do agente; os testes em `agent/tests/test_manager.py` dizem quando cada passo está
pronto.

## O que já está pronto

- API (`main.py`), autenticação (`auth.py`), configuração (`config.py`) e modelos.
- `ServerManager.status`, `list`, `wait_for_state` e os helpers `_get` e `_spawn`.
- `fake_server.py` e todos os testes.
- `tests/test_api.py` já passa. `tests/test_manager.py` falha até você implementar.

## Conceitos antes de começar

**Processo filho.** Quando o agente liga um servidor, ele pede ao sistema operacional para
executar `java -jar server.jar` (ou o fake server). Esse programa vira um processo "filho"
do agente, com três canais: **stdin** (o que o agente escreve para ele, como `stop`),
**stdout** (o que ele imprime, os logs) e **stderr** (erros; aqui juntamos com o stdout).

**Popen e a versão asyncio.** `subprocess.Popen` é a forma clássica do Python de criar um
processo filho. Usamos `asyncio.create_subprocess_exec`, que é a mesma ideia, mas
"assíncrona": ler a saída e esperar o processo terminar não travam o agente, que continua
respondendo ao app enquanto isso.

**async/await em 30 segundos.** Uma função `async def` pode pausar em cada `await` e deixar
outras coisas rodarem. O FastAPI atende vários pedidos assim, numa thread só. Regra prática:
nunca use `time.sleep` dentro de `async def`; use `await asyncio.sleep`.

**Tarefas em segundo plano.** `self._spawn(rt, corrotina)` coloca uma função `async` para
rodar "ao lado", sem esperar por ela. É assim que `start` responde na hora enquanto
`_watch_output` fica lendo os logs.

**Lock.** `async with rt.lock:` garante que só um start ou stop por servidor rode por vez.
Sem isso, dois toques rápidos no botão poderiam ligar o servidor duas vezes.

**Por que o estado muda em lugares diferentes.** `start` coloca `starting`; quem descobre que
ficou `online` é o `_watch_output`, ao ver `Done (` no log; e quem coloca `offline` é também
o `_watch_output`, quando o processo termina, seja por stop, crash ou kill. Ter um único
lugar responsável pelo `offline` evita estados inconsistentes.

## Passos

1. **Ligar:** `start` e `_watch_output`.
   Rode `pytest tests/test_manager.py -x -k "starts_offline or unknown or then_online or writes_log or twice"`.
2. **Parar:** `stop` e `_graceful_stop` (sem o timeout ainda).
   Rode `pytest tests/test_manager.py -x -k "graceful or when_offline or again"`.
3. **Quando dá errado:** timeout no stop, crash durante o start e `_watch_start_timeout`.
   Rode `pytest` inteiro: tudo verde.
4. Suba a API e teste com curl (veja `agent/README.md`).

Se travar, me mande o erro do pytest e o trecho de código. Primeiro dou uma dica, e só
mostro a solução se você pedir.

## Depois da fase 1

Métricas (RAM/CPU com psutil), jogadores (ping com mcstatus) e a readoção de processos
quando o agente reinicia. Depois, o app Flutter.
