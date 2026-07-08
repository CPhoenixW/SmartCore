from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["work-device"])

_DEVICE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SmartCore Work - 设备</title>
<link rel="stylesheet" href="/static/work/work_v2.css">
<link rel="stylesheet" href="/static/work/work_add_inspire.css">
</head>
<body data-page="device">
<div class="work-layout">
  <aside class="work-sidebar">
    <a class="brand" href="/work" aria-label="SmartCore Work">
      <span class="brand-mark">SC</span>
      <span><strong>SmartCore</strong><small>学生智能助手</small></span>
    </a>
    <nav class="work-nav" aria-label="工作台导航">
      <a class="nav-link" href="/work"><span class="nav-ico">⌂</span>总览</a>
      <a class="nav-link" href="/work/add"><span class="nav-ico">+</span>添加事件</a>
      <a class="nav-link" href="/work/update"><span class="nav-ico">✎</span>更新事件</a>
      <a class="nav-link" href="/work/inspire"><span class="nav-ico">◇</span>灵感</a>
      <a class="nav-link" href="/work/course"><span class="nav-ico">□</span>课表</a>
      <a class="nav-link" href="/work/log"><span class="nav-ico">≡</span>日志</a>
      <a class="nav-link active" href="/work/device"><span class="nav-ico">◉</span>设备</a>
      <a class="nav-link" href="/work/settings"><span class="nav-ico">⚙</span>设置</a>
    </nav>
  </aside>
  <section class="work-content">
    <header class="topbar">
      <label class="top-search"><span>⌕</span><input id="deviceLogSearch" placeholder="搜索人物、状态、模型信息..." autocomplete="off"></label>
      <div class="topbar-actions">
        <span class="status-pill" id="apiStatus">API 待命</span>
        <span class="top-muted" id="lastRefresh">未刷新</span>
        <a class="top-avatar" id="topUserLink" href="/work/settings" aria-label="用户设置">
          <img id="topAvatarImg" alt="" hidden>
          <span id="topAvatarText">SC</span>
        </a>
      </div>
    </header>
    <main class="page-main">
      <section class="page-head">
        <div><h1>设备</h1><p>查看树莓派状态、识别日志并异步请求当前摄像头画面</p></div>
      </section>
      <section class="content-grid two-one device-grid">
        <div class="stack">
          <article class="card">
            <header><h2>树莓派当前状态</h2><button class="btn" id="refreshDeviceBtn" type="button">刷新</button></header>
            <div class="card-body">
              <div class="device-status-main">
                <span class="device-state-dot" id="deviceStateDot"></span>
                <div><div class="device-state-title" id="deviceStateTitle">等待状态</div><div class="row-meta" id="deviceStateSeen">—</div></div>
              </div>
              <div class="device-kv-grid device-kv-large">
                <div><span>是否有人</span><strong id="devicePresent">—</strong></div>
                <div><span>识别人物</span><strong id="devicePersons">—</strong></div>
                <div><span>状态置信度</span><strong id="deviceConfidence">—</strong></div>
                <div><span>时钟偏差</span><strong id="deviceClockSkew">—</strong></div>
                <div><span>识别模型</span><strong id="deviceModel">—</strong></div>
                <div><span>摄像头</span><strong id="deviceCamera">—</strong></div>
              </div>
            </div>
          </article>
          <article class="card">
            <header><h2>树莓派识别日志</h2><span class="top-muted" id="deviceLogCount">0 条</span></header>
            <div class="card-body list device-log-list" id="deviceLogList"></div>
          </article>
        </div>
        <aside class="stack">
          <article class="card camera-card">
            <header><h2>当前摄像头画面</h2><button class="btn btn-primary" id="requestCameraBtn" type="button">请求当前画面</button></header>
            <div class="card-body">
              <div class="camera-frame" id="cameraFrame"><span>尚未请求画面</span><img id="cameraImage" alt="树莓派摄像头画面" hidden></div>
              <div class="row-meta" id="cameraRequestMeta">请求会在树莓派下一次心跳时领取</div>
            </div>
          </article>
          <article class="card">
            <header><h2>照片请求记录</h2></header>
            <div class="card-body list" id="photoRequestList"></div>
          </article>
        </aside>
      </section>
    </main>
  </section>
</div>
<div class="toast" id="toast"></div>
<script type="module" src="/static/work/work_device.js"></script>
</body>
</html>"""


@router.get("/work/device", response_class=HTMLResponse)
def work_device() -> str:
    return _DEVICE_HTML
