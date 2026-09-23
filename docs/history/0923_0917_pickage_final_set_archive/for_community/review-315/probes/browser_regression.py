import sys,os,subprocess,time,uuid,json,urllib.request,urllib.error,urllib.parse
from pathlib import Path
root=Path(__file__).resolve().parents[4];sys.path.insert(0,str(root/'.git/phase5-pylibs'))
from playwright.sync_api import sync_playwright,expect
db='pickage_315_test_'+uuid.uuid4().hex
logs=[];processes=[];result={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'mock':False,'checks':[],'page_errors':[]}
evidence=root/'docs/for_community/review-315/evidence'
def sql(text):
    return subprocess.run(['docker','exec','-i','pickage-local-postgres-1','psql','-v','ON_ERROR_STOP=1','-U','postgres','-d',db],input=text.encode(),capture_output=True,check=True)
def launch(cmd,cwd,env,name):
    f=open(root/'.git'/name,'wb');logs.append(f)
    p=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(p)
    return p
def wait_url(url):
    for _ in range(50):
        try:
            with urllib.request.urlopen(url,timeout=2) as r:
                if r.status==200:return
        except Exception:time.sleep(.5)
    raise AssertionError('Local service startup timeout')
try:
    subprocess.run(['docker','exec','pickage-local-postgres-1','psql','-U','postgres','-d','postgres','-c',f'CREATE DATABASE {db}'],check=True,capture_output=True)
    env=os.environ.copy();env.update(SPRING_DATASOURCE_URL=f'jdbc:postgresql://localhost:15432/{db}',COMMUNITY_ENABLED='false')
    env.pop('GITHUB_COMMUNITY_TOKEN',None)
    launch(['C:/Program Files/Eclipse Adoptium/jdk-21.0.11.10-hotspot/bin/java.exe','-jar',str(root/'backend/build/libs/pickage-0.0.1-SNAPSHOT.jar'),'--server.port=18085','--server.address=127.0.0.1'],root/'backend',env,'phase5-browser-backend.log')
    wait_url('http://127.0.0.1:18085/actuator/health')
    sql((root/'deploy/local/seed/seed_mock_parity.sql').read_text(encoding='utf-8'))
    env.update(VITE_USE_MOCK='false',VITE_API_BASE_URL='/api',VITE_DEV_API_TARGET='http://127.0.0.1:18085')
    launch(['node',str(root/'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','15173','--strictPort'],root/'frontend',env,'phase5-browser-frontend.log')
    wait_url('http://127.0.0.1:15173')
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:result['page_errors'].append(str(error)))
        responses=[]
        page.on('response',lambda r:responses.append({'url':r.url.replace('http://127.0.0.1:15173',''),'status':r.status}) if urllib.parse.urlparse(r.url).path.startswith('/api/') else None)
        page.goto('http://127.0.0.1:15173/report/phase5-review')
        expect(page.get_by_role('heading',name='분석 결과',exact=True)).to_be_visible()
        expect(page.get_by_label('시작 스냅샷')).to_be_visible(timeout=15000)
        expect(page.get_by_text('winston',exact=True).first).to_be_visible()
        start=page.get_by_label('시작 스냅샷');options=start.locator('option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
        assert len(options)>1
        start.select_option(options[-2]);result['checks'].append('mock off: real seeded ecosystem renders and snapshot filter changes')
        page.screenshot(path=str(evidence/'browser-ecosystem.png'),full_page=True)
        before=page.request.get('http://127.0.0.1:15173/api/packages?names=winston,pino,bunyan').json()
        disabled=page.request.post('http://127.0.0.1:15173/api/packages/community/refresh?name=winston&trigger=TAB_OPENED')
        assert disabled.status==200 and disabled.json()['data']['refresh']['error_code']=='COMMUNITY_DISABLED'
        result['checks'].append('missing token: community refresh disabled, existing overview unchanged')
        for _ in range(3):
            page.get_by_role('tab',name='기능 비교',exact=False).click()
            expect(page.get_by_role('tabpanel')).to_be_visible()
            page.get_by_role('tab',name='생태계 변화',exact=True).click()
            expect(page.get_by_label('시작 스냅샷')).to_be_visible()
        assert before==page.request.get('http://127.0.0.1:15173/api/packages?names=winston,pino,bunyan').json()
        result['checks'].append('ecosystem/features round trip three times preserves real overview')
        page.get_by_role('tab',name='기능 비교',exact=False).click();page.wait_for_timeout(10000)
        page.screenshot(path=str(evidence/'browser-features.png'),full_page=True)
        result['checks'].append('existing feature comparison sample renders; real AI evaluation not covered')
        page.get_by_role('tab',name='생태계 변화',exact=True).click()
        for suffix in ['', '/downloads','/dependents','/version']:
            r=page.request.get('http://127.0.0.1:15173/api/packages'+suffix+'?names=winston,pino,bunyan');assert r.status==200
        page.goto('http://127.0.0.1:15173/analyze');expect(page.get_by_role('combobox',name='기준 npm 패키지명')).to_be_visible()
        page.get_by_role('combobox',name='기준 npm 패키지명').fill('winston')
        page.get_by_role('button',name='패키지 확인',exact=True).click()
        expect(page.get_by_role('heading',name='비교할 패키지를 선택하세요',exact=True)).to_be_visible(timeout=10000)
        page.get_by_role('combobox',name='직접 추가할 패키지명').fill('pino')
        page.get_by_role('button',name='패키지 추가',exact=True).click()
        expect(page.get_by_text('pino',exact=True).first).to_be_visible()
        page.wait_for_timeout(500)
        result['checks'].append('analyze input and real similar-package lookup remain interactive')
        result['fixture_limitations']=['seed does not install dictionary static manifest; its 404 falls back to the search API']
        assert not result['page_errors'],result['page_errors']
        assert responses and all(r['status']<400 or r['url']=='/api/dict-manifest' and r['status']==404 for r in responses),responses
        result['responses']=responses;result['status']='PASS';browser.close()
finally:
    for p in reversed(processes):
        p.terminate()
        try:p.wait(timeout=8)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    for f in logs:f.close()
    assert db.startswith('pickage_315_test_') and len(db)==49
    subprocess.run(['docker','exec','pickage-local-postgres-1','psql','-U','postgres','-d','postgres','-c',f'DROP DATABASE IF EXISTS {db} WITH (FORCE)'],check=True,capture_output=True)
    (evidence/'browser-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
