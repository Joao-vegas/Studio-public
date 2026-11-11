import json, sys, urllib.request, urllib.parse, pathlib, concurrent.futures as cf
UA = {"User-Agent": "EstudioJoao/1.0 (seu-email@exemplo.com) editorial-research"}
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
def busca(q, n=10):
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6,
         "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1200}
    d = json.loads(get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))
    out = []
    for pg in sorted(d.get("query", {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
        ii = pg["imageinfo"][0]; m = ii.get("extmetadata", {})
        out.append({"titulo": pg["title"], "thumb": ii.get("thumburl"), "pagina": ii.get("descriptionurl"),
                    "licenca": m.get("LicenseShortName", {}).get("value", ""), "autor": m.get("Artist", {}).get("value", "")[:120],
                    "w": ii.get("width"), "h": ii.get("height")})
    return out
dest = pathlib.Path(sys.argv[1]); dest.mkdir(parents=True, exist_ok=True)
consultas = json.loads(pathlib.Path(sys.argv[2]).read_text())
meta = {}
def um(item):
    k, q = item
    res = []
    try:
        todos = [r for r in busca(q) if r["thumb"]]
        # tela cheia em 1080x1920 pede foto grande (30-out, Theranos: cérebro de 344 px virou borrão): fica com as de lado maior >= 1100 px
        grandes = [r for r in todos if max(r.get("w") or 0, r.get("h") or 0) >= 1100]
        for i, r in enumerate((grandes or sorted(todos, key=lambda r: -max(r.get("w") or 0, r.get("h") or 0)))[:4]):
            f = dest / f"{k}-{i}.jpg"
            f.write_bytes(get(r["thumb"])); r["arquivo"] = f.name; res.append(r)
    except Exception as e:
        print("falhou", k, e)
    return k, res
with cf.ThreadPoolExecutor(6) as ex:
    for k, res in ex.map(um, consultas.items()):
        meta[k] = res
(dest / "origem.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
print(sum(len(v) for v in meta.values()), "imagens")
