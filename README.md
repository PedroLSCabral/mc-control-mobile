# MC Control

Sistema pessoal para controlar servidores de Minecraft numa VM remota pelo celular,
inspirado no Crafty Controller.

| Pasta | O que é | Estado |
|---|---|---|
| [`agent/`](agent/) | Agente em Python + FastAPI que roda na VM e liga, para e monitora os servidores | Fase 1, em andamento |
| [`app/`](app/) | App Flutter (Android primeiro, iOS depois) que conversa só com o agente | Fase 2 |
| [`docs/`](docs/) | Arquitetura e guias de estudo | |

O acesso ao agente é feito só pelo Tailscale; ele nunca fica exposto na internet.
