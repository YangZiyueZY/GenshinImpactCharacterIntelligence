**[king-of-infinite-space.github.io/genshin-social-network](https://king-of-infinite-space.github.io/genshin-social-network/)**

---

以游戏《原神》(Genshin Impact)中的人物为例制作的社交网络图。以人物为顶点，若人物A语音中有关于人物B的条目，添加A→B的边。\
A social network graph of Genshin characters. Each node is a character and each edge from A to B is a voice line of character A about character B.

#### 布局说明 | About layouts

本项目使用[Cytoscape.js](https://js.cytoscape.org/)生成网络图。采用了以下布局。\
This project uses __ to generate network graph. The following layouts are used.

- [fcose](https://github.com/iVis-at-Bilkent/cytoscape.js-fcose)：基于力导向算法。（进行力学模拟，顶点互相排斥，边提供张力，直至平衡。）Based on force-directed layout. Nodes repel each other and edges pull them together. The forces are simulated until equilibrium is reached.

- [avsdf](https://github.com/iVis-at-Bilkent/cytoscape.js-avsdf)：在圆周上排列顶点，使得边的交叉尽可能少。The nodes are distributed along a circle such that the crossing of edges is minimized.

- custom：同心圆布局。初始状态下边越多的顶点越靠近中心。选中人物后以其为中心，与之连接越多的人物越靠近中心。A concentric layout. Initially, nodes with more edges are closer to the center. When a character is selected, it moves to the center and nodes with more edges with it are closer.

#### 探索此图 | Explore the graph

`cy` 变量是Cytoscape.js图的对象。`stats`变量包含了每个节点的统计数字。可在控制台进行探索。\
`cy` is the variable for Cytoscape.js graph object. `stats` includes some statistics of nodes. Feel free to explore them in the console.


#### 数据更新 | Updating the data

数据由 `utils/fetch_data.py` 生成。两个数据源在 2026-11 实测可用（旧接口 `ys.mihoyo.com/content/ysCn/getContentList` 已返回 `retcode -1`，Dimbreath 的 datamined 仓库已消失/被 DMCA 下架）：

| 用途 | 端点 |
| --- | --- |
| 角色清单、官方头像（`iTotal` / `sTitle` / `sExt`） | `https://act-api-takumi-static.mihoyo.com/content_v2_user/app/16471662a82d418a/getContentList?iAppId=43&iChanId=726&iPageSize=200&iPage=1&sLangKey=zh-cn` |
| 语音台词、角色节点（`ExcelBinOutput` + `TextMap`） | `https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/main/` |

两个地址都作为缺省值写在代码里（可用环境变量 `URL_ZH` / `DATA_REPO_URL` 覆盖）。

本地运行：

```bat
set REF_VER=7.2.1
set REF_DATE=2026-11-04
set PERIOD=21
python utils/fetch_data.py --refresh
```

常用参数：`--dry-run` 只报告不写盘；`--offline` 不联网（只用 `data_raw/` 缓存）；`--source hoyolab` 改用官方 wiki 的语音页（双语语音的备用源）；`--strict-released` 丢弃不在官方清单里的角色（旧行为）；`--no-images` / `--no-notion` / `--replace-lines`。每次写盘前自动备份到 `local/backup/<时间戳>/`，且**只有校验通过才会覆盖** `data/`。

CI：`.github/workflows/update.yml` 手动触发，跑完自动 commit + push；`data/**` 与 `page/**` 的变更都会触发 `deployGhPage.yml` 重新发布 Pages。

前端不依赖任何第三方 CDN：页面库都在 `page/vendor/`，数据与头像在 `data/`，部署时一起打包进 Pages artifact。

#### 页面功能 | What the page does

- **星图 / 同心 / 环列 / 年表** 四种排布；节点按元素着色，连线按目标角色的元素着色，粗细表示证言条数。
- **点选角色** 打开档案卡：元素、武器、星级、所属、称号、生日、命之座、四国 CV。
- **再点另一个角色** 进入对坐视图：按「互相提到 / 仅一方提到」分组展示原文，可一键连播两人对话。
- **角色语音**：每句台词带中/日/英/韩四国配音，来源可在 **HoYoLab 官方 wiki** 与 **B 站 wiki** 之间切换（数据里有什么源就显示什么源，缺源自动回落并标注）。
- **检索**：支持中文名、英文名、别称（如「木偶」「散兵」）与称号；`/` 聚焦搜索框，`Esc` 逐级退出。
- **筛选**：元素 / 武器 / 地区 / 星级多选，统计与 Top 榜随之更新；「关系链」可查两人之间的最短关系链。
- **深链**：`?a=<英文 slug>&b=...&layout=grid` 可直接分享；移动端为底部抽屉（可下拉收起），桌面/平板为侧栏面板。
- **动效**：统一时长阶梯 90/180/320/450/700ms，入场集中在 2–3 处；`prefers-reduced-motion` 有独立降级方案。

#### 数据文件 | Data files

- `data/char_data.json` / `data/char_data_min.json`：图谱本身（角色、`lines` 证言）。
- `data/profile.json`：档案字段（元素/武器/星级/地区/生日/命之座/称号/所属/四国 CV/实装版本）。
- `data/voice/<角色>.json`：该角色的全部语音条目，每条含 `title/text` 与按来源分组的音频 URL，`line` 指回图谱边。

音频不下载进仓库，直接引用官方 CDN：

| 来源 | 音频 | 说明 |
| --- | --- | --- |
| HoYoLab 官方 wiki | `upload-static.hoyoverse.com` / `act-webstatic.hoyoverse.com` 的 mp3/wav | 四国语齐全，由 `utils/build_voice_data.py` 生成 |
| B 站 wiki（biligame） | `patchwiki.biligame.com` 的 ogg | 体积更小、国内更快，由 `utils/biligame_voice.py` 合并 |

两个脚本都可重复运行（分别缓存 `data_raw/hoyolab/`、`data_raw/biligame/`）。米游社观测枢的详情接口需要应用签名（返回 `retcode -2010`），故未接入。


#### 版权声明 | Copyright disclaimer

本项目仅用于演示和研究目的。游戏内容版权归mihoyo所有。\
This project is for demonstration and research purpose only. Copyright holder of game data is mihoyo.

---

##### 作者声明 | Personal notice
本人并非该游戏玩家，只是“云玩家”。抵制氪金游戏从我做起。\
I don't even play this game (only read and watch the stories). I'm against gacha games.

##### 类似项目 | Similar project
[CaoMeiYouRen/genshin-relation-graph: 原神人物关系图](https://github.com/CaoMeiYouRen/genshin-relation-graph)

##### 原神相关百科网站 | Genshin wikis
[原神WIKI_玩家共建原神百科-BWIKI_哔哩哔哩](https://wiki.biligame.com/ys/%E9%A6%96%E9%A1%B5)\
[旅行者创作平台-观测枢-原神wiki-米游社](https://bbs.mihoyo.com/ys/obc/)\
[原神 - 萌娘百科 万物皆可萌的百科全书](https://zh.moegirl.org.cn/%E5%8E%9F%E7%A5%9E)\
[Genshin Impact Wiki | Fandom](https://genshin-impact.fandom.com/wiki/Genshin_Impact_Wiki)\
[Honey Impact | Honey Impact - Genshin Impact DB and Tools](https://genshin.honeyhunterworld.com/) (multi-language | 多语言)\
[Genshin DB - Genshin Impact Database](https://genshindb.org/)\
[Genshin Impact Characters List - Genshin.gg Wiki Database](https://genshin.gg/)

##### Github上的其他原神相关项目（仅供参考） | Other Genshin related projects on Github (for reference only)
[Dimbreath/GenshinData: Repository containing the game data for the game Genshin Impact.](https://github.com/Dimbreath/GenshinData)\
[uzair-ashraf/genshin-impact-wish-simulator: A React web application to simulate Genshin Impact gacha in the browser](https://github.com/uzair-ashraf/genshin-impact-wish-simulator)\
[GenshinMap/genshinmap.github.io: A flexible, community-driven interactive map for Genshin Impact.](https://github.com/GenshinMap/genshinmap.github.io)

<img src='https://count.lnfinite.space/repo/genshin-social-network.svg?plus=1' width='0' height='0' />