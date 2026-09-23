from discovery.service import worker_lock
from discovery import store

if __name__=='__main__':
    with worker_lock():
        count=0
        for row in store.rows():
            if row['status']=='rejected' and (row['reason'] or '').startswith('Resolution below configured minimum'):
                store.update(row['id'],status='found',reason='',attempts=0)
                count+=1
        print(f'Requeued {count} resolution rejections. Start START_DISCOVERY.bat.')
