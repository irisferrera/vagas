#!/usr/bin/env python3
"""Busca vagas PO/PM/BA nas empresas-alvo via API pública do Gupy, calcula aderência
com o currículo da Íris, mantém só >=80% e <=2 dias, e regenera dashboard.html.
NOTA: escrito sem poder testar contra o Gupy (rede bloqueada no ambiente de criação).
Rode uma vez manualmente e confira o resultado antes de confiar."""
import json, re, datetime as dt, urllib.parse, urllib.request, pathlib

EMPRESAS = ["CI&T","Zup Innovation","GFT Technologies","DBC Company","Compass UOL","Stefanini",
 "Accenture","Thoughtworks","ArcTouch","LWSA","RD Station","TOTVS","SAP","Omie","Asaas","Conta Azul",
 "VTEX","Sympla","Grupo Boticário","Natura","iFood","Dentsu"]
CARGOS = ["product owner","product manager","business analyst","analista de negócios","PO"]
MAX_DIAS, MIN_ADERENCIA = 30, 80

# Termos do currículo, com peso (ajuste à vontade)
TERMOS = {
 "product owner":3,"product manager":3,"business analyst":2,"analista de negócios":2,
 "backlog":2,"scrum":2,"kanban":1,"discovery":3,"dual-track":2,"mvp":2,"roadmap":2,"okr":1,
 "histórias de usuário":2,"critérios de aceite":2,"prd":1,"jira":1,"confluence":1,
 "b2b":2,"saas":2,"api":2,"integra":2,"stakeholder":2,"métricas":1,"ia generativa":2,
 "genai":2,"ágil":2,"agile":2,"requisitos":2,"squad":1,"cspo":1,
}
SENIORIDADE_RUIM = ["estágio","estagiário","trainee","júnior","junior","head","diretor","gerente"]

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def aderencia(vaga):
    texto = " ".join(str(vaga.get(k,"")) for k in ("name","description","type")).lower()
    total = sum(TERMOS.values())
    ganho = sum(p for t,p in TERMOS.items() if t in texto)
    nota = round(100*ganho/total*2.2)  # fator de calibração: ~45% dos termos => 100
    if any(s in vaga.get("name","").lower() for s in SENIORIDADE_RUIM): nota -= 25
    return max(0,min(100,nota))

def main():
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_DIAS)
    achadas = {}
    for emp in EMPRESAS:
        for cargo in CARGOS:
            q = urllib.parse.urlencode({"name":f"{cargo}","companyName":emp,"limit":50})
            try: dados = get(f"https://portal.api.gupy.io/api/job?{q}")
            except Exception as e:
                print("falha",emp,cargo,e); continue
            for v in dados.get("data",[]):
                pub = dt.datetime.fromisoformat(v["publishedDate"].replace("Z","+00:00"))
                if pub < limite: continue
                nota = aderencia(v)
                if nota < MIN_ADERENCIA: continue
                achadas[v["id"]] = {"empresa":v.get("careerPageName") or emp,"titulo":v["name"],
                  "local":", ".join(filter(None,[v.get("city"),v.get("state")])) or ("Remoto" if v.get("isRemoteWork") else "—"),
                  "publicada":pub.isoformat(),"aderencia":nota,"link":v["jobUrl"]}
    vagas = sorted(achadas.values(), key=lambda x:-x["aderencia"])
    agora = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    pasta = pathlib.Path(__file__).parent
    tpl = (pasta/"dashboard.html").read_text(encoding="utf-8")
    tpl = re.sub(r"/\*JOBS\*/.*?/\*END\*/", "/*JOBS*/"+json.dumps({"atualizado":agora,"vagas":vagas},ensure_ascii=False)+"/*END*/", tpl, flags=re.S)
    (pasta/"dashboard.html").write_text(tpl, encoding="utf-8")
    print(f"{len(vagas)} vagas >= {MIN_ADERENCIA}% em {agora}")

if __name__ == "__main__": main()
