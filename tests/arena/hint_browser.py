"""真实浏览器验证三档提示、概率、只选牌不执行与清除。"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

out = Path(__file__).resolve().parents[2] / 'artifacts/ai-hint'
out.mkdir(parents=True, exist_ok=True)
reports = []
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
    try:
        for name in ['discard', 'chi', 'peng', 'gang_an', 'gang_ming', 'gang_bu', 'hu']:
            context = browser.new_context(viewport={'width':1440, 'height':1000})
            page = context.new_page()
            errors, mutations = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('request', lambda req: mutations.append(req.url) if req.url.rsplit('/',1)[-1] in ('action','advance','next') else None)
            try:
                page.goto('http://localhost:8867')
                page.wait_for_load_state('networkidle')
                with page.expect_response(lambda r: r.url.endswith('/api/rooms') and r.request.method == 'POST') as response:
                    page.get_by_role('button', name='入座开局').click()
                created = response.value.json()
                state = created['snapshot']
                path = 'http://localhost:8867/api/rooms/' + state['id']
                headers = {'x-room-token':created['token']}
                page.locator('.scene-notice').wait_for(state='hidden', timeout=60000)
                expect(page.get_by_role('button', name='AI 提示', exact=True)).to_be_enabled()
                assert state['currentPlayer'] == 0
                for difficulty in ['easy', 'medium', 'hard']:
                    page.get_by_label('提示 AI', exact=True).select_option(difficulty)
                    expect(page.locator('.tile-probability')).to_have_count(0)
                    with page.expect_response(lambda r: r.url.endswith('/hint')) as response:
                        page.get_by_role('button', name='AI 提示', exact=True).click()
                    hint = response.value.json()
                    scores = {a['id']:a['probability'] for a in hint['actions']}
                    expect(page.get_by_role('button', name='AI 提示', exact=True)).to_be_enabled()
                    expect(page.locator('.tile-probability')).to_have_count(len(state['players'][0]['hand']))
                    assert page.request.get(path, headers=headers).json() == state
                    assert not mutations, mutations
                    discards = [a for a in state['legalActions'] if a['kind'] == 'discard']
                    if discards:
                        best = max(discards, key=lambda a:scores[a['id']])
                        index = state['players'][0]['hand'].index(best['tile'])
                        expect(page.locator('.hand-tile').nth(index).locator('.mahjong-tile')).to_have_class(__import__('re').compile(r'.*selected.*'))
                    else:
                        expect(page.locator('.hand-rack .selected')).to_have_count(0)
                    for i, tile in enumerate(state['players'][0]['hand']):
                        action = next((a for a in discards if a['tile']==tile), None)
                        value = f"{scores[action['id']]*100:.2f}%" if action else '—'
                        expect(page.locator('.tile-probability').nth(i)).to_have_text(value)
                    for action in state['legalActions']:
                        if action['kind'] == 'discard': continue
                        button = page.locator('.action-row button').filter(has_text=action['label'])
                        expect(button.locator('.action-probability')).to_have_text(f"{scores[action['id']]*100:.2f}%")
                    assert not errors, errors
                page.screenshot(path=str(out/(name+'.png')),full_page=True)
                if name == 'discard':
                    page.set_viewport_size({'width':390,'height':844})
                    page.screenshot(path=str(out/'mobile.png'),full_page=True)
                    assert page.locator('.hand-rack').evaluate('(el)=>el.scrollWidth <= el.clientWidth')
                    page.set_viewport_size({'width':1440,'height':1000})
                    # 推理失败只影响提示，不阻断手动出牌；之后仍可重新提示。
                    page.route('**/hint', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"提示暂不可用"}'), times=1)
                    page.get_by_role('button',name='AI 提示',exact=True).click()
                    expect(page.locator('.hint-error')).to_have_text('提示暂不可用')
                    expect(page.locator('.tile-probability')).to_have_count(0)
                    expect(page.get_by_role('button',name='出牌',exact=True)).to_be_enabled()
                    page.get_by_role('button',name='AI 提示',exact=True).click()
                    expect(page.locator('.hint-error')).to_have_count(0)
                    expect(page.locator('.tile-probability')).to_have_count(len(state['players'][0]['hand']))
                    page.get_by_role('button',name='出牌',exact=True).click()
                    expect(page.locator('.tile-probability')).to_have_count(0)
                    assert mutations
                reports.append(dict(scenario=name, difficulties=['easy','medium','hard'], passed=True, pageErrors=errors))
            except Exception:
                page.screenshot(path=str(out/(name+'-failure.png')),full_page=True)
                raise
            finally:
                context.close()
        (out/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(reports,ensure_ascii=False),flush=True)
    finally:
        browser.close()
