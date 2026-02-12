import math
import sys
import os
import json
import numpy as np
from typing import Tuple, List, Optional
from PIL import Image, ImageFilter, ImageDraw, ImageFont
# ---------- TriGrid 渲染模块 ----------
try:
    import trigridRenderer
    TRIGRID_GL_AVAILABLE = trigridRenderer.is_available()
except ImportError:
    TRIGRID_GL_AVAILABLE = False
    trigridRenderer = None
    print("提示: 未安装 trigridRenderer 模块，将使用 NumPy 版本回退")

# Pillow 兼容性：部分旧版 Pillow 没有 Image.Resampling
try:
    RESAMPLING_LANCZOS = Image.Resampling.LANCZOS
except Exception:
    RESAMPLING_LANCZOS = Image.LANCZOS

BLUR_R = 0.035
WIDTH = 1920
HEIGHT = 1080
CHILDREN_SIZE = 0.6
DIM = 0.6
SHADER_ALPHA = 0.5
SHADER_POWER = 0.035
ILLUSTRATION_RAISE_PX = 40

# 字体相关常量
FONT_PATH = "font.ttf"
FONT_SIZE_LARGE = 66
FONT_SIZE_MEDIUM = 30
FONT_SIZE_SMALL = 50
TEXT_COLOR = (255, 255, 255, 255) 
TEXT_MARGIN = 50
LINE_SPACING = 19

# 难度颜色定义
DIFFICULTY_COLORS = {
    "EZ": (50, 205, 50, 200),
    "HD": (23, 165, 255, 200),
    "IN": (255, 56, 92, 200),
    "AT": (158, 158, 158, 200),
    "SP": (255, 255, 255, 200),
}
PADDING_X = 15
PADDING_Y = 15
RECT_RADIUS = 0
DIFFICULTY_FONT_SIZE = 50  # 整数部分字号
DECIMAL_FONT_SIZE = 25  # 小数部分字号（较小）
DIFFICULTY_SPACING = 30  # 难度之间的水平间距
DECIMAL_ALIGN_OFFSET = 8  # 小数部分垂直偏移，使其底部对齐整数部分
INT_VERTICAL_OFFSET = -8  # 整数部分垂直偏移，负值向上，正值向下
DECIMAL_VERTICAL_OFFSET = 5  # 小数部分垂直偏移，负值向上，正值向下

WIDTH_MULTIPLIER = 1.3
EXTRA_PADDING_X = 10

FIXED_BLOCK_WIDTH = 110  # 固定块宽度
FIXED_BLOCK_HEIGHT = 80  # 固定块高度
PARALLELOGRAM_SKEW_FACTOR = -0.8  # 平行四边形倾斜因子
BLOCK_MIN_WIDTH = 100  # 最小块宽度（作为后备）
EXTRA_WIDTH_FACTOR = 1.2  # 额外宽度系数
PARALLELOGRAM_ANGLE_TOP_LEFT = 105  # 顶部左角角度，另一个为75

# 长条块常量（用于歌曲名/作曲者下方的大条背景）
LONG_BLOCK_WIDTH = 950
LONG_BLOCK_HEIGHT = 140
LONG_BLOCK_PADDING_X = 20
LONG_BLOCK_PADDING_Y = 12
LONG_BLOCK_TEXT_SPACING = 19
LONG_BLOCK_ALPHA = 150

FONT_CANDIDATES = [
    FONT_PATH,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), FONT_PATH),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf"),
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Heiti.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/msyh.ttc",
]


def find_font(size: int, candidates: Optional[List[str]] = None) -> ImageFont.ImageFont:
    if candidates is None:
        candidates = FONT_CANDIDATES

    for p in candidates:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        raise RuntimeError("无法加载任何字体")


def parse_difficulties_arg(arg: str) -> List[float]:
    vals: List[float] = []
    if not arg:
        return vals
    # 尝试解析格式：EZ=1,HD=2.5 或 1,2.5,3 或 单个数值
    try:
        # 查找所有数值
        import re

        nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", arg)
        for n in nums:
            try:
                vals.append(float(n))
            except Exception:
                continue
        return vals
    except Exception:
        return vals


def parse_difficulties_kv(arg: str) -> dict:
    res = {}
    if not arg:
        return res
    try:
        parts = [p.strip() for p in arg.split(",") if p.strip()]
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                vstr = v.strip()
                try:
                    res[k] = float(vstr)
                except Exception:
                    res[k] = vstr
            else:
                continue
        return res
    except Exception:
        return res


def compute_dpower(width: int, height: int, deg: int = 75) -> float:
    l1 = (0, 0, width, 0)
    l2 = (0, height, *rotate_point(0, height, deg, (width**2 + height**2) ** 0.5))
    x, _ = compute_intersection(*l1, *l2)
    try:
        return float(x) / float(width)
    except Exception:
        return 0.0


def draw_parallelogram(draw, x, y, width, height, dpower, color):
    skew_offset = height * dpower * 0.8 
    points = [
        (x, y), 
        (x + width - skew_offset, y), 
        (x + width, y + height), 
        (x + skew_offset, y + height), 
    ]
    draw.polygon(points, fill=color)
    return points


def rotate_point(x: float, y: float, θ: float, r: float) -> Tuple[float, float]:
    xo = r * math.cos(math.radians(θ))
    yo = r * math.sin(math.radians(θ))
    return x + xo, y + yo


def compute_intersection(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
) -> Tuple[float, float]:
    a1 = y1 - y0
    b1 = x0 - x1
    c1 = x1 * y0 - x0 * y1
    a2 = y3 - y2
    b2 = x2 - x3
    c2 = x3 * y2 - x2 * y3
    denom = a1 * b2 - a2 * b1
    if denom == 0:
        return 0.0, 0.0
    return (b2 * c1 - b1 * c2) / denom, (a1 * c2 - a2 * c1) / denom


def draw_parallelogram_block(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    width: float,
    height: float,
    dpower: float,
    skew_factor: float,
    color: Tuple[int, int, int, int],
    skew_offset_override: Optional[float] = None,
    angle_deg: Optional[float] = None,
) -> List[Tuple[float, float]]:

    if angle_deg is not None:
        rad = math.radians(angle_deg)
        try:
            skew_offset = height / math.tan(rad)
        except Exception:
            skew_offset = height * dpower * skew_factor
    elif skew_offset_override is not None:
        skew_offset = skew_offset_override
    else:
        skew_offset = height * dpower * skew_factor
    points = [(x, y), (x + width, y), (x + width + skew_offset, y + height), (x + skew_offset, y + height)]
    draw.polygon(points, fill=color)
    return points


def create_diagonal_rectangle(draw, x0, y0, x1, y1, dpower, angle_deg: int = PARALLELOGRAM_ANGLE_TOP_LEFT):
    width = x1 - x0
    height = y1 - y0

    try:
        rad = math.radians(angle_deg)
        skew = int(abs(height / math.tan(rad)))
    except Exception:
        skew = int(abs(width * dpower))

    points = [
        (x0 + skew, y0),
        (x1, y0),
        (x1 - skew, y1),
        (x0, y1),
    ]

    return points


def apply_shadow_effect(base_image, x0, y0, x1, y1, dpower, shadow_alpha, shadow_power):
    shadow = Image.new("RGBA", base_image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)

    points = create_diagonal_rectangle(shadow_draw, x0, y0, x1, y1, dpower)
    shadow_draw.polygon(points, fill=(0, 0, 0, int(255 * shadow_alpha)))

    shadow_blur_radius = (base_image.width + base_image.height) * shadow_power
    shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur_radius))

    return shadow

def apply_trigrid_effect(base_image, params=None, t=0.0, use_gl=True):
    """
    对 PIL Image 应用 TriGrid 着色器，返回合成后的图像。
    优先使用 OpenGL 渲染器（如果可用），否则回退到 NumPy 实现。
    """
    # ---------- OpenGL 路径 ----------
    if use_gl and TRIGRID_GL_AVAILABLE and trigridRenderer is not None:
        try:
            # 临时保存当前图像为临时文件（或直接使用内存？）
            # 更好的方式：直接使用内存中的 base_image
            # 但 OpenGL 渲染器需要从文件加载纹理，所以这里需要保存到临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.png', delete=True) as tmp:
                base_image.save(tmp.name, format='PNG')
                img = trigridRenderer.render_trigrid_gl(tmp.name, params, t, base_image.size)
            return img
        except Exception as e:
            print(f"  OpenGL 渲染失败，回退到 NumPy: {e}")
            # 继续执行 NumPy 路径

    # ---------- NumPy 回退路径（原纯软件实现）----------
    try:
        import numpy as np
    except ImportError:
        print("  警告: NumPy 未安装，无法渲染 TriGrid 网格")
        return None

    if params is None:
        params = TRIGRID_DEFAULT_PARAMS

    base_arr = np.asarray(base_image, dtype=np.float32) / 255.0
    shader_arr = render_trigrid_shader(base_arr, params, t)
    shader_img = Image.fromarray((shader_arr * 255).astype(np.uint8)).convert('RGBA')
    return shader_img


def _draw_wings(image: Image.Image):
    w, h = image.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    alpha = 100
    angle_B = math.radians(75)
    tanB = math.tan(angle_B)
    b = int(h / tanB)
    max_b = max(4, int(w * 0.4))
    if b > max_b:
        b = max_b

    left_tri = [(0, 0), (b, 0), (0, h)]
    right_tri = [(w, h), (w - b, h), (w, 0)]
    od.polygon(left_tri, fill=(0, 0, 0, alpha))
    od.polygon(right_tri, fill=(0, 0, 0, alpha))
    image.alpha_composite(overlay)


def load_song_info(data_dir="data"):
    info_path = os.path.join(data_dir, "info.json")
    difficulty_path = os.path.join(data_dir, "difficulty.json")

    song_info = {}
    difficulty_info = {}

    try:
        if os.path.exists(info_path):
            with open(info_path, "r", encoding="utf-8") as f:
                songs = json.load(f)
                for song in songs:
                    song_id = song[0]
                    song_info[song_id] = {
                        "name": song[1],
                        "composer": song[2],
                        "illustrator": song[3],
                        "charter": song[4:],
                    }
            print(f"加载了 {len(song_info)} 首歌曲信息")
    except Exception as e:
        print(f"加载歌曲信息失败: {e}")

    try:
        if os.path.exists(difficulty_path):
            with open(difficulty_path, "r", encoding="utf-8") as f:
                difficulties = json.load(f)
                for diff in difficulties:
                    song_id = diff[0]
                    difficulty_info[song_id] = diff[1:]
            print(f"加载了 {len(difficulty_info)} 首歌曲难度信息")
    except Exception as e:
        print(f"加载难度信息失败: {e}")

    return song_info, difficulty_info


def get_song_id_from_filename(filename):
    basename = os.path.splitext(filename)[0]

    if basename.endswith(".0"):
        basename = basename[:-2]

    difficulty_suffixes = ["_EZ", "_HD", "_IN", "_AT", "_Legacy"]
    for suffix in difficulty_suffixes:
        if basename.endswith(suffix):
            basename = basename[: -len(suffix)]
            break

    return basename


def add_text_with_outline(draw, text, position, font, fill_color):
    try:
        x, y = position
        draw.text((x, y), text, font=font, fill=fill_color)
        return True

    except Exception as e:
        print(f"  绘制文字失败: {e}")
        return False


def add_song_info_to_image(
    image, song_id, song_info, difficulty_info, dpower=None, child_top_y: Optional[int] = None
):
    try:
        draw = ImageDraw.Draw(image)

        # 获取歌曲信息
        info = song_info.get(song_id, {})
        difficulties = difficulty_info.get(song_id, [])

        # 构建显示文本
        song_name = info.get("name", "")
        composer = info.get("composer", "")

        if not song_name:
            print("  未找到歌曲名称，跳过文字添加")
            return True

        try:
            font_large = find_font(FONT_SIZE_LARGE)
            font_medium = find_font(FONT_SIZE_MEDIUM)
            font_small = find_font(FONT_SIZE_SMALL)
            try:
                if hasattr(font_large, "path") and font_large.path:
                    print(f"  使用字体: {os.path.basename(font_large.path)}")
            except Exception:
                pass
        except Exception as e:
            print(f"  警告: 无法加载字体: {e}")
            return False

        song_name_y = TEXT_MARGIN
        bbox = draw.textbbox((0, 0), song_name, font=font_large)
        song_name_height = bbox[3] - bbox[1] if bbox else FONT_SIZE_LARGE

        # 添加作曲家（歌曲名称下方）
        composer_height = 0
        if composer:
            composer_text = composer
            bbox_comp = draw.textbbox((0, 0), composer_text, font=font_medium)
            composer_height = bbox_comp[3] - bbox_comp[1] if bbox_comp else FONT_SIZE_MEDIUM
        block_w = LONG_BLOCK_WIDTH
        content_height = song_name_height + (composer_height if composer_height else 0) + LONG_BLOCK_PADDING_Y * 3
        block_h = max(LONG_BLOCK_HEIGHT, int(content_height))
        block_x = (image.width - block_w) // 2
        child_height = int(HEIGHT * CHILDREN_SIZE)
        if child_top_y is None:
            child_y0 = (HEIGHT - child_height) // 2
        else:
            child_y0 = int(child_top_y)
        child_y1 = child_y0 + child_height
        block_y = child_y1 + LONG_BLOCK_PADDING_Y
        max_block_y = image.height - block_h - TEXT_MARGIN
        if block_y > max_block_y:
            block_y = max_block_y

        if dpower is None:
            dpower = compute_dpower(WIDTH, HEIGHT)

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        draw_parallelogram_block(
            overlay_draw,
            block_x,
            block_y,
            block_w,
            block_h,
            dpower,
            PARALLELOGRAM_SKEW_FACTOR,
            (0, 0, 0, LONG_BLOCK_ALPHA),
            angle_deg=PARALLELOGRAM_ANGLE_TOP_LEFT,
        )
        image.alpha_composite(overlay)

        def fit_font_for_width(text: str, max_width: int, max_size: int) -> ImageFont.ImageFont:
            for size in range(max_size, 8, -1):
                try:
                    f = find_font(size)
                except Exception:
                    continue
                bbox_t = draw.textbbox((0, 0), text, font=f)
                text_w = bbox_t[2] - bbox_t[0] if bbox_t else 0
                if text_w + 2 * LONG_BLOCK_PADDING_X <= max_width:
                    return f
            return find_font(8)

        name_font = fit_font_for_width(song_name, block_w - 2 * LONG_BLOCK_PADDING_X, FONT_SIZE_LARGE)
        name_bbox = draw.textbbox((0, 0), song_name, font=name_font)
        name_h = name_bbox[3] - name_bbox[1] if name_bbox else 0
        name_x = block_x + LONG_BLOCK_PADDING_X
        name_y = block_y + LONG_BLOCK_PADDING_Y
        add_text_with_outline(draw, song_name, (name_x, name_y), name_font, TEXT_COLOR)

        if composer:
            comp_font = fit_font_for_width(composer_text, block_w - 2 * LONG_BLOCK_PADDING_X, FONT_SIZE_MEDIUM)
            comp_x = block_x + LONG_BLOCK_PADDING_X
            comp_y = name_y + name_h + LONG_BLOCK_TEXT_SPACING
            add_text_with_outline(draw, composer_text, (comp_x, comp_y), comp_font, TEXT_COLOR)

        # 添加难度（底部右侧，水平排列）
        if difficulties:
            # 难度标签和对应的数值
            difficulty_labels = ["EZ", "HD", "IN", "AT", "SP"]

            valid_difficulties = []
            if isinstance(difficulties, dict):
                for label in difficulty_labels:
                    val = difficulties.get(label)
                    if val is None:
                        continue
                    # 如果值为字符串且为 '?' 则显示 '?'；否则尝试转换为数值
                    if isinstance(val, str):
                        if val.strip() == "?":
                            valid_difficulties.append((label, "?"))
                            continue
                        try:
                            fval = float(val)
                        except Exception:
                            continue
                        if fval > 0:
                            valid_difficulties.append((label, f"{fval:.1f}"))
                    else:
                        try:
                            fval = float(val)
                        except Exception:
                            continue
                        if fval > 0:
                            valid_difficulties.append((label, f"{fval:.1f}"))
            else:
                for i, diff in enumerate(difficulties):
                    if i < len(difficulty_labels) and diff > 0:
                        diff_str = f"{diff:.1f}"
                        valid_difficulties.append((difficulty_labels[i], diff_str))

            if valid_difficulties:
                try:
                    font_decimal = find_font(DECIMAL_FONT_SIZE)
                except Exception:
                    font_decimal = font_small

                if dpower is None:
                    dpower = compute_dpower(WIDTH, HEIGHT)

                block_width = FIXED_BLOCK_WIDTH
                block_height = FIXED_BLOCK_HEIGHT
                child_width = int(WIDTH * CHILDREN_SIZE)
                child_height = int(HEIGHT * CHILDREN_SIZE)
                skew_per_block = abs(block_height / math.tan(math.radians(PARALLELOGRAM_ANGLE_TOP_LEFT)))
                skew_extra = int(skew_per_block)
                total_width = (
                    block_width * len(valid_difficulties)
                    + DIFFICULTY_SPACING * (len(valid_difficulties) - 1)
                    + int(skew_extra * (len(valid_difficulties) - 1))
                )

                start_x = (image.width - total_width) // 2
                start_y = song_name_y

                # 绘制每个难度块
                for i, (label, value) in enumerate(valid_difficulties):
                    # 处理特殊值 '?'，将其当作整数部分显示
                    if isinstance(value, str) and value == "?":
                        int_part, decimal_part = value, ""
                    else:
                        if "." in value:
                            int_part, decimal_part = value.split(".")
                        else:
                            int_part, decimal_part = value, ""

                    bbox_int = draw.textbbox((0, 0), int_part, font=font_small)
                    int_width = (
                        bbox_int[2] - bbox_int[0]
                        if bbox_int
                        else len(int_part) * DIFFICULTY_FONT_SIZE * 0.6
                    )
                    int_height = (
                        bbox_int[3] - bbox_int[1] if bbox_int else DIFFICULTY_FONT_SIZE
                    )

                    decimal_text = f".{decimal_part}" if decimal_part else ""
                    if decimal_text:
                        bbox_decimal = draw.textbbox(
                            (0, 0), decimal_text, font=font_decimal
                        )
                        decimal_width = (
                            bbox_decimal[2] - bbox_decimal[0]
                            if bbox_decimal
                            else len(decimal_text) * DECIMAL_FONT_SIZE * 0.6
                        )
                        decimal_height = (
                            bbox_decimal[3] - bbox_decimal[1]
                            if bbox_decimal
                            else DECIMAL_FONT_SIZE
                        )
                    else:
                        decimal_width = 0
                        decimal_height = DECIMAL_FONT_SIZE

                    text_total_width = int_width + decimal_width
                    text_x = start_x + (block_width - text_total_width) // 2

                    int_y_offset = (block_height - int_height) // 2
                    int_y_offset += INT_VERTICAL_OFFSET

                    int_bottom = int_y_offset + int_height
                    decimal_y_offset = int_bottom - decimal_height
                    decimal_y_offset += DECIMAL_VERTICAL_OFFSET

                    block_color = DIFFICULTY_COLORS.get(label, (255, 255, 255, 200))

                    if label == "SP":
                        text_fill = (0, 0, 0, 255)
                    else:
                        text_fill = TEXT_COLOR

                    draw_parallelogram_block(
                        draw,
                        start_x,
                        start_y,
                        block_width,
                        block_height,
                        dpower,
                        PARALLELOGRAM_SKEW_FACTOR,
                        block_color,
                        angle_deg=PARALLELOGRAM_ANGLE_TOP_LEFT,
                    )

                    draw.text(
                        (text_x, start_y + int_y_offset),
                        int_part,
                        font=font_small,
                        fill=text_fill,
                    )

                    if decimal_text:
                        draw.text(
                            (text_x + int_width, start_y + decimal_y_offset),
                            decimal_text,
                            font=font_decimal,
                            fill=text_fill,
                        )
                    start_x += block_width + DIFFICULTY_SPACING + skew_extra

        return True

    except Exception as e:
        print(f"  添加歌曲信息失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def process_image(
    input_path, output_path, song_info=None, difficulty_info=None, add_text=True
):
    # 1. 打开并裁剪图像
    im = Image.open(input_path).convert("RGBA")
    r = im.width / im.height

    print(f"原始图像尺寸: {im.width}x{im.height}, 宽高比: {r:.3f}")

    # 裁剪为 16:9
    target_ratio = WIDTH / HEIGHT
    if r > target_ratio:
        # 太宽，裁剪左右
        new_width = im.height * target_ratio
        left = (im.width - new_width) / 2
        right = left + new_width
        im = im.crop((left, 0, right, im.height))
    else:
        # 太高，裁剪上下
        new_height = im.width / target_ratio
        top = (im.height - new_height) / 2
        bottom = top + new_height
        im = im.crop((0, top, im.width, bottom))

    print(f"裁剪后尺寸: {im.width}x{im.height}")

    # 2. 调整到目标尺寸
    im = im.resize((WIDTH, HEIGHT), RESAMPLING_LANCZOS)

    # 3. 创建模糊背景
    blur_radius = (im.width + im.height) * BLUR_R
    print(f"模糊半径: {blur_radius}")
    blur_im = im.filter(ImageFilter.GaussianBlur(blur_radius))

    # 4. 创建最终画布
    result = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))

    # 5. 添加模糊背景
    result.paste(blur_im, (0, 0))

    # 6. 添加暗化层
    darken = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, int(255 * (1 - DIM))))
    result = Image.alpha_composite(result, darken)

    # 6.5 集成 trigrid 网格效果
    # ====== TriGrid 网格效果 ======
    trigrid_base_path = "./resources/TriGridBase.png"
    if os.path.exists(trigrid_base_path):
        base_tex = Image.open(trigrid_base_path).convert("RGBA")
        base_tex = base_tex.resize((WIDTH, HEIGHT), RESAMPLING_LANCZOS)
        shader_img = apply_trigrid_effect(base_tex, t=0.0, use_gl=True)
        if shader_img is not None:
            result = Image.alpha_composite(result, shader_img)
            print("  TriGrid网格已应用")
        else:
            print("  警告: TriGrid网格渲染失败，跳过")
    else:
        print(f"  警告: 未找到TriGrid基础纹理 {trigrid_base_path}，跳过网格")

    # 7. 计算对角线矩形的位置和参数
    dpower = compute_dpower(WIDTH, HEIGHT)
    child_width = int(WIDTH * CHILDREN_SIZE)
    child_height = int(HEIGHT * CHILDREN_SIZE)
    x0 = (WIDTH - child_width) // 2
    # 记录插画原始顶部 Y（居中时的值），用于信息块定位
    orig_child_top = (HEIGHT - child_height) // 2
    y0 = orig_child_top
    # 将插画整体上移指定像素，并记录新的顶部坐标（向上移动：减小 Y）
    y0 = max(TEXT_MARGIN, y0 - ILLUSTRATION_RAISE_PX)
    x1 = x0 + child_width
    y1 = y0 + child_height

    print(
        f"子图像位置: ({x0}, {y0}) 到 ({x1}, {y1}), 大小: {child_width}x{child_height}"
    )
    print(f"对角线参数: {dpower}")

    # 8. 应用阴影效果
    shadow = apply_shadow_effect(
        result, x0, y0, x1, y1, dpower, SHADER_ALPHA, SHADER_POWER
    )
    result = Image.alpha_composite(result, shadow)

    # 9. 创建对角线矩形蒙版
    mask = Image.new("L", (child_width, child_height), 0)
    mask_draw = ImageDraw.Draw(mask)

    # 在蒙版上绘制对角线矩形
    points = create_diagonal_rectangle(
        mask_draw, 0, 0, child_width, child_height, dpower
    )
    mask_draw.polygon(points, fill=255)

    # 10. 准备子图像
    child_im = im.resize((child_width, child_height), RESAMPLING_LANCZOS)

    # 应用蒙版
    child_im.putalpha(mask)

    # 11. 将子图像粘贴到结果上
    result.paste(child_im, (x0, y0), child_im)

    # 12. 如果有歌曲信息并且要求添加文本，则添加
    if add_text and song_info is not None:
        # 从文件名提取歌曲ID
        filename = os.path.basename(input_path)
        song_id = get_song_id_from_filename(filename)
        print(f"检测到歌曲ID: {song_id}")

        # 添加歌曲信息到图片
        if song_id:
            text_added = add_song_info_to_image(
                result, song_id, song_info, difficulty_info, dpower, child_top_y=orig_child_top
            )
            if not text_added:
                print("  警告: 添加文字失败，但图片已保存")

    # 在文本和其他图层绘制完成后绘制左右角三角形覆盖（◤ 内容 ◢）
    try:
        _draw_wings(result)
    except Exception:
        pass

    # 13. 保存结果
    result = result.convert("RGB")
    result.save(output_path, "PNG")

    print(f"处理完成，结果保存到: {output_path}")
    return True


def run(input_path, output_path, data_dir="data", add_text=True):
    song_info = None
    difficulty_info = None

    if add_text:
        song_info, difficulty_info = load_song_info(data_dir)

    return process_image(input_path, output_path, song_info, difficulty_info, add_text)


def debug_mode():
    print("=== 调试模式 ===")

    # 设置路径
    data_dir = "data"
    input_dir = os.path.join(data_dir, "Illustration")
    output_dir = os.path.join(data_dir, "output", "Cover")

    # 检查输入目录
    if not os.path.exists(input_dir):
        print(f"错误: 输入目录不存在: {input_dir}")
        return False

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录: {output_dir}")

    # 加载歌曲信息
    song_info, difficulty_info = load_song_info(data_dir)

    if not song_info:
        print("警告: 未找到歌曲信息，将生成无文字的封面")

    # 获取所有PNG文件
    png_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".png")]

    if not png_files:
        print(f"错误: 在 {input_dir} 中未找到PNG文件")
        return False

    print(f"找到 {len(png_files)} 个PNG文件")

    # 处理每个文件
    success_count = 0
    fail_count = 0

    for i, filename in enumerate(png_files, 1):
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)

        print(f"\n[{i}/{len(png_files)}] 处理: {filename}")

        # 检查是否已存在
        if os.path.exists(output_path):
            print(f"  跳过: 文件已存在 {output_path}")
            success_count += 1
            continue

        try:
            # 处理图像
            success = process_image(
                input_path, output_path, song_info, difficulty_info, add_text=True
            )

            if success:
                success_count += 1
                print(f"  成功: 已保存到 {output_path}")
            else:
                fail_count += 1
                print(f"  失败: 处理 {filename} 时出错")

        except Exception as e:
            fail_count += 1
            print(f"  异常: 处理 {filename} 时发生错误: {str(e)}")
            import traceback

            traceback.print_exc()

    print("\n=== 处理完成 ===")
    print(f"成功: {success_count}, 失败: {fail_count}, 总计: {len(png_files)}")

    return fail_count == 0


if __name__ == "__main__":
    if not os.path.exists(FONT_PATH):
        print(f"提示: 字体文件 '{FONT_PATH}' 不存在")
        print("如需添加文字，请将字体文件放在项目根目录并重命名为 'font.ttf'")
        print("程序将尝试使用系统字体或默认字体\n")

    if len(sys.argv) < 2:
        print("使用方法:")
        print("  单文件模式: python3 autoImage.py <输入图片> <输出图片> <song name> <composer> <difficulties> (e.g. '1,2.5')")
        print("    示例: python3 autoImage.py in.png out.png 'Song Name' 'Composer' 'EZ=1,HD=2.5'")
        print("  调试模式: python3 autoImage.py --debug")
        sys.exit(1)

    if sys.argv[1] == "--debug":
        success = debug_mode()
        if success:
            # 清理 OpenGL 资源
            if TRIGRID_GL_AVAILABLE and trigridRenderer is not None:
               renderer = trigridRenderer.get_cached_renderer()
            if renderer._initialized:
               renderer.cleanup()
            print("调试模式执行成功!")
            sys.exit(0)
        else:
            print("调试模式执行失败!")
            sys.exit(1)

    if len(sys.argv) < 3:
        print("错误: 单文件模式需要输入和输出路径")
        print("使用方法: python3 autoImage.py <输入图片> <输出图片> <song name> <composer> <difficulties>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # 可选参数：歌曲名、作曲、难度字符串
    song_name = sys.argv[3] if len(sys.argv) > 3 else None
    composer = sys.argv[4] if len(sys.argv) > 4 else None
    difficulties_arg = sys.argv[5] if len(sys.argv) > 5 else None

    if not os.path.exists(input_path):
        print(f"错误: 输入文件不存在 '{input_path}'")
        sys.exit(1)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"创建目录: {output_dir}")

    try:
        if song_name:
            # 直接使用命令行提供的信息，不从 data 加载
            song_id = get_song_id_from_filename(os.path.basename(input_path))
            song_info = {song_id: {"name": song_name, "composer": composer or ""}}
            if difficulties_arg and "=" in difficulties_arg:
                difficulties = parse_difficulties_kv(difficulties_arg)
            else:
                difficulties = parse_difficulties_arg(difficulties_arg or "")
            difficulty_info = {song_id: difficulties}
            success = process_image(input_path, output_path, song_info, difficulty_info, add_text=True)
        else:
            # 传统路径，从 data 加载信息
            success = run(input_path, output_path, data_dir="data", add_text=True)

        if success:
            print("处理成功!")
            sys.exit(0)
        else:
            print("处理失败!")
            sys.exit(1)

    except Exception as e:
        print(f"处理图像时出错: {str(e)}")
        import traceback

        # 清理 OpenGL 资源
        if TRIGRID_GL_AVAILABLE and trigridRenderer is not None:
           renderer = trigridRenderer.get_cached_renderer()
        if renderer._initialized:
            renderer.cleanup()

        traceback.print_exc()
        sys.exit(1)
