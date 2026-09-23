import base64
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
import config


def probe(path):
    result=subprocess.run([str(config.FFPROBE),'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=45,check=True)
    data=json.loads(result.stdout)
    video=next((s for s in data['streams'] if s['codec_type']=='video'),None)
    if not video: raise ValueError('No video stream')
    duration=float(data['format'].get('duration',video.get('duration',0)))
    if not math.isfinite(duration) or duration <= 0: raise ValueError('Invalid duration')
    width,height=int(video['width']),int(video['height'])
    sar=video.get('sample_aspect_ratio','1:1')
    try:
        a,b=map(float,sar.split(':')); ratio=a/b
        if math.isfinite(ratio) and ratio>0:width=round(width*ratio)
    except (ValueError,ZeroDivisionError):pass
    rotation=int(float(video.get('tags',{}).get('rotate',0)))
    for side in video.get('side_data_list',[]): rotation=int(side.get('rotation',rotation))
    if abs(rotation)%180 == 90: width,height=height,width
    return {'duration':duration,'width':width,'height':height}


def technical_reason(meta,cfg):
    d=meta.get('duration')
    if d is not None:
        if not isinstance(d,(int,float)) or not math.isfinite(d) or not cfg['min_duration'] <= d <= cfg['max_duration']:
            return f"Duration outside configured limits: {d}s; allowed {cfg['min_duration']}–{cfg['max_duration']}s"
    w,h=meta.get('width'),meta.get('height')
    if w and h:
        if cfg['vertical_only'] and w>=h:return f'Not a vertical video: {w}x{h}; height must exceed width'
        if h<cfg['min_height']:return f"Resolution below configured minimum: {w}x{h}; minimum height {cfg['min_height']}"
    if meta.get('is_live') or meta.get('live_status') in ('is_live','is_upcoming'):return 'Live or upcoming stream'
    return ''


def sha256(path):
    digest=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def sample_times(duration,cfg):
    count=min(cfg['max_frames'],max(3,math.ceil(duration/cfg['sample_interval_seconds'])+1))
    return [round(i*max(0,duration-0.15)/(count-1),3) for i in range(count)]


def extract_frame(video,timestamp,destination):
    # Low-FPS files may have no frame after the requested near-end timestamp.
    for seek in (timestamp, max(0, timestamp-.5)):
        subprocess.run([str(config.FFMPEG),'-hide_banner','-loglevel','error','-y','-ss',str(seek),'-i',str(video),'-frames:v','1','-vf','scale=960:960:force_original_aspect_ratio=decrease',str(destination)],capture_output=True,timeout=45,check=True)
        if destination.is_file(): return seek
    raise ValueError('Frame extraction failed')


def frame_hash(path):
    from PIL import Image
    with Image.open(path) as im:
        # Ignore outer 10% to tolerate overlays at the edges; conservative review only.
        w,h=im.size
        im=im.crop((w*.1,h*.1,w*.9,h*.9)).convert('L').resize((9,8))
        pixels=list(im.get_flattened_data() if hasattr(im,"get_flattened_data") else im.getdata())
    bits=sum((pixels[y*9+x]>pixels[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8))
    return f'{bits:016x}'


def near_duplicate(a,b):
    if abs(a['duration']-b['duration']) > max(1.5,a['duration']*.05): return False
    ah,bh=a['hashes'],b['hashes']
    if min(len(ah),len(bh)) < 3: return False
    # Compare normalized time positions, even if sample counts differ slightly.
    pairs=[(ah[round(i*(len(ah)-1)/7)],bh[round(i*(len(bh)-1)/7)]) for i in range(8)]
    return sum((int(x,16)^int(y,16)).bit_count() <= 7 for x,y in pairs) >= 6


def vision(frame,cfg):
    from .vision_checks import analyze
    return analyze(frame,cfg)


def classify(evidence,cfg):
    if not evidence: return 'uncertain','No frames could be checked'
    if any(e.get('status')=='detected' and e.get('confidence',0)>=.8 and e.get('confirmed') is True and e.get('mark_kind')=='overlay' for e in evidence): return 'detected','Creator/platform mark detected'
    if any(e.get('inspection_error') for e in evidence): return 'uncertain','Technical inspection failure; see frame diagnostics and retry'
    if any(e.get('status')!='clear' or e.get('confidence',0)<.8 or e.get('ocr_suspect') for e in evidence): return 'uncertain','Ambiguous mark, OCR evidence, or incomplete inspection'
    if sum(e['topic_score'] for e in evidence)/len(evidence) < cfg['min_topic_score']: return 'off_topic','Insufficient topic relevance'
    return 'clear','No watermark detected in sampled frames'


def screen(video,folder,cfg):
    from .store import progress
    progress(f"Перевірка медіафайла: {video.name}")
    import pytesseract
    from PIL import Image
    if cfg['tesseract_cmd']: pytesseract.pytesseract.tesseract_cmd=cfg['tesseract_cmd']
    # Missing OCR is a hard failure; do not silently pass videos without this check.
    pytesseract.get_tesseract_version()
    meta=probe(video)
    reason=technical_reason(meta,cfg)
    if reason: return {'status':'rejected','reason':reason,'technical':meta,'evidence':[]}
    subprocess.run([str(config.FFMPEG),'-v','error','-xerror','-i',str(video),'-map','0:v:0','-f','null','-'],capture_output=True,timeout=180,check=True)
    folder.mkdir(parents=True,exist_ok=True)
    evidence=[]; hashes=[]
    times=sample_times(meta['duration'],cfg)
    initial_count=len(times)
    for index,t in enumerate(times):
        progress(f'Відео №{folder.name}: OCR та AI, кадр {index+1}/{len(times)}, час {t:g} с',cfg['vision_timeout_seconds']*6+75)
        frame=folder/f'frame_{index:03d}.jpg'
        t=extract_frame(video,t,frame)
        if index < initial_count: hashes.append(frame_hash(frame))
        text=''
        try:
            with Image.open(frame) as im:
                text=pytesseract.image_to_string(im,config='--psm 11',timeout=30)
            result=vision(frame,cfg)
            result['ocr_text']=text[:2000]
            result['ocr_suspect']=bool(re.search(r'@[\w.]{3,}|(?:https?://|www\.)\S+|\b(?:tiktok|capcut|viberush)\b',text,re.I))
        except Exception as exc:
            result={'status':'uncertain','confidence':0,'topic_score':0,'reason':f'Inspection failed: {type(exc).__name__}: {str(exc)[:300]}','inspection_error':True,'ocr_text':text[:2000]}
        result.update(timestamp=t,frame=str(frame.resolve()))
        evidence.append(result)
        # Two nearby frames help inspect intermittent/moving marks, with a strict budget.
        if index < initial_count and (result['status']!='clear' or result.get('ocr_suspect')):
            for extra in (max(0,t-.5),min(meta['duration']-.15,t+.5)):
                if len(times)<cfg['max_frames']+8 and all(abs(extra-old)>.1 for old in times): times.append(extra)
    status,reason=classify(evidence,cfg)
    return {'detector_version':'1.1.6','status':status,'reason':reason,'technical':meta,'evidence':evidence,'fingerprint':{'duration':meta['duration'],'hashes':hashes},'sampling_note':'Sampled frames only; no guarantee of absence throughout the video.'}
