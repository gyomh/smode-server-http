#    #########      ###         ###      #########      #########         ###############
# ###               ######   ######   ###         ###   ###      ###      ###
# ###               ###   ###   ###   ###         ###   ###         ###   ###
#    #########      ###   ###   ###   ###         ###   ###         ###   ############
#             ###   ###         ###   ###         ###   ###         ###   ###
#             ###   ###         ###   ###         ###   ###      ###      ###
# ############      ###         ###      #########      #########         ###############
#
# -------------------- "Guillaume Henrion aka [GYOMH]" "30/09/2026" --------------------
# __________________________________________ ___________________________________________
# |                                       | |                                         |
# |    SMODE SERVER HTTP                  | | API HTTP/JSON pour Smode :              |
# |       V0.3                            | | - Base sur smode_bridge.py (queue +     |
# |                                       | |   thread principal, pas de deadlock)    |
# |_______________________________________| |_________________________________________|
# |    Instructions :                     | | - Ecoute 127.0.0.1 + IP(s) de Host      |
# | 1- Coller dans un Script Smode        | | - LAN : /status /slots /run             |
# | 2- Launch Mode = At Every Update      | | - /exec /eval : cette machine seule     |
# | 3- Saisir Port (Host = LAN, option)   | |   (ou LAN si Token renseigne)           |
# | 4- Glisser des Scripts dans slot1-8   | | - Chataigne / Stream Deck / navigateur  |
# |_______________________________________| |_________________________________________|
#
# HISTORIQUE
# V0.1 - 30/09/2026 - Premiere version : serveur HTTP/JSON sur 0.0.0.0 (local + LAN),
#                      endpoints /status /slots /run /exec /eval. /exec et /eval
#                      reserves a 127.0.0.1 sauf si Token renseigne (header X-Token
#                      ou ?token=). Port saisi a la main (defaut 8892).
# V0.2 - 30/09/2026 - Plus de 0.0.0.0 : ecoute sur 127.0.0.1 + IP(s) saisies dans
#                      Host (vide = localhost seulement). Fix : /exec et /eval acceptes
#                      quand le client == IP locale de la connexion (appel depuis
#                      le PC via sa propre IP LAN, qui donnait 403).
# V0.3 - 01/10/2026 - Version publiee. Host vide par defaut (localhost seulement). /exec et /eval
#                      refuses si la requete porte un en-tete Origin (page web : un site ne doit
#                      jamais pouvoir executer du code, meme vers localhost) ou un Host inconnu
#                      (DNS rebinding), sauf Token valide. CORS ouvert seulement pour /status /run.
#

port: Oil.PositiveInteger(8892)  # saisi a la main ; changer puis cocher restartServer
host: Oil.String("")  # IP(s) d'ecoute reseau, separees par des virgules (vide = localhost seulement). 127.0.0.1 est toujours actif
token: Oil.String("")  # autorise /exec et /eval depuis le reseau (header "X-Token: xxx" ou ?token=xxx)
slot1: Oil.createObject("WeakPointer(PythonScriptTool)")
slot2: Oil.createObject("WeakPointer(PythonScriptTool)")
slot3: Oil.createObject("WeakPointer(PythonScriptTool)")
slot4: Oil.createObject("WeakPointer(PythonScriptTool)")
slot5: Oil.createObject("WeakPointer(PythonScriptTool)")
slot6: Oil.createObject("WeakPointer(PythonScriptTool)")
slot7: Oil.createObject("WeakPointer(PythonScriptTool)")
slot8: Oil.createObject("WeakPointer(PythonScriptTool)")
restartServer: Oil.Boolean(False)  # cocher = redemarrage a chaud (se decoche tout seul)

import contextlib
import io
import json
import queue
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_EXEC_NAMESPACE = globals()
N_SLOTS = 8

if "_SMODE_HTTP_QUEUE" not in globals():
    _SMODE_HTTP_QUEUE = queue.Queue()

def _safeRepr(value):
    try:
        return repr(value)
    except Exception:
        return "<unrepr-able>"

def _slots():
    return [(i, getattr(script, f"slot{i}")) for i in range(1, N_SLOTS + 1)]

def _labelOf(tool):
    lab = tool.label
    return str(lab.get() if hasattr(lab, "get") else lab)

def run_slot(n):
    tool = getattr(script, f"slot{int(n)}").get()
    if tool is None:
        raise RuntimeError(f"slot{n} est vide")
    tool.execute.trig()
    return _labelOf(tool)

def run_script(name):
    for i, slot in _slots():
        tool = slot.get()
        if tool is not None and _labelOf(tool) == name:
            tool.execute.trig()
            return name
    raise RuntimeError(f"aucun slot ne contient un Script nomme {name!r}")

def list_slots():
    return {i: (_labelOf(s.get()) if s.get() is not None else None) for i, s in _slots()}

# --- Taches executees sur le thread principal (Oil interdit ailleurs) -------------------

def _task_status(_arg):
    return {"port": script.port.get(), "slots": list_slots()}

def _task_run(arg):
    return run_slot(arg) if str(arg).isdigit() else run_script(arg)

def _task_exec(code):
    exec(code, _EXEC_NAMESPACE)
    return _safeRepr(_EXEC_NAMESPACE["result"]) if "result" in _EXEC_NAMESPACE else None

def _task_eval(expr):
    return _safeRepr(eval(expr, _EXEC_NAMESPACE))

_TASKS = {"status": _task_status, "run": _task_run, "exec": _task_exec, "eval": _task_eval}
_PRIVILEGED = ("exec", "eval")  # code arbitraire : localhost ou token
_LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}  # valeurs acceptees pour l'en-tete Host (anti DNS rebinding)

class SmodeHttpHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_OPTIONS(self):
        self._respond(204, {})

    def _readParams(self):
        """Fusionne query string, corps JSON et corps form-urlencoded (Chataigne)."""
        u = urllib.parse.urlparse(self.path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        if body:
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    params.update(data)
            except Exception:
                params.update({k: v[0] for k, v in urllib.parse.parse_qs(body).items()})
        return u.path.strip("/").split("/"), params

    def _allowed(self, head, params):
        if head not in _PRIVILEGED:
            return True
        tk = script.token.get()
        if bool(tk) and (self.headers.get("X-Token") or params.get("token")) == tk:
            return True
        # Sans token : jamais depuis une page web (un navigateur ajoute toujours Origin sur une requete
        # inter-sites, meme vers 127.0.0.1) et seulement si Host est une adresse connue (DNS rebinding).
        if self.headers.get("Origin") is not None:
            return False
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in _ALLOWED_HOSTS:
            return False
        client = self.client_address[0]
        # meme machine : loopback, ou client == adresse locale de la connexion (ex: 192.168.1.20 -> 192.168.1.20)
        return client in _LOOPBACK or client == self.request.getsockname()[0]

    def _route(self):
        parts, params = self._readParams()
        head = parts[0]
        if head == "" and "code" in params:  # compat smode_bridge (POST / code=...)
            head = "exec"
        if head == "slots":
            head = "status"
        self._cors = head not in _PRIVILEGED
        if not self._allowed(head, params):
            self._respond(403, {"success": False, "error": f"/{head} reserve a localhost (ou token valide)"})
            return
        if head == "run":
            arg = parts[1] if len(parts) > 1 else params.get("slot", params.get("name"))
        elif head == "exec":
            arg = params.get("code")
        elif head == "eval":
            arg = params.get("expr")
        elif head == "status":
            arg = None
        else:
            self._respond(404, {"success": False, "error": f"endpoint inconnu: /{head}"})
            return
        if head != "status" and arg is None:
            self._respond(400, {"success": False, "error": "parametre manquant"})
            return
        box = {"task": head, "arg": urllib.parse.unquote(str(arg)) if arg is not None else None,
               "result": None, "done": threading.Event()}
        _SMODE_HTTP_QUEUE.put(box)
        if not box["done"].wait(timeout=15):
            self._respond(504, {"success": False, "error": "timeout: Script bien en 'At Every Update' ?"})
            return
        self._respond(200, box["result"])

    def _respond(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if getattr(self, "_cors", True):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def _hosts():
    extra = [h.strip() for h in script.host.get().split(",") if h.strip()]
    return ["127.0.0.1"] + [h for h in extra if h != "127.0.0.1"]

def _startServers(p, hosts):
    """Un serveur par IP precise (jamais 0.0.0.0). Une IP invalide n'arrete pas les autres."""
    global _ALLOWED_HOSTS
    _ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"} | set(hosts)
    servers = []
    for h in hosts:
        try:
            server = ThreadingHTTPServer((h, p), SmodeHttpHandler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
            print(f"[smode_server_http] ecoute sur {h}:{p}")
        except Exception as e:
            print(f"[smode_server_http] {h}:{p} impossible: {e!r}")
    return servers

def _processQueue():
    while not _SMODE_HTTP_QUEUE.empty():
        req = _SMODE_HTTP_QUEUE.get_nowait()
        out = io.StringIO()
        res = {"success": True, "result": None, "output": "", "error": None}
        _EXEC_NAMESPACE.pop("result", None)
        try:
            with contextlib.redirect_stdout(out):
                res["result"] = _TASKS[req["task"]](req["arg"])
        except Exception as e:
            res["success"] = False
            res["error"] = repr(e)
        res["output"] = out.getvalue()
        req["result"] = res
        req["done"].set()

def _armSlots():
    for i, slot in _slots():
        try:
            tool = slot.get()
            if tool is not None and tool.launchMode.get() != 0:
                tool.launchMode.set(0)
        except Exception as e:
            print(f"[smode_server_http] slot{i}: {e!r}")

def _restartServer():
    global _SMODE_HTTP_SERVERS
    old = _SMODE_HTTP_SERVERS
    p = script.port.get()
    hosts = _hosts()  # lu ici (thread principal) : Oil interdit dans le thread
    def _do():
        global _SMODE_HTTP_SERVERS
        for s in old:
            s.shutdown()
            s.server_close()
        _SMODE_HTTP_SERVERS = _startServers(p, hosts)
    threading.Thread(target=_do, daemon=True).start()

if "_SMODE_HTTP_SERVERS" not in globals():
    _SMODE_HTTP_SERVERS = _startServers(script.port.get(), _hosts())

if script.restartServer.get():
    script.restartServer.set(False)
    _restartServer()
_armSlots()
_processQueue()
