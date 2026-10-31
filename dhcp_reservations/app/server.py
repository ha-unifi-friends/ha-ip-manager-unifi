"""DHCP Reservations – Home Assistant add-on (Ingress).

Talks directly to the UniFi OS API of the gateway (Python standard library only).
"""
import ipaddress
import socket
import struct
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
VIEWS_PATH = os.environ.get("VIEWS_PATH", "/data/views.json")
VIEWS_LOCK = threading.Lock()
VERSIONS_DIR = os.environ.get("VERSIONS_DIR", "/data/versions")
SETTINGS_PATH = os.environ.get("SETTINGS_PATH", "/data/settings.json")
VERSIONS_LOCK = threading.Lock()
AUTO_RETENTION_DEFAULT = 30
KNOWN_PATH = os.environ.get("KNOWN_PATH", "/data/known_devices.json")
RULES_PATH = os.environ.get("RULES_PATH", "/data/rules.json")
SCANS_PATH = os.environ.get("SCANS_PATH", "/data/portscans.json")
VENDORS_PATH = os.environ.get("VENDORS_PATH", "/data/vendors.json")
VENDOR_API = os.environ.get("VENDOR_API", "https://api.macvendors.com/")
SCAN_LOCK = threading.Lock()
WATCH_INTERVAL = int(os.environ.get("WATCH_INTERVAL", "120"))


def daily_enabled():
    try:
        v = load_options().get("daily_version", True)
    except (OSError, ValueError):
        v = True
    return v is not False


def retention_days():
    try:
        return max(1, int(load_options().get("auto_version_retention_days") or AUTO_RETENTION_DEFAULT))
    except (OSError, ValueError, TypeError):
        return AUTO_RETENTION_DEFAULT
VERSION_FIELDS = ("name", "hostname", "oui", "note", "use_fixedip", "fixed_ip", "fixed_network_id", "network_id", "ip",
                  "conn", "is_device", "device_name", "device_model", "fixed_ap_enabled", "fixed_ap_mac",
                  "local_dns_record_enabled", "local_dns_record", "first_seen", "last_seen")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
PORT = int(os.environ.get("PORT", "8099"))
# Home Assistant ingress proxy; all other sources are rejected.
ALLOWED_CLIENTS = {"172.30.32.2", "127.0.0.1", "::1"}
DEV = os.environ.get("DEV") == "1"
MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def load_options():
    with open(OPTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


class UnifiError(Exception):
    def __init__(self, msg, status=502):
        super().__init__(msg)
        self.status = status


class Unifi:
    def __init__(self, opts):
        host = opts["unifi_host"].strip().rstrip("/")
        self.base = os.environ.get("UNIFI_BASE") or (
            host if host.startswith("http") else f"https://{host}"
        )
        self.user = opts["username"]
        self.password = opts["password"]
        self.site = opts.get("site") or "default"
        ctx = ssl.create_default_context()
        if not opts.get("verify_ssl", False):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(self.jar),
        )
        self.csrf = ""
        self.lock = threading.Lock()
        self.logged_in = False

    def _raw(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            resp = self.opener.open(req, timeout=20)
            status, headers, raw = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            status, headers, raw = e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise UnifiError(f"Controller not reachable ({self.base}): {e}")
        new = headers.get("X-Updated-CSRF-Token") or headers.get("X-CSRF-Token")
        if new:
            self.csrf = new
        try:
            payload = json.loads(raw.decode() or "{}")
        except ValueError:
            payload = {"raw": raw[:300].decode(errors="replace")}
        return status, payload

    def login(self):
        if not self.user or not self.password:
            raise UnifiError("Username/password missing in the add-on configuration.", 500)
        self.jar.clear()
        self.csrf = ""
        status, payload = self._raw(
            "POST", "/api/auth/login",
            {"username": self.user, "password": self.password, "remember": True},
        )
        if status != 200:
            raise UnifiError(f"Login to the controller failed (HTTP {status}). Check the credentials.", 502)
        self.logged_in = True
        log("Login OK")

    def call(self, method, path, body=None, v2=False):
        full = (f"/proxy/network/v2/api/site/{self.site}{path}" if v2
                else f"/proxy/network/api/s/{self.site}{path}")
        with self.lock:
            if not self.logged_in:
                self.login()
            status, payload = self._raw(method, full, body)
            if status in (401, 403):
                self.login()
                status, payload = self._raw(method, full, body)
        if isinstance(payload, list):
            if status >= 400:
                raise UnifiError(f"Controller returned HTTP {status}", 502)
            return payload
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        if status >= 400 or meta.get("rc") == "error":
            msg = meta.get("msg") or payload.get("message") or f"HTTP {status}"
            raise UnifiError(f"Controller error: {msg}", 400 if status < 500 else 502)
        return payload.get("data", []) if isinstance(payload, dict) else payload


def net_info(n):
    subnet = n.get("ip_subnet")
    cidr = None
    if subnet:
        try:
            cidr = str(ipaddress.ip_interface(subnet).network)
        except ValueError:
            pass
    vlan = n.get("vlan") if n.get("vlan_enabled") else None
    return {
        "id": n["_id"],
        "name": n.get("name", "?"),
        "vlan": int(vlan) if vlan not in (None, "") else None,
        "subnet": cidr,
        "gateway": subnet.split("/")[0] if subnet else None,
        "dhcp_start": n.get("dhcpd_start"),
        "dhcp_stop": n.get("dhcpd_stop"),
        "purpose": n.get("purpose"),
    }


def build_snapshot(api):
    users = api.call("GET", "/rest/user")
    online = api.call("GET", "/stat/sta")
    nets = [net_info(n) for n in api.call("GET", "/rest/networkconf")
            if n.get("purpose") != "wan" and n.get("ip_subnet")]
    sta = {c["mac"].lower(): c for c in online if c.get("mac")}
    # v2 API (as used by the UniFi UI): returns the connection type incl. Teleport/VPN.
    # Best effort: without it, WiFi/Wired is derived from the classic API.
    try:
        active = api.call("GET", "/clients/active?includeTrafficUsage=false&includeUnifiDevices=false", v2=True)
    except UnifiError as e:
        log("v2 clients/active not available:", e)
        active = []
    v2 = {}
    extra = []
    for a in active if isinstance(active, list) else []:
        mac = (a.get("mac") or "").lower()
        if mac:
            v2[mac] = a
        elif conn_of(a, {}, {}) == "teleport":
            extra.append(a)
    rows = {}
    for u in users:
        mac = (u.get("mac") or "").lower()
        if not mac:
            continue
        rows[mac] = merge(u, sta.get(mac), v2.get(mac))
    for mac, s in sta.items():
        if mac not in rows:
            rows[mac] = merge({}, s, v2.get(mac))
    for mac, a in v2.items():
        if mac not in rows:
            rows[mac] = merge({}, a, a)
    for i, a in enumerate(extra):
        r = merge({}, a, a)
        r["mac"] = ""
        rows[f"teleport:{a.get('id') or a.get('_id') or i}"] = r
    # UniFi devices (APs, switches, gateway) are not in stat/sta – status, IP and uplink come from stat/device.
    devs = api.call("GET", "/stat/device")
    for d in devs:
        mac = (d.get("mac") or "").lower()
        if not mac:
            continue
        rows[mac] = merge_device(rows.get(mac) or merge({}, {}, {}), d, nets)
    aps = sorted(({"mac": d["mac"].lower(), "name": d.get("name") or d["mac"]}
                  for d in devs if d.get("mac") and str(d.get("type", "")).startswith("uap")
                  and str(d.get("device_category") or "ap") == "ap"),
                 key=lambda d: d["name"].lower())
    return {
        "networks": nets,
        "aps": aps,
        "clients": sorted(rows.values(), key=lambda r: (r["name"] or r["hostname"] or r["mac"]).lower()),
        "fetched_at": int(time.time()),
    }


DEVICE_KIND = {"uap": "ap", "usw": "switch", "udm": "gateway", "ugw": "gateway", "uxg": "gateway", "usg": "gateway"}


def merge_device(row, d, nets):
    """Merge status, IP and uplink of an adopted UniFi device into a client row."""
    mac = d["mac"].lower()
    kind = DEVICE_KIND.get(str(d.get("type", "")), "device")
    if kind == "ap" and d.get("model", "").startswith("ULTE"):
        kind = "device"
    up = d.get("uplink") or d.get("last_uplink") or {}
    ip = d.get("ip") or ""
    if kind == "gateway":
        lan = next((n for n in nets if n.get("gateway")), None)
        ip = (lan or {}).get("gateway") or ip
    net = next((n for n in nets if n.get("subnet") and ip and _in(ip, n["subnet"])), None)
    wireless = str(up.get("type", "")).startswith("wireless")
    row.update({
        "mac": mac,
        "known": row.get("known", False),
        "is_device": True,
        "device_kind": kind,
        "device_name": d.get("name") or "",
        "device_model": d.get("model") or "",
        "hostname": row.get("hostname") or d.get("name") or "",
        "oui": row.get("oui") or "Ubiquiti Inc",
        "online": d.get("state") == 1,
        "ip": ip or row.get("ip", ""),
        "ip_is_last": False,
        "network_id": net["id"] if net else row.get("network_id", ""),
        "conn": "wifi" if wireless else "wired",
        "wired": not wireless,
        "uplink": up.get("uplink_device_name") or up.get("name") or "",
        "port": up.get("uplink_remote_port") or up.get("port_idx") if not wireless else None,
        "essid": "",
        "last_seen": d.get("last_seen") or row.get("last_seen") or 0,
    })
    if kind == "gateway":
        row["uplink"], row["port"] = "Internet (WAN)", None
    return row


def _in(ip, cidr):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr)
    except ValueError:
        return False


def conn_of(a, s, u):
    """'wifi' | 'wired' | 'teleport' – the v2 type takes precedence."""
    t = str(a.get("type") or a.get("connection_type") or "").upper()
    if "TELEPORT" in t or "VPN" in t or a.get("is_vpn") or s.get("is_vpn"):
        return "teleport"
    if "WIRELESS" in t or "WIFI" in t:
        return "wifi"
    if "WIRED" in t:
        return "wired"
    src = s if s else u
    return "wired" if src.get("is_wired") else "wifi"


def merge(u, s, a=None):
    s = s or {}
    a = a or {}
    ip = s.get("ip") or a.get("ip") or None
    conn = conn_of(a, s, u)
    port = s.get("sw_port") or a.get("sw_port")
    uplink = (s.get("last_uplink_name") or a.get("last_uplink_name") or a.get("uplink_name")
              or u.get("last_uplink_name") or "")
    return {
        "conn": conn,
        "port": port if conn == "wired" else None,
        "id": u.get("_id") or s.get("user_id") or s.get("_id"),
        "known": bool(u.get("_id")),
        "mac": (u.get("mac") or s.get("mac") or "").lower(),
        "name": u.get("name") or s.get("name") or "",
        "hostname": s.get("hostname") or u.get("hostname") or "",
        "oui": u.get("oui") or s.get("oui") or "",
        "note": u.get("note") or "",
        "use_fixedip": bool(u.get("use_fixedip")),
        "fixed_ip": u.get("fixed_ip") or "" if u.get("use_fixedip") else "",
        "fixed_network_id": u.get("network_id") or "" if u.get("use_fixedip") else "",
        "icon_id": u.get("dev_id_override") or u.get("dev_id") or s.get("dev_id_override") or s.get("dev_id") or None,
        "fixed_ap_enabled": bool(u.get("fixed_ap_enabled")),
        "fixed_ap_mac": (u.get("fixed_ap_mac") or "").lower() if u.get("fixed_ap_enabled") else "",
        "ap_mac": (s.get("ap_mac") or "").lower(),
        "vno_id": u.get("virtual_network_override_id") or "" if u.get("virtual_network_override_enabled") else "",
        "local_dns_record_enabled": bool(u.get("local_dns_record_enabled")),
        "local_dns_record": u.get("local_dns_record") or "",
        "online": bool(s or a),
        "ip": ip or u.get("last_ip") or "",
        "ip_is_last": not ip and bool(u.get("last_ip")),
        "network_id": s.get("network_id") or a.get("network_id") or u.get("last_connection_network_id") or "",
        "network_name": s.get("network") or a.get("network_name") or a.get("network") or "",
        "wired": conn == "wired",
        "essid": (s.get("essid") or a.get("essid") or "") if conn == "wifi" else "",
        "signal": s.get("signal") if conn == "wifi" else None,
        "uplink": uplink,
        "last_seen": s.get("last_seen") or u.get("last_seen") or 0,
        "first_seen": u.get("first_seen") or s.get("first_seen") or 0,
        "blocked": bool(u.get("blocked")),
    }


def clean_mac(v):
    mac = (v or "").strip().lower().replace("-", ":")
    if not MAC_RE.match(mac):
        raise UnifiError("Invalid MAC address.", 400)
    return mac


def validate_ip(ip, net):
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise UnifiError(f"“{ip}” is not a valid IP address.", 400)
    if net and net.get("subnet") and addr not in ipaddress.ip_network(net["subnet"]):
        raise UnifiError(f"{addr} is not in network {net['name']} ({net['subnet']}).", 400)
    return str(addr)


def save_client(api, body):
    """Create or update a client (name, note, fixed IP, network, AP lock, DNS)."""
    nets = {n["id"]: n for n in (net_info(x) for x in api.call("GET", "/rest/networkconf"))}
    mac = clean_mac(body.get("mac"))
    users = api.call("GET", "/rest/user")
    existing = next((u for u in users if (u.get("mac") or "").lower() == mac), None)
    payload = {"name": (body.get("name") or "").strip(), "note": (body.get("note") or "").strip()}
    payload["noted"] = True
    use_fixed = bool(body.get("use_fixedip"))
    payload["use_fixedip"] = use_fixed
    if use_fixed:
        net = nets.get(body.get("network_id") or "")
        if not net:
            raise UnifiError("Please choose a network (VLAN) for the reservation.", 400)
        payload["network_id"] = net["id"]
        payload["fixed_ip"] = validate_ip(body.get("fixed_ip") or "", net)
        unchanged = existing and existing.get("use_fixedip") and existing.get("fixed_ip") == payload["fixed_ip"]
        for u in ([] if unchanged else users):
            if u.get("use_fixedip") and u.get("fixed_ip") == payload["fixed_ip"] and u.get("mac", "").lower() != mac:
                raise UnifiError(f"{payload['fixed_ip']} is already reserved for {u.get('name') or u.get('mac')}.", 409)
    else:
        payload["fixed_ip"] = ""
    if "fixed_ap_enabled" in body:
        lock = bool(body.get("fixed_ap_enabled"))
        payload["fixed_ap_enabled"] = lock
        if lock:
            ap = clean_mac(body.get("fixed_ap_mac"))
            devs = api.call("GET", "/stat/device")
            if not any((d.get("mac") or "").lower() == ap and str(d.get("type", "")).startswith("uap") for d in devs):
                raise UnifiError("Selected access point not found.", 400)
            payload["fixed_ap_mac"] = ap
    dns = (body.get("local_dns_record") or "").strip()
    payload["local_dns_record_enabled"] = bool(body.get("local_dns_record_enabled")) and bool(dns)
    payload["local_dns_record"] = dns if payload["local_dns_record_enabled"] else ""

    if existing:
        api.call("PUT", f"/rest/user/{existing['_id']}", payload)
        log("Updated", mac, payload.get("fixed_ip"))
    else:
        payload["mac"] = mac
        api.call("POST", "/rest/user", payload)
        log("Created", mac, payload.get("fixed_ip"))
    return {"ok": True}


def remove_reservation(api, mac):
    mac = clean_mac(mac)
    u = next((u for u in api.call("GET", "/rest/user") if (u.get("mac") or "").lower() == mac), None)
    if not u:
        raise UnifiError("Client not found.", 404)
    api.call("PUT", f"/rest/user/{u['_id']}", {"use_fixedip": False, "fixed_ip": ""})
    log("Reservation removed", mac)
    return {"ok": True}


def reconnect_client(api, mac):
    """Kick a Wi-Fi client so it reconnects and requests a new DHCP lease (UniFi "Reconnect")."""
    mac = clean_mac(mac)
    api.call("POST", "/cmd/stamgr", {"cmd": "kick-sta", "mac": mac})
    log("Reconnect", mac)
    return {"ok": True}


def forget_client(api, mac):
    mac = clean_mac(mac)
    api.call("POST", "/cmd/stamgr", {"cmd": "forget-sta", "macs": [mac]})
    log("Forgotten", mac)
    return {"ok": True}


def load_views():
    try:
        with open(VIEWS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("views"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"views": [], "default": "all"}


def save_views(body):
    """Store user-defined views (built-in views live in the UI). Written atomically."""
    if not isinstance(body, dict) or not isinstance(body.get("views"), list):
        raise UnifiError("Invalid views payload.", 400)
    views = []
    for v in body["views"][:100]:
        if not isinstance(v, dict) or not str(v.get("id", "")).strip() or not str(v.get("name", "")).strip():
            raise UnifiError("Every view needs an id and a name.", 400)
        views.append({"id": str(v["id"])[:64], "name": str(v["name"]).strip()[:60], "state": v.get("state") or {}})
    data = {"views": views, "default": str(body.get("default") or "all")[:64]}
    with VIEWS_LOCK:
        tmp = VIEWS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, VIEWS_PATH)
    log("Views saved:", len(views))
    return data


# Devices from the Home Assistant device registry that carry a MAC connection.
HA_TEMPLATE = """{%- set ns = namespace(out=[]) -%}
{%- for did in states | map(attribute='entity_id') | map('device_id') | reject('none') | unique -%}
{%- set macs = device_attr(did, 'connections') | selectattr(0, 'eq', 'mac') | map(attribute=1) | map('lower') | list -%}
{%- if macs -%}
{%- set ns.out = ns.out + [{'id': did, 'macs': macs, 'name_by_user': device_attr(did, 'name_by_user'), 'name': device_attr(did, 'name'),
  'domains': device_attr(did, 'config_entries') | map('config_entry_attr', 'domain') | reject('none') | list, 'area': area_name(did)}] -%}
{%- endif -%}
{%- endfor -%}
{{ ns.out | tojson }}"""


def supervisor_token():
    """The token is in the environment, or – with the s6 init of the base image – only in s6's env store."""
    for key in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
        for folder in ("/run/s6/container_environment", "/var/run/s6/container_environment"):
            try:
                with open(os.path.join(folder, key), encoding="utf-8") as f:
                    v = f.read().strip()
                if v:
                    return v
            except OSError:
                pass
    return ""


def ha_devices():
    token = supervisor_token()
    base = os.environ.get("HA_API", "http://supervisor/core/api")
    if not token and "HA_API" not in os.environ:
        raise UnifiError("Home Assistant API is not available to the add-on (update the add-on to grant access).", 500)
    req = urllib.request.Request(base + "/template", data=json.dumps({"template": HA_TEMPLATE}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=30).read().decode()
    except urllib.error.HTTPError as e:
        raise UnifiError(f"Home Assistant API returned HTTP {e.code}.", 502)
    except (urllib.error.URLError, OSError) as e:
        raise UnifiError(f"Home Assistant not reachable: {e}", 502)
    try:
        devs = json.loads(raw)
    except ValueError:
        raise UnifiError("Unexpected answer from Home Assistant.", 502)
    out = []
    for d in devs:
        macs = [m for m in (normalize_mac(x) for x in d.get("macs") or []) if m]
        if macs:
            out.append({"id": d.get("id"), "macs": macs, "name_by_user": d.get("name_by_user") or "",
                        "name": d.get("name") or "", "domains": d.get("domains") or [], "area": d.get("area") or ""})
    log("HA devices with MAC:", len(out))
    return {"devices": out}


def normalize_mac(v):
    h = re.sub(r"[^0-9a-f]", "", str(v or "").lower())
    return ":".join(h[i:i + 2] for i in range(0, 12, 2)) if len(h) == 12 else None


# ---------------------------------------------------------------- versions
def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_settings():
    s = _read_json(SETTINGS_PATH, {})
    return {"daily": daily_enabled(), "baseline": s.get("baseline") or None, "retention_days": retention_days()}


def save_settings(body):
    cur = {"baseline": load_settings()["baseline"]}  # daily / retention live in the add-on configuration
    if "baseline" in body:
        b = body["baseline"]
        if b and not os.path.exists(_vpath(b)):
            raise UnifiError("Version not found.", 404)
        cur["baseline"] = b or None
    with VERSIONS_LOCK:
        _write_json(SETTINGS_PATH, cur)
    return load_settings()


def _vpath(vid):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", str(vid or "")):
        raise UnifiError("Invalid version id.", 400)
    return os.path.join(VERSIONS_DIR, f"{vid}.json")


def _index():
    return _read_json(os.path.join(VERSIONS_DIR, "index.json"), [])


def _save_index(idx):
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    _write_json(os.path.join(VERSIONS_DIR, "index.json"), idx)


def list_versions():
    idx = sorted(_index(), key=lambda m: m.get("created", 0), reverse=True)
    return {"versions": idx, "settings": load_settings()}


def create_version(api, kind="manual", label="", user=""):
    """kind: manual | daily | auto (auto = before a bulk action, label says which)."""
    snap = build_snapshot(api)
    now = int(time.time())
    vid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + "-" + os.urandom(2).hex()
    clients = {}
    for c in snap["clients"]:
        if c.get("mac"):
            clients[c["mac"]] = {k: c.get(k) for k in VERSION_FIELDS}
    meta = {"id": vid, "created": now, "kind": kind if kind in ("manual", "daily", "auto") else "manual",
            "label": (label or "").strip()[:80], "user": (user or "")[:60], "pinned": False,
            "devices": len(clients), "reserved": sum(1 for c in clients.values() if c.get("use_fixedip"))}
    with VERSIONS_LOCK:
        os.makedirs(VERSIONS_DIR, exist_ok=True)
        _write_json(_vpath(vid), {"meta": meta, "networks": snap["networks"], "aps": snap.get("aps", []), "clients": clients})
        idx = _index()
        idx.append(meta)
        _save_index(idx)
    log("Version saved:", vid, meta["kind"], meta["label"])
    purge_versions()
    return meta


def get_version(vid):
    data = _read_json(_vpath(vid), None)
    if not data:
        raise UnifiError("Version not found.", 404)
    return data


def device_history(mac):
    """The record of one MAC in every version (oldest first), with that version's networks and APs."""
    mac = normalize_mac(mac)
    if not mac:
        raise UnifiError("Invalid MAC.", 400)
    out = []
    for meta in sorted(_index(), key=lambda m: m.get("created", 0)):
        data = _read_json(_vpath(meta["id"]), None)
        if not data:
            continue
        out.append({"meta": meta, "record": (data.get("clients") or {}).get(mac),
                    "networks": data.get("networks") or [], "aps": data.get("aps") or []})
    return {"mac": mac, "versions": out}


def update_version(vid, body):
    with VERSIONS_LOCK:
        idx = _index()
        meta = next((m for m in idx if m["id"] == vid), None)
        if not meta:
            raise UnifiError("Version not found.", 404)
        if "label" in body:
            meta["label"] = str(body["label"] or "").strip()[:80]
        if "pinned" in body:
            meta["pinned"] = bool(body["pinned"])
        _save_index(idx)
        data = _read_json(_vpath(vid), None)
        if data:
            data["meta"] = meta
            _write_json(_vpath(vid), data)
    return meta


def delete_version(vid):
    with VERSIONS_LOCK:
        idx = [m for m in _index() if m["id"] != vid]
        _save_index(idx)
        try:
            os.remove(_vpath(vid))
        except OSError:
            pass
    if load_settings()["baseline"] == vid:
        save_settings({"baseline": None})
    log("Version deleted:", vid)
    return {"ok": True}


def purge_versions():
    """Automatic versions (daily / before bulk actions) are kept for the configured days; manual, pinned and the baseline forever."""
    limit = time.time() - retention_days() * 86400
    base = load_settings()["baseline"]
    old = [m for m in _index() if m.get("kind") in ("daily", "auto") and not m.get("pinned")
           and m["id"] != base and m.get("created", 0) < limit]
    for m in old:
        delete_version(m["id"])


DAILY_LOCK = threading.Lock()


def ensure_daily():
    """Create today's 'Daily' version if the option is on and none exists yet."""
    with DAILY_LOCK:
        if not load_settings()["daily"]:
            return
        today = time.strftime("%Y-%m-%d")
        if not any(m.get("kind") == "daily" and time.strftime("%Y-%m-%d", time.localtime(m.get("created", 0))) == today
                   for m in _index()):
            create_version(API, "daily", "Daily")


# ---------------------------------------------------------------- Home Assistant calls
def ha_call(path, body):
    """POST to the Home Assistant Core API through the Supervisor."""
    token = supervisor_token()
    base = os.environ.get("HA_API", "http://supervisor/core/api")
    if not token and "HA_API" not in os.environ:
        raise UnifiError("Home Assistant API is not available to the add-on.", 500)
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=20).read().decode()
    except urllib.error.HTTPError as e:
        raise UnifiError(f"Home Assistant API returned HTTP {e.code}.", 502)
    except (urllib.error.URLError, OSError) as e:
        raise UnifiError(f"Home Assistant not reachable: {e}", 502)
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


# ---------------------------------------------------------------- new-device notifications
def is_random_mac(mac):
    try:
        return bool(int(mac.split(":")[0], 16) & 2)
    except (ValueError, AttributeError, IndexError):
        return False


def notify_options():
    try:
        o = load_options()
    except (OSError, ValueError):
        o = {}
    nets = o.get("notify_networks") or []
    if isinstance(nets, str):
        nets = [x for x in re.split(r"[,;]", nets)]
    return {"on": o.get("notify_new_devices", True) is not False,
            "nets": [str(x).strip().lower() for x in nets if str(x).strip()],
            "random": o.get("notify_random_mac", False) is True}


def _net_matches(net, wanted):
    if not wanted:
        return True
    if not net:
        return False
    keys = {str(net.get("name") or "").lower(), str(net.get("vlan") or "").lower(), str(net.get("subnet") or "").lower()}
    return any(w in keys for w in wanted)


def check_new_devices(api, snap=None):
    """Remembers every client MAC; notifies Home Assistant about MACs it has not seen before."""
    snap = snap or build_snapshot(api)
    nets = {n["id"]: n for n in snap["networks"]}
    known = _read_json(KNOWN_PATH, None)
    clients = [c for c in snap["clients"] if c.get("mac") and not c.get("is_device")]
    if known is None:  # first run: learn silently
        _write_json(KNOWN_PATH, {c["mac"]: int(time.time()) for c in clients})
        log("Known devices initialised:", len(clients))
        return []
    new = [c for c in clients if c["mac"] not in known]
    if not new:
        return []
    now = int(time.time())
    for c in new:
        known[c["mac"]] = now
    _write_json(KNOWN_PATH, known)
    opt = notify_options()
    out = []
    for c in new:
        n = nets.get(c.get("network_id") or "") or nets.get(c.get("fixed_network_id") or "")
        if not opt["on"] or not _net_matches(n, opt["nets"]) or (is_random_mac(c["mac"]) and not opt["random"]):
            continue
        info = {"mac": c["mac"], "name": c.get("name") or "", "hostname": c.get("hostname") or "", "vendor": c.get("oui") or "",
                "ip": c.get("ip") or "", "network": (n or {}).get("name") or c.get("network_name") or "",
                "vlan": (n or {}).get("vlan"), "connection": c.get("conn") or "", "random_mac": is_random_mac(c["mac"])}
        out.append(info)
        try:
            ha_call("/events/clients_reservations_new_device", info)
        except UnifiError as e:
            log("Event failed:", e)
    if out:
        lines = [f"- **{x['name'] or x['hostname'] or 'Unknown'}** · `{x['mac']}` · {x['vendor'] or 'unknown vendor'} · "
                 f"{x['network'] or '?'}{' (' + str(x['vlan']) + ')' if x['vlan'] else ''} · {x['ip'] or 'no IP'}" for x in out]
        try:
            ha_call("/services/persistent_notification/create", {
                "title": f"New device{'s' if len(out) > 1 else ''} in the network ({len(out)})",
                "message": "\n".join(lines) + "\n\nOpen *Clients & Reservations* to name it or give it a fixed IP.",
                "notification_id": "clients_reservations_new_" + (out[0]["mac"].replace(":", "") if len(out) == 1 else str(now))})
        except UnifiError as e:
            log("Notification failed:", e)
        log("New devices:", ", ".join(x["mac"] for x in out))
    return out


# ---------------------------------------------------------------- vendor lookup (only the 3-byte OUI is sent)
def vendor_lookup_enabled():
    try:
        return load_options().get("vendor_lookup", True) is not False
    except (OSError, ValueError):
        return True


def fill_vendors(snap, limit=40):
    """Looks up the vendor of OUIs UniFi does not know (macvendors.com, max. 1 request per second)."""
    if not vendor_lookup_enabled():
        return 0
    cache = _read_json(VENDORS_PATH, {})
    now, todo = int(time.time()), []
    for c in snap["clients"]:
        mac = c.get("mac") or ""
        if not mac or c.get("oui") or c.get("is_device") or is_random_mac(mac):
            continue
        oui = mac[:8]
        hit = cache.get(oui)
        if hit and (hit.get("vendor") or now - hit.get("ts", 0) < 30 * 86400):
            continue
        if oui not in todo:
            todo.append(oui)
    done = 0
    for oui in todo[:limit]:
        vendor = None
        try:
            req = urllib.request.Request(VENDOR_API + oui, headers={"User-Agent": "clients-reservations-addon"})
            vendor = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace").strip()[:80]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                vendor = ""
            elif e.code == 429:
                log("Vendor lookup: rate limited, trying again later")
                break
        except (urllib.error.URLError, OSError) as e:
            log("Vendor lookup not reachable:", e)
            break
        if vendor is not None:
            cache[oui] = {"vendor": vendor, "ts": now}
            done += 1
        time.sleep(1.1)
    if done:
        _write_json(VENDORS_PATH, cache)
        log("Vendor lookup:", done, "prefixes")
    return done


def load_vendors():
    return {"vendors": {k: v.get("vendor", "") for k, v in _read_json(VENDORS_PATH, {}).items() if v.get("vendor")}}


def watch_worker():
    time.sleep(20)
    while True:
        try:
            if API:
                snap = build_snapshot(API)
                check_new_devices(API, snap)
                fill_vendors(snap)
        except Exception as e:  # noqa: BLE001
            log("Background check failed:", e)
        time.sleep(WATCH_INTERVAL)


# ---------------------------------------------------------------- network rules
RULE_FIELDS = ("vendor", "name", "hostname")


def load_rules():
    r = _read_json(RULES_PATH, [])
    return {"rules": r if isinstance(r, list) else []}


def save_rules(body):
    rules = []
    for r in (body or {}).get("rules") or []:
        f, v, n = str(r.get("field") or ""), str(r.get("contains") or "").strip(), str(r.get("network_id") or "")
        if f in RULE_FIELDS and v and n:
            rules.append({"field": f, "contains": v[:60], "network_id": n})
    _write_json(RULES_PATH, rules[:200])
    log("Rules saved:", len(rules))
    return {"rules": rules}


# ---------------------------------------------------------------- port check
# (port, service, scheme for a browser link or "")
SCAN_PORTS = [
    (21, "FTP", ""), (22, "SSH", ""), (23, "Telnet", ""), (25, "SMTP", ""), (53, "DNS", ""), (80, "HTTP", "http"),
    (81, "HTTP", "http"), (139, "NetBIOS", ""), (443, "HTTPS", "https"), (445, "SMB", ""), (554, "RTSP", ""),
    (631, "IPP printing", "http"), (1880, "Node-RED", "http"), (1883, "MQTT", ""), (3000, "HTTP", "http"),
    (3389, "RDP", ""), (5000, "HTTP", "http"), (5001, "HTTPS", "https"), (5900, "VNC", ""), (6053, "ESPHome API", ""),
    (7000, "AirPlay", ""), (8000, "HTTP", "http"), (8008, "HTTP", "http"), (8009, "Chromecast", ""), (8080, "HTTP", "http"),
    (8081, "HTTP", "http"), (8123, "Home Assistant", "http"), (8443, "HTTPS", "https"), (8883, "MQTT (TLS)", ""),
    (8888, "HTTP", "http"), (9000, "HTTP", "http"), (9100, "Printer (JetDirect)", ""), (32400, "Plex", "http"),
]


def _port_open(ip, port, timeout=0.7):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_title(scheme, ip, port):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{scheme}://{ip}:{port}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (port check)"})
        with urllib.request.urlopen(req, timeout=2.5, context=ctx if scheme == "https" else None) as r:
            html = r.read(65536).decode("utf-8", "replace")
            server = r.headers.get("Server") or ""
    except urllib.error.HTTPError as e:
        try:
            html = e.read(65536).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            html = ""
        server = (e.headers or {}).get("Server") or ""
    except Exception:  # noqa: BLE001
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    t = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    return (t or server)[:80]


def port_scan(body):
    mac = clean_mac(body.get("mac"))
    ip = str(body.get("ip") or "")
    try:
        if ipaddress.ip_address(ip).version != 4:
            raise ValueError
    except ValueError:
        raise UnifiError("Invalid IP address.", 400)
    if not SCAN_LOCK.acquire(blocking=False):
        raise UnifiError("Another port check is running – try again in a few seconds.", 409)
    try:
        found = []
        # small batches so an IDS/IPS does not see a burst
        for i in range(0, len(SCAN_PORTS), 6):
            batch = SCAN_PORTS[i:i + 6]
            res = {}
            threads = [threading.Thread(target=lambda p=p: res.__setitem__(p[0], _port_open(ip, p[0]))) for p in batch]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            found += [p for p in batch if res.get(p[0])]
            time.sleep(0.15)
        out = []
        for port, svc, scheme in found:
            title = _http_title(scheme, ip, port) if scheme else ""
            if not scheme and port in (80, 443):
                scheme = "http" if port == 80 else "https"
            out.append({"port": port, "service": svc, "scheme": scheme, "title": title})
        rec = {"ip": ip, "ts": int(time.time()), "open": out}
        scans = _read_json(SCANS_PATH, {})
        scans[mac] = rec
        _write_json(SCANS_PATH, scans)
        log("Port check", mac, ip, "open:", ",".join(str(x["port"]) for x in out) or "none")
        return rec
    finally:
        SCAN_LOCK.release()


def load_scans():
    return {"scans": _read_json(SCANS_PATH, {})}


# ---------------------------------------------------------------- ping (ICMP echo)
def _icmp_checksum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def ping(body, count=4, timeout=1.0):
    ip = str(body.get("ip") or "")
    try:
        if ipaddress.ip_address(ip).version != 4:
            raise ValueError
    except ValueError:
        raise UnifiError("Invalid IP address.", 400)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        raw = True
    except PermissionError:
        try:  # unprivileged ICMP (needs net.ipv4.ping_group_range)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP)
            raw = False
        except OSError:
            raise UnifiError("Ping is not permitted in this container.", 500)
    ident = os.getpid() & 0xFFFF
    times = []
    with sock:
        sock.settimeout(timeout)
        for seq in range(count):
            payload = struct.pack("!d", time.time()) + b"clients-reservations"
            hdr = struct.pack("!BBHHH", 8, 0, 0, ident, seq)
            pkt = struct.pack("!BBHHH", 8, 0, _icmp_checksum(hdr + payload), ident, seq) + payload
            t0 = time.perf_counter()
            try:
                sock.sendto(pkt, (ip, 0))
            except OSError as e:
                raise UnifiError(f"Ping failed: {e}", 502)
            got = None
            while True:
                left = timeout - (time.perf_counter() - t0)
                if left <= 0:
                    break
                sock.settimeout(left)
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    break
                if addr[0] != ip:
                    continue
                icmp = data[(data[0] & 0x0F) * 4:] if raw else data
                if len(icmp) >= 8 and icmp[0] == 0:
                    rseq = struct.unpack("!H", icmp[6:8])[0]
                    if rseq == seq and (not raw or struct.unpack("!H", icmp[4:6])[0] == ident):
                        got = (time.perf_counter() - t0) * 1000
                        break
            times.append(round(got, 2) if got is not None else None)
            if seq < count - 1:
                time.sleep(max(0.0, 0.3 - (time.perf_counter() - t0)))
    ok = [t for t in times if t is not None]
    res = {"ip": ip, "sent": count, "received": len(ok), "times": times,
           "min": min(ok) if ok else None, "avg": round(sum(ok) / len(ok), 2) if ok else None, "max": max(ok) if ok else None}
    log("Ping", ip, f"{len(ok)}/{count}")
    return res


# ---------------------------------------------------------------- wake on LAN
def wake_on_lan(body):
    mac = clean_mac(body.get("mac"))
    ip, bcast = str(body.get("ip") or ""), str(body.get("broadcast") or "")
    sent = []
    try:  # Home Assistant runs on the host network and reaches its own LAN segment
        ha_call("/services/wake_on_lan/send_magic_packet", {"mac": mac, **({"broadcast_address": bcast} if bcast else {})})
        sent.append("Home Assistant (wake_on_lan)")
    except UnifiError as e:
        log("HA wake_on_lan not available:", e)
    pkt = b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16
    for target in [t for t in (bcast, ip) if t]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(pkt, (target, 9))
            sent.append(target)
        except OSError as e:
            log("WoL to", target, "failed:", e)
    if not sent:
        raise UnifiError("Could not send the magic packet.", 502)
    log("Wake on LAN", mac, "via", ", ".join(sent))
    return {"ok": True, "via": sent}


def daily_worker():
    """Creates one 'Daily' version per day while the option is on."""
    while True:
        try:
            ensure_daily()
            purge_versions()
        except Exception as e:  # noqa: BLE001
            log("Daily version failed:", e)
        time.sleep(600)


API = None


class Handler(BaseHTTPRequestHandler):
    server_version = "dhcp-reservations/1.0"

    def log_message(self, fmt, *args):
        if DEV:
            log(fmt % args)

    def _allowed(self):
        if DEV or self.client_address[0] in ALLOWED_CLIENTS:
            return True
        self._send(403, {"error": "Only reachable through Home Assistant (Ingress)."})
        return False

    def _send(self, status, obj=None, body=None, ctype="application/json; charset=utf-8"):
        data = body if body is not None else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _user(self):
        # Home Assistant ingress passes the logged-in user
        return (self.headers.get("X-Remote-User-Display-Name") or self.headers.get("X-Remote-User-Name") or "").strip()

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            raise UnifiError("Request too large.", 400)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise UnifiError("Invalid JSON.", 400)

    def _route(self, method):
        if not self._allowed():
            return
        path = self.path.split("?")[0]
        # Ingress strips the prefix; match on the path suffix to be safe.
        try:
            if method == "GET" and (path == "/" or path.endswith("/index.html")):
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    return self._send(200, body=f.read(), ctype="text/html; charset=utf-8")
            if method == "GET" and path.endswith("/api/snapshot"):
                return self._send(200, build_snapshot(API))
            if method == "POST" and path.endswith("/api/client"):
                return self._send(200, save_client(API, self._json_body()))
            if method == "POST" and path.endswith("/api/unreserve"):
                return self._send(200, remove_reservation(API, self._json_body().get("mac")))
            if method == "GET" and path.endswith("/api/ha_devices"):
                return self._send(200, ha_devices())
            if method == "GET" and path.endswith("/api/views"):
                return self._send(200, load_views())
            if method == "POST" and path.endswith("/api/views"):
                return self._send(200, save_views(self._json_body()))
            m = re.search(r"/api/history/([0-9A-Fa-f:.-]{12,17})$", urllib.parse.unquote(path))
            if method == "GET" and m:
                return self._send(200, device_history(m.group(1)))
            m = re.search(r"/api/versions/([A-Za-z0-9_-]+)(/update|/delete)?$", path)
            if m:
                vid, act = m.group(1), m.group(2)
                if method == "GET" and not act:
                    return self._send(200, get_version(vid))
                if method == "POST" and act == "/update":
                    return self._send(200, update_version(vid, self._json_body()))
                if method == "POST" and act == "/delete":
                    return self._send(200, delete_version(vid))
            if method == "GET" and path.endswith("/api/versions"):
                return self._send(200, list_versions())
            if method == "POST" and path.endswith("/api/versions"):
                b = self._json_body()
                return self._send(200, create_version(API, b.get("kind", "manual"), b.get("label", ""), self._user()))
            if method == "POST" and path.endswith("/api/version_settings"):
                return self._send(200, save_settings(self._json_body()))
            if method == "POST" and path.endswith("/api/ping"):
                return self._send(200, ping(self._json_body()))
            if method == "GET" and path.endswith("/api/vendors"):
                return self._send(200, load_vendors())
            if method == "POST" and path.endswith("/api/portscan"):
                return self._send(200, port_scan(self._json_body()))
            if method == "GET" and path.endswith("/api/portscans"):
                return self._send(200, load_scans())
            if method == "GET" and path.endswith("/api/rules"):
                return self._send(200, load_rules())
            if method == "POST" and path.endswith("/api/rules"):
                return self._send(200, save_rules(self._json_body()))
            if method == "POST" and path.endswith("/api/wol"):
                return self._send(200, wake_on_lan(self._json_body()))
            if method == "POST" and path.endswith("/api/check_new"):
                return self._send(200, {"new": check_new_devices(API)})
            if method == "POST" and path.endswith("/api/reconnect"):
                return self._send(200, reconnect_client(API, self._json_body().get("mac")))
            if method == "POST" and path.endswith("/api/forget"):
                return self._send(200, forget_client(API, self._json_body().get("mac")))
            self._send(404, {"error": "Nicht gefunden"})
        except UnifiError as e:
            log("Error:", e)
            self._send(e.status, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            log("Unexpected error:", repr(e))
            self._send(500, {"error": f"Internal error: {e}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def main():
    global API
    API = Unifi(load_options())
    log(f"Starting on port {PORT}, controller {API.base}, site {API.site}")
    threading.Thread(target=daily_worker, daemon=True).start()
    threading.Thread(target=watch_worker, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
