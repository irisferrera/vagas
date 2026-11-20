#!/usr/bin/env python3
"""Busca vagas PO/PM/BA no portal público do Gupy, filtra pelas empresas-alvo,
publicadas há <= MAX_DIAS dias e com aderência >= MIN_ADERENCIA ao currículo da Íris.
Regenera dashboard.html. Falha (exit 1) se a API não responder, para o GitHub ficar vermelho."""
import json, re, sys, html, pathlib, datetime as dt, urllib.parse, urllib.request

MAX_DIAS, MIN_ADERENCIA = 30, 80

# nome exibido -> regex para casar com o nome da empresa/página de carreira no Gupy
EMPRESAS = {
 "CI&T": r"ci\s?&\s?t|ciandt", "Zup Innovation": r"\bzup\b", "GFT Technologies": r"\bgft\b",
 "DBC Company": r"\bdbc\b", "Compass UOL": r"compass|\buol\b", "Stefanini": r"stefanini|\bgauge\b",
 "Accenture": r"accenture", "Thoughtworks": r"thoughtworks", "ArcTouch": r"arctouch",
 "LWSA": r"\blwsa\b|locaweb", "RD Station / TOTVS": r"rd\s?station|totvs", "SAP": r"\bsap\b",
 "Omie": r"\bomie\b", "Asaas": r"\basaas\b", "Conta Azul": r"conta\s?azul|contaazul",
 "VTEX": r"\bvtex\b", "Sympla": r"\bsympla\b", "Grupo Boticário": r"botic[aá]rio",
 "Natura &Co": r"natura", "iFood": r"\bifood\b", "Dentsu": r"dentsu",
}
CARGOS = ["product owner", "product manager", "business analyst", "analista de negócios"]
TITULO_OK = re.compile(r"product owner|\bpo\b|product manager|business analyst|analista de neg[oó]cios|\bpm\b|\bba\b", re.I)
SENIORIDADE_RUIM = ["estágio","estagiário","trainee","júnior","junior","head","diretor","gerente"]
TERMOS = {
 "product owner":3,"product manager":3,"business analyst":2,"analista de negócios":2,"backlog":2,
 "scrum":2,"kanban":1,"discovery":3,"dual-track":2,"mvp":2,"roadmap":2,"okr":1,
 "histórias de usuário":2,"critérios de aceite":2,"prd":1,"jira":1,"confluence":1,"b2b":2,"saas":2,
 "api":2,"integra":2,"stakeholder":2,"métricas":1,"ia generativa":2,"genai":2,"ágil":2,"agile":2,
 "requisitos":2,"squad":1,"cspo":1,
}
BASES = ["https://portal.gupy.io/api/job-search/jobs", "https://employability-portal.gupy.io/api/v1/jobs", "https://portal.api.gupy.io/api/v1/jobs"]
HDR = {"Referer": "https://portal.gupy.io/", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", "Accept": "application/json"}
erros = {"n": 0, "ok": 0, "amostra": None}
stats = {"pag": [], "recentes": 0, "alvo_qualquer_data": 0, "empresas": {}}

def http(url, json_=True):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=30) as r:
            corpo = r.read().decode("utf-8", "replace")
        erros["ok"] += 1
        return json.loads(corpo) if json_ else corpo
    except Exception as e:
        erros["n"] += 1
        if erros["amostra"] is None: erros["amostra"] = f"{url} -> {e}"
        return None

def pagina(base, cargo, offset):
    q = urllib.parse.urlencode({"jobName": cargo, "name": cargo, "limit": 100, "offset": offset,
                                "sortBy": "publishedDate", "sortOrder": "desc"})
    d = http(f"{base}?{q}")
    if d and d.get("pagination") is not None and offset == 0:
        stats["pag"].append((cargo, d.get("pagination")))
    return (d or {}).get("data") if d else None

def parse_data(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None

def texto_da_vaga(v):
    t = " ".join(str(v.get(k) or "") for k in ("name", "description", "type"))
    if len(t) < 400 and v.get("jobUrl"):  # descrição ausente na listagem: lê a página da vaga
        h = http(v["jobUrl"], json_=False)
        if h: t += " " + re.sub(r"<[^>]+>", " ", html.unescape(h))
    return t.lower()

def aderencia(v):
    t = texto_da_vaga(v)
    ganho = sum(p for k, p in TERMOS.items() if k in t)
    nota = round(100 * ganho / sum(TERMOS.values()) * 2.2)
    if any(s in (v.get("name") or "").lower() for s in SENIORIDADE_RUIM): nota -= 25
    return max(0, min(100, nota))

def empresa_alvo(v):
    nome = f'{v.get("careerPageName") or ""} {v.get("companyName") or ""}'.lower()
    for exibir, rx in EMPRESAS.items():
        if re.search(rx, nome): return exibir
    return None

def main():
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_DIAS)
    vistas, cand = {}, {}
    base_ok = None
    for cargo in CARGOS:
        for base in ([base_ok] if base_ok else BASES):
            sem_recentes = 0
            for off in range(0, 1000, 100):
                dados = pagina(base, cargo, off)
                if dados is None: break
                base_ok = base
                if not dados: break
                novas_recentes = 0
                for v in dados:
                    vid = v.get("id") or v.get("jobId")
                    pub = parse_data(v.get("publishedDate"))
                    if not vid or not pub: continue
                    if vid not in vistas:
                        vistas[vid] = 1
                        nome_emp = v.get("careerPageName") or v.get("companyName") or "?"
                        stats["empresas"][nome_emp] = stats["empresas"].get(nome_emp, 0) + 1
                        if pub >= limite: stats["recentes"] += 1
                        if empresa_alvo(v): stats["alvo_qualquer_data"] += 1
                    if pub >= limite: novas_recentes += 1
                    emp = empresa_alvo(v)
                    if emp and pub >= limite and TITULO_OK.search(v.get("name") or ""):
                        cand[vid] = (v, emp, pub)
                sem_recentes = 0 if novas_recentes else sem_recentes + 1
                if sem_recentes >= 3: break  # 3 páginas seguidas sem vaga recente: para
            if base_ok: break
    final = []
    for vid, (v, emp, pub) in cand.items():
        nota = aderencia(v)
        if nota >= MIN_ADERENCIA:
            final.append({"empresa": emp, "titulo": v["name"],
              "local": ", ".join(filter(None, [v.get("city"), v.get("state")])) or ("Remoto" if v.get("isRemoteWork") else "—"),
              "publicada": pub.isoformat(), "aderencia": nota, "link": v.get("jobUrl", "")})
    final.sort(key=lambda x: -x["aderencia"])
    agora = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    print(f"Requisições ok: {erros['ok']} | falhas: {erros['n']} | vagas lidas: {len(vistas)} | "
          f"das empresas-alvo e recentes: {len(cand)} | com aderência >= {MIN_ADERENCIA}%: {len(final)}")
    if erros["amostra"]: print("Exemplo de falha:", erros["amostra"])
    print(f"Diagnóstico: recentes (qualquer empresa): {stats['recentes']} | das empresas-alvo (qualquer data): {stats['alvo_qualquer_data']}")
    for c, pg in stats["pag"]: print("Paginação", c, "->", pg)
    top = sorted(stats["empresas"].items(), key=lambda x: -x[1])[:15]
    print("Empresas mais frequentes:", "; ".join(f"{n} ({q})" for n, q in top))
    pasta = pathlib.Path(__file__).parent
    f = pasta / "dashboard.html"; tpl = f.read_text(encoding="utf-8")
    dados = json.dumps({"atualizado": agora, "vagas": final}, ensure_ascii=False)
    tpl = re.sub(r"/\*JOBS\*/.*?/\*END\*/", lambda m: "/*JOBS*/" + dados + "/*END*/", tpl, flags=re.S)
    tpl = re.sub(r"publicadas há até \d+ dias?", f"publicadas há até {MAX_DIAS} dias", tpl)
    f.write_text(tpl, encoding="utf-8")
    if erros["ok"] == 0:
        print("ERRO: nenhuma requisição funcionou; a API do Gupy não respondeu."); sys.exit(1)

if __name__ == "__main__": main()
