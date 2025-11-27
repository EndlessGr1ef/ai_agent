#!/usr/bin/env python3
"""
SVG攻击范围分析器
用于解析明日方舟干员技能的攻击范围SVG图形
"""

import re
from typing import List, Tuple, Set


class AttackRangeAnalyzer:
    """分析SVG攻击范围图形"""

    def __init__(self):
        self.grid_size = 26  # 每个网格的基本大小（像素）
        self.margin = 1      # 网格间距

    def parse_svg(self, svg_content: str) -> dict:
        """解析SVG内容并提取攻击范围信息

        Args:
            svg_content: SVG代码字符串

        Returns:
            包含攻击范围信息的字典
        """
        # 提取viewBox信息
        viewbox_match = re.search(r'viewBox="([^"]+)"', svg_content)
        if viewbox_match:
            viewbox_values = viewbox_match.group(1).split()
            # viewBox is "minX minY width height", we need width and height
            if len(viewbox_values) >= 4:
                width = int(viewbox_values[2])
                height = int(viewbox_values[3])
            else:
                width, height = 0, 0
        else:
            width, height = 0, 0

        # 提取所有rect元素（在defs中）
        rect_pattern = r'<rect[^>]+id="([^"]+)"[^>]*>'
        rects = re.findall(rect_pattern, svg_content)

        # 创建ID到rect信息的映射
        rect_map = {}
        for rect_match in rects:
            rect_full = re.search(f'<rect[^>]+id="{rect_match}"[^>]*>', svg_content)
            if rect_full:
                rect_str = rect_full.group(0)
                # 提取属性（使用更精确的正则表达式避免匹配stroke-width）
                # 从stroke-width之后开始匹配width和height
                after_stroke = re.search(r'stroke-width="[^"]+"\s*([^>]+)', rect_str)
                if after_stroke:
                    remaining = after_stroke.group(1)
                    width_match = re.search(r'width="(\d+)"', remaining)
                    height_match = re.search(r'height="(\d+)"', remaining)
                else:
                    # 如果没有stroke-width，直接匹配
                    width_match = re.search(r'width="(\d+)"', rect_str)
                    height_match = re.search(r'height="(\d+)"', rect_str)

                fill_match = re.search(r'fill="([^"]+)"', rect_str)

                if width_match and height_match:
                    rect_map[rect_match] = {
                        'width': int(width_match.group(1)),
                        'height': int(height_match.group(1)),
                        'fill': fill_match.group(1) if fill_match else None
                    }
                    print(f"  Found rect #{rect_match}: fill={rect_map[rect_match]['fill']}, size={rect_map[rect_match]['width']}x{rect_map[rect_match]['height']}")

        # 提取所有use元素
        use_pattern = r'<use[^>]+>'
        uses = re.findall(use_pattern, svg_content)

        # 解析每个use元素的位置和引用的rect
        attack_cells = []
        total_cells = []

        print(f"  Found {len(uses)} use elements")

        for i, use_elem in enumerate(uses):
            # 提取引用的rect ID
            href_match = re.search(r'xlink:href="#([^"]+)"', use_elem)
            if not href_match:
                href_match = re.search(r'href="#([^"]+)"', use_elem)

            if not href_match:
                print(f"    Use #{i}: no href found")
                continue

            rect_id = href_match.group(1)

            # 提取位置信息
            x_match = re.search(r'x="([^"]+)"', use_elem)
            y_match = re.search(r'y="([^"]+)"', use_elem)

            if not x_match or not y_match:
                print(f"    Use #{i} (#{rect_id}): missing coordinates")
                continue

            x = int(x_match.group(1))
            y = int(y_match.group(1))

            print(f"    Use #{i}: rect #{rect_id} at ({x}, {y})")

            if rect_id in rect_map:
                rect_info = rect_map[rect_id]

                # 计算网格坐标（以grid_size为单位）
                grid_x = round(x / self.grid_size)
                grid_y = round(y / self.grid_size)

                cell_info = {
                    'x': x,
                    'y': y,
                    'grid_x': grid_x,
                    'grid_y': grid_y,
                    'width': rect_info['width'],
                    'height': rect_info['height'],
                    'fill': rect_info['fill'],
                    'rect_id': rect_id,
                    'is_attack_range': rect_info['fill'] and rect_info['fill'].lower() != 'none'
                }

                total_cells.append(cell_info)
                if cell_info['is_attack_range']:
                    attack_cells.append(cell_info)
                    print(f"      -> Attack range cell!")
            else:
                print(f"    Use #{i}: rect #{rect_id} not found in rect_map")

        # 分析攻击范围形状
        shape_info = self._analyze_shape(attack_cells, total_cells)

        return {
            'canvas_size': (width, height),
            'total_cells': total_cells,
            'attack_cells': attack_cells,
            'attack_count': len(attack_cells),
            'shape_info': shape_info
        }

    def _analyze_shape(self, attack_cells: List[dict], total_cells: List[dict]) -> dict:
        """分析攻击范围的形状特征

        Args:
            attack_cells: 攻击范围内的网格
            total_cells: 所有网格

        Returns:
            形状分析结果
        """
        if not attack_cells:
            return {'type': 'none', 'description': '无攻击范围'}

        # 获取网格坐标
        grid_coords = [(cell['grid_x'], cell['grid_y']) for cell in attack_cells]

        # 计算边界
        min_x = min(coord[0] for coord in grid_coords)
        max_x = max(coord[0] for coord in grid_coords)
        min_y = min(coord[1] for coord in grid_coords)
        max_y = max(coord[1] for coord in grid_coords)

        width = max_x - min_x + 1
        height = max_y - min_y + 1

        # 判断形状类型 - 按优先级排序
        if len(attack_cells) == 1:
            shape_type = 'single'
            description = '单体攻击（1格）'
        elif self._is_cross_shape(grid_coords):
            shape_type = 'cross'
            description = '十字形范围'
        elif self._is_T_shape(grid_coords):
            shape_type = 'T_shape'
            description = self._generate_smart_description(attack_cells, grid_coords)
        elif self._is_Z_shape(grid_coords):
            shape_type = 'Z_shape'
            description = self._generate_smart_description(attack_cells, grid_coords)
        elif self._is_diagonal_line(grid_coords):
            shape_type = 'diagonal'
            description = self._generate_smart_description(attack_cells, grid_coords)
        elif self._is_L_shape(grid_coords):
            shape_type = 'L_shape'
            description = self._generate_smart_description(attack_cells, grid_coords)
        elif self._is_diamond_shape(grid_coords, min_x, max_x, min_y, max_y):
            shape_type = 'diamond'
            description = '菱形范围'
        elif width == 1 and height == len(attack_cells):
            shape_type = 'line'
            description = f'直线攻击（{len(attack_cells)}格直线）'
        elif width == 2 and height == 2 and len(attack_cells) == 4:
            shape_type = 'square_2x2'
            description = '2×2方形范围'
        elif width == 3 and height == 3 and len(attack_cells) == 9:
            shape_type = 'square_3x3'
            description = '3×3方形范围'
        elif width == 2 and len(attack_cells) == 2:
            shape_type = 'horizontal_2'
            description = '水平2格'
        elif height == 2 and len(attack_cells) == 2:
            shape_type = 'vertical_2'
            description = '垂直2格'
        else:
            shape_type = 'custom'
            # 使用智能描述生成器
            description = self._generate_smart_description(attack_cells, grid_coords)

        return {
            'type': shape_type,
            'description': description,
            'width': width,
            'height': height,
            'bounds': (min_x, max_x, min_y, max_y),
            'grid_coords': grid_coords
        }

    def _is_cross_shape(self, coords: List[Tuple[int, int]]) -> bool:
        """判断是否为十字形"""
        # 寻找中心点
        all_x = [c[0] for c in coords]
        all_y = [c[1] for c in coords]
        center_x = all_x[len(all_x)//2]
        center_y = all_y[len(all_y)//2]

        # 十字形应该有中心点和上下左右4个方向
        required = {(center_x, center_y), (center_x-1, center_y), (center_x+1, center_y),
                   (center_x, center_y-1), (center_x, center_y+1)}
        return set(coords) == required

    def _is_diamond_shape(self, coords: List[Tuple[int, int]], min_x: int, max_x: int, min_y: int, max_y: int) -> bool:
        """判断是否为菱形（钻石形）"""
        # 简单的菱形判断：宽度和高度相等，且为奇数
        width = max_x - min_x + 1
        height = max_y - min_y + 1

        if width != height or width % 2 == 0:
            return False

        # 检查是否形成菱形模式
        center_x = (min_x + max_x) // 2
        center_y = (min_y + max_y) // 2

        for x, y in coords:
            # 检查是否在菱形边界内
            dist = abs(x - center_x) + abs(y - center_y)
            max_dist = width // 2
            if dist > max_dist:
                return False

        return True

    def _is_L_shape(self, coords: List[Tuple[int, int]]) -> bool:
        """判断是否为L形（更严格的检测）"""
        if len(coords) < 4:
            return False

        coords_set = set(coords)
        min_x = min(x for x, y in coords)
        max_x = max(x for x, y in coords)
        min_y = min(y for x, y in coords)
        max_y = max(y for x, y in coords)

        # L形的特征：有一个明显的拐角，两条线段呈90度
        # 常见的L形：左边一列 + 底下一行（或其他变体）

        # 检查是否是典型的L形（左下角拐角）
        # 左下L: (min_x, min_y到max_y) + (min_x, max_y到max_x)
        left_column = all((min_x, y) in coords_set for y in range(min_y, max_y + 1))
        bottom_row = all((x, max_y) in coords_set for x in range(min_x, max_x + 1))
        if left_column and bottom_row:
            # 确保不是完整的矩形
            if len(coords) < (max_x - min_x + 1) * (max_y - min_y + 1):
                return True

        # 检查其他方向的L形
        for corner_x, corner_y in [(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)]:
            # 检查从这个拐角出发的两条线
            horizontal_len = 0
            vertical_len = 0

            # 向右/左检查水平线
            for dx in range(-5, 6):
                if (corner_x + dx, corner_y) in coords_set:
                    horizontal_len = max(horizontal_len, abs(dx) + 1)

            # 向上/下检查垂直线
            for dy in range(-5, 6):
                if (corner_x, corner_y + dy) in coords_set:
                    vertical_len = max(vertical_len, abs(dy) + 1)

            # 如果两条线都存在且有足够长度（>=3），则可能是L形
            if horizontal_len >= 2 and vertical_len >= 2:
                # 排除完整的矩形
                expected_cells = horizontal_len + vertical_len - 1
                if len(coords) < (max_x - min_x + 1) * (max_y - min_y + 1):
                    return True

        return False

    def _is_T_shape(self, coords: List[Tuple[int, int]]) -> bool:
        """判断是否为T形（更严格的检测）"""
        if len(coords) < 5:
            return False

        coords_set = set(coords)

        # T形特征：顶部有横线，中间有垂直线向下
        y_coords = sorted(set(y for x, y in coords))

        if len(y_coords) < 3:
            return False

        # 找顶部横线（Y最小的行）
        min_y = min(y_coords)
        top_row = [(x, y) for x, y in coords if y == min_y]

        if len(top_row) < 3:  # T形顶部至少需要3个点
            return False

        # 检查是否有垂直线从顶部中间向下
        top_min_x = min(x for x, y in top_row)
        top_max_x = max(x for x, y in top_row)
        top_mid_x = (top_min_x + top_max_x) // 2

        # 检查从顶部中间是否有向下延伸
        for dy in range(1, len(y_coords)):
            if (top_mid_x, min_y + dy) not in coords_set:
                # T形不允许在中间断开
                break
        else:
            # 找到了完整的T形
            return True

        return False

    def _is_Z_shape(self, coords: List[Tuple[int, int]]) -> bool:
        """判断是否为Z形（之字形，更严格的检测）"""
        if len(coords) < 6:
            return False

        coords_set = set(coords)
        y_coords = sorted(set(y for x, y in coords))

        # Z形需要至少3行
        if len(y_coords) < 3:
            return False

        # 检查是否是Z形：上下两条横线 + 中间的对角线连接
        min_y = min(y_coords)
        max_y = max(y_coords)
        middle_y = y_coords[len(y_coords) // 2]

        # 检查顶部横线
        top_row = [(x, y) for x, y in coords if y == min_y]
        # 检查底部横线
        bottom_row = [(x, y) for x, y in coords if y == max_y]

        if len(top_row) < 2 or len(bottom_row) < 2:
            return False

        # 检查是否有对角线连接
        # Z形的对角线通常是从上横线的右端连接到中间或下横线的左端
        top_max_x = max(x for x, y in top_row)
        bottom_min_x = min(x for x, y in bottom_row)

        # 检查对角线模式
        if (top_max_x, min_y) in coords_set and (bottom_min_x, max_y) in coords_set:
            # 检查中间是否有连接点
            for y in y_coords[1:-1]:
                if any((x, y) in coords_set for x in range(top_max_x - 2, top_max_x + 3)):
                    return True

        return False

    def _is_diagonal_line(self, coords: List[Tuple[int, int]]) -> bool:
        """判断是否是对角线"""
        if len(coords) < 3:
            return False

        coords_set = set(coords)

        # 对角线：坐标差值相等
        for i in range(len(coords) - 2):
            (x1, y1), (x2, y2), (x3, y3) = coords[i], coords[i+1], coords[i+2]

            # 检查是否在对角线上
            if (x2 - x1 == y2 - y1) and (x3 - x2 == y3 - y2):
                return True

        return False

    def _generate_smart_description(self, attack_cells: List[dict], grid_coords: List[Tuple[int]]) -> str:
        """智能生成特殊形状的描述

        Args:
            attack_cells: 攻击范围内的网格
            grid_coords: 网格坐标列表

        Returns:
            智能描述文本
        """
        coords = sorted(set(grid_coords))

        # L形检测
        if self._is_L_shape(coords):
            return f"L形攻击范围（{len(attack_cells)}格）"

        # T形检测
        if self._is_T_shape(coords):
            return f"T形攻击范围（{len(attack_cells)}格）"

        # Z形检测
        if self._is_Z_shape(coords):
            return f"Z形攻击范围（之字形，{len(attack_cells)}格）"

        # 对角线检测
        if self._is_diagonal_line(coords):
            return f"对角线攻击路径（{len(attack_cells)}格斜线）"

        # 检查缺口（空心形状）
        coords_set = set(coords)
        min_x = min(x for x, y in coords)
        max_x = max(x for x, y in coords)
        min_y = min(y for x, y in coords)
        max_y = max(y for x, y in coords)

        total_cells = (max_x - min_x + 1) * (max_y - min_y + 1)
        actual_cells = len(coords)

        if actual_cells < total_cells * 0.7:  # 如果实际格子少于理论格子的70%
            return f"空心形状（{len(attack_cells)}格，中心有缺口）"

        # 矩形检测（宽高不相等的情况）
        width = max_x - min_x + 1
        height = max_y - min_y + 1

        if width > height:
            return f"水平长方形（{width}×{height}，{len(attack_cells)}格）"
        elif height > width:
            return f"垂直长方形（{width}×{height}，{len(attack_cells)}格）"

        # 默认：列出坐标（限制显示数量）
        if len(coords) <= 8:
            coord_str = ", ".join(f"({x},{y})" for x, y in coords)
            return f"自定义形状: {len(attack_cells)}格 - {coord_str}"
        else:
            coord_str = ", ".join(f"({x},{y})" for x, y in coords[:6])
            return f"自定义形状: {len(attack_cells)}格 - {coord_str}..."

    def has_multiple_regions(self, grid_coords: List[Tuple[int]]) -> bool:
        """检测是否有多段独立的攻击范围

        Args:
            grid_coords: 网格坐标列表

        Returns:
            是否有多段范围
        """
        if len(grid_coords) < 2:
            return False

        coords_set = set(grid_coords)

        # 使用BFS找到连通区域
        visited = set()
        regions = []

        for coord in coords_set:
            if coord in visited:
                continue

            # BFS搜索连通区域
            region = []
            queue = [coord]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue

                visited.add(current)
                region.append(current)

                # 检查相邻的格子（4邻接）
                x, y = current
                neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]

                for neighbor in neighbors:
                    if neighbor in coords_set and neighbor not in visited:
                        queue.append(neighbor)

            if region:
                regions.append(region)

        return len(regions) > 1

    def visualize_range(self, analysis_result: dict, style: str = 'border') -> str:
        """可视化攻击范围（纯文本格式，适合向量数据库）

        Args:
            analysis_result: parse_svg的返回结果
            style: 可视化风格 ('border', 'compact')
                   - border: 边框风格（推荐数据库存储）
                   - compact: 紧凑ASCII风格（最节省空间）

        Returns:
            纯文本可视化字符串
        """
        shape_info = analysis_result['shape_info']

        if shape_info['type'] == 'none':
            return "无攻击范围"

        grid_coords = shape_info.get('grid_coords', [])

        if not grid_coords:
            return "无攻击范围"

        # 计算绘制区域
        min_x = min(coord[0] for coord in grid_coords)
        max_x = max(coord[0] for coord in grid_coords)
        min_y = min(coord[1] for coord in grid_coords)
        max_y = max(coord[1] for coord in grid_coords)

        # 创建网格集合（使用set提高查询性能）
        grid = set(grid_coords)

        # 根据风格绘制
        if style == 'compact':
            return self._draw_compact(grid, min_x, max_x, min_y, max_y)
        else:  # border (default and recommended)
            return self._draw_border(grid, min_x, max_x, min_y, max_y)

    def _draw_border(self, grid: set, min_x: int, max_x: int, min_y: int, max_y: int) -> str:
        """边框风格绘制（推荐用于数据库）"""
        lines = []
        width = max_x - min_x + 1

        # 顶部边框
        lines.append('┌' + '─' * width + '┐')

        # 中间内容
        for y in range(min_y, max_y + 1):
            line = '│'
            for x in range(min_x, max_x + 1):
                if (x, y) in grid:
                    line += '█'
                else:
                    line += ' '
            line += '│'
            lines.append(line)

        # 底部边框
        lines.append('└' + '─' * width + '┘')

        return '\n'.join(lines)

    def _draw_compact(self, grid: set, min_x: int, max_x: int, min_y: int, max_y: int) -> str:
        """紧凑ASCII风格绘制（最节省空间）"""
        lines = []
        for y in range(min_y, max_y + 1):
            line = ''
            for x in range(min_x, max_x + 1):
                if (x, y) in grid:
                    line += 'X'  # 使用单字符
                else:
                    line += '.'
            lines.append(line)
        return '\n'.join(lines)

    def export_for_database(self, analysis_result: dict) -> dict:
        """导出适合向量数据库的格式（只包含border和compact）

        Args:
            analysis_result: parse_svg的返回结果

        Returns:
            包含border和compact格式的字典
        """
        # 添加元数据
        shape_info = analysis_result['shape_info']
        result = {
            'border': self.visualize_range(analysis_result, style='border'),
            'compact': self.visualize_range(analysis_result, style='compact'),
            'metadata': {
                'type': shape_info['type'],
                'attack_count': len(shape_info.get('grid_coords', [])),
                'width': shape_info['width'],
                'height': shape_info['height']
            }
        }

        return result


def test_examples():
    """测试给出的例子"""
    analyzer = AttackRangeAnalyzer()

    # 例子1: 单体攻击范围
    svg1 = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 52 26" style="vertical-align:top;width:52px;height:26px;width:!important;height:!important"><defs><rect id="1" fill="#27a6f3" width="22" height="22"></rect><rect id="2" fill="none" stroke="gray" stroke-width="2" width="20" height="20"></rect></defs><use xlink:href="#1" x="1" y="1"></use><use xlink:href="#2" x="28" y="2"></use></svg>'''

    print("=" * 70)
    print("例子1: 单体攻击范围")
    print("=" * 70)
    result1 = analyzer.parse_svg(svg1)

    # Border风格
    print("Border风格:")
    print("-" * 50)
    print(analyzer.visualize_range(result1, style='border'))

    # Compact风格
    print("\nCompact风格:")
    print("-" * 50)
    print(analyzer.visualize_range(result1, style='compact'))

    # 数据库导出
    print("\n向量数据库导出:")
    print("-" * 50)
    db_export = analyzer.export_for_database(result1)
    import json
    print(json.dumps(db_export, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)

    # 例子2: 十字形攻击范围
    svg2 = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 78 78" style="vertical-align:top;width:78px;height:78px;width:!important;height:!important"><defs><rect id="1" fill="#27a6f3" width="22" height="22"></rect><rect id="2" fill="none" stroke="gray" stroke-width="2" width="20" height="20"></rect></defs><use xlink:href="#1" x="28" y="2"></use><use xlink:href="#1" x="2" y="28"></use><use xlink:href="#1" x="27" y="27"></use><use xlink:href="#1" x="54" y="28"></use><use xlink:href="#1" x="28" y="54"></use></svg>'''

    print("\n例子2: 十字形攻击范围")
    print("=" * 70)
    result2 = analyzer.parse_svg(svg2)

    # Border风格
    print("Border风格:")
    print("-" * 50)
    print(analyzer.visualize_range(result2, style='border'))

    # Compact风格
    print("\nCompact风格:")
    print("-" * 50)
    print(analyzer.visualize_range(result2, style='compact'))

    # 数据库导出
    print("\n向量数据库导出:")
    print("-" * 50)
    db_export = analyzer.export_for_database(result2)
    import json
    print(json.dumps(db_export, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("\n总结")
    print("=" * 70)
    print("✓ Border风格 - 边框清晰，视觉友好")
    print("✓ Compact风格 - 最少字符，节省空间")
    print("✓ export_for_database() - 一次性导出两种格式")
    print("=" * 70)


def format_brackets_text(text: str) -> str:
    """格式化带有【】的文本，每个【】单独换行

    Args:
        text: 原始文本，例如：【代号】银灰【性别】男...

    Returns:
        格式化后的文本，每个【】在单独行
    """
    import re
    # 匹配每个【...】模式并替换为换行
    formatted = re.sub(r'【', '\n【', text)
    # 移除开头的空行
    formatted = formatted.lstrip('\n')
    return formatted


if __name__ == '__main__':
    test_examples()
