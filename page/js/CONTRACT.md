# 契约 v1 — Editorial Archive 重写

风格 A 编辑式档案馆：暖白纸面 #F2ECE0，墨色文字，朱印红 #A63E2E 唯一强调，深青 #2B4A52 第二数据色。
约束：无 CDN、无构建、无新依赖；纯静态 HTML + CSS + ES module JS，系统字体栈，本地 SVG sprite。
guide 管审美禁色禁字；system 管 8pt/44px/焦点/状态/动效曲线。禁紫/靛/品红装饰（元素语义色雷例外只用于数据编码）；禁 Inter/Roboto/Arial/system-ui/-apple-system；禁 emoji 图标。
性能：无动画光晕/星空/逐节点阴影、无 backdrop-filter 覆盖画布；只 transform/opacity 动效；桌面 dpr<=1.5，手机 dpr<=1.25；年表行标 DOM 只建一次仅 transform。

## 文件写域（严格遵守）
- lead: page/index.html, page/js/app.js, page/js/data.js, page/js/dom.js, page/vendor/icons.svg, page/icon.svg
- shell-ux: page/css/tokens.css, page/css/shell.css, page/js/index-panel.js
- plate-graph: page/js/graph.js, page/css/plate.css
- dossier-player: page/js/dossier.js, page/js/player.js, page/css/dossier.css
- verify: local/verify/** 不改 page/**
- review: 只读 + local/verify/review-*.md

## HTML 约定（lead 交付）
#app 根。Masthead: .masthead 含 .brand>.seal-mark, #layoutTabs, #search, #searchResults, #toggleIndex, #resetView, #langToggle。
左索引: #indexRail 含 #filterElement/#filterWeapon/#filterRegion/#filterRarity, #statNodes/#statEdges/#statAvg/#topMentioned, #pathHint/#pathClear, #randomPair, [data-filter-group]=element|weapon|region|rarity。
图版: #stage 含 #plateHeader(#plateTitle,#plateSub), #cy, #legend, #pathbar, #quoteCard, #hint, #zoomControls, #toast, #mobileLayoutSwitch, #fabIndex。
档案: #dossier 含 #dossierGrip,#dossierClose,#dossierBody。播放器: #player 含 #playerBody。启动遮罩 #boot。
body 状态类: index-hidden, index-open, dossier-open, show-en。
图标: <svg class="ico"><use href="vendor/icons.svg#id"></use></svg>。id: search filter reset sliders play pause close chevron link shuffle zoom-in zoom-out globe info audio check。

## JS 模块契约（ES module）
### data.js (lead)
导出 ELEMENT_COLOR, ELEMENT_LABEL, LANG_LABEL, SOURCE_LABEL, LAYOUTS, KEY, state, loadAll(), loadVoice(p), elColor(el), fmt(n), personMatches(p,term), aliasesOf(p), slugForName(term), activeFilters(), passesFilters(p), setFilter(group,val,on), toggleFilter(group,val), clearFilters(), filterSummary(), saveUi(), loadUi(), updateUrl(), readUrl()。
state: base,chars,profile,aliases,people(Map by en),byZh(Map),slugTo(Map),edges(Map from|to ->{from,to,lines}),outMap,inMap,voice,selected([person]),path,filters{element,Set...},layout,drawerTab,lang,source,showEn,audio{item,lang,source,autoplay}。
person: id,zh,en,slug,img,bg,ver,element,weapon,region,rarity,title,affiliation,birthday,constellation,release,cv{zh,ja,en,ko},lines,outTotal,inTotal。

### dom.js (lead)
导出 $(sel,root?), $$(sel,root?), el(tag,cls?,text?), icon(id,cls?) 生成 svg use, toast(msg,ms?)。

### index-panel.js (shell-ux)
导出 initIndexPanel(ctx)；ctx={state,data,dom,graph,dossier,player}。
职责：渲染 4 组筛选 chips（aria-pressed；手机 >=44px）；统计数字+Top5；搜索下拉（上下键/Enter/Esc，/ 聚焦）；绑定 #layoutTabs 与 #mobileLayoutSwitch → graph.applyLayout(name)；#resetView → graph.resetView()；#toggleIndex/#fabIndex 开合索引；#randomPair → dossier.showRandomPair()；#langToggle → dossier.setShowEn()；筛选变更 → graph.applyFilters()+data.saveUi+updateUrl。四布局文案星图/同心/环列/年表 = fcose/concentric/avsdf/grid；active 同步 aria-selected。

### graph.js (plate-graph)
导出 initGraph(ctx) 返回 {cy,build,applyLayout(name,animate?),applyFilters,resetView,fitGraph,focusPerson(p),highlightSelection,showPath(nodes),clearPath,setViewportToIds(ids,padding),showEdgeCard(edge,pos,pinned),hideEdgeCard}。
职责：cytoscape 初始化（vendor 全局 cytoscape），按 state 构造节点/边；纸底圆章、1px 墨线圆框、无 shadow、元素色细描边；连线低透明细线按目标元素色，粗细=条数。四布局算法沿用旧 app.js（备份 local/backup/20261122-110449-pre-rewrite/app.js）。图例/路径条/引用卡/图版标题/年表行标/缩放控件。node tap → dossier.selectPerson(p); edge hover/tap → quote card; 空白 tap → dossier.clearSelection()。性能：pixelRatio<=1.5/1.25，年表行标 DOM 复用+仅 transform，shadow-blur=0。

### dossier.js (dossier-player)
导出 initDossier(ctx) 返回 {selectPerson(p),clearSelection,open,close,render,showRandomPair,setShowEn,showEdgeQuote(from,to,lines),markPlaying}。
职责：档案 DOM 生成进 #dossierBody（不改 index.html）；三页签 voice/mentions/mentioned；徽标/台账/CV；语音列表、语种/来源切换、播放按钮 → player.play(item,lang,source,queue)；双人对比（对坐，互提/单提分组，连播）；手机 #dossierGrip 拖拽关闭；调用 graph.highlightSelection() 与 data.updateUrl()。

### player.js (dossier-player)
导出 initPlayer(ctx) 返回 {play(item,lang,source,queue),toggle,stop,seek(ratio)}。
职责：<audio id="audio"> 生成进 #playerBody；进度条可点/键盘 slider(role=slider, aria values)；播放/暂停/关闭；队列自动下一首；调用 dossier.markPlaying()。

### app.js (lead)
主控：import * as data from './data.js' 等；加载数据→预载头像→initGraph→initDossier→initPlayer→initIndexPanel→启动事件(Esc/resize/orientationchange)→读 URL/深链→应用初始布局→window.__app={state,cy:graph.cy,...controllers}→移除 boot。

## CSS 职责（link 顺序固定）
1. css/tokens.css (shell-ux)：variables/reset/body grid/focus-visible
2. css/shell.css (shell-ux)：masthead/indexRail/search/chips/统计/pathbar 壳/响应式
3. css/plate.css (plate-graph)：stage/图版标题/网格/角标/legend/zoom/hint/quoteCard/row-label
4. css/dossier.css (dossier-player)：dossier/档案内容/对坐/player/boot/sheet

## 验收
禁色/禁字/emoji grep；手机 390px 可点高度>=44px 无横向溢出；平移帧率>=52fps（基线54.1）；深链 ?a=&b=&layout=&tab= 与 localStorage KEY 'genshin-relations-ui' 不变。
