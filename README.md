# GenshinImpactCharacterIntelligence

以游戏《原神》(Genshin Impact) 中的人物关系为数据制作的交互式社交网络图。以人物为顶点；若人物 A 的语音中有关于人物 B 的条目，则添加一条 A → B 的边。

本项目基于上游仓库继续开发，上游项目地址：[King-of-Infinite-Space/genshin-social-network](https://github.com/King-of-Infinite-Space/genshin-social-network)。

---

## 布局说明 | About layouts

前端使用 [Cytoscape.js](https://js.cytoscape.org/) 绘制网络图，保留四种布局：

- **星图 / fcose**：[cytoscape.js-fcose](https://github.com/iVis-at-Bilkent/cytoscape.js-fcose) 力导向布局。节点互相排斥，边提供张力，直至平衡。
- **环列 / avsdf**：[cytoscape.js-avsdf](https://github.com/iVis-at-Bilkent/cytoscape.js-avsdf) 圆周布局，尽量减少边交叉。
- **同心 / custom**：同心圆布局。初始状态下连接越多的角色越靠近中心；选中人物后以其为中心，与该人物连接越多的人物越靠近中心。
- **年表 / grid**：按角色实装版本分行展示，便于观察不同版本角色之间的关系。

## 页面功能 | What the page does

- 四种排布：星图、同心、环列、年表。
- 节点按元素着色，连线按目标角色的元素着色，粗细表示语音证言条数。
- 点选角色打开档案：元素、武器、星级、所属、称号、生日、命之座、四国 CV。
- 再点选另一名角色进入「对坐」视图，按「互相提到 / 仅一方提到」展示原文，并支持连播两人对话。
- 角色语音支持中 / 日 / 英 / 韩四国配音，来源可在 **HoYoLab 官方 wiki** 与 **B 站 wiki** 之间切换；缺源会自动回落并标注。
- 检索支持中文名、英文名、别称和称号；`/` 聚焦搜索框，`Esc` 逐级退出。
- 筛选支持元素 / 武器 / 地区 / 星级多选，统计与 Top 榜随之更新。
- 「关系链」可查询两名角色之间的最短关系链。
- 深链：`?a=<英文 slug>&b=<英文 slug>&layout=grid&tab=voice` 可直接分享。
- 移动端使用底部的档案抽屉和左侧滑出索引；桌面端使用侧栏档案和左侧索引。
- 已按编辑式档案馆风格重写视觉与界面结构，并保留四布局、检索、筛选、语音、对坐、关系链等原有功能。

## 探索图谱 | Explore the graph

浏览器控制台中可通过 `window.__app` 访问应用状态与图谱控制器：

```js
window.__app.state      // 当前应用状态
window.__app.cy         // Cytoscape.js 图谱实例
window.__app.selectPerson(person)
window.__app.applyLayout("grid")
```

## 数据更新 | Updating the data

数据由 `utils/fetch_data.py` 生成。当前数据源：

| 用途 | 端点 |
| --- | --- |
| 角色清单、官方头像 | `https://act-api-takumi-static.mihoyo.com/content_v2_user/app/16471662a82d418a/getContentList?iAppId=43&iChanId=726&iPageSize=200&iPage=1&sLangKey=zh-cn` |
| 语音台词、角色节点 | `https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/main/` |

本地运行示例：

```bat
set REF_VER=7.2.1
set REF_DATE=2026-11-04
set PERIOD=21
python utils/fetch_data.py --refresh
```

常用参数：

- `--dry-run`：只报告差异，不写盘。
- `--offline`：只使用 `data_raw/` 缓存。
- `--source hoyolab`：使用官方 wiki 语音页作为备用源。
- `--strict-released`：丢弃不在官方清单中的角色。
- `--no-images` / `--no-notion` / `--replace-lines`：按需要跳过或替换对应步骤。

每次写盘前会自动备份到 `local/backup/<时间戳>/`，且只有校验通过才会覆盖 `data/`。

CI：

- `.github/workflows/update.yml`：手动触发数据更新并自动提交。
- `.github/workflows/deployGhPage.yml`：`data/**` 或 `page/**` 变更时构建并发布 GitHub Pages。

前端不依赖任何第三方 CDN：图谱库位于 `page/vendor/`，数据与头像位于 `data/`，部署时一起打包进 Pages artifact。

## 数据文件 | Data files

- `data/char_data.json` / `data/char_data_min.json`：图谱本体，包含角色和 `lines` 证言。
- `data/profile.json`：档案字段，包括元素、武器、星级、地区、生日、命之座、称号、所属、四国 CV、实装版本。
- `data/voice/<角色>.json`：角色全部语音条目，每条含 `title/text` 与按来源分组的音频 URL；`line` 指回图谱边。

音频不下载进仓库，直接引用官方 CDN：

| 来源 | 音频 | 说明 |
| --- | --- | --- |
| HoYoLab 官方 wiki | `upload-static.hoyoverse.com` / `act-webstatic.hoyoverse.com` 的 mp3/wav | 四国语齐全，由 `utils/build_voice_data.py` 生成 |
| B 站 wiki（biligame） | `patchwiki.biligame.com` 的 ogg | 体积更小，由 `utils/biligame_voice.py` 合并 |

两个脚本都可重复运行，分别缓存 `data_raw/hoyolab/` 与 `data_raw/biligame/`。

## 贡献者与上游仓库 | Contributors and upstream

本仓库基于上游项目继续开发：

- 上游仓库：[King-of-Infinite-Space/genshin-social-network](https://github.com/King-of-Infinite-Space/genshin-social-network)
- 上游贡献者：
  - [King-of-Infinite-Space](https://github.com/King-of-Infinite-Space) — 上游项目作者，贡献 141 次提交。
  - [github-actions[bot]](https://github.com/apps/github-actions) — 上游数据更新与 Pages 自动化，贡献 45 次提交。

上游贡献者数据来自 GitHub Contributors API：`https://api.github.com/repos/King-of-Infinite-Space/genshin-social-network/contributors`。

### 来自上游仓库的文件与代码

按当前工作区与上游仓库 `d859abd` 的文件哈希逐项比对，当前仓库中 **127 个文件与上游完全一致**，主要包括：

- 数据文件：`data/char_data.json`、`data/char_data_min.json`、`data/alias.json`；
- 官方头像：`data/image/**`，共 122 个图片文件；
- 项目基础文件：`LICENSE.md`、`.gitattributes`。

此外，以下文件虽经修改，但保留或沿用了上游逻辑：

- `utils/fetch_data.py`、`utils/download_images.py`、`utils/notion_db.py`、`utils/prepare_data.py`；
- `.github/workflows/update.yml`、`.github/workflows/deployGhPage.yml`；
- `page/index.html` 中原有的数据模型、布局与交互语义。

本仓库新增或重写的主要部分：

- `page/css/**`、`page/js/**`、`page/icon.svg`、`page/vendor/icons.svg`：编辑式档案馆风格的重写前端；
- `data/profile.json`、`data/voice/**`、`utils/biligame_voice.py`、`utils/build_voice_data.py`、`utils/hoyolab_source.py`：当前分支中的档案、语音与多来源语音构建数据；
- `page/vendor/` 下的 Cytoscape.js 及布局插件文件保留在本仓库中以便静态部署。

## 版权声明 | Copyright disclaimer

本项目仅用于演示和研究目的。游戏内容版权归 miHoYo 所有。This project is for demonstration and research purposes only. Game content copyright belongs to miHoYo.

## 类似项目 | Similar projects

- [CaoMeiYouRen/genshin-relation-graph](https://github.com/CaoMeiYouRen/genshin-relation-graph)
- [Dimbreath/GenshinData](https://github.com/Dimbreath/GenshinData)
- [uzair-ashraf/genshin-impact-wish-simulator](https://github.com/uzair-ashraf/genshin-impact-wish-simulator)
- [GenshinMap/genshinmap.github.io](https://github.com/GenshinMap/genshinmap.github.io)
