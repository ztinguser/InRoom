# PDF 解析测试

`fixtures/` 中的 11 个 PDF 全部由 `generate_fixtures.py` 合成，不包含真实个人资料。
运行测试直接读取已提交夹具，无需安装 PDF 生成工具，也不访问外部服务。

在 backend 目录运行：

```powershell
uv run pytest tests/parsing -q
```

需要重新生成夹具时才运行以下命令；额外依赖仅用于生成，不加入业务依赖：

```powershell
uv run --with reportlab --with pypdf python tests/parsing/generate_fixtures.py
```

- text：两页中英文合成文本；columns：双栏坐标。
- scan：只有图片；mixed：图片加可提取页眉；blank：空白页。
- limit / too_many：20 / 21 页边界；empty：零页文档。
- encrypted：测试密码 test-password；owner_encrypted：空用户密码、非空所有者密码。
- broken：只有 PDF 文件头、没有有效对象树，故意无法渲染。

本次 12 项解析测试通过，并已渲染检查有效夹具的 51 页。
扫描页只验证 review_pages 标记，不表示 OCR 已实现；双栏只验证文本及坐标，
不表示阅读顺序、语义段落、多样损坏文件、执行时间或内存限制已通过验收。
文本块编号仅在固定提取结果中使用，不保证跨解析器版本不变。
