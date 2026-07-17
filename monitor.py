"""
Painel de monitoramento da rede de sites NEIF (Streamlit).

Para cada site mostra:
  - se está no ar (HTTP 200 no domínio de produção);
  - status do último "Post diário" (cron de geração de conteúdo);
  - status do último "Deploy no VPS";
  - título/data do último post publicado (lido do RSS index.xml do Hugo).

Configuração por variáveis de ambiente:
  GITHUB_TOKEN     token do GitHub só-leitura — recomendado (rate limit maior).
  DASH_PASSWORD    se definido, protege o painel com uma senha.
  REFRESH_SECONDS  intervalo de atualização/cache em segundos (padrão 120).
  GH_OWNER         dono dos repositórios (padrão "tiagossevero").
"""
from __future__ import annotations

import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# Parser XML seguro (evita XXE / billion-laughs). Fallback só p/ dev local;
# em produção o defusedxml está no requirements.txt.
try:
    from defusedxml.ElementTree import fromstring as xml_fromstring
except Exception:  # noqa: BLE001
    from xml.etree.ElementTree import fromstring as xml_fromstring

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # dependência opcional
    st_autorefresh = None

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
GH_OWNER = os.environ.get("GH_OWNER", "tiagossevero")
GH_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
DASH_PASSWORD = os.environ.get("DASH_PASSWORD", "")
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "120"))

BRT = ZoneInfo("America/Sao_Paulo")
API = "https://api.github.com"

# Casamos pelo ARQUIVO do workflow (robusto: o campo "name" da API às vezes
# vem como o caminho do arquivo em runs antigos).
WF_POST = "post-diario.yml"
WF_DEPLOY = "deploy.yml"

SITES = [
    {"repo": "site-ivadual",      "dominio": "ivadual.com.br",      "tem_post": True},
    {"repo": "site-cf88",         "dominio": "cf88.com.br",         "tem_post": True},
    {"repo": "site-claudera",     "dominio": "claudera.com.br",     "tem_post": True},
    {"repo": "site-incorp",       "dominio": "incorp.com.br",       "tem_post": True},
    {"repo": "site-tiago",        "dominio": "tiago.emp.br",        "tem_post": True},
    {"repo": "site-villagos",     "dominio": "villagos.com.br",     "tem_post": True},
    {"repo": "site-studiovolari", "dominio": "studiovolari.com.br", "tem_post": False},
]


# ---------------------------------------------------------------------------
# Coleta de dados
# ---------------------------------------------------------------------------
def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h


def _parse_iso(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _idade(quando: dt.datetime | None) -> str:
    if not quando:
        return "—"
    seg = int((dt.datetime.now(dt.timezone.utc) - quando).total_seconds())
    seg = max(seg, 0)
    if seg < 3600:
        return f"há {seg // 60} min"
    if seg < 86400:
        return f"há {seg // 3600} h"
    return f"há {seg // 86400} d"


def runs_do_repo(repo: str) -> dict:
    """Últimos runs por nome de workflow (a API já vem do mais novo p/ o antigo)."""
    try:
        r = requests.get(
            f"{API}/repos/{GH_OWNER}/{repo}/actions/runs",
            headers=_headers(),
            params={"per_page": 30, "exclude_pull_requests": "true"},
            timeout=15,
        )
        r.raise_for_status()
        runs = r.json().get("workflow_runs", [])
    except Exception as e:  # noqa: BLE001
        return {"_erro": str(e)}
    ultimos: dict = {}
    for run in runs:
        chave = (run.get("path") or "").rsplit("/", 1)[-1]  # ex.: "post-diario.yml"
        if chave and chave not in ultimos:  # API já vem do mais novo p/ o antigo
            ultimos[chave] = {
                "conclusion": run.get("conclusion"),
                "status": run.get("status"),
                "quando": _parse_iso(run.get("created_at")),
                "url": run.get("html_url"),
            }
    return ultimos


def site_no_ar(dominio: str) -> dict:
    try:
        r = requests.get(f"https://{dominio}/", timeout=12, allow_redirects=True,
                         headers={"User-Agent": "neif-monitor/1.0"})
        return {"ok": r.status_code == 200, "code": r.status_code,
                "ms": int(r.elapsed.total_seconds() * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "code": None, "erro": type(e).__name__}


def ultimo_post(dominio: str) -> dict:
    """Lê o RSS (index.xml) do Hugo e devolve título/data do post mais recente."""
    try:
        r = requests.get(f"https://{dominio}/index.xml", timeout=12,
                         headers={"User-Agent": "neif-monitor/1.0"})
        r.raise_for_status()
        item = xml_fromstring(r.content).find(".//item")
        if item is None:
            return {}
        quando = None
        pub = item.findtext("pubDate")
        if pub:
            try:
                quando = parsedate_to_datetime(pub)
                if quando.tzinfo is None:
                    quando = quando.replace(tzinfo=dt.timezone.utc)
            except Exception:  # noqa: BLE001
                quando = None
        return {"titulo": (item.findtext("title") or "").strip(), "quando": quando}
    except Exception:  # noqa: BLE001
        return {}


def coletar_site(site: dict) -> dict:
    return {
        **site,
        "runs": runs_do_repo(site["repo"]),
        "vivo": site_no_ar(site["dominio"]),
        "post": ultimo_post(site["dominio"]) if site["tem_post"] else {},
    }


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def carregar() -> list:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(coletar_site, SITES))


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------
def cel_run(runs: dict, nome: str) -> str:
    if "_erro" in runs:
        return "⚠️ erro API"
    run = runs.get(nome)
    if not run:
        return "➖"
    if run.get("status") and run["status"] != "completed":
        emoji = "⏳"
    else:
        emoji = {"success": "✅", "failure": "❌"}.get(run.get("conclusion"), "⚠️")
    txt = f"{emoji} {_idade(run.get('quando'))}"
    return f"[{txt}]({run['url']})" if run.get("url") else txt


def checar_senha() -> None:
    if not DASH_PASSWORD or st.session_state.get("_ok"):
        return
    st.title("🔒 Painel NEIF")
    senha = st.text_input("Senha", type="password")
    if senha and senha == DASH_PASSWORD:
        st.session_state["_ok"] = True
        st.rerun()
    elif senha:
        st.error("Senha incorreta.")
    st.stop()


def main() -> None:
    st.set_page_config(page_title="Painel NEIF", page_icon="📡", layout="wide")
    checar_senha()

    if st_autorefresh:
        st_autorefresh(interval=REFRESH_SECONDS * 1000, key="_ar")

    with st.sidebar:
        st.header("📡 Painel NEIF")
        st.caption("Rede de sites — status ao vivo")
        st.write("🔐 GitHub: " + ("autenticado" if GH_TOKEN else "⚠️ sem token (rate limit baixo)"))
        st.write(f"🔁 Atualiza a cada **{REFRESH_SECONDS}s**")
        if st.button("Atualizar agora", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption("Agora: " + dt.datetime.now(BRT).strftime("%d/%m %H:%M:%S BRT"))

    dados = carregar()
    hoje = dt.datetime.now(BRT).date()

    no_ar = sum(1 for d in dados if d["vivo"].get("ok"))
    com_post = [d for d in dados if d["tem_post"]]
    posts_hoje = sum(
        1 for d in com_post
        if d["post"].get("quando") and d["post"]["quando"].astimezone(BRT).date() == hoje
    )
    falhas = sum(
        1 for d in dados for wf in (WF_POST, WF_DEPLOY)
        if isinstance(d["runs"], dict) and d["runs"].get(wf, {}).get("conclusion") == "failure"
    )

    st.title("📡 Painel da rede de sites NEIF")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sites no ar", f"{no_ar}/{len(dados)}")
    m2.metric("Posts de hoje", f"{posts_hoje}/{len(com_post)}")
    m3.metric("Crons com falha", falhas, delta_color="inverse")
    m4.metric("Última coleta", dt.datetime.now(BRT).strftime("%H:%M:%S"))
    st.divider()

    cab = st.columns([2.4, 1.1, 3.0, 1.7, 1.7])
    for col, txt in zip(cab, ("**Site**", "**No ar**", "**Último post**",
                              "**Post diário**", "**Deploy**")):
        col.markdown(txt)

    for d in dados:
        with st.container(border=True):
            c = st.columns([2.4, 1.1, 3.0, 1.7, 1.7])

            c[0].markdown(f"**{d['repo'].replace('site-', '')}**  \n"
                          f"[{d['dominio']}](https://{d['dominio']})")

            v = d["vivo"]
            if v.get("ok"):
                c[1].markdown(f"🟢 200  \n<sub>{v.get('ms', '?')} ms</sub>",
                              unsafe_allow_html=True)
            else:
                detalhe = v.get("code") or v.get("erro") or "sem resposta"
                c[1].markdown(f"🔴 {detalhe}")

            if not d["tem_post"]:
                c[2].markdown("<sub>site legado (sem post)</sub>", unsafe_allow_html=True)
            elif d["post"].get("titulo"):
                q = d["post"].get("quando")
                sel = "🟩" if (q and q.astimezone(BRT).date() == hoje) else "▫️"
                titulo = d["post"]["titulo"]
                titulo = titulo if len(titulo) <= 60 else titulo[:57] + "…"
                c[2].markdown(f"{sel} {titulo}  \n<sub>{_idade(q)}</sub>",
                              unsafe_allow_html=True)
            else:
                c[2].markdown("<sub>—</sub>", unsafe_allow_html=True)

            c[3].markdown(cel_run(d["runs"], WF_POST) if d["tem_post"] else "➖")
            c[4].markdown(cel_run(d["runs"], WF_DEPLOY))

    st.caption("✅ sucesso · ❌ falha · ⏳ rodando · ➖ n/d · 🟩 post publicado hoje. "
               "Clique nos status para abrir o run no GitHub.")


if __name__ == "__main__":
    main()
