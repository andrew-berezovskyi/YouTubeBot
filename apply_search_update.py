"""Apply the requested portrait / 3-minute profile without replacing private settings."""
import json
import shutil
from discovery.settings import load,root
from discovery.service import worker_lock
from discovery import store

def main():
    with worker_lock('discovery'):
        cfg=load()
        path=root()/'discovery_settings.json'
        backup=path.with_name('discovery_settings.before_1.1.4.json')
        if path.exists() and not backup.exists():shutil.copy2(path,backup)
        cfg.update(min_duration=5,max_duration=180,vertical_only=True,youtube_shorts_only=False,youtube_scan_limit=60)
        temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)
        count=0
        for row in store.rows():
            reason=row['reason'] or ''
            if (row['status']=='error' and 'JavaScript runtime' in reason) or (row['status']=='rejected' and reason.startswith('Duration outside configured limits')):
                if row['status']=='rejected':
                    from discovery.screening import technical_reason
                    info=json.loads(row['info'] or '{}')
                    if technical_reason(info,cfg):continue
                store.update(row['id'],status='found',reason='',attempts=0)
                count+=1
        print(f'Applied: portrait only, 5–180 seconds, scan 60 per query. Requeued: {count}.')
        print('Other settings and permission decisions preserved. Close and reopen the discovery GUI.')
if __name__=='__main__':main()
