from pathlib import Path
from PIL import Image
import base64
import io

SUPPORTED_INPUT = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif', '.gif', '.svg'}
SUPPORTED_OUTPUT = ['PNG', 'JPEG', 'WebP', 'BMP', 'TIFF', 'SVG']

_FORMAT_EXT = {
    'PNG': '.png',
    'JPEG': '.jpg',
    'WebP': '.webp',
    'BMP': '.bmp',
    'TIFF': '.tiff',
    'SVG': '.svg',
}


def _svg_to_pil(svg_path: str) -> Image.Image:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM

    drawing = svg2rlg(svg_path)
    if drawing is None:
        raise ValueError(f"SVG 파싱 실패: {svg_path}")

    png_bytes = renderPM.drawToString(drawing, fmt='PNG', dpi=150)
    return Image.open(io.BytesIO(png_bytes)).convert('RGBA')


def _open_image(path: str) -> Image.Image:
    p = Path(path)
    if p.suffix.lower() == '.svg':
        return _svg_to_pil(path)
    return Image.open(path)


def _resize(img: Image.Image, width, height, keep_aspect: bool) -> Image.Image:
    if not width and not height:
        return img

    orig_w, orig_h = img.size

    if keep_aspect:
        if width and height:
            ratio = min(width / orig_w, height / orig_h)
            new_size = (max(1, int(orig_w * ratio)), max(1, int(orig_h * ratio)))
        elif width:
            new_size = (width, max(1, int(orig_h * (width / orig_w))))
        else:
            new_size = (max(1, int(orig_w * (height / orig_h))), height)
    else:
        new_size = (width or orig_w, height or orig_h)

    return img.resize(new_size, Image.LANCZOS)


def _prepare_mode(img: Image.Image, output_format: str) -> Image.Image:
    """Convert image mode to be compatible with the target format."""
    if output_format == 'JPEG':
        if img.mode in ('RGBA', 'LA'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            return bg
        if img.mode == 'P':
            img = img.convert('RGBA')
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            return bg
        return img.convert('RGB')

    if output_format == 'BMP':
        return img.convert('RGB')

    if img.mode == 'P':
        return img.convert('RGBA')

    return img


_rembg_session = None

def get_rembg_session():
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        _rembg_session = new_session("birefnet-massive")
    return _rembg_session


def remove_background(img: Image.Image) -> Image.Image:
    from rembg import remove
    session = get_rembg_session()
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    result = remove(
        buf.getvalue(),
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=10,
    )
    return Image.open(io.BytesIO(result)).convert('RGBA')


def convert_image(input_path: str, output_dir: str, output_format: str,
                  quality: int = 85, width=None, height=None,
                  keep_aspect: bool = True, remove_bg: bool = False) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    img = _open_image(input_path)
    if remove_bg:
        img = remove_background(img)
    img = _resize(img, width, height, keep_aspect)
    img = _prepare_mode(img, output_format)

    out_ext = _FORMAT_EXT[output_format]
    out_path = output_dir / (Path(input_path).stem + out_ext)

    if output_format == 'SVG':
        _save_as_svg(img, out_path)
        return out_path

    save_kwargs = {}
    if output_format == 'JPEG':
        save_kwargs = {'quality': quality, 'optimize': True}
    elif output_format == 'WebP':
        save_kwargs = {'quality': quality}
    elif output_format == 'PNG':
        save_kwargs = {'optimize': True}

    img.save(out_path, format=output_format, **save_kwargs)
    return out_path


def _save_as_svg(img: Image.Image, out_path: Path) -> None:
    """Embed the image as base64 PNG inside an SVG wrapper."""
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA')
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    w, h = img.size
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'  <image width="{w}" height="{h}" '
        f'xlink:href="data:image/png;base64,{b64}"/>\n'
        f'</svg>\n'
    )
    out_path.write_text(svg, encoding='utf-8')
