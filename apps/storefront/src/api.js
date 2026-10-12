export async function api(path, options = {}) {
  const token = sessionStorage.getItem('zhifu-token')
  const response = await fetch('/api' + path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}), ...options.headers } })
  const payload = await response.json().catch(() => ({ detail: '服务响应异常' }))
  if (!response.ok) {
    if (response.status === 401) sessionStorage.removeItem('zhifu-token')
    throw new Error(payload.detail || payload.message || '请求失败，请稍后再试')
  }
  return payload.data
}
export const post = (path, body, headers = {}) => api(path, { method: 'POST', body: JSON.stringify(body), headers })
export const money = amount => Number(amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
