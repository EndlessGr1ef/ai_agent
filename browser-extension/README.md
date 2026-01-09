# AI 划词搜索 - 浏览器扩展

一个智能划词解释的 Chrome 扩展，选中网页文字即可获得 AI 解释。

## 功能特性

- 🎯 **划词即查** - 选中文字后悬停红点触发 AI 解释
- 🧠 **上下文感知** - 自动提取选中文字周围的上下文
- 🌍 **多语言支持** - 支持中文、英文、日文、韩文输出
- ⚙️ **可配置 API** - 支持自定义 API 端点和模型

## 安装方式

### 方式一：开发者模式加载（推荐）

1. **构建扩展**
   ```bash
   cd browser-extension
   pnpm install
   pnpm build
   ```

2. **在 Chrome 中加载**
   - 打开 Chrome，访问 `chrome://extensions/`
   - 开启右上角的 **"开发者模式"**
   - 点击 **"加载已解压的扩展程序"**
   - 选择 `browser-extension/dist` 目录

3. **配置 API**
   - 点击扩展图标，选择"设置选项"
   - 输入你的 API Key
   - 配置 API 地址和模型（可选）

### 方式二：开发模式

```bash
cd browser-extension
pnpm install
pnpm dev
```

然后在 Chrome 中加载 `dist` 目录，修改代码后会自动热更新。

## 使用方法

1. 在任意网页中选中一段文字
2. 悬停在出现的红色小圆点上
3. 等待 AI 分析并显示解释结果

## 技术栈

- React 18 + TypeScript
- Vite (构建工具)
- Chrome Extension Manifest V3

## 项目结构

```
browser-extension/
├── src/
│   ├── App.tsx              # 弹出窗口 UI
│   ├── main.tsx             # 弹出窗口入口
│   ├── background/          # Service Worker
│   ├── content/             # 内容脚本（划词功能）
│   ├── options/             # 设置页面
│   └── utils/               # 工具函数
├── dist/                    # 构建输出（用于加载到 Chrome）
└── manifest.json            # 扩展配置
```

## 常见问题

### Q: 为什么扩展图标点击后没反应？
确保已在设置中配置了有效的 API Key。

### Q: 为什么划词后没有出现红点？
检查页面是否有 Content Security Policy 限制，部分网站（如 Chrome 内置页面）无法注入内容脚本。

### Q: 支持哪些 API？
支持所有兼容 Anthropic API 格式的服务，包括：
- Anthropic Claude
- MiniMax（默认）
- 其他 OpenAI 兼容 API
