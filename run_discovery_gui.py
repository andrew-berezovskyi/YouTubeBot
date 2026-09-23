import json
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from discovery.settings import root, load, DEFAULTS
from discovery import store

class App:
    def __init__(self, window):
        self.window=window; self.process=None
        window.title('VibeRush — пошук і перевірка відео');window.geometry('1120x700')
        bar=ttk.Frame(window,padding=10);bar.pack(fill='x')
        ttk.Button(bar,text='Знайти й перевірити',command=self.start).pack(side='left',padx=3)
        ttk.Button(bar,text='Зупинити',command=self.stop).pack(side='left',padx=3)
        ttk.Button(bar,text='Налаштування',command=self.settings).pack(side='left',padx=3)
        self.watch=tk.BooleanVar();self.process_videos=tk.BooleanVar()
        ttk.Checkbutton(bar,text='Повторювати',variable=self.watch).pack(side='left',padx=8)
        ttk.Checkbutton(bar,text='Обробляти та завантажувати',variable=self.process_videos).pack(side='left',padx=8)
        self.visibility=tk.StringVar(value='private')
        ttk.Combobox(bar,textvariable=self.visibility,values=['private','public'],state='readonly',width=9).pack(side='left')
        ttk.Label(window,text='За замовчуванням лише пошук і перевірка. Завантаження на YouTube вмикається окремо.',padding=8).pack(anchor='w')
        columns=('id','source','status','title','reason')
        self.table=ttk.Treeview(window,columns=columns,show='headings',selectmode='browse')
        for name,label,width in [('id','№',45),('source','Джерело',85),('status','Статус',125),('title','Назва',330),('reason','Результат',450)]:
            self.table.heading(name,text=label);self.table.column(name,width=width)
        self.table.pack(fill='both',expand=True,padx=10)
        scrollbar=ttk.Scrollbar(window,orient='horizontal',command=self.table.xview)
        scrollbar.pack(fill='x',padx=10)
        self.table.configure(xscrollcommand=scrollbar.set)
        self.table.bind('<<TreeviewSelect>>',self.details)
        self.detail=tk.Text(window,height=9,wrap='word');self.detail.pack(fill='x',padx=10,pady=5)
        actions=ttk.Frame(window,padding=10);actions.pack(fill='x')
        ttk.Button(actions,text='Відкрити оригінал',command=self.open_url).pack(side='left',padx=3)
        ttk.Button(actions,text='Кадри й звіт',command=self.open_report).pack(side='left',padx=3)
        ttk.Button(actions,text='Підтвердити дозвіл на використання',command=self.approve).pack(side='left',padx=3)
        ttk.Button(actions,text='Повторити перевірку',command=self.retry).pack(side='left',padx=3)
        ttk.Button(actions,text='Відхилити',command=self.reject).pack(side='left',padx=3)
        self.state=tk.StringVar(value='Готово');ttk.Label(window,textvariable=self.state,padding=8).pack(anchor='w')
        self.phase=tk.StringVar(value='Очікує запуску')
        ttk.Label(window,textvariable=self.phase,padding=8,wraplength=1050).pack(anchor='w')
        window.protocol('WM_DELETE_WINDOW',self.close);self.refresh()

    def selected(self):
        ids=self.table.selection()
        return next((r for r in store.rows() if ids and str(r['id'])==ids[0]),None)

    def refresh(self):
        selected=self.table.selection()
        data=store.rows()[:500]
        current=set(self.table.get_children());wanted={str(r['id']) for r in data}
        for item in current-wanted:self.table.delete(item)
        for index,row in enumerate(data):
            cid=str(row['id']);values=tuple(row[k] for k in ('id','source','status','title','reason'))
            if cid in current:self.table.item(cid,values=values)
            else:self.table.insert('','end',iid=cid,values=values)
            self.table.move(cid,'',index)
        if selected and selected[0] in wanted:self.table.selection_set(selected)
        progress=store.current_progress()
        if progress and self.process and progress['pid']==self.process.pid:
            elapsed=max(0,int(time.time()-progress['started']))
            limit=f" / ліміт {progress['timeout']:g} с" if progress['timeout'] else ''
            self.phase.set(f"{progress['phase']} — {elapsed} с{limit}")
        if self.process and self.process.poll() is not None:
            self.state.set(f'Процес завершено, код {self.process.returncode}. Журнал: Logs/discovery-worker.log')
            self.process=None
        self.window.after(2000,self.refresh)

    def details(self,event=None):
        row=self.selected()
        self.detail.delete('1.0','end')
        if row:
            report=json.loads(row['report'])
            text=f"{row['url']}\nАвтор: {row['creator'] or 'невідомий'}\n{row['reason']}\n"
            for e in report.get('evidence',[]):
                if e.get('status')!='clear' or e.get('ocr_suspect'):
                    text+=f"{e['timestamp']} с: {e.get('reason','')} | OCR: {e.get('ocr_text','').strip()}\n"
            self.detail.insert('end',text)

    def start(self):
        if self.process:return
        if self.process_videos.get() and self.visibility.get()=='public':
            if not messagebox.askyesno('Публічні відео','Увімкнути публічну публікацію відібраних відео за встановленими лімітами?'):return
        try:load()
        except Exception as e:messagebox.showerror('Налаштування',str(e));return
        args=[sys.executable,'-u',str(root()/'run_discovery.py')]
        if self.watch.get():args+=['--watch']
        if self.process_videos.get():args+=['--process']
        if self.process_videos.get() and self.visibility.get()=='public':args+=['--publish']
        logs=root()/'Logs';logs.mkdir(exist_ok=True)
        with open(logs/'discovery-worker.log','a',encoding='utf-8') as f:
            self.process=subprocess.Popen(args,cwd=root(),stdout=f,stderr=subprocess.STDOUT)
        self.state.set('Процес запущено. Поточний етап показаний нижче.');self.phase.set('Запуск…')

    def stop(self):
        if self.process and self.process.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True)
            else:self.process.terminate()
            self.state.set('Зупинка. Перервану публікацію потрібно перевірити у YouTube Studio.')

    def idle(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Процес працює','Спочатку зупини пошук.');return False
        return True

    def settings(self):
        if not self.idle():return
        win=tk.Toplevel(self.window);win.title('Налаштування пошуку — JSON');win.geometry('820x650')
        ttk.Label(win,text='Джерела, теми, ліміти та дозволені автори. Пояснення полів — у START_HERE_UK.md.',padding=8).pack()
        editor=tk.Text(win,wrap='none');editor.pack(fill='both',expand=True)
        try: current=load()
        except Exception:current=DEFAULTS
        editor.insert('1.0',json.dumps(current,ensure_ascii=False,indent=2))
        def save():
            path=root()/'discovery_settings.json';old=path.read_bytes() if path.exists() else None
            try:
                value=json.loads(editor.get('1.0','end'))
                path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');load()
            except Exception as e:
                if old is None:path.unlink(missing_ok=True)
                else:path.write_bytes(old)
                messagebox.showerror('Помилка',str(e));return
            win.destroy()
        ttk.Button(win,text='Зберегти',command=save).pack(pady=8)

    def approve(self):
        if not self.idle():return
        row=self.selected()
        if row and messagebox.askyesno('Дозвіл','Підтверджуєш, що маєш дозвіл на повторне використання саме цього відео? Перевірка водяного знака все одно обов’язкова.'):
            cfg=load()
            if row['url'] not in cfg['approved_video_urls']:cfg['approved_video_urls'].append(row['url'])
            (root()/'discovery_settings.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            if row['status']=='needs_permission':store.update(row['id'],status='found',reason='Permission confirmed')

    def retry(self):
        if not self.idle():return
        row=self.selected()
        if row and row['status'] in ('error','review','watermark','rejected'):
            store.update(row['id'],status='found',attempts=0,reason='Requested fresh inspection',sha256=None,fingerprint=None)
        elif row:messagebox.showinfo('Повторна перевірка','Публікації з невизначеним результатом перевіряються через основну чергу та YouTube Studio. Автоматичний повтор заблоковано.')

    def reject(self):
        if not self.idle():return
        row=self.selected()
        if row and row['status'] not in ('published','uploading','upload_uncertain'):store.update(row['id'],status='rejected',reason='Rejected by user')

    def open_url(self):
        import webbrowser
        row=self.selected()
        if row:webbrowser.open(row['url'])

    def open_report(self):
        row=self.selected()
        if not row:return
        folder=root()/'Screening'/str(row['id'])
        if not folder.exists():messagebox.showinfo('Звіт','Відео ще не перевірене.');return
        if os.name=='nt':os.startfile(folder)
        else:subprocess.Popen(['xdg-open',str(folder)])

    def close(self):
        self.stop();self.window.destroy()

if __name__=='__main__':
    window=tk.Tk();App(window);window.mainloop()
