#!/usr/bin/env python3
"""
Alfred Script Filter: Claude Account Usage  (v3 — session key + oauth + i18n)

Auth priority:
  1. CLAUDE_SESSION_KEY env / ~/.claude-session-key  →  Cookie auth via claude.ai API
  2. CLAUDE_OAUTH_TOKEN env                          →  Bearer auth via anthropic API
  3. Claude Code Keychain                            →  Bearer auth (auto-refresh)
  4. ~/.claude/.credentials.json                     →  Bearer auth (auto-refresh)
"""

import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_AI_API = "https://claude.ai/api"
KEYCHAIN_SERVICE = "Claude Code-credentials"
USER_AGENT = "claude-code/2.1.5"
ANTHROPIC_BETA = "oauth-2025-04-20"
SESSION_KEY_FILE = os.path.expanduser("~/.claude-session-key")
CREDENTIALS_FILE = os.path.expanduser("~/.claude/.credentials.json")
STATUS_URL = "https://status.claude.com/api/v2/summary.json"

FALLBACK_TOKEN_ENDPOINTS = [
    "https://claude.ai/oauth/token",
    "https://claude.ai/api/oauth/token",
]

CACHE_DIR = os.environ.get(
    "alfred_workflow_cache",
    os.path.join(os.environ.get("TMPDIR", "/tmp"), "claude-usage-alfred"),
)
ENDPOINT_CACHE_FILE = os.path.join(CACHE_DIR, "token_endpoint.json")
USAGE_CACHE_FILE = os.path.join(CACHE_DIR, "usage_cache.json")
ORG_CACHE_FILE = os.path.join(CACHE_DIR, "org_cache.json")
STATUS_CACHE_FILE = os.path.join(CACHE_DIR, "status_cache.json")
CACHE_TTL = 60
ORG_CACHE_TTL = 3600
STATUS_CACHE_TTL = 120


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  i18n
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANG = os.environ.get("CLAUDE_USAGE_LANG", "zh").strip().lower()
if LANG not in ("zh", "en"):
    LANG = "zh"

STRINGS = {
    # ── errors ──
    "no_creds":            {"zh": "未找到 Claude 登录凭证",
                            "en": "No Claude credentials found"},
    "no_creds_sub":        {"zh": "请设置 Session Key 或运行 claude auth login",
                            "en": "Set a Session Key or run claude auth login"},
    "fetch_fail":          {"zh": "获取用量失败",
                            "en": "Failed to fetch usage"},
    "rate_limited":        {"zh": "请求过于频繁，已被限流 (429)",
                            "en": "Rate limited (429)"},
    "rate_limited_sub":    {"zh": "请等待 30 秒后重试",
                            "en": "Please wait 30 seconds and retry"},
    "org_id_fail":         {"zh": "无法获取组织 ID，Session Key 可能已失效",
                            "en": "Cannot get org ID, Session Key may have expired"},
    "sk_expired":          {"zh": "Session Key 已失效 (HTTP {code})，请更新",
                            "en": "Session Key expired (HTTP {code}), please update"},
    # ── session key help ──
    "sk_update":           {"zh": "Session Key 已过期，请更新",
                            "en": "Session Key expired, please update"},
    "sk_update_sub":       {"zh": "回车打开 claude.ai 登录页面",
                            "en": "Press Enter to open claude.ai"},
    "sk_step":             {"zh": "步骤: 打开 EditThisCookie 插件 → 找到 sessionKey",
                            "en": "Open EditThisCookie extension → find sessionKey"},
    "sk_step_sub":         {"zh": "复制 sk-ant-sid... 值 → 粘贴到 Workflow 配置或 ~/.claude-session-key",
                            "en": "Copy sk-ant-sid... value → paste in Workflow config or ~/.claude-session-key"},
    "sk_alt":              {"zh": "备选: 运行 claude auth login 重新登录",
                            "en": "Alt: run claude auth login to re-authenticate"},
    # ── usage display ──
    "5h_usage":            {"zh": "5 小时用量",  "en": "5-Hour Usage"},
    "7d_usage":            {"zh": "7 天用量",    "en": "7-Day Usage"},
    "opus_weekly":         {"zh": "Opus 周用量",  "en": "Opus Weekly"},
    "sonnet_weekly":       {"zh": "Sonnet 周用量","en": "Sonnet Weekly"},
    "oauth_weekly":        {"zh": "OAuth Apps 周用量", "en": "OAuth Apps Weekly"},
    "no_data":             {"zh": "无数据",       "en": "No data"},
    "no_data_sub":         {"zh": "可能尚未使用",  "en": "Possibly not used yet"},
    "no_reset":            {"zh": "暂无重置时间",  "en": "No reset time available"},
    "open_usage":          {"zh": "回车打开 Usage","en": "Enter to open Usage"},
    "cached":              {"zh": "缓存",         "en": "cached"},
    "reset_done":          {"zh": "已重置",       "en": "reset"},
    "reset_in":            {"zh": "后重置",       "en": "until reset"},
    # ── status ──
    "status_all_ok":       {"zh": "所有服务正常",   "en": "All Systems Operational"},
    "status_minor":        {"zh": "部分服务降级",   "en": "Partially Degraded"},
    "status_major":        {"zh": "主要服务中断",   "en": "Major Outage"},
    "status_critical":     {"zh": "严重服务中断",   "en": "Critical Outage"},
    "status_title":        {"zh": "Claude 服务状态","en": "Claude Status"},
    "status_unknown":      {"zh": "未知",          "en": "Unknown"},
    "status_unavail":      {"zh": "无法获取状态信息，回车打开 status.claude.com",
                            "en": "Cannot fetch status, Enter to open status.claude.com"},
    "status_open":         {"zh": "回车打开 status.claude.com",
                            "en": "Enter to open status.claude.com"},
    "status_details":      {"zh": "回车查看详情",   "en": "Enter for details"},
    "affected":            {"zh": "受影响",        "en": "Affected"},
    "active_incidents":    {"zh": "个活跃事件",     "en": "active incident(s)"},
    "incident_unknown":    {"zh": "未知事件",       "en": "Unknown incident"},
    "incident_status":     {"zh": "状态",          "en": "Status"},
    "copy_json":           {"zh": "⌘+回车 复制原始用量 JSON 到剪贴板",
                            "en": "⌘+Enter to copy raw usage JSON to clipboard"},
    "view_status":         {"zh": "查看 Claude 服务状态",
                            "en": "View Claude Service Status"},
}


def t(key, **kwargs):
    s = STRINGS.get(key, {}).get(LANG, key)
    if kwargs:
        s = s.format(**kwargs)
    return s


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  JWT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def decode_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Keychain I/O
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _keychain_account():
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        for line in (r.stdout + r.stderr).split("\n"):
            if '"acct"<blob>=' in line:
                v = line.split('"acct"<blob>=', 1)[1].strip()
                if v.startswith("0x"):
                    return bytes.fromhex(v[2:]).decode("utf-8", errors="replace")
                if v.startswith('"') and v.endswith('"'):
                    return v[1:-1]
                if v in ("<NULL>", ""):
                    return ""
                return v
    except Exception:
        pass
    return ""


def read_keychain():
    account = _keychain_account()
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return account, None
        return account, json.loads(r.stdout.strip())
    except Exception:
        return account, None


def write_keychain(account, creds):
    try:
        return (
            subprocess.run(
                [
                    "security", "add-generic-password", "-U",
                    "-s", KEYCHAIN_SERVICE,
                    "-a", account or "",
                    "-w", json.dumps(creds, ensure_ascii=False),
                ],
                capture_output=True, timeout=5,
            ).returncode == 0
        )
    except Exception:
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Credentials file (~/.claude/.credentials.json)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def read_credentials_file():
    for path in [CREDENTIALS_FILE, os.path.expanduser("~/.claude/credentials.json")]:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            continue
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Session Key support
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_session_key():
    sk = os.environ.get("CLAUDE_SESSION_KEY", "").strip()
    if sk:
        return sk
    try:
        with open(SESSION_KEY_FILE) as f:
            sk = f.read().strip()
            if sk:
                return sk
    except Exception:
        pass
    return None


def _session_request(url, session_key):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cookie": f"sessionKey={session_key}",
            "User-Agent": "Mozilla/5.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _read_org_cache():
    try:
        with open(ORG_CACHE_FILE) as f:
            c = json.load(f)
            if datetime.now(timezone.utc).timestamp() - c.get("ts", 0) < ORG_CACHE_TTL:
                return c.get("org_id")
    except Exception:
        return None


def _write_org_cache(org_id):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(ORG_CACHE_FILE, "w") as f:
            json.dump({"org_id": org_id, "ts": datetime.now(timezone.utc).timestamp()}, f)
    except Exception:
        pass


def fetch_org_id(session_key):
    cached = _read_org_cache()
    if cached:
        return cached
    try:
        orgs = _session_request(f"{CLAUDE_AI_API}/organizations", session_key)
        if isinstance(orgs, list) and orgs:
            org_id = orgs[0].get("uuid") or orgs[0].get("id")
            if org_id:
                _write_org_cache(org_id)
                return org_id
    except Exception:
        pass
    return None


def fetch_usage_session(session_key):
    org_id = fetch_org_id(session_key)
    if not org_id:
        return {"error": t("org_id_fail")}
    try:
        data = _session_request(
            f"{CLAUDE_AI_API}/organizations/{org_id}/usage", session_key
        )
        return _normalize_session_usage(data)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        if e.code in (401, 403):
            try:
                os.remove(ORG_CACHE_FILE)
            except Exception:
                pass
            return {"error": t("sk_expired", code=e.code)}
        return {"error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def _normalize_session_usage(data):
    if "five_hour" in data or "seven_day" in data:
        return data
    result = {}
    if isinstance(data, dict):
        inner = data.get("usage", data)
        for key in ("five_hour", "seven_day", "seven_day_opus",
                     "seven_day_sonnet", "seven_day_oauth_apps"):
            if key in inner:
                result[key] = inner[key]
        camel_map = {
            "fiveHour": "five_hour", "sevenDay": "seven_day",
            "sevenDayOpus": "seven_day_opus", "sevenDaySonnet": "seven_day_sonnet",
            "sevenDayOauthApps": "seven_day_oauth_apps",
        }
        for camel, snake in camel_map.items():
            if camel in inner and snake not in result:
                result[snake] = inner[camel]
        if result:
            return result
    return data if isinstance(data, dict) else {"error": "unexpected response format"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Token endpoint discovery
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _read_endpoint_cache():
    try:
        with open(ENDPOINT_CACHE_FILE) as f:
            c = json.load(f)
            if datetime.now(timezone.utc).timestamp() - c.get("ts", 0) < 86400:
                return c.get("url")
    except Exception:
        return None


def _write_endpoint_cache(url):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(ENDPOINT_CACHE_FILE, "w") as f:
            json.dump({"url": url, "ts": datetime.now(timezone.utc).timestamp()}, f)
    except Exception:
        pass


def _discover_from_wellknown(issuer):
    bases = [b for b in ([issuer] if issuer else []) + ["https://claude.ai"] if b]
    for base in bases:
        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        ):
            try:
                req = urllib.request.Request(
                    base.rstrip("/") + path,
                    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ep = json.loads(resp.read().decode()).get("token_endpoint")
                    if ep:
                        _write_endpoint_cache(ep)
                        return ep
            except Exception:
                continue
    return None


def resolve_token_endpoints(issuer=None):
    seen, result = set(), []
    def _add(u):
        if u and u not in seen:
            seen.add(u)
            result.append(u)
    _add(_read_endpoint_cache())
    _add(_discover_from_wellknown(issuer))
    for fb in FALLBACK_TOKEN_ENDPOINTS:
        _add(fb)
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Token refresh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _post_refresh(endpoint, refresh_tok, client_id=None):
    params = {"grant_type": "refresh_token", "refresh_token": refresh_tok}
    if client_id:
        params["client_id"] = client_id
    try:
        req = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode(params).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
                "anthropic-beta": ANTHROPIC_BETA,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            if "access_token" in body:
                _write_endpoint_cache(endpoint)
                return body
    except Exception:
        pass
    return None


def do_refresh(refresh_tok, old_access=None):
    issuer = client_id = None
    if old_access:
        jwt = decode_jwt(old_access)
        if jwt:
            issuer = jwt.get("iss")
            client_id = jwt.get("azp") or jwt.get("client_id")
    for ep in resolve_token_endpoints(issuer):
        result = _post_refresh(ep, refresh_tok, client_id)
        if result:
            return result
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Expiry detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _ts_remaining(ts):
    try:
        if ts > 1e12:
            ts /= 1000
        return (
            datetime.fromtimestamp(ts, tz=timezone.utc).timestamp()
            - datetime.now(timezone.utc).timestamp()
        )
    except Exception:
        return None


def token_expired(oauth):
    for key in ("expiresAt", "expires_at"):
        ea = oauth.get(key)
        if ea is not None:
            try:
                rem = _ts_remaining(float(ea))
                if rem is not None:
                    return rem < 300
            except (ValueError, TypeError):
                pass
    tok = oauth.get("accessToken", "")
    if tok:
        jwt = decode_jwt(tok)
        if jwt and "exp" in jwt:
            rem = _ts_remaining(float(jwt["exp"]))
            if rem is not None:
                return rem < 300
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Persist refreshed tokens
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def apply_refresh_result(account, full_creds, oauth, token_resp, old_refresh):
    new_access = token_resp.get("access_token")
    if not new_access:
        return None
    oauth["accessToken"] = new_access
    oauth["refreshToken"] = token_resp.get("refresh_token", old_refresh)
    if "expires_in" in token_resp:
        oauth["expiresAt"] = int(
            datetime.now(timezone.utc).timestamp()
        ) + int(token_resp["expires_in"])
    full_creds["claudeAiOauth"] = oauth
    write_keychain(account, full_creds)
    return new_access


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Obtain OAuth token (with multi-source fallback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _try_oauth_from_creds(creds, account=None):
    if not creds:
        return None
    oauth = creds.get("claudeAiOauth", {})
    access = oauth.get("accessToken")
    refresh = oauth.get("refreshToken")
    if not access and not refresh:
        return None
    expired = token_expired(oauth)
    if expired is True and refresh:
        resp = do_refresh(refresh, access)
        if resp:
            new = apply_refresh_result(account or "", creds, oauth, resp, refresh)
            if new:
                return new
    if expired is True:
        return None
    return access


def obtain_oauth_token():
    env = os.environ.get("CLAUDE_OAUTH_TOKEN", "").strip()
    if env:
        return env
    account, creds = read_keychain()
    token = _try_oauth_from_creds(creds, account)
    if token:
        return token
    file_creds = read_credentials_file()
    token = _try_oauth_from_creds(file_creds)
    if token:
        return token
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Usage API (OAuth) + caching
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fetch_usage_oauth(token):
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {token}",
            "anthropic-beta": ANTHROPIC_BETA,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def read_usage_cache():
    try:
        with open(USAGE_CACHE_FILE) as f:
            cache = json.load(f)
        if datetime.now(timezone.utc).timestamp() - cache.get("_ts", 0) < CACHE_TTL:
            data = cache.copy()
            data.pop("_ts", None)
            return data
    except Exception:
        pass
    return None


def read_stale_cache():
    try:
        with open(USAGE_CACHE_FILE) as f:
            cache = json.load(f)
        age = datetime.now(timezone.utc).timestamp() - cache.get("_ts", 0)
        data = cache.copy()
        data.pop("_ts", None)
        return data, age
    except Exception:
        return None, 0


def write_usage_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache = data.copy()
        cache["_ts"] = datetime.now(timezone.utc).timestamp()
        with open(USAGE_CACHE_FILE, "w") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Claude service status
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS_ICONS = {"none": "✅", "minor": "🟡", "major": "🟠", "critical": "🔴"}


def _read_status_cache():
    try:
        with open(STATUS_CACHE_FILE) as f:
            c = json.load(f)
            if datetime.now(timezone.utc).timestamp() - c.get("_ts", 0) < STATUS_CACHE_TTL:
                c2 = c.copy()
                c2.pop("_ts", None)
                return c2
    except Exception:
        pass
    return None


def _write_status_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache = data.copy()
        cache["_ts"] = datetime.now(timezone.utc).timestamp()
        with open(STATUS_CACHE_FILE, "w") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_claude_status():
    cached = _read_status_cache()
    if cached:
        return cached
    try:
        req = urllib.request.Request(
            STATUS_URL,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            _write_status_cache(data)
            return data
    except Exception:
        return None


def build_status_items(data):
    if not data:
        return [{
            "title": f"🌐 {t('view_status')}",
            "subtitle": t("status_unavail"),
            "arg": "https://status.claude.com/#",
            "valid": True, "icon": {"path": "icon.png"},
        }]

    items = []
    status = data.get("status", {})
    indicator = status.get("indicator", "none")
    icon = STATUS_ICONS.get(indicator, "❓")
    label_map = {"none": "status_all_ok", "minor": "status_minor",
                 "major": "status_major", "critical": "status_critical"}
    label = t(label_map.get(indicator, "status_unknown"))

    components = data.get("components", [])
    degraded = [c for c in components
                if c.get("status") != "operational" and c.get("name")]
    incidents = data.get("incidents", [])

    if indicator == "none" and not incidents:
        items.append({
            "title": f"{icon} {t('status_title')}: {label}",
            "subtitle": t("status_open"),
            "arg": "https://status.claude.com/#",
            "valid": True, "icon": {"path": "icon.png"},
        })
    else:
        sub_parts = []
        if degraded:
            names = ", ".join(c["name"] for c in degraded[:4])
            sub_parts.append(f"{t('affected')}: {names}")
        if incidents:
            sub_parts.append(f"{len(incidents)} {t('active_incidents')}")
        subtitle = " · ".join(sub_parts) if sub_parts else t("status_details")

        items.append({
            "title": f"{icon} {t('status_title')}: {label}",
            "subtitle": f"{subtitle}  ·  {t('status_open')}",
            "arg": "https://status.claude.com/#",
            "valid": True, "icon": {"path": "icon.png"},
        })
        for inc in incidents[:2]:
            inc_name = inc.get("name", t("incident_unknown"))
            inc_status = inc.get("status", "")
            inc_icon = "🔶" if inc.get("impact") == "minor" else "🔴"
            items.append({
                "title": f"  {inc_icon} {inc_name}",
                "subtitle": f"{t('incident_status')}: {inc_status}",
                "arg": inc.get("shortlink", "https://status.claude.com/#"),
                "valid": True, "icon": {"path": "icon.png"},
            })

    return items


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Display helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def time_until_reset(resets_at):
    if not resets_at:
        return None
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        total = int((dt - datetime.now(timezone.utc)).total_seconds())
        if total <= 0:
            return t("reset_done")
        d, rem = divmod(total, 86400)
        h, rem = divmod(rem, 3600)
        m, _ = divmod(rem, 60)
        parts = []
        if d:
            parts.append(f"{d}d")
        if h:
            parts.append(f"{h}h")
        parts.append(f"{m}m")
        return " ".join(parts) + " " + t("reset_in")
    except Exception:
        return None


def usage_bar(pct, width=20):
    filled = max(0, min(width, int(round(pct / 100 * width))))
    return "█" * filled + "░" * (width - filled)


def usage_icon(pct):
    if pct >= 90:
        return "🔴"
    if pct >= 70:
        return "🟡"
    if pct >= 40:
        return "🟠"
    return "🟢"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Fetch usage (unified: session key → OAuth, with cache)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fetch_usage_data():
    cached = read_usage_cache()
    if cached is not None:
        return cached, True, "cache"

    session_key = get_session_key()
    if session_key:
        data = fetch_usage_session(session_key)
        if "error" not in data:
            write_usage_cache(data)
            return data, False, "session"

    oauth_token = obtain_oauth_token()
    if oauth_token:
        data = fetch_usage_oauth(oauth_token)
        if "error" in data and "401" in str(data.get("error", "")):
            account, creds = read_keychain()
            if creds:
                oauth = creds.get("claudeAiOauth", {})
                refresh = oauth.get("refreshToken")
                if refresh:
                    resp = do_refresh(refresh, oauth_token)
                    if resp:
                        new = apply_refresh_result(account, creds, oauth, resp, refresh)
                        if new:
                            data = fetch_usage_oauth(new)
        if "error" not in data:
            write_usage_cache(data)
            return data, False, "oauth"
        if "429" in str(data.get("error", "")):
            stale, age = read_stale_cache()
            if stale:
                return stale, True, "cache"
            return data, False, None
        return data, False, None

    return None, False, None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Session key help items
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _session_key_help_items():
    return [
        {
            "title": f"🔑 {t('sk_update')}",
            "subtitle": t("sk_update_sub"),
            "arg": "https://claude.ai",
            "valid": True, "icon": {"path": "icon.png"},
        },
        {
            "title": f"📌 {t('sk_step')}",
            "subtitle": t("sk_step_sub"),
            "valid": False, "icon": {"path": "icon.png"},
        },
        {
            "title": f"📖 {t('sk_alt')}",
            "arg": "claude auth login",
            "valid": True, "icon": {"path": "icon.png"},
        },
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Alfred items
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODEL_ROWS = [
    ("seven_day_opus",      "opus_weekly"),
    ("seven_day_sonnet",    "sonnet_weekly"),
    ("seven_day_oauth_apps","oauth_weekly"),
]


def build_items():
    items = []
    data, from_cache, auth_method = fetch_usage_data()

    if data is None:
        items.append({
            "title": f"⚠️ {t('no_creds')}",
            "subtitle": t("no_creds_sub"),
            "valid": False, "icon": {"path": "icon.png"},
        })
        items.extend(_session_key_help_items())
        return items

    if "error" in data:
        err_msg = str(data["error"])
        items.append({
            "title": f"❌ {t('fetch_fail')}",
            "subtitle": err_msg[:100],
            "valid": False, "icon": {"path": "icon.png"},
        })
        if "401" in err_msg or "403" in err_msg or "expired" in err_msg.lower() or "失效" in err_msg:
            items.extend(_session_key_help_items())
        elif "429" in err_msg:
            items.append({
                "title": f"⏳ {t('rate_limited')}",
                "subtitle": t("rate_limited_sub"),
                "valid": False, "icon": {"path": "icon.png"},
            })
        return items

    cache_note = f"  ⚡ {t('cached')}" if from_cache else ""

    # ── 5-Hour ───────────────────────────────────────────────
    sec = data.get("five_hour")
    if sec:
        pct = sec.get("utilization", 0)
        rst = time_until_reset(sec.get("resets_at")) or ""
        items.append({
            "title": f"{usage_icon(pct)}  {t('5h_usage')}: {pct:.1f}%   {usage_bar(pct)}",
            "subtitle": f"{'⏳ ' + rst if rst else t('no_reset')}{cache_note}  ·  {t('open_usage')}",
            "arg": "https://claude.ai/settings/usage",
            "valid": True, "icon": {"path": "icon.png"},
        })
    else:
        items.append({
            "title": f"⬜  {t('5h_usage')}: {t('no_data')}",
            "subtitle": t("no_data_sub"),
            "valid": False, "icon": {"path": "icon.png"},
        })

    # ── 7-Day ────────────────────────────────────────────────
    sec = data.get("seven_day")
    if sec:
        pct = sec.get("utilization", 0)
        rst = time_until_reset(sec.get("resets_at")) or ""
        items.append({
            "title": f"{usage_icon(pct)}  {t('7d_usage')}: {pct:.1f}%   {usage_bar(pct)}",
            "subtitle": f"{'⏳ ' + rst if rst else t('no_reset')}{cache_note}  ·  {t('open_usage')}",
            "arg": "https://claude.ai/settings/usage",
            "valid": True, "icon": {"path": "icon.png"},
        })

    # ── Model rows ───────────────────────────────────────────
    for key, label_key in MODEL_ROWS:
        sec = data.get(key)
        if sec and sec.get("utilization") is not None:
            pct = sec["utilization"]
            rst = time_until_reset(sec.get("resets_at")) or ""
            items.append({
                "title": f"{usage_icon(pct)}  {t(label_key)}: {pct:.1f}%   {usage_bar(pct)}",
                "subtitle": f"{'⏳ ' + rst if rst else t('no_reset')}{cache_note}",
                "arg": "https://claude.ai/settings/usage",
                "valid": True, "icon": {"path": "icon.png"},
            })

    # ── Service status ───────────────────────────────────────
    status_data = fetch_claude_status()
    status_items = build_status_items(status_data)
    if status_items:
        status_items[0]["mods"] = {"cmd": {
            "subtitle": t("copy_json"),
            "arg": json.dumps(data, indent=2, ensure_ascii=False),
            "valid": True,
        }}
    items.extend(status_items)
    return items


def main():
    sys.stdout.write(json.dumps({"items": build_items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
