# Smode Server HTTP

*[English version](README.md)*

Un petit **serveur HTTP/JSON qui tourne dans un Script Smode**, pour que tout ce qui sait envoyer une requête HTTP
(Chataigne, un Stream Deck, une page web sur votre réseau, `curl`...) puisse déclencher des Scripts Smode et, si
besoin, exécuter du code dans Smode.

Il est dérivé du pont générique de [smode-mcp](https://github.com/gyomh/smode-mcp), mais avec un autre but :
**smode-mcp** permet à Claude de piloter Smode, **Smode Server HTTP** offre une API structurée à vos surfaces de
contrôle.

> **Expérimental, pas un outil officiel Smode.** Construit par essais et erreurs sur l'API Oil
> (voir [smode-oil-reference](https://github.com/gyomh/smode-oil-reference)). À utiliser sur un réseau de confiance.

## Installation

1. Glissez `smode_server_http.py` dans votre projet Smode.
2. Mettez son **Launch Mode** sur **At Every Update** (le serveur confie le travail au fil principal de Smode via
   une file, qui n'est traitée que pendant la mise à jour du Script).
3. Choisissez un **Port** (par défaut `8892`) et, seulement si d'autres machines doivent y accéder, renseignez
   **Host** avec la ou les IP de votre machine, séparées par des virgules. Vide = **localhost uniquement**.
4. Glissez les Scripts à déclencher dans **slot1 à slot8**. Ils passent en lancement manuel.

Après un changement de port ou d'hôtes, cochez **restartServer** (il se décoche seul) pour l'appliquer sans
redémarrer Smode.

## Endpoints

| Endpoint | Qui peut l'appeler | Ce qu'il fait |
|---|---|---|
| `GET /status` (ou `/slots`) | Réseau local | Le port et la liste des 8 slots |
| `GET /run/<n>` ou `/run/<nom du script>` | Réseau local | Déclenche le Script du slot `n`, ou du slot dont le Script porte ce nom |
| `POST /exec` avec `code=...` | Cette machine seulement (ou token valide) | Exécute du code Python dans Smode (affectez une variable `result` pour récupérer une valeur) |
| `GET /eval?expr=...` | Cette machine seulement (ou token valide) | Évalue une expression Python dans Smode |

Les paramètres sont acceptés en query string, en corps JSON ou en corps form-urlencoded (le défaut de Chataigne).
Les réponses sont en JSON : `{"success": true, "result": ..., "output": "...", "error": null}`.

Exemples :

```
curl http://127.0.0.1:8892/status
curl http://127.0.0.1:8892/run/1
curl -X POST http://127.0.0.1:8892/exec --data-urlencode "code=result = len(script.project.masterScene.layers)"
```

Dans Chataigne, un module HTTP pointé sur `127.0.0.1` et le port, avec une requête comme `/run/1`, suffit pour
déclencher un Script depuis un bouton de Stream Deck.

## Sécurité

`/exec` et `/eval` exécutent du code arbitraire dans Smode, ils sont donc verrouillés :

- Le serveur n'écoute jamais sur `0.0.0.0` : seulement sur `127.0.0.1` et les IP listées dans **Host**.
- `/exec` et `/eval` ne sont acceptés **que depuis la machine elle-même**, ou depuis le réseau avec un **Token**
  valide (en-tête `X-Token: xxx` ou `?token=xxx`).
- **Les requêtes venant d'une page web sont refusées** (toute requête portant un en-tête `Origin`, que les
  navigateurs ajoutent aux requêtes inter-sites, même vers `127.0.0.1`), de même que celles dont le `Host` n'est
  pas une de vos adresses (DNS rebinding). Sans cela, n'importe quel site visité pourrait demander à votre Smode
  d'exécuter du code.
- Le CORS n'est ouvert que pour `/status` et `/run`.
- `/run` et `/status` sont volontairement ouverts au réseau : ne mettez que des Scripts inoffensifs dans les slots.

## Crédit

Basé sur le motif file + fil principal de `smode_bridge.py`, de [smode-mcp](https://github.com/gyomh/smode-mcp).

## Licence

MIT — voir [LICENSE](LICENSE).
