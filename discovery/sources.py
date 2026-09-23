import json
import subprocess
import sys
import tempfile
import time
import re
from urllib.error import HTTPError
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode, quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import config

HOSTS = ("youtube.com", "youtu.be", "reddit.com", "redd.it", "tiktok.com", "vimeo.com")

def canonical_url(url):
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.username or p.password or p.port not in (None,443): raise ValueError("Only public HTTPS platform URLs are supported")
    if not any(host == h or host.endswith('.'+h) for h in HOSTS): raise ValueError(f"Unsupported platform: {host}")
    if host in ("youtu.be", "www.youtu.be"):
        return "https://www.youtube.com/watch?v=" + p.path.strip('/').split('/')[0]
    if host.endswith("youtube.com"):
        video = parse_qs(p.query).get("v", [None])[0]
        if p.path.startswith(("/shorts/", "/live/")): video = p.path.split('/')[2]
        if video: return "https://www.youtube.com/watch?v=" + quote(video, safe='-_')
    return urlunsplit(("https",host,p.path.rstrip('/'),p.query if p.path == '/results' else '', ''))

def sanitize_error(text,cfg=None):
    """Keep useful extractor errors while removing access material."""
    text=re.sub(r'\x1b\[[0-9;]*m','',str(text))
    if cfg and cfg.get('cookie_file'): text=text.replace(cfg['cookie_file'],'[cookie file]')
    safe=[]
    for line in text.splitlines():
        if re.search(r'(?:authorization|set-cookie|cookie)\s*[:=]',line,re.I):
            safe.append('[authentication detail omitted]');continue
        line=re.sub(r'https?://[^\s<>]+','[URL]',line)
        line=re.sub(r'(?i)\b(token|password|secret|api_key|signature)\s*[:=]\s*[^\s,;]+',r'\1=[redacted]',line)
        line=re.sub(r'[A-Za-z]:\\[^\r\n]+','[local path]',line)
        if line.strip():safe.append(line.strip())
    safe.sort(key=lambda line: 0 if 'ERROR:' in line else 1)
    return ' | '.join(safe[:5])[:900] or 'Extractor returned no diagnostic details'


def request_timeout(cfg,download=False,kind='metadata'):
    if download:return cfg['download_timeout_seconds']
    return cfg.get('search_timeout_seconds',45) if kind=='search' else cfg.get('metadata_timeout_seconds',60)


def wait_for_process(process,timeout):
    from .store import heartbeat
    deadline=time.monotonic()+timeout
    try:
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired(process.args,timeout)
            try:return process.wait(timeout=min(10,remaining))
            except subprocess.TimeoutExpired:heartbeat()
    except (subprocess.TimeoutExpired,KeyboardInterrupt):
        if sys.platform=='win32':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
        process.kill();process.wait()
        raise


def ytdlp(target, cfg, download_dir=None, *, kind='metadata'):
    from .store import progress
    timeout=request_timeout(cfg,download_dir is not None,kind)
    phase='Завантаження відео' if download_dir is not None else ('Пошук відео' if kind=='search' else 'Отримання даних відео')
    progress(f'{phase}: {target}',timeout)
    args=[sys.executable,'-m','yt_dlp','--ignore-config','--no-progress','--socket-timeout','15',
          '--retries','1','--extractor-retries','1','--no-cache-dir','--playlist-end',str(cfg.get('youtube_scan_limit',40) if kind=='search' and urlsplit(target).path=='/results' else cfg['results_per_query'])]
    from .runtime import runtime_args
    args += runtime_args()
    if cfg.get('cookie_file'):
        cookies=Path(cfg['cookie_file'])
        if not cookies.is_absolute():cookies=Path(config.BASE_DIR)/cookies
        if not cookies.is_file():raise ValueError('Configured cookie_file does not exist')
        args+=['--cookies',str(cookies)]
    if download_dir is None:
        args+=['--skip-download','--dump-single-json']
        if kind=='search':args+=['--flat-playlist']
        else:args+=['--no-playlist']
    else:
        args+=['--no-simulate','--no-playlist','--max-filesize',f"{cfg['max_download_mb']}M",
               '--ffmpeg-location',str(config.FFMPEG),'-f',f"bv*[height<={1920}][height>={cfg['min_height']}]+ba/b[height<=1920][height>={cfg['min_height']}]",
               '--merge-output-format','mp4','-o',str(download_dir/'video.%(ext)s'),
               '--print','after_move:filepath']
    args+=['--',target]
    with tempfile.TemporaryFile(mode='w+',encoding='utf-8',errors='replace') as out, tempfile.TemporaryFile(mode='w+',encoding='utf-8',errors='replace') as err:
        process=subprocess.Popen(args,stdout=out,stderr=err,text=True,
                                 env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
        try:code=wait_for_process(process,timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'{phase}: timeout after {timeout:g} seconds') from None
        out.seek(0);output=out.read()
        err.seek(0);diagnostic=sanitize_error(err.read(),cfg)
        if code:raise RuntimeError(f'yt-dlp exit {code}: {diagnostic}')
    if download_dir is None:
        try:return json.loads(output)
        except json.JSONDecodeError:raise RuntimeError(f'yt-dlp returned invalid JSON: {diagnostic}') from None
    files=[p for p in download_dir.iterdir() if p.suffix.lower() in ('.mp4','.webm','.mkv','.mov')]
    if len(files)!=1:raise RuntimeError('Download did not produce exactly one complete video: '+diagnostic)
    if files[0].stat().st_size>cfg['max_download_mb']*1024*1024:raise RuntimeError('Downloaded video exceeds size limit')
    return files[0]


def entries(info):
    if info.get('entries') is not None:
        for item in info['entries']:
            if item: yield from entries(item)
    else: yield info

def discover(cfg):
    from .store import add, event, progress, rows
    known={r['url'] for r in rows()}
    jobs = [(youtube_search_url(q), 'youtube') for q in cfg['queries']] if cfg['youtube_search'] else []
    for u in cfg['source_urls']:
        try:
            url=canonical_url(u)
            if 'reddit.com' in urlsplit(url).hostname and not cfg['reddit_search']:continue
            jobs.append((url,'configured'))
        except ValueError: event('Invalid configured source URL; skipped')
    for target, source in jobs:
        try:
            event(f'Search {source}: {target}')
            count=0; scanned=0; skipped=0; duplicates=0
            items=list(entries(ytdlp(target,cfg,kind='search')))
            items.sort(key=lambda item: not is_short_entry(item))
            for item in items:
                scanned+=1
                if source=='youtube' and not youtube_candidate(item,cfg):
                    skipped+=1;continue
                url = item.get('webpage_url') or item.get('url')
                if url and not url.startswith('http') and item.get('ie_key') == 'Youtube': url='https://www.youtube.com/watch?v='+url
                if url:
                    try:
                        url=canonical_url(url)
                        if url in known:
                            duplicates+=1;continue
                        add(url,item.get('title',''),source)
                        known.add(url)
                        count+=1
                        if count>=cfg['results_per_query']:break
                    except ValueError: continue
            event(f"Search {source}: scanned={scanned}; selected={count}; skipped={skipped}; already_known={duplicates}")
            if source=="youtube" and count==0:
                event("No new matching candidates in this batch. Try a more specific query or a creator /shorts URL.")
        except Exception as e: event(f"Source {source}: {type(e).__name__}: {sanitize_error(e,cfg)}")
    if cfg['reddit_search']:
        for query in cfg['queries']:
            try:
                event(f'Reddit RSS search: {query}')
                progress(f'Пошук Reddit: {query}',30)
                url='https://www.reddit.com/search.rss?'+urlencode({'q':query+' has:video','sort':'new','limit':cfg['results_per_query']})
                req=Request(url,headers={'User-Agent':'VibeRushDiscovery/1.1 (personal video discovery)'})
                with urlopen(req,timeout=30) as response: feed=ET.fromstring(response.read(2_000_000))
                ns={'a':'http://www.w3.org/2005/Atom'}
                for item in feed.findall('a:entry',ns)[:cfg['results_per_query']]:
                    link=item.find('a:link',ns)
                    if link is not None: add(canonical_url(link.attrib['href']),item.findtext('a:title','',ns),'reddit')
            except HTTPError as e:
                event(f"Reddit RSS unavailable: HTTP {e.code} {e.reason}")
                if e.code in (401,403,429):
                    event('Reddit RSS blocked or rate-limited; remaining Reddit queries skipped for this cycle')
                    break
            except Exception as e:event(f"Reddit RSS unavailable: {type(e).__name__}: {sanitize_error(e,cfg)}")

def metadata(url,cfg):
    result=ytdlp(canonical_url(url),cfg)
    if result.get('entries') is not None: raise ValueError('Expected a single video')
    info = {key:result.get(key) for key in ('id','title','duration','width','height','uploader','uploader_url','channel_url','license','webpage_url','view_count','upload_date','is_live','live_status')}
    # Top-level dimensions can describe the selected low-resolution muxed
    # format. Inspect video streams, excluding storyboards/audio/DRM formats.
    formats=[f for f in result.get('formats',[]) if f.get('vcodec') not in (None,'none')
             and not f.get('has_drm') and f.get('url') and f.get('width') and f.get('height')
             and 0 < f['height'] <= 1920]
    if formats:
        suitable=[f for f in formats if not cfg['vertical_only'] or f['height']>f['width']]
        best=max(suitable or formats,key=lambda f:(f['height'],f['width']))
        info.update(width=best['width'],height=best['height'])
    from .store import event
    sizes=sorted({(f['width'],f['height']) for f in formats})
    event('Available video sizes: '+(', '.join(f'{w}x{h}' for w,h in sizes) or 'not provided')+
          f"; screening size={info.get('width')}x{info.get('height')}")
    return info


def permitted(url,info,cfg):
    # A license label alone is not proof of ownership. User approves exact videos or creators.
    def normalized(values):
        result=set()
        for value in values:
            try: result.add(canonical_url(value))
            except ValueError: continue
        return result
    if canonical_url(url) in normalized(cfg['approved_video_urls']): return True
    approved=normalized(cfg['approved_creator_urls'])
    for key in ('channel_url','uploader_url'):
        try:
            if info.get(key) and canonical_url(info[key]) in approved: return True
        except ValueError: pass
    return False


def enabled_candidate(row,cfg):
    host=(urlsplit(row['url']).hostname or '').lower()
    if (host=='redd.it' or host.endswith('.redd.it') or host=='reddit.com' or host.endswith('.reddit.com')) and not cfg['reddit_search']:
        return False
    if row['source']=='youtube' and not cfg['youtube_search']:return False
    return True


def youtube_search_url(query):
    # YoutubeSearchURLIE preserves Shorts shelves. ytsearch uses a videos-only
    # parameter in yt-dlp's YoutubeSearchIE. Do not rely on hashtag matching.
    return 'https://www.youtube.com/results?'+urlencode({'search_query':query})


def is_short_entry(item):
    return any(urlsplit(item.get(k) or '').path.startswith('/shorts/') for k in ('url','webpage_url'))


def youtube_candidate(item,cfg):
    from .screening import technical_reason
    short=is_short_entry(item)
    if cfg.get('youtube_shorts_only',False) and not short:return False
    if technical_reason(item,{**cfg,'min_height':0}):return False
    # Missing search dimensions are NOT proof of portrait orientation.
    # Shorts shelves or known short duration qualify for metadata inspection only.
    return short or isinstance(item.get('duration'),(int,float)) or bool(item.get('width') and item.get('height'))
