"""
剧情爬虫常量定义
"""

# 剧情页面URL模式
STORY_URL_PATTERNS = [
    '剧情',
    '故事',
    '活动',
    '剧情回顾',
    'Side Story',
    'Event',
    '剧情记录',
    '世界观',
    '设定',
    '记录'
]

# 排除的URL模式
EXCLUDED_URL_PATTERNS = [
    '干员',
    '角色',
    '技能',
    '天赋',
    'Category:',
    'Template:',
    'User:',
    '帮助:',
    'File:',
    'Special:'
]

# 剧情页面HTML元素选择器
STORY_SELECTORS = {
    'playback_button': '#button_playback_all',
    'dialogue_list': 'li',
    'speaker_tag': 'em',
    'content_tag': 'span',
    'main_content': '#mw-content-text, .mw-parser-output'
}

# 章节识别模式
CHAPTER_PATTERNS = [
    r'^第[一二三四五六七八九十\d]+章',  # 第X章
    r'^第[一二三四五六七八九十\d]+话',   # 第X话
    r'^Episode\s+\d+',                 # Episode X
    r'^Chapter\s+\d+',                 # Chapter X
    r'^\d+\.',                         # 1. 2. 3.
    r'^序[章幕]',                      # 序章/序幕
    r'^终[章幕]',                      # 终章/终幕
]

# 旁白关键词
NARRATION_KEYWORDS = [
    '旁白',
    '叙述',
    '画外音',
    '场景描述',
    '地点',
    '时间',
    '系统提示',
    '【',
    '】'
]

# 角色名常见后缀（用于过滤）
CHARACTER_SUFFIXES = [
    '干员',
    '博士',
    '队长',
    '长官',
    '医生',
    '护士',
    '助手',
    '队员'
]

# 存储目录
STORAGE_DIR = {
    'characters': '干员',
    'stories': '剧情',
    'general': '其他'
}

# 剧情内容类型
STORY_TYPES = {
    'MAINLINE': 'mainline',
    'CHARACTER': 'character',
    'ACTIVITY': 'activity',
    'SIDE': 'side',
    'WORLDVIEW': 'worldview',
    'GENERAL': 'general'
}
