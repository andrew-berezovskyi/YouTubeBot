"""Local dependency checks; does not search, download or publish videos."""
import asyncio
import importlib.util
import json
import subprocess
from urllib.request import urlopen
import config
from discovery.settings import load

async def check_browser():
    """Exercise startup and await cleanup before reporting success.

    Uses a temporary headless browser, without the Google profile or network.
    The old check stopped the sync driver after only reading executable_path.
    """
    from playwright.async_api import async_playwright

    async def probe():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, timeout=30000)
            try:
                context = await browser.new_context()
                try:
                    page = await context.new_page()
                    await page.set_content("<title>VibeRush diagnostic</title><p>OK</p>", timeout=10000)
                    if await page.title() != "VibeRush diagnostic":
                        raise RuntimeError("Browser page check failed")
                finally:
                    await context.close()
            finally:
                await browser.close()
        return "Chromium launched, page checked and browser closed; Google sign-in not tested"

    return await probe()


def main():
    failures=[]
    def check(label,fn):
        try:
            result=fn();print(f'OK  {label}: {result}')
        except Exception as exc:
            failures.append(label);print(f'FAIL {label}: {type(exc).__name__}: {exc}')
    cfg=load()
    from discovery.runtime import require_runtime
    check('YouTube JavaScript runtime',require_runtime)
    def package(name):
        if importlib.util.find_spec(name) is None:raise RuntimeError('Install requirements.txt')
        return 'installed'
    for name in ('yt_dlp_ejs','yt_dlp','ollama','playwright','pytesseract','PIL'):check(name,lambda n=name:package(n))
    def executable(path):
        subprocess.run([str(path),'-version'],capture_output=True,check=True,timeout=10)
        return 'available'
    check('FFmpeg',lambda:executable(config.FFMPEG));check('FFprobe',lambda:executable(config.FFPROBE))
    def ocr():
        import pytesseract
        if cfg['tesseract_cmd']:pytesseract.pytesseract.tesseract_cmd=cfg['tesseract_cmd']
        return str(pytesseract.get_tesseract_version())
    check('Tesseract OCR',ocr)
    def models():
        with urlopen(config.OLLAMA_HOST.rstrip('/')+'/api/tags',timeout=10) as response:data=json.load(response)
        names={m['name'] for m in data.get('models',[])}
        missing={config.VISION_MODEL,config.METADATA_MODEL}-names
        if missing:raise RuntimeError('Missing models: '+', '.join(sorted(missing)))
        return 'vision and metadata models available'
    check('Ollama models',models)
    def browser():
        return asyncio.run(check_browser())
    check('Playwright browser',browser)
    return bool(failures)

if __name__=='__main__':raise SystemExit(main())
