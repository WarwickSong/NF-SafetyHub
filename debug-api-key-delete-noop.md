# Debug Session: api-key-delete-noop

Status: [RESOLVED]

## Symptom
管理员页面中吊销 API key 后尝试删除，页面没有反应；重新加载后待删除 key 仍存在。非内网环境删除成功，内网部署下失败；此前 APIKey 编辑也出现过类似通信问题。

## Initial Evidence
Nginx 日志仅显示：
- GET /admin/api_keys.html 304
- GET /admin/api/api-keys 200

未观察到 DELETE /admin/api/api-keys/... 或其他删除相关请求。

## Hypotheses
1. 内网反代/安全网关对 DELETE 等非 POST 方法不兼容，导致删除请求没有到达后端。
2. 前端删除按钮事件未进入请求分支。
3. 前端发起了错误 URL 或 method。
4. 浏览器端 JavaScript 抛错中断删除流程。
5. 浏览器或反代缓存导致旧脚本继续运行。

## Evidence
- 后端原有 DELETE /admin/api/api-keys/{api_key_id} 在本地测试中可以成功删除 revoked key。
- 用户确认非内网环境可删除，内网环境删除后刷新仍存在，说明后端删除逻辑本身不是根因。
- 用户提供的内网 nginx 日志没有 DELETE 请求，说明请求在浏览器到后端之间未按预期抵达。
- 交付说明中已有类似记录：内网管理后台执行 PATCH/POST 时曾因通信/访问方式导致页面停在保存状态。

## Root Cause
内网部署链路对管理后台的非 POST 写操作兼容性不足，DELETE 删除请求未可靠到达 SafetyHub 后端。页面原先缺少删除中的反馈，会让该问题表现为“点击后没有反应”。

## Fix
- 保留原 DELETE /admin/api/api-keys/{api_key_id} 接口，兼容已有调用。
- 新增 POST /admin/api/api-keys/{api_key_id}/delete 兼容端点，复用同一删除服务逻辑，仍只允许删除 revoked key。
- 前端删除改为调用 POST /delete 端点，绕过内网链路对 DELETE 方法的限制。
- 前端删除按钮增加防重复点击、删除中提示、失败提示与按钮恢复。
- 管理后台静态文件增加缓存控制，HTML no-store，JS/CSS no-cache + must-revalidate，避免部署后旧脚本干扰验证。

## Verification
- python -m pytest tests/test_api_keys.py tests/test_admin_auth.py::test_admin_static_assets_include_cache_control_headers tests/test_admin_auth.py::test_admin_login_assets_are_public tests/test_admin_auth.py::test_admin_static_page_allows_valid_basic_auth -q：17 passed。
- VS Code diagnostics：admin/router.py、main.py、middleware/auth.py、admin/static/js/app.js、admin/static/api_keys.html 均无诊断错误。
