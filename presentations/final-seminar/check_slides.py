"""Browser checks for the standalone deck; no Django/database access.

Use a temporary Playwright environment rather than adding an app dependency.
Run from any directory with: uv run --with playwright python path/to/check_slides.py
Set PLAYWRIGHT_BROWSERS_PATH if using an existing browser installation.
"""

from pathlib import Path
import os
import json
import re
import tempfile

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
CAPTURES = Path(tempfile.gettempdir()) / "smart-final-seminar-checks"
CAPTURES.mkdir(exist_ok=True)


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("SLIDES_BROWSER_PATH"))
        context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
        context.set_offline(True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((ROOT / "index.html").as_uri())
        page.evaluate("localStorage.clear()")
        page.reload()
        page.evaluate("document.fonts.ready")
        assert page.locator(".slide").count() == 11
        assert "Python owns the calendar" in page.locator(".slide").nth(5).text_content()
        assert "Live OAuth setup pending" in page.locator(".slide").nth(9).text_content()
        assert "596 passed" in page.locator(".slide").nth(6).text_content()
        assert page.evaluate("[...document.querySelectorAll('.slide')].reduce((n,s)=>n+Number(s.dataset.seconds),0)") == 350
        assert page.evaluate("document.fonts.check('40px Instrument')")
        assert page.evaluate("[...document.querySelectorAll('.slide img')].every(img=>img.src.startsWith('data:'))")
        assert '5:50' in (ROOT / 'speaker-notes.md').read_text()
        assert 'n>=360' in (ROOT / 'index.html').read_text()

        assert page.locator(".slide img").evaluate_all("images=>images.length>=4&&images.every(img=>img.complete&&img.naturalWidth>0)")

        # Fixed stage must stay proportional and contain its visible text at both sizes.
        for width, height in [(1280, 720), (390, 844)]:
            page.set_viewport_size({"width": width, "height": height})
            for index in range(11):
                page.evaluate("i=>presentation.showSlide(i)", index)
                page.wait_for_timeout(250)
                assert page.locator(".slide.active").count() == 1
                stage = page.locator("#deckStage").bounding_box()
                assert abs(stage["width"] / stage["height"] - 16 / 9) < 0.001
                assert stage["x"] >= -1 and stage["y"] >= -1
                problems = page.locator(".slide.active").evaluate("""slide=>{
                    const rect=slide.getBoundingClientRect(), footer=slide.querySelector('footer').getBoundingClientRect();
                    const clearance=4*rect.width/1920;
                    return [...slide.querySelectorAll('[data-edit],figure')].flatMap(el=>{
                        const r=el.getBoundingClientRect();
                        const messages=[];
                        if(r.left<rect.left-1||r.right>rect.right+1||r.top<rect.top-1||r.bottom>footer.top-clearance)messages.push(el.tagName+': outside content area: '+el.textContent.slice(0,45));
                        if(el.scrollWidth>el.clientWidth+2||(!/^H[123]$/.test(el.tagName)&&el.scrollHeight>el.clientHeight+2))messages.push(el.tagName+': internal overflow: '+el.textContent.slice(0,45));
                        return messages;
                    });
                }""")
                assert not problems, f"Slide {index+1}, viewport {width}: {problems}"
                overlaps = page.locator('.slide.active').evaluate("""slide=>{
                    const messages=[];
                    for(const group of slide.querySelectorAll('.recap-grid,.two-column,.availability-layout,.reliability-layout,.cloud-nodes,.pipeline,.reach-layout')){
                        const children=[...group.children];
                        for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++){
                            const a=children[i].getBoundingClientRect(),b=children[j].getBoundingClientRect();
                            if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)messages.push(group.className+': overlapping panels');
                        }
                    }
                    for(const note of slide.querySelectorAll('.note-line')){
                        for(const figure of slide.querySelectorAll('figure')){
                            const range=document.createRange();range.selectNodeContents(note);
                            const b=figure.getBoundingClientRect();
                            for(const a of range.getClientRects()){
                                if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)messages.push('Note text overlaps screenshot/caption');
                            }
                        }
                    }
                    return messages;
                }""")
                assert not overlaps, f'Slide {index+1}: {overlaps}'
                page.evaluate("document.body.classList.remove('show-controls')")
                page.screenshot(path=str(CAPTURES / f"slide-{index+1}-{width}.png"))

        page.set_viewport_size({"width": 1280, "height": 720})
        page.keyboard.press("Home")
        page.keyboard.press("ArrowRight")
        assert page.locator("#count").inner_text() == "2 / 11"
        page.keyboard.press("PageDown")
        assert page.locator("#count").inner_text() == "3 / 11"
        page.keyboard.press("Space")
        assert page.locator("#count").inner_text() == "4 / 11"
        page.keyboard.press("PageUp")
        assert page.locator("#count").inner_text() == "3 / 11"
        page.keyboard.press("End")
        assert page.locator("#next").is_disabled()
        page.keyboard.press("ArrowRight")
        assert page.locator("#count").inner_text() == "11 / 11"
        page.keyboard.press("Home")
        assert page.locator("#previous").is_disabled()
        # Notes live only in a separate offline presenter window. Both windows
        # control the same slide/timer state; the audience never gets an overlay.
        with page.expect_popup() as opened:
            page.keyboard.press("n")
        presenter = opened.value
        presenter.set_viewport_size({"width": 1000, "height": 850})
        presenter.on("pageerror", lambda error: errors.append(str(error)))
        presenter.locator("#notes-copy").wait_for()
        assert "Private Presenter" in presenter.title()
        assert presenter.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert "0:00–0:15" in presenter.locator("#notes-budget").inner_text()
        assert "Smart Schedule started" in presenter.locator("#notes-copy").inner_text()
        assert page.locator("#notes-panel, #notes-copy").count() == 0
        assert page.locator(".speaker-notes:visible").count() == 0
        assert "Share only the original slides window" in presenter.locator("header").inner_text()
        presenter.get_by_role("button", name="Next →").click()
        assert page.locator("#count").inner_text() == "2 / 11"
        assert "The original problem" in presenter.locator("#notes-copy").inner_text()
        assert "Up next: 3." in presenter.locator("#next-slide").inner_text()
        presenter.keyboard.press("PageDown")
        assert page.locator("#count").inner_text() == "3 / 11"
        page.keyboard.press("End")
        assert presenter.locator("#presenter-count").inner_text() == "11 / 11"
        assert presenter.locator("#presenter-next").is_disabled()
        assert "Final slide" in presenter.locator("#next-slide").inner_text()
        presenter.keyboard.press("Home")
        assert presenter.locator("#presenter-previous").is_disabled()
        page.keyboard.press("p")
        assert len(context.pages) == 2, "Reuse the already open presenter window"
        presenter.screenshot(path=str(CAPTURES / "presenter-view.png"), full_page=True)
        page.screenshot(path=str(CAPTURES / "audience-with-presenter-open.png"))
        presenter.get_by_role("button", name="Start timer").click()
        page.wait_for_timeout(1150)
        presenter.get_by_role("button", name="Pause timer").click()
        assert page.locator("#clock").inner_text() == presenter.locator("#presenter-clock").inner_text()
        assert not page.evaluate("presentation.running")
        presenter.get_by_role("button", name="Reset", exact=True).click()
        assert page.locator("#clock").inner_text() == "0:00"
        assert presenter.locator("#presenter-clock").inner_text() == "0:00"
        presenter.close()

        # A blocked popup must never fall back to displaying notes to the audience.
        page.evaluate("window.originalOpen=window.open; window.open=()=>null")
        page.keyboard.press("n")
        assert page.locator("#presenter-status").is_visible()
        assert "Allow popups" in page.locator("#presenter-status").inner_text()
        assert page.locator(".speaker-notes:visible").count() == 0
        page.evaluate("window.open=window.originalOpen; delete window.originalOpen")
        with page.expect_popup() as reopened:
            page.get_by_role("button", name="Presenter", exact=True).click()
        assert page.locator("#presenter-status").is_hidden()
        reopened.value.locator("#notes-copy").wait_for()
        reopened.value.close()
        page.keyboard.press("t")
        page.wait_for_timeout(1150)
        page.keyboard.press("t")
        assert page.locator("#clock").inner_text() == "0:01"
        paused = page.evaluate("presentation.totalElapsed()")
        page.wait_for_timeout(100)
        assert page.evaluate("presentation.totalElapsed()") == paused
        page.evaluate("presentation.elapsed=360; presentation.updateClock()")
        assert "overtime" in page.locator("#clock").get_attribute("class")
        page.keyboard.press("r")
        assert page.locator("#clock").inner_text() == "0:00"

        # Editing must retain text, suppress slide shortcuts, and produce portable HTML.
        page.keyboard.press("e")
        title = page.locator(".slide.active h1")
        title.fill("Smart Schedule — rehearsal")
        title.press("ArrowRight")
        assert page.locator("#count").inner_text() == "1 / 11"
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
        with page.expect_popup() as exported_presenter:
            page.keyboard.press("p")
        exported_presenter.value.locator("#notes-copy").wait_for()
        exported_presenter.value.close()
        page.goto((ROOT / "index.html").as_uri())
        page.evaluate("localStorage.clear()")
        page.reload()
        assert page.locator("h1").inner_text() == "Smart\nSchedule."

        # Wheel, swipe and direct URL navigation all use the same controller.
        page.mouse.move(600, 400)
        page.mouse.wheel(0, 100)
        page.wait_for_timeout(100)
        assert page.locator("#count").inner_text() == "2 / 11"
        page.evaluate("""()=>{
            const stage=document.getElementById('deckStage');
            stage.dispatchEvent(new TouchEvent('touchstart',{touches:[new Touch({identifier:1,target:stage,clientX:250,clientY:200})]}));
            stage.dispatchEvent(new TouchEvent('touchend',{changedTouches:[new Touch({identifier:1,target:stage,clientX:100,clientY:205})]}));
        }""")
        assert page.locator("#count").inner_text() == "3 / 11"
        page.goto((ROOT / "index.html").as_uri() + "#5")
        assert page.locator("#count").inner_text() == "5 / 11"
        assert not errors, errors

        # Print honors CSS page size and reveals every slide without presenter UI.
        page.keyboard.press("Home")
        page.pdf(path=str(ROOT / "smart-schedule-final.pdf"), print_background=True, prefer_css_page_size=True)
        pdf = (ROOT / "smart-schedule-final.pdf").read_bytes()
        assert len(re.findall(rb"/Type /Page\b", pdf)) == 11, "PDF must contain eleven pages"
        assert b"/MediaBox [0 0 1440 810]" in pdf, "PDF must stay widescreen"
        browser.close()
        print(json.dumps({"result": "PASS", "slides": 11, "viewports": ["1280×720", "390×844"], "private_presenter": "PASS", "script_budget_seconds": 350, "pdf_pages": 11, "browser_errors": errors, "screenshots": str(CAPTURES)}, indent=2))


if __name__ == "__main__":
    main()
