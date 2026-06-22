# -*- coding: utf-8 -*-
"""Swagger UI shell for curated OpenAPI spec."""

API_DOCS_PAGE = """
<div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
  <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/50">
    <h2 class="text-lg font-semibold text-gray-800">API 文档</h2>
    <p class="text-xs text-gray-500 mt-1">Release、Bootstrap、Ops 与 GM 核心路径（<code>/openapi.json</code>）。</p>
  </div>
  <div id="swagger-ui" class="min-h-[70vh]"></div>
</div>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
window.addEventListener('DOMContentLoaded', function () {
  SwaggerUIBundle({
    url: '/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [SwaggerUIBundle.presets.apis],
    layout: 'BaseLayout'
  });
});
</script>
"""


def render_api_docs_page() -> str:
    return API_DOCS_PAGE
