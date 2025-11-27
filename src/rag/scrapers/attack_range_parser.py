"""
明日方舟攻击范围SVG解析器
识别和解析PRTS Wiki中的攻击范围SVG图表
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class AttackRangePattern:
    """攻击范围模式"""
    name: str
    description: str
    grid: List[List[bool]]
    range_type: str  # 'melee', 'ranged', 'aoe', 'special'
    template: str


class AttackRangeParser:
    """解析SVG攻击范围"""

    # 常见的攻击范围模式
    PATTERNS = {
        'center_single': AttackRangePattern(
            name='中心单格',
            description='只攻击自身所在格子',
            grid=[
                [False, False, False],
                [False, True, False],
                [False, False, False]
            ],
            range_type='melee',
            template='□■□\n□■□\n□■□'
        ),
        'cross': AttackRangePattern(
            name='十字形',
            description='攻击上下左右四个方向',
            grid=[
                [False, True, False],
                [True, True, True],
                [False, True, False]
            ],
            range_type='melee',
            template='□■□\n■■■\n□■□'
        ),
        'all_9': AttackRangePattern(
            name='九宫格',
            description='攻击周围所有9个格子',
            grid=[
                [True, True, True],
                [True, True, True],
                [True, True, True]
            ],
            range_type='melee',
            template='■■■\n■■■\n■■■'
        ),
        'center_3x3': AttackRangePattern(
            name='3x3中心实心',
            description='中心3x3区域全攻击',
            grid=[
                [True, True, True],
                [True, True, True],
                [True, True, True]
            ],
            range_type='aoe',
            template='■■■\n■■■\n■■■'
        ),
    }

    def __init__(self):
        self.svg_content = ""
        self.defs = {}
        self.uses = []
        self.grid_size = None

    def parse_svg(self, svg_content: str) -> Optional[Dict]:
        """
        解析SVG并识别攻击范围

        Args:
            svg_content: SVG代码字符串

        Returns:
            解析结果字典或None
        """
        self.svg_content = svg_content

        # 步骤1: 提取defs
        self._extract_defs()

        # 步骤2: 提取use元素
        self._extract_uses()

        # 步骤3: 确定网格大小
        grid_dim = self._detect_grid_dimensions()
        if not grid_dim:
            return None

        rows, cols = grid_dim

        # 步骤4: 构建网格
        grid = self._build_grid(rows, cols)
        if not grid:
            return None

        # 步骤5: 识别模式
        pattern = self._identify_pattern(grid)

        # 步骤6: 生成描述
        description = self._generate_description(grid, pattern)

        return {
            'pattern_name': pattern.name if pattern else '未知',
            'description': description,
            'grid': grid,
            'rows': rows,
            'cols': cols,
            'range_type': pattern.range_type if pattern else 'unknown',
            'center_position': self._find_center(grid),
            'attack_cells': self._count_attack_cells(grid)
        }

    def _extract_defs(self):
        """提取SVG定义"""
        self.defs = {}

        # 匹配rect定义
        def_pattern = r'<rect\s+id="(\d+)"\s+fill="([^"]+)"(?:\s+stroke="([^"]*)")?.*?width="(\d+)"\s+height="(\d+)"'

        for match in re.finditer(def_pattern, self.svg_content, re.DOTALL):
            rect_id = match.group(1)
            fill = match.group(2)
            stroke = match.group(3) or 'none'
            width = int(match.group(4))
            height = int(match.group(5))

            self.defs[rect_id] = {
                'fill': fill,
                'stroke': stroke,
                'width': width,
                'height': height,
                'is_attack_range': fill != 'none' and fill != '#000000'
            }

    def _extract_uses(self):
        """提取use元素"""
        self.uses = []

        # 匹配use元素 (支持xlink:href和href)
        use_pattern = r'<use\s+(?:xlink:)?href="#(\d+)"\s+x="(\d+)"\s+y="(\d+)"'

        for match in re.finditer(use_pattern, self.svg_content):
            href = match.group(1)
            x = int(match.group(2))
            y = int(match.group(3))

            self.uses.append({
                'href': href,
                'x': x,
                'y': y,
                'is_attack': self.defs.get(href, {}).get('is_attack_range', False)
            })

    def _merge_close_coordinates(self, coords: List[int], tolerance: int = 5) -> List[int]:
        """
        合并相近的坐标（处理中心格子尺寸不同导致的偏移）

        Args:
            coords: 原始坐标列表
            tolerance: 容差值，小于此值的差异视为相同

        Returns:
            合并后的坐标列表
        """
        if not coords:
            return []

        sorted_coords = sorted(set(coords))
        merged = [sorted_coords[0]]

        for coord in sorted_coords[1:]:
            # 如果当前坐标与上一个坐标差距小于容差，视为同一位置
            if abs(coord - merged[-1]) > tolerance:
                merged.append(coord)
            else:
                print(f"    合并坐标: {coord} -> {merged[-1]} (差值{abs(coord - merged[-1])})")

        return merged

    def _detect_grid_dimensions(self) -> Optional[Tuple[int, int]]:
        """检测网格维度"""
        if not self.uses:
            return None

        # 提取所有x和y坐标
        x_coords = sorted(set(use['x'] for use in self.uses))
        y_coords = sorted(set(use['y'] for use in self.uses))

        print(f"  Debug - 合并前坐标: x={x_coords}, y={y_coords}")

        # 合并相近的坐标（处理因尺寸不同导致的偏移）
        x_merged = self._merge_close_coordinates(x_coords, tolerance=3)
        y_merged = self._merge_close_coordinates(y_coords, tolerance=3)

        # 去重后计算行列数
        cols = len(x_merged)
        rows = len(y_merged)

        print(f"  Debug - 合并后坐标: x={x_merged}, y={y_merged}")
        print(f"  Debug - 网格大小: {rows}x{cols}, 实际元素: {len(self.uses)}")

        # 验证是否是矩形网格
        expected_count = rows * cols
        actual_count = len(self.uses)

        if expected_count != actual_count:
            print(f"  Warning: 网格不匹配，期望{expected_count}个，实际{actual_count}个")
            # 如果差距不大，仍然继续
            if abs(expected_count - actual_count) <= 2:
                print(f"  但差距在可接受范围内，继续处理...")

        return rows, cols

    def _build_grid(self, rows: int, cols: int) -> Optional[List[List[bool]]]:
        """构建攻击范围网格"""
        if not self.uses:
            return None

        # 创建空网格
        grid = [[False for _ in range(cols)] for _ in range(rows)]

        # 提取唯一坐标并排序
        x_coords = sorted(set(use['x'] for use in self.uses))
        y_coords = sorted(set(use['y'] for use in self.uses))

        # 合并相近坐标（与_detect_grid_dimensions保持一致）
        x_merged = self._merge_close_coordinates(x_coords, tolerance=3)
        y_merged = self._merge_close_coordinates(y_coords, tolerance=3)

        print(f"  Debug - 网格映射: x坐标映射到列，y坐标映射到行")

        # 填充网格 - 将每个use元素映射到最近的网格位置
        for use in self.uses:
            x, y = use['x'], use['y']

            # 找到最近的列（x坐标）
            col = None
            min_x_diff = float('inf')
            for i, ref_x in enumerate(x_merged):
                diff = abs(x - ref_x)
                if diff < min_x_diff:
                    min_x_diff = diff
                    col = i

            # 找到最近的行（y坐标）
            row = None
            min_y_diff = float('inf')
            for i, ref_y in enumerate(y_merged):
                diff = abs(y - ref_y)
                if diff < min_y_diff:
                    min_y_diff = diff
                    row = i

            if col is not None and row is not None:
                if 0 <= row < rows and 0 <= col < cols:
                    grid[row][col] = use['is_attack']
                    print(f"    元素 ({x},{y}) -> 网格[{row}][{col}] = {'攻击' if use['is_attack'] else '空'}")
                else:
                    print(f"    Warning: 坐标越界 ({row},{col}) 超出 {rows}x{cols}")

        return grid

    def _identify_pattern(self, grid: List[List[bool]]) -> Optional[AttackRangePattern]:
        """识别攻击范围模式"""
        # 将网格转换为字符串表示用于匹配
        grid_str = '\n'.join(''.join('■' if cell else '□' for cell in row) for row in grid)

        # 尝试匹配已知模式
        for pattern_name, pattern in self.PATTERNS.items():
            if grid_str == pattern.template:
                return pattern

        return None

    def _generate_description(self, grid: List[List[bool]],
                              pattern: Optional[AttackRangePattern]) -> str:
        """生成描述文本"""
        rows = len(grid)
        cols = len(grid[0])

        # 统计攻击格子数
        attack_count = sum(1 for row in grid for cell in row if cell)
        total_count = rows * cols

        if pattern:
            desc = f"{pattern.name}: {pattern.description}"
        else:
            desc = f"自定义模式: {attack_count}/{total_count} 格可攻击"

        # 添加详细信息
        desc += f"\n网格: {rows}x{cols}, 攻击格子: {attack_count}个"

        return desc

    def _find_center(self, grid: List[List[bool]]) -> Optional[Tuple[int, int]]:
        """找到中心位置"""
        rows = len(grid)
        cols = len(grid[0])

        # 假设中心在-middle
        center_row = rows // 2
        center_col = cols // 2

        return center_row, center_col

    def _count_attack_cells(self, grid: List[List[bool]]) -> int:
        """统计攻击格子数量"""
        return sum(1 for row in grid for cell in row if cell)

    def visualize_grid(self, grid: List[List[bool]]) -> str:
        """可视化网格"""
        lines = []
        lines.append("+" + "---" * len(grid[0]) + "+")

        for row in grid:
            row_str = "| " + " | ".join("■" if cell else "□" for cell in row) + " |"
            lines.append(row_str)
            lines.append("+" + "---" * len(grid[0]) + "+")

        return "\n".join(lines)

    def get_pattern_examples(self) -> Dict[str, str]:
        """获取模式示例"""
        examples = {}

        examples['中心单格'] = '''
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 78 78">
  <defs>
    <rect id="1" fill="#27a6f3" width="22" height="22"/>
    <rect id="2" fill="none" stroke="gray" width="20" height="20"/>
  </defs>
  <use href="#2" x="2" y="2"/><use href="#2" x="28" y="2"/><use href="#2" x="54" y="2"/>
  <use href="#2" x="2" y="28"/><use href="#1" x="27" y="27"/><use href="#2" x="54" y="28"/>
  <use href="#2" x="2" y="54"/><use href="#2" x="28" y="54"/><use href="#2" x="54" y="54"/>
</svg>
'''

        examples['十字形'] = '''
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 78 78">
  <defs>
    <rect id="1" fill="#27a6f3" width="22" height="22"/>
    <rect id="2" fill="none" stroke="gray" width="20" height="20"/>
  </defs>
  <use href="#2" x="2" y="2"/><use href="#1" x="28" y="2"/><use href="#2" x="54" y="2"/>
  <use href="#1" x="2" y="28"/><use href="#1" x="27" y="27"/><use href="#1" x="54" y="28"/>
  <use href="#2" x="2" y="54"/><use href="#1" x="28" y="54"/><use href="#2" x="54" y="54"/>
</svg>
'''

        return examples


def parse_and_visualize(svg_code: str):
    """解析并可视化SVG攻击范围"""
    parser = AttackRangeParser()
    result = parser.parse_svg(svg_code)

    if not result:
        print("无法解析SVG")
        return

    print("=" * 50)
    print(f"攻击范围: {result['pattern_name']}")
    print(f"描述: {result['description']}")
    print(f"类型: {result['range_type']}")
    print("\n可视化:")
    print(parser.visualize_grid(result['grid']))
    print("\n数组表示:")
    for i, row in enumerate(result['grid']):
        print(f"  {i}: {row}")
    print("=" * 50)


# 测试代码
if __name__ == "__main__":
    # 测试用例1: 中心单格
    svg_1 = '''
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 78 78">
  <defs><rect id="1" fill="#27a6f3" width="22" height="22"></rect><rect id="2" fill="none" stroke="gray" stroke-width="2" width="20" height="20"></rect></defs>
  <use xlink:href="#2" x="2" y="2"/><use xlink:href="#2" x="28" y="2"/><use xlink:href="#2" x="54" y="2"/>
  <use xlink:href="#2" x="2" y="28"/><use xlink:href="#1" x="27" y="27"/><use xlink:href="#2" x="54" y="28"/>
  <use xlink:href="#2" x="2" y="54"/><use xlink:href="#2" x="28" y="54"/><use xlink:href="#2" x="54" y="54"/>
</svg>
    '''

    # 测试用例2: 3x3全部攻击（近战范围）
    svg_2 = '''
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 78 78">
  <defs><rect id="1" fill="#27a6f3" width="22" height="22"></rect><rect id="2" fill="none" stroke="gray" stroke-width="2" width="20" height="20"></rect></defs>
  <use xlink:href="#1" x="2" y="2"/><use xlink:href="#1" x="28" y="2"/><use xlink:href="#1" x="54" y="2"/>
  <use xlink:href="#1" x="2" y="28"/><use xlink:href="#1" x="27" y="27"/><use xlink:href="#1" x="54" y="28"/>
  <use xlink:href="#1" x="2" y="54"/><use xlink:href="#1" x="28" y="54"/><use xlink:href="#1" x="54" y="54"/>
</svg>
    '''

    print("\n测试用例1: 中心单格（阻挡近战）")
    parse_and_visualize(svg_1)

    print("\n测试用例2: 九宫格全攻击")
    parse_and_visualize(svg_2)
