# Contracts

本特性为纯重构操作(类名和文件名重命名),不涉及API契约变更。

所有现有的API契约保持不变:
- BaseExchange接口契约保持不变
- XT Exchange REST API v4集成保持不变
- 所有方法签名保持不变

参考现有契约测试:
- `tests/unit/test_exchanges/test_xt_contract.py` - 验证BaseExchange接口遵从性
- `tests/integration/test_xt_integration.py` - 验证XT API集成

重命名后,这些契约测试必须全部通过以验证无功能性变更。
