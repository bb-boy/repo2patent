# Round 1 技术交底（基于源码事实）

## 一、技术问题
1. 文件链路与网络链路并存，存在字段口径不统一与处理路径割裂问题。
2. 元数据、波形、日志、PLC互锁数据类型差异明显，单一持久化路径难以兼顾写入与查询。
3. 主数据源不可用时缺少统一回退路径，会造成同步任务中断与状态不可追踪。

## 二、拟保护技术方案
1. 建立双数据源接入层，统一接收TDMS文件数据和消息队列网络数据。
2. 以统一字段模型承载shotNo、fileName、filePath、expectedDuration、actualDuration、status等核心字段。
3. 按消息主题进行异步解耦路由：shot-metadata、wave-data、operation-log、plc-interlock。
4. 结构化数据写入关系型数据库，波形序列压缩后写入时序数据库，查询时解压恢复。
5. 通过REST接口触发单任务、批量、全量同步，通过WebSocket进行状态与结果推送。
6. 对主数据源执行可用性检测，不可用时切换备用源，恢复后执行回退。

## 三、可验证技术效果
1. 双源数据统一建模后，跨链路字段映射一致。
2. 主题分流减少跨模块改动范围，提高链路隔离性。
3. 分层存储降低波形数据占用，并保持按炮号和通道的查询能力。
4. 主备切换使同步任务在异常场景下保持连续执行。

## 四、源码证据锚点
- DataPipelineService：`syncShotToKafka`、`syncAllShotsToKafka`。
- DataConsumer：`@KafkaListener`四类主题消费、`compressWaveData`、`decompressWaveData`。
- DataService：`primarySource`、`fallback`、可用性状态聚合。
- DataController：`/api/data/source/switch`。
- KafkaController：`/api/kafka/sync/shot`、`/api/kafka/sync/batch`、`/api/kafka/sync/all`。
- WebSocketController：`convertAndSend`与定时推送（`@Scheduled(fixedRate = 5000)`）。
