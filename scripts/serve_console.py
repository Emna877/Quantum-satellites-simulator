"""Console UI/API: python -m scripts.serve_console --port 8000 (add --host 0.0.0.0 inside a container).

Each run is a separate worker process because JPype cannot restart its JVM.
Only console assets and explicitly addressed run records are served, never .env/.git.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import urlsplit, unquote
import uuid

from experiments.console import defaults, catalog, validate_request

ROOT=Path(__file__).resolve().parent.parent
RUNS=ROOT/'data'/'console_runs'
ID=re.compile(r'^[a-f0-9]{32}$')


class Runs:
    def __init__(self):
        self.jobs={}
        self.lock=threading.Lock()

    def start(self,request):
        values=validate_request(request)
        with self.lock:
            if any(job['process'].poll() is None for job in self.jobs.values()):
                raise RuntimeError('A simulation is already running. Wait for it to finish.')
            identity=uuid.uuid4().hex
            folder=RUNS/identity
            folder.mkdir(parents=True)
            (folder/'request.json').write_text(json.dumps(values),encoding='utf-8')
            with (folder/'worker.log').open('w',encoding='utf-8') as output:
                process=subprocess.Popen([sys.executable,'-m','experiments.console',
                    '--request',str(folder/'request.json'),'--out',str(folder/'run.json'),'--id',identity],
                    cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                    env=dict(os.environ,PYTHONIOENCODING='utf-8'),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.jobs[identity]=dict(process=process,folder=folder)
            return identity

    def status(self,identity):
        if not ID.fullmatch(identity):
            raise ValueError('Invalid run ID')
        folder=RUNS/identity
        job=self.jobs.get(identity)
        if job and job['process'].poll() is None:
            return dict(id=identity,status='running',message='Computing shared Orekit geometry and both model pipelines…')
        if (folder/'run.json').is_file():
            return dict(id=identity,status='completed')
        if job:
            return dict(id=identity,status='failed',message=(folder/'worker.log').read_text(encoding='utf-8')[-3000:])
        raise FileNotFoundError('Run not found')

    def history(self):
        records=[]
        if RUNS.exists():
            for folder in sorted(RUNS.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True):
                if ID.fullmatch(folder.name) and (folder/'run.json').is_file():
                    request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
                    records.append(dict(id=folder.name,**request))
        return records[:50]


RUN_MANAGER=Runs()


class Handler(BaseHTTPRequestHandler):
    def send(self,status,content,content_type='application/json; charset=utf-8'):
        if isinstance(content,(dict,list)):
            content=json.dumps(content,allow_nan=False).encode('utf-8')
        elif isinstance(content,str):
            content=content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path=unquote(urlsplit(self.path).path)
        try:
            if path=='/api/config':
                return self.send(200,dict(defaults=defaults(),scenarios=catalog(),format='console_run.v1'))
            if path=='/api/runs':
                return self.send(200,RUN_MANAGER.history())
            if path.startswith('/api/jobs/'):
                return self.send(200,RUN_MANAGER.status(path.split('/')[-1]))
            if path.startswith('/api/runs/'):
                identity=path.split('/')[-1]
                if not ID.fullmatch(identity):
                    raise ValueError('Invalid run ID')
                return self.send(200,(RUNS/identity/'run.json').read_bytes())
            relative='index.html' if path in ('/','/console','/console/') else path.removeprefix('/console/').lstrip('/')
            file=(ROOT/'console'/relative).resolve()
            if not file.is_relative_to(ROOT/'console') or file.suffix not in ('.html','.css','.js','.mjs','.svg','.png') or not file.is_file():
                raise FileNotFoundError('Asset not found')
            return self.send(200,file.read_bytes(),'text/javascript' if file.suffix=='.mjs' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        except (FileNotFoundError,ValueError) as exc:
            self.send(404,dict(error=str(exc)))

    def do_POST(self):
        if self.path!='/api/run':
            return self.send(404,dict(error='Unknown endpoint'))
        origin=self.headers.get('Origin')
        if urlsplit('http://'+self.headers.get('Host','')).hostname not in ('127.0.0.1','localhost'):
            return self.send(403,dict(error='Only localhost requests are allowed'))
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
            return self.send(403,dict(error='Cross-origin requests are not allowed'))
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.send(415,dict(error='Use application/json'))
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 65536:
                raise ValueError('Request body is too large or empty')
            identity=RUN_MANAGER.start(json.loads(self.rfile.read(size)))
            self.send(202,dict(id=identity,status='running'))
        except (ValueError,TypeError,KeyError) as exc:
            self.send(400,dict(error=str(exc)))
        except RuntimeError as exc:
            self.send(409,dict(error=str(exc)))


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'Threat Analysis Console: http://{args.host}:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for job in RUN_MANAGER.jobs.values():
            if job['process'].poll() is None:
                job['process'].terminate()


if __name__=='__main__':
    main()
