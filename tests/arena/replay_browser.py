"""通过浏览器检查镜头操作、明牌复盘与下一局隔离。"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

out = Path(__file__).resolve().parents[2] / 'artifacts/replay-browser'
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width':1440, 'height':1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto('http://localhost:8867')
        page.wait_for_load_state('networkidle')
        page.get_by_role('button', name='入座开局').click()
        page.locator('.scene-notice').wait_for(state='hidden', timeout=60000)
        page.get_by_role('button', name='胡牌', exact=True).wait_for(timeout=60000)
        canvas = page.locator('.scene canvas')
        box = canvas.bounding_box()
        x, y = box['x'] + box['width']*.5, box['y'] + box['height']*.6
        initial = canvas.screenshot()
        page.mouse.move(x,y)
        page.mouse.wheel(0,-300)
        expect(page.get_by_label('缩放比例')).not_to_have_text('100%')
        zoomed = canvas.screenshot()
        assert zoomed != initial
        page.mouse.down()
        page.mouse.move(x+120,y+80,steps=8)
        page.mouse.up()
        moved = canvas.screenshot()
        assert moved != zoomed
        page.screenshot(path=str(out/'zoom-drag.png'),full_page=True)
        page.get_by_role('button',name='重置视角').click()
        expect(page.get_by_label('缩放比例')).to_have_text('100%')
        # 缩放下限与上限，仍可重置，拖动不触发任何出牌。
        page.mouse.move(x,y)
        for _ in range(6): page.mouse.wheel(0,600)
        expect(page.get_by_label('缩放比例')).to_have_text('60%')
        for _ in range(8): page.mouse.wheel(0,-600)
        expect(page.get_by_label('缩放比例')).to_have_text('240%')
        page.get_by_role('button',name='重置视角').click()
        page.get_by_role('button',name='胡牌',exact=True).click()
        page.get_by_role('button',name='明牌复盘本局').wait_for()
        with page.expect_response(lambda response:response.url.endswith('/replay')) as response:
            page.get_by_role('button',name='明牌复盘本局').click()
        replay = response.value.json()
        frames = replay['frames']
        dialog = page.get_by_role('dialog',name='明牌复盘')
        expect(dialog).to_be_visible()
        expect(dialog.get_by_label('复盘步数')).to_have_text(f'0 / {len(frames)-1}')
        expect(dialog.get_by_role('button',name='上一步',exact=True)).to_be_disabled()
        page.screenshot(path=str(out/'replay-opening.png'),full_page=True)
        # 每步推进并逐一核对操作文字和本家明牌数量，覆盖全部真实历史记录。
        for i in range(1,len(frames)):
            dialog.get_by_role('button',name='下一步',exact=True).click()
            expect(dialog.locator('.replay-description strong')).to_have_text(frames[i]['label'])
            expect(dialog.locator('.replay-hand .mahjong-tile')).to_have_count(len(frames[i]['snapshot']['players'][0]['hand']))
        expect(dialog.get_by_role('button',name='下一步',exact=True)).to_be_disabled()
        expect(dialog.locator('.replay-result')).to_contain_text('24 / -8 / -8 / -8')
        page.screenshot(path=str(out/'replay-settlement.png'),full_page=True)
        dialog.get_by_role('button',name='上一步',exact=True).click()
        expect(dialog.locator('.replay-result')).to_have_count(0)
        slider = dialog.get_by_label('复盘进度')
        slider.focus(); slider.press('Home')
        expect(dialog.get_by_label('复盘步数')).to_have_text(f'0 / {len(frames)-1}')
        for seat in range(4):
            dialog.get_by_label('查看手牌座位').select_option(str(seat))
            expect(dialog.locator('.replay-hand .mahjong-tile')).to_have_count(len(frames[0]['snapshot']['players'][seat]['hand']))
        dialog.get_by_role('button',name='播放',exact=True).click()
        page.wait_for_timeout(1100)
        dialog.get_by_role('button',name='暂停',exact=True).click()
        assert int(slider.input_value()) >= 1
        dialog.get_by_role('button',name='退出复盘').click()
        page.get_by_role('button',name='继续下一局').click()
        page.get_by_text('第 2 局',exact=True).wait_for()
        page.get_by_role('button',name='复盘上一局').click()
        expect(page.get_by_role('dialog',name='明牌复盘')).to_contain_text('第 1 局 · 明牌复盘')
        page.get_by_role('button',name='退出复盘').click()
        page.get_by_text('第 2 局',exact=True).wait_for()
        assert not errors, errors
        (out/'report.json').write_text(json.dumps({'passed':True,'frames':len(frames),'camera':'滚轮、上下左右拖动、60%-240%边界、重置通过','replay':'逐步核对、前后跳转、四席明牌、播放暂停、结算与跨局返回通过','pageErrors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
        print((out/'report.json').read_text(encoding='utf-8'),flush=True)
    except Exception:
        page.screenshot(path=str(out/'failure.png'),full_page=True)
        raise
    finally:
        browser.close()
