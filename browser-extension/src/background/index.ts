// Background service worker for handling AI requests

console.log('[AI Search] Background service worker loaded');

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === 'queryAI') {
    handleAIQuery(request.payload)
      .then(result => {
        sendResponse({ data: result });
      })
      .catch(error => {
        console.error('[AI Search] Query error:', error);
        sendResponse({ error: error.message || String(error) });
      });
    
    return true;
  }
  
  return false;
});

// Maximum context length sent to API (in characters)
const MAX_CONTEXT_FOR_API = 2000;

async function handleAIQuery(payload: { 
  selection: string; 
  context: string; 
  pageUrl?: string; 
  pageTitle?: string;
}): Promise<string> {
  const settings = await chrome.storage.local.get(['anthropicApiKey', 'anthropicBaseUrl', 'anthropicModel', 'targetLanguage']);
  
  const apiKey = settings.anthropicApiKey as string | undefined;
  const baseUrl = (settings.anthropicBaseUrl as string) || 'https://api.minimaxi.com/anthropic';
  const model = (settings.anthropicModel as string) || 'MiniMax-M2';
  const targetLang = (settings.targetLanguage as string) || '中文';

  if (!apiKey) {
    throw new Error('请先在设置页面配置 API Key');
  }

  // Prepare context (truncate if needed)
  const contextForApi = payload.context.length > MAX_CONTEXT_FOR_API 
    ? payload.context.substring(0, MAX_CONTEXT_FOR_API) + '...'
    : payload.context;

  const systemPrompt = `你是一个极简解释助手。用户在浏览网页时选中了一段文字进行查询。
请结合提供的页面信息和上下文内容，对选中的文字进行精准、简练的解释或翻译。
目标语言: ${targetLang}
请直接输出核心答案，不要有冗余的开场白。`;

  const userPrompt = `<page>
  <url>${payload.pageUrl || 'unknown'}</url>
  <title>${payload.pageTitle || 'unknown'}</title>
</page>
<context>${contextForApi}</context>
<selection>${payload.selection}</selection>

请解释上述选中内容。`;

  const response = await fetch(`${baseUrl}/v1/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01'
    },
    body: JSON.stringify({
      model: model,
      max_tokens: 1024,
      system: systemPrompt,
      messages: [
        { role: 'user', content: userPrompt }
      ],
      stream: false
    })
  });


  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    try {
      const errorData = await response.json();
      errorMessage = errorData.error?.message || errorData.message || JSON.stringify(errorData);
    } catch {
      errorMessage = await response.text() || errorMessage;
    }
    throw new Error(errorMessage);
  }

  const data = await response.json();
  
  // Try multiple response formats
  
  // Format 1: Anthropic/MiniMax format with content array
  if (data.content && Array.isArray(data.content)) {
    // Look for text field first (standard Anthropic)
    for (const item of data.content) {
      if (item.text) {
        return item.text;
      }
    }
    // If no text, check for thinking field (MiniMax extended thinking)
    for (const item of data.content) {
      if (item.thinking) {
        // If only thinking is present, use it as the response
        return item.thinking;
      }
    }
    // Try to get any string content
    if (data.content[0] && typeof data.content[0] === 'string') {
      return data.content[0];
    }
  }
  
  // Format 2: OpenAI format
  if (data.choices && data.choices[0] && data.choices[0].message) {
    return data.choices[0].message.content;
  }
  
  // Format 3: Direct text response
  if (data.text) {
    return data.text;
  }
  
  // Format 4: Message format
  if (data.message && typeof data.message === 'string') {
    return data.message;
  }

  // Format 5: Result format
  if (data.result) {
    return typeof data.result === 'string' ? data.result : JSON.stringify(data.result);
  }
  
  // Format 6: Output format
  if (data.output) {
    return typeof data.output === 'string' ? data.output : JSON.stringify(data.output);
  }

  // Log and throw with actual response for debugging
  throw new Error('API 返回格式异常: ' + JSON.stringify(data).substring(0, 300));
}
