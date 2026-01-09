import React, { useState, useEffect } from 'react';

const OptionsApp: React.FC = () => {
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.minimaxi.com/anthropic');
  const [model, setModel] = useState('MiniMax-M2');
  const [targetLang, setTargetLang] = useState('中文');
  const [status, setStatus] = useState<{ type: 'success' | 'error' | 'idle', message: string }>({ type: 'idle', message: '' });

  useEffect(() => {
    chrome.storage.local.get(['anthropicApiKey', 'anthropicBaseUrl', 'anthropicModel', 'targetLanguage'], (result) => {
      if (result.anthropicApiKey) setApiKey(result.anthropicApiKey as string);
      if (result.anthropicBaseUrl) setBaseUrl(result.anthropicBaseUrl as string);
      if (result.anthropicModel) setModel(result.anthropicModel as string);
      if (result.targetLanguage) setTargetLang(result.targetLanguage as string);
    });
  }, []);

  const handleSave = () => {
    chrome.storage.local.set({
      anthropicApiKey: apiKey,
      anthropicBaseUrl: baseUrl,
      anthropicModel: model,
      targetLanguage: targetLang
    }, () => {
      setStatus({ type: 'success', message: '✓ 配置已保存' });
      setTimeout(() => setStatus({ type: 'idle', message: '' }), 3000);
    });
  };

  // Styles
  const containerStyle: React.CSSProperties = {
    minHeight: '100vh',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    padding: '40px 20px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  };

  const cardStyle: React.CSSProperties = {
    maxWidth: 560,
    margin: '0 auto',
    backgroundColor: '#fff',
    borderRadius: 24,
    boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
    overflow: 'hidden',
  };

  const headerStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
    padding: '32px 32px 28px',
    color: '#fff',
  };

  const logoStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    marginBottom: 8,
  };

  const iconStyle: React.CSSProperties = {
    width: 56,
    height: 56,
    background: 'linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%)',
    borderRadius: 16,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 24,
    boxShadow: '0 8px 16px rgba(236,72,153,0.3)',
  };

  const titleStyle: React.CSSProperties = {
    fontSize: 28,
    fontWeight: 700,
    margin: 0,
  };

  const subtitleStyle: React.CSSProperties = {
    fontSize: 14,
    opacity: 0.8,
    marginTop: 4,
  };

  const formStyle: React.CSSProperties = {
    padding: 32,
  };

  const sectionStyle: React.CSSProperties = {
    marginBottom: 28,
  };

  const sectionTitleStyle: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 600,
    color: '#6b7280',
    textTransform: 'uppercase' as const,
    letterSpacing: 1,
    marginBottom: 16,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 14,
    fontWeight: 500,
    color: '#374151',
    marginBottom: 8,
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '14px 16px',
    fontSize: 15,
    border: '2px solid #e5e7eb',
    borderRadius: 12,
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
    backgroundColor: '#f9fafb',
    boxSizing: 'border-box' as const,
  };

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    cursor: 'pointer',
    appearance: 'none' as const,
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 12px center',
    backgroundSize: 20,
    paddingRight: 44,
  };

  const hintStyle: React.CSSProperties = {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 6,
  };

  const rowStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 16,
  };

  const buttonStyle: React.CSSProperties = {
    width: '100%',
    padding: '16px 24px',
    fontSize: 16,
    fontWeight: 600,
    color: '#fff',
    background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)',
    border: 'none',
    borderRadius: 12,
    cursor: 'pointer',
    transition: 'transform 0.15s, box-shadow 0.15s',
    boxShadow: '0 4px 14px rgba(59,130,246,0.4)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  };

  const statusStyle: React.CSSProperties = {
    textAlign: 'center' as const,
    padding: '12px 16px',
    borderRadius: 10,
    fontSize: 14,
    fontWeight: 500,
    marginTop: 16,
    backgroundColor: status.type === 'success' ? '#dcfce7' : status.type === 'error' ? '#fee2e2' : 'transparent',
    color: status.type === 'success' ? '#166534' : status.type === 'error' ? '#dc2626' : 'transparent',
  };

  const infoCardStyle: React.CSSProperties = {
    backgroundColor: '#f0f9ff',
    borderRadius: 12,
    padding: 20,
    marginTop: 24,
    border: '1px solid #bae6fd',
  };

  const infoTitleStyle: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 600,
    color: '#0369a1',
    marginBottom: 12,
  };

  const infoListStyle: React.CSSProperties = {
    margin: 0,
    paddingLeft: 20,
    fontSize: 13,
    color: '#0c4a6e',
    lineHeight: 1.8,
  };

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        <div style={headerStyle}>
          <div style={logoStyle}>
            <div style={iconStyle}>✨</div>
            <div>
              <h1 style={titleStyle}>AI Selection Search</h1>
              <p style={subtitleStyle}>划词即解释 · 智能上下文分析</p>
            </div>
          </div>
        </div>

        <div style={formStyle}>
          {/* API Section */}
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>
              <span>🔑</span> API 配置
            </div>
            
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>API 密钥</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                style={inputStyle}
                onFocus={(e) => {
                  e.target.style.borderColor = '#3b82f6';
                  e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.1)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = '#e5e7eb';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>

            <div>
              <label style={labelStyle}>接口地址 (Base URL)</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                style={inputStyle}
                onFocus={(e) => {
                  e.target.style.borderColor = '#3b82f6';
                  e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.1)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = '#e5e7eb';
                  e.target.style.boxShadow = 'none';
                }}
              />
              <p style={hintStyle}>默认: https://api.minimaxi.com/anthropic</p>
            </div>
          </div>

          {/* Model Section */}
          <div style={sectionStyle}>
            <div style={sectionTitleStyle}>
              <span>🤖</span> 模型设置
            </div>
            
            <div style={rowStyle}>
              <div>
                <label style={labelStyle}>模型标识</label>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  style={inputStyle}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#3b82f6';
                    e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '#e5e7eb';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>

              <div>
                <label style={labelStyle}>输出语言</label>
                <select
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                  style={selectStyle}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#3b82f6';
                    e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '#e5e7eb';
                    e.target.style.boxShadow = 'none';
                  }}
                >
                  <option value="中文">🇨🇳 中文</option>
                  <option value="English">🇺🇸 English</option>
                  <option value="日本語">🇯🇵 日本語</option>
                  <option value="한국어">🇰🇷 한국어</option>
                </select>
              </div>
            </div>
          </div>

          {/* Save Button */}
          <button 
            style={buttonStyle}
            onClick={handleSave}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 6px 20px rgba(59,130,246,0.5)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 14px rgba(59,130,246,0.4)';
            }}
          >
            <span>💾</span> 保存配置
          </button>

          {status.type !== 'idle' && (
            <div style={statusStyle}>{status.message}</div>
          )}

          {/* Info Card */}
          <div style={infoCardStyle}>
            <div style={infoTitleStyle}>📖 使用指南</div>
            <ul style={infoListStyle}>
              <li>在网页上划选任意文字</li>
              <li>悬停在出现的红色小圆点上</li>
              <li>AI 将自动分析上下文并给出解释</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OptionsApp;
