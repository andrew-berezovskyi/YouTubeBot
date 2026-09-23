"""Requeue only the known debugging cases, preserving their earlier evidence."""
import shutil
from datetime import datetime
from discovery import store
from discovery.settings import root
from discovery.service import worker_lock

if __name__=='__main__':
    with worker_lock():
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        count=0
        for row in store.rows():
            if row['id'] not in (48,49,50) or row['status'] not in ('watermark','review'):continue
            source=root()/'Screening'/str(row['id'])
            if source.exists():shutil.copytree(source,root()/'Screening'/'previous_checks'/stamp/str(row['id']))
            store.update(row['id'],status='found',reason='Recheck with detector 1.1.6',attempts=0)
            count+=1
        print(f'Requeued {count} known cases. Previous reports backed up. Start START_DISCOVERY.bat.')
