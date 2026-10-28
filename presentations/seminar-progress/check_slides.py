"""Browser checks for the standalone deck; no Django/database access.

Use a temporary Playwright environment rather than adding an app dependency.
Run from any directory with: uv run --with playwright python path/to/check_slides.py
Set PLAYWRIGHT_BROWSERS_PATH if using an existing browser installation.
"""

from pathlib import Path
import json
import re
import tempfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
CAPTURES = Path(tempfile.gettempdir()) / "smart-seminar-checks"
CAPTURES.mkdir(exist_ok=True)


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((ROOT / "index.html").as_uri())
        page.evaluate("localStorage.clear()")
        page.reload()
        page.evaluate("document.fonts.ready")
        assert page.locator(".slide").count() == 6
        assert page.evaluate("[...document.querySelectorAll('.slide')].reduce((n,s)=>n+Number(s.dataset.seconds),0)") == 175
        assert page.evaluate("document.fonts.check('40px Instrument')")
        assert page.locator(".slide img").evaluate("img=>img.complete&&img.naturalWidth>0")

        # Fixed stage must stay proportional and contain its visible text at both sizes.
        for width, height in [(1280, 720), (390, 844)]:
            page.set_viewport_size({"width": width, "height": height})
            for index in range(6):
                page.evaluate("i=>presentation.showSlide(i)", index)
                page.wait_for_timeout(250)
                assert page.locator(".slide.active").count() == 1
                stage = page.locator("#deckStage").bounding_box()
                assert abs(stage["width"] / stage["height"] - 16 / 9) < 0.001
                assert stage["x"] >= -1 and stage["y"] >= -1
                problems = page.locator(".slide.active").evaluate("""slide=>{
                    const rect=slide.getBoundingClientRect(), footer=slide.querySelector('footer').getBoundingClientRect();
                    return [...slide.querySelectorAll('[data-edit],figure')].flatMap(el=>{
                        const r=el.getBoundingClientRect();
                        const messages=[];
                        if(r.left<rect.left-1||r.right>rect.right+1||r.top<rect.top-1||r.bottom>footer.top-3)messages.push(el.tagName+': outside content area: '+el.textContent.slice(0,45));
                        if(el.scrollWidth>el.clientWidth+2||(!/^H[123]$/.test(el.tagName)&&el.scrollHeight>el.clientHeight+2))messages.push(el.tagName+': internal overflow: '+el.textContent.slice(0,45));
                        return messages;
                    });
                }""")
                assert not problems, f"Slide {index+1}, viewport {width}: {problems}"
                page.screenshot(path=str(CAPTURES / f"slide-{index+1}-{width}.png"))

        page.set_viewport_size({"width": 1280, "height": 720})
        page.keyboard.press("Home")
        page.keyboard.press("ArrowRight")
        assert page.locator("#count").inner_text() == "2 / 6"
        page.keyboard.press("PageDown")
        assert page.locator("#count").inner_text() == "3 / 6"
        page.keyboard.press("Space")
        assert page.locator("#count").inner_text() == "4 / 6"
        page.keyboard.press("PageUp")
        assert page.locator("#count").inner_text() == "3 / 6"
        page.keyboard.press("End")
        assert page.locator("#next").is_disabled()
        page.keyboard.press("ArrowRight")
        assert page.locator("#count").inner_text() == "6 / 6"
        page.keyboard.press("Home")
        assert page.locator("#previous").is_disabled()
        page.keyboard.press("n")
        assert page.locator("#notes-panel").is_visible()
        assert "0:00–0:20" in page.locator("#notes-budget").inner_text()
        page.keyboard.press("Escape")
        assert page.locator("#notes-panel").is_hidden()
        page.keyboard.press("t")
        page.wait_for_timeout(1150)
        page.keyboard.press("t")
        assert page.locator("#clock").inner_text() == "0:01"
        paused = page.evaluate("presentation.totalElapsed()")
        page.wait_for_timeout(100)
        assert page.evaluate("presentation.totalElapsed()") == paused
        page.evaluate("presentation.elapsed=180; presentation.updateClock()")
        assert "overtime" in page.locator("#clock").get_attribute("class")
        page.keyboard.press("r")
        assert page.locator("#clock").inner_text() == "0:00"

        # Editing must retain text, suppress slide shortcuts, and produce portable HTML.
        page.keyboard.press("e")
        title = page.locator(".slide.active h1")
        title.fill("Smart Schedule — rehearsal")
        title.press("ArrowRight")
        assert page.locator("#count").inner_text() == "1 / 6"
        with page.expect_download() as download_info:
            page.keyboard.press("Control+s")
        downloaded = CAPTURES / "edited-presentation.html"
        download_info.value.save_as(downloaded)
        page.keyboard.press("Escape")
        page.reload()
        assert page.locator("h1").inner_text() == "Smart Schedule — rehearsal"
        context.clear_permissions()
        page.evaluate("localStorage.clear()")
        page.goto(downloaded.as_uri())
        assert page.locator("h1").inner_text() == "Smart Schedule — rehearsal"
        page.goto((ROOT / "index.html").as_uri())
        page.evaluate("localStorage.clear()")
        page.reload()
        assert page.locator("h1").inner_text() == "Smart\nSchedule."

        # Wheel, swipe and direct URL navigation all use the same controller.
        page.mouse.move(600, 400)
        page.mouse.wheel(0, 100)
        page.wait_for_timeout(100)
        assert page.locator("#count").inner_text() == "2 / 6"
        page.evaluate("""()=>{
            const stage=document.getElementById('deckStage');
            stage.dispatchEvent(new TouchEvent('touchstart',{touches:[new Touch({identifier:1,target:stage,clientX:250,clientY:200})]}));
            stage.dispatchEvent(new TouchEvent('touchend',{changedTouches:[new Touch({identifier:1,target:stage,clientX:100,clientY:205})]}));
        }""")
        assert page.locator("#count").inner_text() == "3 / 6"
        page.goto((ROOT / "index.html").as_uri() + "#5")
        assert page.locator("#count").inner_text() == "5 / 6"
        assert not errors, errors

        # Print honors CSS page size and reveals every slide without presenter UI.
        page.keyboard.press("Home")
        page.pdf(path=str(ROOT / "smart-schedule-progress.pdf"), print_background=True, prefer_css_page_size=True)
        pdf = (ROOT / "smart-schedule-progress.pdf").read_bytes()
        assert len(re.findall(rb"/Type /Page\b", pdf)) == 6, "PDF must contain six pages"
        assert b"/MediaBox [0 0 1440 810]" in pdf, "PDF must stay widescreen"
        browser.close()
        print(json.dumps({"result": "PASS", "slides": 6, "viewports": ["1280×720", "390×844"], "script_budget_seconds": 175, "pdf_pages": 6, "browser_errors": errors, "screenshots": str(CAPTURES)}, indent=2))


if __name__ == "__main__":
    main()
