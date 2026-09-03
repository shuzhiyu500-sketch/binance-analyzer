# 线上男装针织热销选品雷达 V1

**状态：** 方案与数据契约（尚未启动大规模采集）。  
**目标：** 每日或定时从 1–2 个已授权、可复现的数据源发现「男装羊毛衫／针织衫」中正在热销、正在增长且有生产研究价值的商品，并保存商品主图及其来源证据。

## 1. 边界与原则

### 本期交付边界

V1 交付一个可审计的选品池，而不是 ERP、生产管理系统或全网爬虫。范围只包括：

1. 数据源可行性调查与准入门槛；
2. 商品、图片、特征、快照和评分的数据模型；
3. 可解释的热销／增长／竞争／机会评分；
4. 一个最多两源、少量关键词、低频运行的最小采集方案；
5. 对每一条数据保留来源、采集时点和字段出处。

### 合规红线

- 只访问无需绕过限制即可获得的数据，或使用已获账号授权的官方／合作伙伴 API。
- **不**规避验证码、登录、风控、访问控制、robots 限制、签名机制或反爬；出现任何一项即停止该适配器并记录 `ACCESS_RESTRICTED`。
- 不伪造商品链接或图片链接；图片不可取得时写入 `IMAGE_UNAVAILABLE`，而不是补图。
- 本文的「可行」不等于已经获准自动抓取。上线前必须由负责人保存对应渠道的授权证明、开发者条款链接和一次字段验收结果。
- 不把搜索结果摘要或模型推断冒充平台事实。所有推断均带 `INFERENCE` 标签和模型版本。

## 2. 数据源侦察与评分

### 评分方法

每项 1–5 分，权重为：合规可持续性 30%、商品和图片完整性 25%、热度／增长信号 20%、链接可复核性 15%、工程稳定性 10%。总分 = 加权分 × 20。访问稳定性与字段可得性必须通过一次真实、小样本、获授权的验收后才可从「待验」改为实测。

| 候选渠道 | 登录／验证码／动态渲染风险 | 公开或授权可得字段 | 图片与链接 | 热度信号 | 初始分 | 结论 |
| --- | --- | --- | --- | --- | ---: | --- |
| 淘宝／天猫公开页 | 常见登录、风控与动态渲染；不可当作自动抓取入口 | 价格、标题、店铺、部分销量/评价信号需逐字段验收 | 通常可见，但图片 URL 的再利用权限需确认 | 强，但口径不稳定 | 48（仅公开页） | 只作人工侦察；若已获淘宝联盟/开放平台授权，可升级为主源候选 |
| 京东公开页 | 动态渲染与风控风险；不应规避 | 商品页可能展示价格、评价等，须以授权接口返回为准 | 商品与图片通常可定位，须保存原始响应证据 | 评价数相对有价值，销量口径须验证 | 52（仅公开页） | 只作人工侦察；京东联盟／开放平台授权后可升级为主源候选 |
| 拼多多公开页 | 登录、App 导流、动态渲染风险高 | 公开字段及持续访问稳定性待验 | 图片存在不代表可自动下载 | 热度口径待验 | 30 | V1 不接入自动采集 |
| 抖音商品／搜索 | 登录、App、动态内容与访问限制风险高 | 公开可见信号变化快，字段口径待验 | 图片/视频核心但复用和下载权限须确认 | 趋势价值高、交易信号未必公开 | 35 | V1 只做人工趋势观察；不自动抓取 |
| 小红书公开内容 | 登录、内容动态化、反自动化风险高 | 内容互动是内容信号而非成交事实 | 图像价值高，但商品字段较弱 | 可用于灵感，不宜作销量依据 | 28 | V1 不作为商品主数据源 |
| 百度／必应等搜索结果 | 结果页、地区、频率和 API 可用性均需验收 | 标题、落地页、摘要；不是商品事实源 | 可保存结果中原始落地链接，图片不保证 | 适合发现与交叉验证，不适合销量 | 55 | 只作低频「发现源」，不计销量分 |
| **淘宝联盟／淘宝开放平台（已授权）** | 以批准后的 API、配额和字段为准 | 标题、价格、链接、店铺、图片及推广/交易相关字段以接口实际返回为准 | 可保留接口返回的原始图 URL 与授权下载副本 | 需确认是否有可用销量或趋势字段 | **待验收，目标 ≥80** | **推荐主源 A**：前提是书面/API 授权与字段验收通过 |
| **京东联盟／京东开放平台（已授权）** | 以批准后的 API、配额和字段为准 | 价格、推广商品字段、评价等以接口实际返回为准 | 可保留接口返回图 URL 与授权下载副本 | 可用评价历史作辅助增长信号 | **待验收，目标 ≥78** | **推荐主源 B**：与主源 A 同时只保留一个作为第二源 |

### V1 推荐与准入判定

推荐先申请并验收 **一个淘宝生态授权商品接口** 和 **一个京东生态授权商品接口**。二者都能返回可复核商品 URL、标题、价格、店铺标识和至少一张主图时，才进入日常任务；缺少其中任何关键字段的渠道不进主池。若暂未取得授权，V1 仅做人工导入（CSV/JSON）和评分验证，不执行网页自动化。

搜索引擎仅作为辅助发现：用它发现候选链接或关键词，记录 `source_type=SEARCH_DISCOVERY`，但不将摘要中的销量、价格或上架时间写作事实。抖音、小红书可在后续作为「款式灵感」侧池；它们不能替代商品交易主源。

### 上线验收表（每个来源必须填写）

| 检查项 | 通过标准 | 未通过动作 |
| --- | --- | --- |
| 访问许可 | 有可追溯的 API 授权、合同、书面许可或明确适用的公开使用规则 | 不自动访问 |
| 稳定性 | 连续 7 天计划频率内无验证码、登录挑战和 4xx/反爬拦截 | 降为人工源并标记 `ACCESS_RESTRICTED` |
| 商品事实 | 小样本中 ID、标题、价格、URL、店铺和品类均可获得 | 不入主池 |
| 图片 | 至少一张原始主图 URL；仅在许可允许时下载 | 保留 `IMAGE_UNAVAILABLE`，不伪造 |
| 信号口径 | 明确销量、评价或其他信号的名称、单位、时间范围 | 不计算对应分数 |
| 复现 | 保存请求版本、原始响应哈希与采集时间，可复查 | 不进入生产评分 |

## 3. 数据模型

使用 PostgreSQL（也可先用 SQLite）并保留不可变的采集快照。金额统一为 `price_amount` + `currency`，时间一律 UTC ISO 8601；`NULL` 表示未知，绝不以 0 代替未知。

### 3.1 商品主表 `products`

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `product_pk` | UUID | 内部主键 |
| `platform` | text | 枚举：`taobao`、`tmall`、`jd`、`pdd`、`douyin`、`xiaohongshu`、`search`、`other` |
| `platform_product_id` | text | 平台原始商品 ID；与 `platform` 联合唯一 |
| `title` | text | 原始商品标题，保留抓取时版本 |
| `canonical_url` | text | 原始或授权接口给出的商品 URL，禁止拼造 |
| `shop_name` / `platform_shop_id` | text | 原始店铺名称／可得时的店铺 ID |
| `category_path` | json | 平台原始分类路径；不得强行映射 |
| `search_keyword` | text | 发现该商品的关键词 |
| `source_name` / `source_type` | text | 接口/人工导入名称；`AUTHORIZED_API`、`MANUAL_PUBLIC`、`SEARCH_DISCOVERY` |
| `first_seen_at` / `last_seen_at` | timestamptz | 首次／最近观察时点 |
| `record_status` | text | `ACTIVE`、`OFF_SHELF`、`ACCESS_RESTRICTED`、`INVALID` |

### 3.2 不可变观测表 `product_observations`

一件商品每次运行一行，绝不覆盖历史，以计算增长和持续时间。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `observation_id` / `product_pk` / `observed_at` | UUID / UUID / timestamptz | 主键、外键、采集时点 |
| `price_amount` / `currency` | numeric / char(3) | 当次展示价格；区间价另存 `price_max_amount` |
| `sales_signal_value` / `sales_signal_label` | numeric / text | 原始数值和原始标签，例如「已售」「月销」；未知则均为 NULL |
| `sales_signal_window` | text | `CUMULATIVE`、`MONTHLY`、`RECENT`、`UNKNOWN` |
| `review_count` | integer | 原始公开评价数；未知为 NULL |
| `listed_at` | timestamptz | 页面明确给出才写；否则 NULL |
| `raw_payload_uri` / `payload_sha256` | text | 加密存储的响应位置与哈希，便于审计 |
| `field_evidence` | json | 每个字段的来源路径、原文和 `FACT` 标签 |

### 3.3 图片表 `product_images`

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `image_id` / `product_pk` | UUID / UUID | 主键、商品外键 |
| `image_role` / `sort_order` | text / integer | `MAIN`、`DETAIL`、`VARIANT`、`UNKNOWN`；主图优先 |
| `source_image_url` | text | 仅保存实际取得的原始 URL；不可得则 NULL |
| `image_source` | text | 如 `authorized_api`、`public_page_manual` |
| `acquisition_status` | text | `URL_SAVED`、`DOWNLOADED`、`IMAGE_UNAVAILABLE`、`ACCESS_RESTRICTED`、`DOWNLOAD_NOT_PERMITTED` |
| `local_path` / `sha256` | text | 仅许可下载成功后填写；去重用哈希 |
| `content_type` / `width` / `height` | text / integer | 下载成功后校验得到 |
| `retrieved_at` / `failure_reason` | timestamptz / text | 取图时间或明确失败原因 |

图片下载是**可选项**：先存 URL 和来源，只有授权条款允许且普通 HTTP 请求无挑战时才下载；响应不是图片 MIME、重定向到登录/验证码或返回 401/403/429 时立即停止并记录状态。

### 3.4 特征表 `product_attributes`

每个特征单独一行，支持多值与纠错。

| 字段 | 说明 |
| --- | --- |
| `product_pk`、`attribute_name`、`attribute_value` | 特征名和值；名称限于 `gender`、`fit`、`neckline`、`color`、`pattern`、`texture`、`length`、`sleeve`、`thickness`、`style`、`fabric`、`composition` |
| `evidence_type` | 强制为 `FACT` 或 `INFERENCE` |
| `evidence_text` / `evidence_image_id` | `FACT` 存页面原文或字段路径；`INFERENCE` 指向实际分析的图片 |
| `extractor` / `extractor_version` / `confidence` | 人工、规则或模型名称/版本及 0–1 置信度 |
| `created_at` | 生成时间 |

`FACT` 仅用于网页或授权接口明确提供的信息（例如成分、尺码表中的衣长）；视觉模型看到「圆领、宽松、深灰」只能是 `INFERENCE`。模型禁止填写不能从图像可靠判断的成分比例。

### 3.5 选品池 `selection_pool`

这是面向运营的物化结果，不取代原始数据：`product_pk`、`scored_at`、四项分数、`opportunity_stars`、`decision_reason`、`data_completeness`、`score_version`、`review_status` 和 `reviewed_by`。同一商品保留历史评分，运营可追溯「当时为什么推荐」。

## 4. 指标和评分模型

### 4.1 先标准化，再评分

所有比较限制在相同的「平台 × 国家/站点 × 类目 × 关键词组 × 价格带」中，使用当天候选集的百分位数（0–100）。缺失值不当作低值，指标权重重新归一化，并在 `data_completeness` 中扣分。至少有两个不同时点、间隔至少 24 小时的观测才可以计算增长速度。

令 `P(x)` 为同组百分位，`clip(x)=min(100,max(0,x))`。对于累计型信号：

- `sales_velocity = max(0, sales_t - sales_t-1) / elapsed_days`，只在销量窗口口径一致时计算；
- `review_velocity = max(0, reviews_t - reviews_t-1) / elapsed_days`；
- `price_stability = 100 - P(abs(price_t - median_price_7d) / median_price_7d)`；
- `freshness = 100 - P(days_since_listed)`。无上架时间时用 `days_since_first_seen` 作为**弱代理**并标注；
- `persistence = min(100, 100 × active_observation_days / 28)`；
- `similarity_density` 是同一特征簇内的商品数百分位，`merchant_density` 是店铺数百分位。特征簇初期以人工确认的领型/版型/花型/主色组合建立，避免仅凭标题误判「同款」。

### 4.2 四项分数（0–100）

| 分数 | 公式 | 解释 |
| --- | --- | --- |
| `HOT_SCORE` | `0.50×P(sales_signal) + 0.25×P(review_count) + 0.15×P(sales_velocity) + 0.10×persistence` | 当前热度；没有公开销量时不虚构，销量项移除并重归一化 |
| `GROWTH_SCORE` | `0.55×P(sales_velocity) + 0.30×P(review_velocity) + 0.15×freshness` | 增长优先；只有一个快照时为 `NULL`，不输出「增长」判断 |
| `COMPETITION_SCORE` | `0.55×similarity_density + 0.30×merchant_density + 0.15×P(price_discount_depth)` | 越高代表竞争越拥挤；不是好分数 |
| `OPPORTUNITY_SCORE` | `0.35×HOT_SCORE + 0.35×GROWTH_SCORE + 0.15×(100-COMPETITION_SCORE) + 0.10×persistence + 0.05×price_stability`，再乘 `data_completeness/100` | 兼顾热度、增长、竞争、持续性和数据可信度 |

`data_completeness` 初版按：ID/URL/标题/店铺/价格/主图 URL 各 10 分，任一热度信号 15 分，至少两次快照 15 分，上架时间或首次发现时间 10 分。`OPPORTUNITY_SCORE` 若关键字段（ID、URL、价格、主图 URL）任一缺失，直接标为「待补证」，不评级。

### 4.3 星级与风险门槛

| 评级 | 条件 | 运营动作 |
| --- | --- | --- |
| ★★★★★ 值得重点研究 | 机会 ≥80，完整度 ≥80，热度 ≥65，增长非 NULL 且 ≥60，竞争 <70 | 人工看图、拆解版型、再核验面料/成分 |
| ★★★★ 值得观察 | 机会 65–79，完整度 ≥70 | 连续观察 7–14 天 |
| ★★★ 普通 | 机会 45–64，或增长证据不足 | 留在池中，不进入打样 |
| ★★ 不建议跟 | 机会 25–44 或竞争 ≥85 | 仅保留作竞品参考 |
| ★ 高风险 | 机会 <25、来源受限、主图不可用、字段冲突或疑似重复 | 不进入生产决策 |

评分卡必须同时呈现原始数值、观测次数、信号口径和缺失项；星级是筛选优先级，不是销量预测或生产指令。

## 5. 最小可行采集方案

### 5.1 今天开始先做什么

1. **申请/确认一个授权商品 API。** 先选择淘宝生态或京东生态之一，取得测试凭证和明确可保存图片的权限；没有许可就跳到第 2 步，不写网页爬虫。
2. **建立本方案的五张表和导入校验。** 先支持人工 CSV/JSON 导入 50–100 个候选，验证主图、快照、`FACT/INFERENCE` 和评分链路。
3. **固定 8 个种子关键词。** `男士针织衫`、`男士羊毛衫`、`男士毛衣`、`男士半高领针织衫`、`男士圆领针织衫`、`男士翻领针织衫`、`男士开衫`、`男士提花毛衣`。每周人工增删关键词并留版本记录。
4. **只实现一个授权源适配器。** 每日 1 次、每关键词最多 20–50 条、严格低于接口配额；写入原始响应哈希、商品快照、主图 URL。不得使用浏览器自动化规避限制。
5. **连续采样 14 天再开增长分。** 首日只显示当前热度和数据完整度；第 2 天起可显示速度，第 14 天再评估持续性。
6. **人工审核前 20 名。** 人工确认性别和类目、检查图片是否确为商品主图、将视觉结论标记为 `INFERENCE`，再决定是否打样。

### 5.2 运行流程

```text
授权 API / 人工导入
  → 字段映射与授权校验
  → products 去重（platform + platform_product_id）
  → product_observations 追加快照
  → product_images（先 URL，许可时才下载）
  → 事实特征提取 → 视觉/文本推断特征
  → 同款簇与评分 → selection_pool
  → 人工复核 / 导出选品清单
```

### 5.3 适配器最低契约

每个适配器只需实现 `discover(keyword)` 和 `fetch_detail(platform_product_id)`，输出：平台 ID、标题、URL、店铺、价格、类目、可得的销量/评价/上架信号、主图 URL、每个字段证据及采集时点。适配器必须显式返回 `access_status`；遇到登录、验证码、403、429、非预期 HTML 或无法确认权限时返回受限状态，**不得重试绕过**。

### 5.4 V1 验收标准

- 同一商品重复运行不产生新的 `products` 行，但会新增一条 `product_observations`。
- 每条进入主池的商品都有真实的平台 ID、原始 URL、价格和至少一个图片状态；无图商品明确为 `IMAGE_UNAVAILABLE`。
- 每个 `FACT` 都能回到 `field_evidence` 的原文/路径；每个 `INFERENCE` 都有模型版本和置信度。
- 评分可由保存的快照重新计算，且缺失销量或上架时间不会被填充为假数据。
- 任何访问限制事件均可审计，且任务安全结束而非尝试规避。

## 6. 后续，不在 V1 实施

- 第二个已授权平台适配器与跨平台同款合并；
- 小红书/抖音内容趋势作为独立灵感信号（非成交事实）；
- 图片相似度聚类、人工标注集和模型评估；
- 供应链、原料、成本、打样与 ERP。

## 7. 需要负责人确认的决策

开始编码前请确认：优先申请淘宝生态还是京东生态的授权；允许保存原图 URL 的保留期限、是否允许落盘；目标站点/币种；以及谁负责人工审核。以上决策会决定字段映射和数据保留策略，不能由采集器自行假设。
