"""Local static frontend server; sends no requests to production."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import re
parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,default=8080)
parser.add_argument('--api-origin',default='http://127.0.0.1:8000')
args=parser.parse_args()
origin=urlsplit(args.api_origin)
if origin.scheme!='http' or origin.hostname not in ('127.0.0.1','localhost') or origin.username or origin.password:
    parser.error('Use an isolated local API origin')
root=Path(__file__).resolve().parent.parent
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path in ('/','/index.html'):
            html=(root/'index.html').read_text()
            api=re.search(r'<meta name="myteam-api" content="([^"]+)"',html).group(1)
            content=html.replace(api,args.api_origin.rstrip('/')).encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
        else:super().do_GET()
ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(root))).serve_forever()
