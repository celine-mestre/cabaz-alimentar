from playwright.sync_api import sync_playwright
errs=[]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1500,'height':1200})
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto('http://localhost:8810', wait_until='domcontentloaded', timeout=90000)
    pg.wait_for_timeout(23000)
    tabs=pg.query_selector_all('[role="tab"]')
    for i,nome in [(2,'Simulador de IVA'),(3,'Comparação UE-27')]:
        tabs[i].click(); pg.wait_for_timeout(6000)
        t=pg.inner_text('body')
        tem_erro = 'Traceback' in t or 'NameError' in t or 'KeyError' in t or 'Error' in t
        print(f'=== {nome}: {"ERRO" if tem_erro else "ok"}')
        if tem_erro:
            for marca in ['NameError','KeyError','AttributeError','TypeError','Traceback']:
                j=t.find(marca)
                if j>=0: print('   ', t[j:j+320].replace('\n',' ')[:320]); break
    b.close()
print('erros JS:', len(errs))
