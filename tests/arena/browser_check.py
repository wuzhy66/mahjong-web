"""浏览器完整对局及规则关键动作回归；请求使用真实 API 和模型。"""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/browser-regression';OUT.mkdir(parents=True,exist_ok=True)
fixtures=json.loads(Path(__file__).with_name('scenarios.json').read_text())
report=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--enable-unsafe-swiftshader'])
    try:
        for kind in ['full','chi','peng','gang_an','gang_ming','gang_bu','hu']:
            print('开始浏览器场景:',kind,flush=True)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page();errors=[];snapshots=[];privacy=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            def capture(response):
                if '/api/rooms' not in response.url or response.status!=200:return
                data=response.json();s=data.get('snapshot',data)
                if 'players' not in s:return
                snapshots.append(s)
                if not s['finished'] and (any(x['hand'] for x in s['players'][1:]) or 'wall' in s or 'seed' in s):privacy.append('hidden-state')
            page.on('response',capture)
            page.goto('http://localhost:8867');page.wait_for_load_state('networkidle')
            assert page.locator('select').count()==3
            page.get_by_role('button',name='入座开局').click()
            page.locator('.hand-rack .mahjong-tile').first.wait_for(timeout=60000)
            page.locator('.scene-notice').wait_for(state='hidden',timeout=60000)
            start=time.monotonic();moves=0
            if kind=='full':
                page.reload();page.locator('.hand-rack .mahjong-tile').first.wait_for()
                while page.locator('.result-card').count()==0:
                    assert time.monotonic()-start<600,'整局超时'
                    assert not page.locator('.error-banner').count(),page.locator('.error-banner').inner_text()
                    if page.locator('.turn-status').inner_text()=='轮到你了':
                        buttons=page.locator('.action-row button:enabled');labels=buttons.all_text_contents()
                        tiles=page.locator('.hand-rack .mahjong-tile:not(.disabled)')
                        if '胡牌' in labels:page.get_by_role('button',name='胡牌',exact=True).click()
                        elif tiles.count():
                            tiles.first.click();page.get_by_role('button',name='出牌',exact=True).click()
                        elif '过' in labels and len(labels)>1:page.get_by_role('button',name='过',exact=True).click()
                        elif len(labels)>1:buttons.first.click()
                        moves+=1
                    page.wait_for_timeout(160)
                final=next(x for x in reversed(snapshots) if x['finished'])
                assert sum(final['result']['scores'])==0
                page.screenshot(path=str(OUT/'full-settlement.png'),full_page=True)
                page.get_by_role('button',name='查看牌桌',exact=True).click()
                page.get_by_role('button',name='查看结算',exact=True).click()
                with page.expect_response(lambda r:r.url.endswith('/next') and r.request.method=='POST') as next_response:
                    page.get_by_role('button',name='继续下一局').click()
                assert next_response.value.status==200
                nxt=next_response.value.json()
                page.get_by_text('第 2 局',exact=True).wait_for()
                assert nxt['dealer']==final['result']['next_dealer']
                assert [x['score'] for x in nxt['players']]==final['result']['scores']
                page.screenshot(path=str(OUT/'next-round.png'),full_page=True)
                detail=dict(result=final['result'],humanActions=moves,nextDealer=nxt['dealer'])
            else:
                before=snapshots[-1];target=fixtures[kind]['target']
                action=next(x for x in before['legalActions'] if x['id']==target)
                page.screenshot(path=str(OUT/(kind+'-before.png')),full_page=True)
                with page.expect_response(lambda r:r.url.endswith('/action') and r.request.method=='POST') as response:
                    page.get_by_role('button',name=action['label'],exact=True).click()
                assert response.value.status==200,response.value.text()
                after=response.value.json()
                assert after['revision']==before['revision']+1
                if kind=='hu':
                    assert after['finished'] and after['result']['winner']==0
                    assert sum(after['result']['scores'])==0
                    page.get_by_role('dialog').wait_for()
                else:
                    meld=next(m for m in after['players'][0]['melds'] if m['type']=={'chi':'chi','peng':'peng','gang_an':'angang','gang_ming':'gang','gang_bu':'gang'}[kind])
                    if kind=='gang_bu':assert meld['added']
                    assert len(meld['tiles'])==(4 if kind.startswith('gang') else 3)
                    if kind in ('chi','peng','gang_ming'):
                        assert sum(len(x['discards']) for x in after['players'])==sum(len(x['discards']) for x in before['players'])-1
                    if kind.startswith('gang'):
                        assert after['wallCount']==before['wallCount']-1
                page.screenshot(path=str(OUT/(kind+'-after.png')),full_page=True)
                detail=dict(action=action,revision=after['revision'])
            assert not errors,errors
            assert not privacy,privacy
            report.append(dict(case=kind,passed=True,seconds=round(time.monotonic()-start,2),snapshots=len(snapshots),**detail))
            print(json.dumps(report[-1],ensure_ascii=False),flush=True)
            context.close()
    except Exception:
        page.screenshot(path=str(OUT/'failure.png'),full_page=True)
        raise
    finally:
        browser.close()
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
