"""Copy actual verbatim assets; model Vite's intentional mock-worker removal."""
from pathlib import Path
import shutil
PUBLIC=Path(__file__).resolve().parents[1]/'webui/web/public'
def copy_public(dist, include_vendor=True):
    dist=Path(dist)
    def ignored(directory,names):
        return ({'mockServiceWorker.js'} | (set() if include_vendor else {'vendor-idna'})) if Path(directory)==PUBLIC else set()
    shutil.copytree(PUBLIC,dist,dirs_exist_ok=True,ignore=ignored)
    (dist/'index.html').write_text('compiled frontend fixture')
    return dist
