# 真实协议样本

`samples.tar.gz` 保存原交接包中 121 条 HTTP 请求体的准确原始字节、MANIFEST.json 和发生器 receipt.json。全部请求体已按原始 MANIFEST 的 SHA-256 校验。

- 原始请求体：3,078,823 字节。
- 压缩包 SHA-256：`743d22ea3aa1e73ae7beebb048d4e8b1922754798a46c804349a7d976ef475cc`。
- 原采样仅验证未知协议，不属于成品性能证据。
- 应用正确处理期望：2,080 个有效对象、revision 11、4 次重复、2 条隔离、117 条唯一消息。

使用 `tarfile.extractfile` 读取测试消息；不需要写入或覆盖任何外部路径。真实发生器性能收据单独存入 evidence/benchmarks/。
