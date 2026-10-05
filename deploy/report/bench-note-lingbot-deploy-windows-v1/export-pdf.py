import json, sys, hashlib
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from pypdf import PdfReader
import pypdfium2 as pdfium

TITLE = 'LingBot-World 1.3B 部署：6GB 笔记本 Windows 原生跑通图生视频'


def main():
    base = Path(sys.argv[1]).resolve()
    raster = Path(sys.argv[2]).resolve()
    raster.mkdir(parents=True, exist_ok=True)
    plan = json.loads((base / 'page-plan.json').read_text(encoding='utf-8'))
    pages = plan['pages']
    name = 'lingbot-deploy-windows.zh.pdf'
    out = base / name
    c = canvas.Canvas(str(out), pagesize=(540, 720), pageCompression=1, invariant=1)
    c.setTitle(TITLE)
    c.setAuthor('本机实验研究报告')
    for i, p in enumerate(pages, 1):
        source = base / f'page-{i:02}.png'
        im = Image.open(source)
        if im.size != (1080, 1440):
            raise ValueError(f'page {i}: invalid dimensions')
        c.bookmarkPage(f'page-{i}')
        c.addOutlineEntry(p['title'], f'page-{i}', level=0, closed=False)
        c.drawImage(str(source), 0, 0, width=540, height=720)
        c.showPage()
    c.save()
    reader = PdfReader(str(out))
    if len(reader.pages) != len(pages):
        raise ValueError('PDF page count mismatch')
    rows = []
    for i, p in enumerate(reader.pages, 1):
        images = list(p.images)
        if len(images) != 1:
            raise ValueError(f'page {i}: image count mismatch')
        original = Image.open(base / f'page-{i:02}.png').convert('RGB')
        embedded = images[0].image.convert('RGB')
        same = original.size == embedded.size and original.tobytes() == embedded.tobytes()
        if not same:
            raise ValueError(f'page {i}: embedded pixel mismatch')
        rows.append({'page': i, 'source_png': f'page-{i:02}.png',
                     'source_sha256': hashlib.sha256((base / f'page-{i:02}.png').read_bytes()).hexdigest(),
                     'embedded_pixels_identical': same, 'pixel_dimensions': list(original.size)})
    pdf = pdfium.PdfDocument(str(out))
    for i in range(len(pdf)):
        page = pdf[i]
        bitmap = page.render(scale=2)
        image = bitmap.to_pil()
        image.save(raster / f'pdf-page-{i+1:02}.png')
        rows[i]['raster_dimensions'] = list(image.size)
        bitmap.close()
        page.close()
    pdf.close()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    qa = {'schema_version': 1, 'page_plan_sha256': sha(base / 'page-plan.json'),
          'pdf': {'path': name, 'sha256': sha(out), 'bytes': out.stat().st_size},
          'page_count': len(pages), 'all_embedded_pixels_identical': True,
          'raster_directory': str(raster), 'rows': rows,
          'scope': 'Every PDF page embeds the exact RGB pixels of the reviewed 1080x1440 PNG. PDFium rerendered all pages; human visual review is recorded separately.',
          'pass': True}
    (base / 'qa').mkdir(parents=True, exist_ok=True)
    (base / 'qa' / 'pdf-export.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'pages': len(pages), 'sha256': qa['pdf']['sha256'], 'bytes': qa['pdf']['bytes'],
                      'embedded_pixels_identical': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
