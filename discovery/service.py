import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from . import store, sources, screening
from .settings import root, load

@contextmanager
def worker_lock(name="discovery"):
    path=root()/'data'/f'{name}.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    # OS releases the lock after a crash; the file itself may remain safely.
    with open(path,'a+b') as f:
        f.seek(0); f.write(b'0'); f.flush(); f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError: raise RuntimeError('Another discovery worker is running')
        try: yield
        finally:
            f.seek(0)
            if os.name=='nt': msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(f,fcntl.LOCK_UN)


def recover():
    for row in store.rows():
        if row['status'] in ('metadata','downloading','screening'):
            store.update(row['id'],status='error',reason='Interrupted; retry will resume from complete download')
        elif row['status']=='uploading':
            # Never blindly retry an ambiguous upload: it may already be on YouTube.
            store.update(row['id'],status='upload_uncertain',reason='Interrupted upload. Check YouTube Studio before retrying.')


def pending_candidates(cfg):
    candidates=[]
    now=time.time()
    for row in reversed(store.rows()):
        if not sources.enabled_candidate(row,cfg):continue
        if row['attempts']>=cfg['max_retries']:continue
        if row['status']=='error' and now-row['updated']<cfg['retry_minutes']*60:continue
        if row['status'] in ('found','error') or (row['status']=='needs_permission' and sources.permitted(row['url'],json.loads(row['info']),cfg)):
            candidates.append(row)
    # Fresh candidates are not held up by repeatedly failing older entries.
    candidates.sort(key=lambda r:(r['status']=='error',r['id']))
    return candidates[:cfg['max_candidates_per_cycle']]


def cycle(cfg):
    sources.discover(cfg)
    downloaded=0
    candidates=pending_candidates(cfg)
    store.event(f'Eligible candidates this cycle: {len(candidates)}')
    processed=[]
    for row in candidates:
        if row['attempts']>=cfg['max_retries']: continue
        if row['status']=='error' and time.time()-row['updated']<cfg['retry_minutes']*60: continue
        if downloaded>=cfg['max_downloads_per_cycle']: break
        cid=row['id']; folder=root()/'Downloads'/str(cid)
        processed.append(cid)
        try:
            used=sum(p.stat().st_size for name in ('Downloads','Screening') for p in (root()/name).rglob('*') if p.is_file())
            if used + cfg['max_download_mb']*1024*1024 > cfg['max_storage_mb']*1024*1024:
                store.event('Download storage limit reached. Review or remove old Downloads/Screening files.');break
            store.update(cid,status='metadata',reason='Отримання тривалості, розміру та автора')
            store.event(f"Candidate {cid}: metadata started — {row['url']}")
            info=sources.metadata(row['url'],cfg)
            store.update(cid,info=json.dumps(info),title=info.get('title') or row['title'],creator=info.get('uploader') or '')
            store.event(f"Candidate {cid}: metadata OK — duration={info.get('duration')}s; size={info.get('width')}x{info.get('height')}")
            reason=screening.technical_reason(info,cfg)
            if reason:
                store.update(cid,status='rejected',reason=reason)
                store.event(f'Candidate {cid}: rejected — {reason}'); continue
            if not sources.permitted(row['url'],info,cfg):
                store.update(cid,status='needs_permission',reason='Add video or creator to approved sources if you have reuse permission')
                store.event(f'Candidate {cid}: needs_permission'); continue
            store.update(cid,status='downloading',attempts=row['attempts']+1)
            folder.mkdir(parents=True,exist_ok=True)
            video=Path(row['path']) if row['path'] else None
            if video is None or not video.is_file():
                # Clean previous partial media only inside this candidate's private folder.
                for old in folder.glob('video.*'): old.unlink()
                video=sources.ytdlp(row['url'],cfg,folder)
            downloaded+=1
            store.progress(f'Відео №{cid}: перевірка повторів')
            store.event(f'Candidate {cid}: download complete; checking duplicates')
            digest=screening.sha256(video)
            store.update(cid,path=str(video.resolve()),sha256=digest,status='screening')
            if any(r['id']!=cid and r['sha256']==digest and (r['report']!='{}' or r['status']=='published') for r in store.rows()):
                store.update(cid,status='duplicate',reason='Exact file already inspected'); video.unlink(); continue
            # Include the original bot history, without changing that database.
            import config, sqlite3
            if Path(config.DATABASE_FILE).exists():
                db=sqlite3.connect(Path(config.DATABASE_FILE).resolve().as_uri()+'?mode=ro',uri=True)
                try: exists=db.execute('SELECT 1 FROM videos WHERE sha256=? LIMIT 1',(digest,)).fetchone()
                finally: db.close()
                if exists:
                    store.update(cid,status='duplicate',reason='File exists in original bot history'); video.unlink(); continue
            store.event(f'Candidate {cid}: watermark screening started')
            report=screening.screen(video,root()/'Screening'/str(cid),cfg)
            fp=report.get('fingerprint')
            if report['status']=='clear' and fp:
                for old in store.rows():
                    if old['id']!=cid and old['fingerprint'] and screening.near_duplicate(fp,json.loads(old['fingerprint'])):
                        report.update(status='uncertain',reason=f"Possible visual duplicate of candidate {old['id']}"); break
            # Keep reports and images for review; paths point to this Windows installation.
            report_dir=root()/'Screening'/str(cid);report_dir.mkdir(parents=True,exist_ok=True)
            (report_dir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            status={'clear':'ready','detected':'watermark','uncertain':'review','off_topic':'rejected','rejected':'rejected'}[report['status']]
            store.update(cid,status=status,reason=report['reason'],report=json.dumps(report),fingerprint=json.dumps(fp) if fp else None)
            store.event(f"Candidate {cid}: {status} — {report['reason']}")
            if status in ('watermark','review','rejected'):
                store.event(f'Candidate {cid}: source retained for review (storage limit still applies)')
        except Exception as exc:
            message=f'{type(exc).__name__}: {sources.sanitize_error(exc,cfg)}'
            store.update(cid,status='error',reason=message,attempts=row['attempts']+1)
            store.event(f'Candidate {cid}: error — {message}')

    from collections import Counter
    counts=Counter(r['status'] for r in store.rows() if r['id'] in processed)
    summary=', '.join(f'{key}={value}' for key,value in sorted(counts.items())) or 'no candidates processed'
    store.event(f'Cycle summary: {summary}')
    store.progress(f'Перевірку завершено: {summary}')


def _process_ready(cfg,publish=False):
    import config
    # Must be set before importing the original pipeline, which imports constants by value.
    config.ENABLE_YOUTUBE_UPLOAD=True
    config.UPLOAD_VISIBILITY='public' if publish else 'private'
    import main
    from database.db import init_db, find_unfinished_run, get_video
    from queue.manager import create_new_queue, get_next_item, finalize_session
    init_db()
    if find_unfinished_run():
        store.event('Original bot has an unfinished run. Resolve it in the original GUI first.');return
    for row in reversed(store.rows()):
        if row['status']!='ready' or not sources.enabled_candidate(row,cfg): continue
        reservation=store.reserve_upload(row['id'],cfg)
        if reservation is None: store.event('Upload interval or daily limit reached');break
        source=Path(row['path'])
        if not source.is_file() or screening.sha256(source)!=row['sha256']:
            store.update(row['id'],status='error',reason='Inspected file missing or changed')
            store.finish_upload(reservation,'file_changed');continue
        # Recheck permission after settings may have changed.
        if not sources.permitted(row['url'],json.loads(row['info']),cfg):
            store.update(row['id'],status='needs_permission',reason='Reuse approval removed')
            store.finish_upload(reservation,'permission_removed');continue
        config.TO_UPLOAD.mkdir(parents=True,exist_ok=True)
        staged=config.TO_UPLOAD/f"discovery_{row['id']}_{row['sha256'][:12]}{source.suffix}"
        try:
            shutil.copy2(source,staged)
            os.environ['YOUTUBEBOT_GUI_COUNT']='1'
            state=create_new_queue([staged]);item=get_next_item(state)
            if item is None: raise RuntimeError('Queue item missing')
            store.update(row['id'],status='uploading',reason='Processing and uploading')
            main.ENABLE_YOUTUBE_UPLOAD=True
            main.UPLOAD_VISIBILITY='public' if publish else 'private'
            store.progress(f"Відео №{row['id']}: обробка та публікація")
            main.process_queue_item(state,item)
            finalize_session(state)
            result=get_video(item['video_id']) or {}
            store.update(row['id'],status='published',reason=result.get('youtube_url') or 'Upload confirmed')
            store.finish_upload(reservation,'published')
            source.unlink(missing_ok=True)
        except Exception as exc:
            store.update(row['id'],status='upload_uncertain',reason='Pipeline stopped. Inspect original queue and YouTube Studio before any retry.')
            store.finish_upload(reservation,'uncertain')
            store.event(f"Pipeline stopped: {type(exc).__name__}; manual reconciliation required")
            break


def process_ready(cfg,publish=False):
    with worker_lock("pipeline"):
        _process_ready(cfg,publish)


def run(watch=False,process=False,publish=False):
    with worker_lock():
        recover()
        while True:
            cfg=load()
            store.event(f"Discovery cycle started; youtube={cfg['youtube_search']}; reddit={cfg['reddit_search']}; search timeout={cfg.get('search_timeout_seconds',45)}s; metadata timeout={cfg.get('metadata_timeout_seconds',60)}s")
            cycle(cfg)
            if process: process_ready(cfg,publish)
            store.event('Discovery cycle finished')
            if not watch: break
            store.progress(f"Очікування наступного циклу: {cfg['interval_minutes']} хв")
            for _ in range(int(cfg['interval_minutes']*60)):
                time.sleep(1)
                if _%10==0:store.heartbeat()
