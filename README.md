# Painel NEIF — monitor da rede de sites

App Streamlit que mostra, num só lugar, a saúde da rede de sites:

- 🟢/🔴 se cada site está **no ar** (HTTP 200 no domínio de produção);
- ✅/❌ status do último **"Post diário"** (cron de conteúdo) e do último **"Deploy no VPS"**;
- 📝 **título e data do último post** publicado (lido do RSS `index.xml` do Hugo);
- resumo no topo: sites no ar, posts do dia, crons com falha.

Atualiza sozinho a cada `REFRESH_SECONDS` (padrão 120s) e tem botão "Atualizar agora".

---

## Rodar local (preview rápido)

```bash
cd site-monitor
pip install -r requirements.txt
# opcional, mas recomendado (some com o rate limit baixo do GitHub):
export GITHUB_TOKEN=ghp_xxx        # no Windows PowerShell: $env:GITHUB_TOKEN="ghp_xxx"
streamlit run monitor.py
```

Abre em `http://localhost:8501`.

---

## Variáveis de ambiente

| Variável | Obrigatória | Para quê |
|---|---|---|
| `GITHUB_TOKEN` | recomendada | Token **só-leitura** do GitHub. Sem ele o painel ainda funciona, mas o GitHub limita a 60 chamadas/hora e o status dos crons pode aparecer como "erro API". |
| `DASH_PASSWORD` | recomendada (no VPS) | Se definida, o painel pede essa senha antes de abrir. |
| `REFRESH_SECONDS` | não | Intervalo de atualização em segundos (padrão `120`). |
| `GH_OWNER` | não | Dono dos repositórios (padrão `tiagossevero`). |

### Como criar o token (só-leitura)

GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**:

- **Resource owner:** `tiagossevero`
- **Repository access:** *Only select repositories* → os 7 `site-*` (ou *All repositories*)
- **Permissions → Repository:** `Actions` = **Read-only**, `Metadata` = **Read-only** (o `Metadata` já vem por padrão)
- Gere e copie o token (`github_pat_...`). Guarde-o só na variável de ambiente — nunca no código.

> Um token clássico com escopo `public_repo` também serve (os repos são públicos), mas o fine-grained só-leitura é o mais seguro.

---

## Deploy no VPS (EasyPanel)

1. **Suba este diretório como repositório** (feito pelo assistente): `github.com/tiagossevero/site-monitor`.
2. No EasyPanel (projeto `sites`): **+ Serviço → App**.
3. **Source → GitHub:** repositório `tiagossevero/site-monitor`, branch `main`.
4. **Build:** tipo **Dockerfile** (o `Dockerfile` deste repo).
5. **Environment:** adicione `GITHUB_TOKEN`, `DASH_PASSWORD` e (opcional) `REFRESH_SECONDS`.
6. **Domains:** adicione um domínio (ex.: `painel.ivadual.com.br`), porta interna **8501**, HTTPS (Let's Encrypt) ligado.
7. No **Registro.br** (zona do domínio-mãe, modo avançado): registro `A` de `painel` → `195.35.40.100`.
8. **Deploy.** Em ~1 min o painel sobe em `https://painel.ivadual.com.br` (pedindo a senha).

Cada `git push` neste repo redeploya o painel automaticamente (se você adicionar o mesmo `deploy.yml`/webhook dos outros sites — opcional, o painel muda pouco).

---

## Personalizar

- **Sites monitorados:** edite a lista `SITES` no topo do `monitor.py`.
- **Incluir outros projetos** (ex.: `rtc`, `ft`): acrescente entradas em `SITES` com `"tem_post": False` (eles não têm o cron de post) e ajuste os **arquivos** de workflow em `WF_POST`/`WF_DEPLOY` (o painel casa pelo nome do arquivo, ex.: `post-diario.yml`, `deploy.yml`).
