# 星间卡藏

原生 TypeScript 单页抽卡体验，无需新增依赖。在仓库根目录执行：

```bash
npm install
npm run card-draw
```

打开 <http://localhost:8000>。启动命令先编译 TypeScript，再通过 Python 提供静态页面；需要本机安装 Python 3。修改 TypeScript 后重新运行命令以编译，按 Ctrl+C 停止服务。生成的 `.build/` 不提交到 Git。

点击“抽取一张”查看卡牌，支持键盘 Tab 聚焦和 Enter / 空格操作。R、SR、SSR 的基础概率分别为 80%、18%、2%，同稀有度的两张卡牌等概率出现。连续 49 抽未出 SSR 后下一抽必得 SSR，任意 SSR 都重置计数。页面刷新即重置，不保存历史。

```bash
npm run test:card-draw
```

测试使用固定随机输入验证概率边界、卡池选择、保底触发及计数重置。

合入 `main` 后，GitHub Actions 会将该页面部署到仓库 Pages 站点的 `/dev-loop/card-draw/` 路径。其他包含 `index.html` 的 `frontend/<目录名>/` 也会自动发布到 `/dev-loop/<目录名>/`。
