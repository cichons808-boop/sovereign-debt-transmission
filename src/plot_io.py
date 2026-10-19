"""Write complete PDF figures atomically."""
from io import BytesIO
from pathlib import Path

def save_pdf(fig,path,**kwargs):
    path=Path(path)
    stream=BytesIO()
    fig.savefig(stream,format='pdf',**kwargs)
    body=stream.getvalue()
    if not body.startswith(b'%PDF') or not body.rstrip().endswith(b'%%EOF'):
        raise ValueError('Incomplete PDF figure')
    temporary=path.with_suffix('.pdf.tmp')
    temporary.write_bytes(body)
    temporary.replace(path)
